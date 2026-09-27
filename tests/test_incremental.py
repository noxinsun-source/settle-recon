from copy import deepcopy
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from app.incremental import AccountStatementInput, IncrementalStatementEngine, StatementTrade
from app.main import create_app


def valid_input(account_id: str = "INST-001") -> AccountStatementInput:
    return AccountStatementInput(
        account_id=account_id,
        reconciliation_date=date(2026, 9, 26),
        source_batches={
            "trades": "TRD-01",
            "cash": "CSH-01",
            "positions": "POS-01",
            "fees": "FEE-01",
        },
        opening_cash=Decimal("10000.00"),
        closing_cash=Decimal("8999.00"),
        opening_positions={"600000.SH": 0},
        closing_positions={"600000.SH": 100},
        trades=[
            StatementTrade(
                trade_id="T-001",
                instrument="600000.SH",
                side="BUY",
                quantity=100,
                gross_amount=Decimal("1000.00"),
                fee=Decimal("1.00"),
            )
        ],
    )


def test_valid_account_passes_quality_gate():
    result = IncrementalStatementEngine().rebuild(valid_input())
    assert result.status == "READY"
    assert result.issues == []


def test_unchanged_account_is_skipped_without_new_version():
    engine = IncrementalStatementEngine()
    first = engine.rebuild(valid_input())
    second = engine.rebuild(valid_input())
    assert first.version == second.version == 1
    assert second.action == "SKIPPED_UNCHANGED"


def test_fee_correction_recomputes_only_changed_account():
    engine = IncrementalStatementEngine()
    original = [valid_input("INST-001"), valid_input("INST-002")]
    engine.rebuild_batch(original)
    corrected = deepcopy(original)
    corrected[0].source_batches["fees"] = "FEE-02"
    corrected[0].trades[0].fee = Decimal("1.50")
    corrected[0].closing_cash = Decimal("8998.50")
    result = engine.rebuild_batch(corrected)
    assert result.recomputed == 1
    assert result.skipped_unchanged == 1
    assert result.statements[0].version == 2


def test_missing_upstream_source_blocks_statement():
    item = valid_input()
    item.source_batches.pop("fees")
    result = IncrementalStatementEngine().rebuild(item)
    assert result.status == "BLOCKED"
    assert result.issues[0].code == "MISSING_SOURCE_BATCH"


def test_cash_conservation_break_blocks_statement():
    item = valid_input()
    item.closing_cash = Decimal("9000.00")
    result = IncrementalStatementEngine().rebuild(item)
    assert any(issue.code == "CASH_CONSERVATION_BROKEN" for issue in result.issues)


def test_position_conservation_break_blocks_statement():
    item = valid_input()
    item.closing_positions["600000.SH"] = 99
    result = IncrementalStatementEngine().rebuild(item)
    assert any(issue.code == "POSITION_CONSERVATION_BROKEN" for issue in result.issues)


def test_v2_api_reuses_unchanged_account_version():
    app = create_app(":memory:")
    payload = [valid_input().model_dump(mode="json")]
    with TestClient(app) as api:
        first = api.post("/v2/statements/rebuild", json=payload)
        second = api.post("/v2/statements/rebuild", json=payload)
    assert first.status_code == 200
    assert first.json()["recomputed"] == 1
    assert second.json()["skipped_unchanged"] == 1
