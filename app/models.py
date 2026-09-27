from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class MatchStatus(str, Enum):
    MATCHED = "MATCHED"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    DATE_MISMATCH = "DATE_MISMATCH"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MISSING_INTERNAL = "MISSING_INTERNAL"
    MISSING_CLEARING = "MISSING_CLEARING"


class InternalTrade(BaseModel):
    trade_id: str = Field(min_length=1, max_length=64)
    account_id: str = Field(min_length=1, max_length=64)
    instrument: str = Field(min_length=1, max_length=32)
    side: Side
    quantity: int = Field(gt=0)
    price: Decimal = Field(gt=0, decimal_places=4)
    trade_date: date
    expected_settlement_date: date

    @property
    def amount(self) -> Decimal:
        return self.price * self.quantity


class ClearingRecord(BaseModel):
    clearing_id: str = Field(min_length=1, max_length=64)
    trade_id: str | None = Field(default=None, max_length=64)
    account_id: str = Field(min_length=1, max_length=64)
    instrument: str = Field(min_length=1, max_length=32)
    side: Side
    quantity: int = Field(gt=0)
    net_amount: Decimal = Field(gt=0, decimal_places=4)
    settlement_date: date


class ReconciliationRequest(BaseModel):
    batch_id: str = Field(min_length=4, max_length=64)
    amount_tolerance: Decimal = Field(default=Decimal("0.01"), ge=0, le=100)
    date_tolerance_days: int = Field(default=0, ge=0, le=7)
    internal_trades: list[InternalTrade]
    clearing_records: list[ClearingRecord]

    @model_validator(mode="after")
    def ensure_unique_ids(self) -> ReconciliationRequest:
        trade_ids = [record.trade_id for record in self.internal_trades]
        clearing_ids = [record.clearing_id for record in self.clearing_records]
        if len(trade_ids) != len(set(trade_ids)):
            raise ValueError("internal_trades 中 trade_id 必须唯一")
        if len(clearing_ids) != len(set(clearing_ids)):
            raise ValueError("clearing_records 中 clearing_id 必须唯一")
        return self


class MatchResult(BaseModel):
    internal_trade_id: str | None
    clearing_id: str | None
    status: MatchStatus
    amount_difference: Decimal | None
    date_difference_days: int | None
    match_method: str
    reason: str


class BatchSummary(BaseModel):
    total_internal: int
    total_clearing: int
    matched: int
    exceptions: int
    by_status: dict[str, int]


class ReconciliationReport(BaseModel):
    batch_id: str
    summary: BatchSummary
    results: list[MatchResult]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
