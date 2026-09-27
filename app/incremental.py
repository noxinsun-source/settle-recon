from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field, model_validator

REQUIRED_SOURCES = {"trades", "cash", "positions", "fees"}


class TradeSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class StatementStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class RebuildAction(str, Enum):
    RECOMPUTED = "RECOMPUTED"
    SKIPPED_UNCHANGED = "SKIPPED_UNCHANGED"


class StatementTrade(BaseModel):
    trade_id: str = Field(min_length=1, max_length=64)
    instrument: str = Field(min_length=1, max_length=32)
    side: TradeSide
    quantity: int = Field(gt=0)
    gross_amount: Decimal = Field(gt=0, decimal_places=4)
    fee: Decimal = Field(ge=0, decimal_places=4)


class AccountStatementInput(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    reconciliation_date: date
    source_batches: dict[str, str]
    opening_cash: Decimal
    closing_cash: Decimal
    deposits: Decimal = Decimal(0)
    withdrawals: Decimal = Decimal(0)
    opening_positions: dict[str, int]
    closing_positions: dict[str, int]
    trades: list[StatementTrade]

    @model_validator(mode="after")
    def normalize(self) -> AccountStatementInput:
        self.account_id = self.account_id.strip()
        self.source_batches = {
            key.strip().lower(): value.strip() for key, value in self.source_batches.items()
        }
        self.opening_positions = {
            key.strip().upper(): value for key, value in self.opening_positions.items()
        }
        self.closing_positions = {
            key.strip().upper(): value for key, value in self.closing_positions.items()
        }
        for trade in self.trades:
            trade.instrument = trade.instrument.strip().upper()
        return self


class QualityIssue(BaseModel):
    code: str
    dimension: str
    expected: str
    observed: str
    message: str


class StatementVersion(BaseModel):
    account_id: str
    reconciliation_date: date
    version: int
    fingerprint: str
    action: RebuildAction
    status: StatementStatus
    issues: list[QualityIssue]
    source_batches: dict[str, str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BatchRebuildResult(BaseModel):
    total_accounts: int
    recomputed: int
    skipped_unchanged: int
    ready: int
    blocked: int
    statements: list[StatementVersion]


class IncrementalStatementEngine:
    """Versioned institutional-statement rebuild with account-level fingerprints."""

    def __init__(self, database_path: str = ":memory:") -> None:
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS statement_versions (
                account_id TEXT NOT NULL,
                reconciliation_date TEXT NOT NULL,
                version INTEGER NOT NULL,
                fingerprint TEXT NOT NULL,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (account_id, reconciliation_date, version)
            )
            """
        )
        self._connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_statement_latest
            ON statement_versions(account_id, reconciliation_date, version DESC)
            """
        )
        self._connection.commit()

    def rebuild_batch(
        self, inputs: list[AccountStatementInput], *, force_full: bool = False
    ) -> BatchRebuildResult:
        statements = [self.rebuild(item, force=force_full) for item in inputs]
        recomputed = sum(item.action is RebuildAction.RECOMPUTED for item in statements)
        skipped = len(statements) - recomputed
        ready = sum(item.status is StatementStatus.READY for item in statements)
        return BatchRebuildResult(
            total_accounts=len(statements),
            recomputed=recomputed,
            skipped_unchanged=skipped,
            ready=ready,
            blocked=len(statements) - ready,
            statements=statements,
        )

    def rebuild(self, item: AccountStatementInput, *, force: bool = False) -> StatementVersion:
        fingerprint = self.fingerprint(item)
        with self._lock:
            latest = self._latest(item.account_id, item.reconciliation_date)
            if latest and latest.fingerprint == fingerprint and not force:
                return latest.model_copy(update={"action": RebuildAction.SKIPPED_UNCHANGED})

            issues = quality_gate(item)
            report = StatementVersion(
                account_id=item.account_id,
                reconciliation_date=item.reconciliation_date,
                version=1 if latest is None else latest.version + 1,
                fingerprint=fingerprint,
                action=RebuildAction.RECOMPUTED,
                status=StatementStatus.BLOCKED if issues else StatementStatus.READY,
                issues=issues,
                source_batches=item.source_batches,
            )
            self._connection.execute(
                "INSERT INTO statement_versions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    report.account_id,
                    report.reconciliation_date.isoformat(),
                    report.version,
                    report.fingerprint,
                    report.model_dump_json(),
                    report.created_at.isoformat(),
                ),
            )
            self._connection.commit()
            return report

    @staticmethod
    def fingerprint(item: AccountStatementInput) -> str:
        canonical = json.dumps(
            item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _latest(self, account_id: str, reconciliation_date: date) -> StatementVersion | None:
        row = self._connection.execute(
            """
            SELECT report_json FROM statement_versions
            WHERE account_id = ? AND reconciliation_date = ?
            ORDER BY version DESC LIMIT 1
            """,
            (account_id, reconciliation_date.isoformat()),
        ).fetchone()
        return None if row is None else StatementVersion.model_validate_json(row["report_json"])


def quality_gate(item: AccountStatementInput) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    missing = sorted(REQUIRED_SOURCES - set(item.source_batches))
    if missing:
        issues.append(
            QualityIssue(
                code="MISSING_SOURCE_BATCH",
                dimension="source_completeness",
                expected=",".join(sorted(REQUIRED_SOURCES)),
                observed=",".join(sorted(item.source_batches)),
                message=f"缺少上游批次：{', '.join(missing)}，禁止生成机构对账单",
            )
        )

    buy_amount = sum(
        (trade.gross_amount for trade in item.trades if trade.side is TradeSide.BUY), Decimal(0)
    )
    sell_amount = sum(
        (trade.gross_amount for trade in item.trades if trade.side is TradeSide.SELL), Decimal(0)
    )
    total_fees = sum((trade.fee for trade in item.trades), Decimal(0))
    expected_cash = (
        item.opening_cash
        + item.deposits
        - item.withdrawals
        - buy_amount
        + sell_amount
        - total_fees
    )
    if expected_cash != item.closing_cash:
        issues.append(
            QualityIssue(
                code="CASH_CONSERVATION_BROKEN",
                dimension="cash",
                expected=f"{expected_cash:.2f}",
                observed=f"{item.closing_cash:.2f}",
                message="期初资金、出入金、成交净额与费用无法勾稽到期末资金",
            )
        )

    position_changes: dict[str, int] = defaultdict(int)
    for trade in item.trades:
        direction = 1 if trade.side is TradeSide.BUY else -1
        position_changes[trade.instrument] += direction * trade.quantity

    instruments = set(item.opening_positions) | set(item.closing_positions) | set(position_changes)
    for instrument in sorted(instruments):
        expected = item.opening_positions.get(instrument, 0) + position_changes.get(instrument, 0)
        observed = item.closing_positions.get(instrument, 0)
        if expected != observed:
            issues.append(
                QualityIssue(
                    code="POSITION_CONSERVATION_BROKEN",
                    dimension=instrument,
                    expected=str(expected),
                    observed=str(observed),
                    message="期初持仓与当日成交无法勾稽到期末持仓",
                )
            )
    return issues

