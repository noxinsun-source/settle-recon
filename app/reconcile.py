from __future__ import annotations

from collections import Counter

from app.models import (
    BatchSummary,
    ClearingRecord,
    InternalTrade,
    MatchResult,
    MatchStatus,
    ReconciliationReport,
    ReconciliationRequest,
)


def reconcile_batch(request: ReconciliationRequest) -> ReconciliationReport:
    remaining_trades = {trade.trade_id: trade for trade in request.internal_trades}
    remaining_clearing = {record.clearing_id: record for record in request.clearing_records}
    results: list[MatchResult] = []

    # Stage 1: deterministic reference match. This is the safest and cheapest path.
    for record in request.clearing_records:
        if not record.trade_id or record.trade_id not in remaining_trades:
            continue
        trade = remaining_trades.pop(record.trade_id)
        remaining_clearing.pop(record.clearing_id)
        results.append(_classify_pair(trade, record, request, "TRADE_ID"))

    # Stage 2: unique composite-key fallback when the clearing file lost trade_id.
    for record in list(remaining_clearing.values()):
        candidates = [
            trade
            for trade in remaining_trades.values()
            if _same_business_key(trade, record)
        ]
        if len(candidates) == 1:
            trade = candidates[0]
            remaining_trades.pop(trade.trade_id)
            remaining_clearing.pop(record.clearing_id)
            results.append(_classify_pair(trade, record, request, "COMPOSITE_KEY"))
        elif len(candidates) > 1:
            results.append(
                MatchResult(
                    internal_trade_id=None,
                    clearing_id=record.clearing_id,
                    status=MatchStatus.NEEDS_REVIEW,
                    amount_difference=None,
                    date_difference_days=None,
                    match_method="AMBIGUOUS_COMPOSITE_KEY",
                    reason=f"存在 {len(candidates)} 条候选成交，禁止自动选择",
                )
            )
            remaining_clearing.pop(record.clearing_id)

    for trade in remaining_trades.values():
        results.append(
            MatchResult(
                internal_trade_id=trade.trade_id,
                clearing_id=None,
                status=MatchStatus.MISSING_CLEARING,
                amount_difference=None,
                date_difference_days=None,
                match_method="UNMATCHED",
                reason="内部成交存在，但清算文件中未找到对应记录",
            )
        )

    for record in remaining_clearing.values():
        results.append(
            MatchResult(
                internal_trade_id=None,
                clearing_id=record.clearing_id,
                status=MatchStatus.MISSING_INTERNAL,
                amount_difference=None,
                date_difference_days=None,
                match_method="UNMATCHED",
                reason="清算记录存在，但内部成交系统中未找到对应记录",
            )
        )

    results.sort(key=lambda item: (item.internal_trade_id or "~", item.clearing_id or "~"))
    counts = Counter(result.status.value for result in results)
    matched = counts[MatchStatus.MATCHED.value]
    summary = BatchSummary(
        total_internal=len(request.internal_trades),
        total_clearing=len(request.clearing_records),
        matched=matched,
        exceptions=len(results) - matched,
        by_status=dict(sorted(counts.items())),
    )
    return ReconciliationReport(batch_id=request.batch_id, summary=summary, results=results)


def _same_business_key(trade: InternalTrade, record: ClearingRecord) -> bool:
    return (
        trade.account_id == record.account_id
        and trade.instrument.upper() == record.instrument.upper()
        and trade.side == record.side
        and trade.quantity == record.quantity
    )


def _classify_pair(
    trade: InternalTrade,
    record: ClearingRecord,
    request: ReconciliationRequest,
    method: str,
) -> MatchResult:
    amount_difference = abs(trade.amount - record.net_amount)
    date_difference = abs((trade.expected_settlement_date - record.settlement_date).days)

    if amount_difference > request.amount_tolerance:
        status = MatchStatus.AMOUNT_MISMATCH
        reason = "成交金额与清算净额超出容差"
    elif date_difference > request.date_tolerance_days:
        status = MatchStatus.DATE_MISMATCH
        reason = "实际清算日期与预计清算日期不一致"
    else:
        status = MatchStatus.MATCHED
        reason = "金额、方向、数量和清算日期核对一致"

    return MatchResult(
        internal_trade_id=trade.trade_id,
        clearing_id=record.clearing_id,
        status=status,
        amount_difference=amount_difference,
        date_difference_days=date_difference,
        match_method=method,
        reason=reason,
    )
