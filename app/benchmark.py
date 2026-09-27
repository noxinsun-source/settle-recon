from __future__ import annotations

import argparse
import json
import time
from copy import deepcopy
from datetime import date
from decimal import Decimal

from app.incremental import AccountStatementInput, IncrementalStatementEngine, StatementTrade


def make_accounts(count: int) -> list[AccountStatementInput]:
    accounts = []
    for index in range(count):
        buy_amount = Decimal("1000.00")
        fee = Decimal("1.00")
        accounts.append(
            AccountStatementInput(
                account_id=f"INST-{index:06d}",
                reconciliation_date=date(2026, 9, 26),
                source_batches={
                    "trades": "TRD-20260926-01",
                    "cash": "CSH-20260926-01",
                    "positions": "POS-20260926-01",
                    "fees": "FEE-20260926-01",
                },
                opening_cash=Decimal("100000.00"),
                closing_cash=Decimal("98999.00"),
                opening_positions={"600000.SH": 0},
                closing_positions={"600000.SH": 100},
                trades=[
                    StatementTrade(
                        trade_id=f"T-{index:06d}",
                        instrument="600000.SH",
                        side="BUY",
                        quantity=100,
                        gross_amount=buy_amount,
                        fee=fee,
                    )
                ],
            )
        )
    return accounts


def benchmark(account_count: int, correction_ratio: float) -> dict[str, int | float]:
    baseline_inputs = make_accounts(account_count)
    incremental_engine = IncrementalStatementEngine()
    incremental_engine.rebuild_batch(baseline_inputs)

    corrected = deepcopy(baseline_inputs)
    changed_count = max(1, int(account_count * correction_ratio))
    for item in corrected[:changed_count]:
        item.source_batches["fees"] = "FEE-20260926-02"
        item.trades[0].fee = Decimal("1.50")
        item.closing_cash = Decimal("98998.50")

    full_engine = IncrementalStatementEngine()
    full_started = time.perf_counter()
    full_result = full_engine.rebuild_batch(corrected, force_full=True)
    full_seconds = time.perf_counter() - full_started

    incremental_started = time.perf_counter()
    incremental_result = incremental_engine.rebuild_batch(corrected)
    incremental_seconds = time.perf_counter() - incremental_started

    return {
        "account_count": account_count,
        "corrected_accounts": changed_count,
        "full_recomputed": full_result.recomputed,
        "incremental_recomputed": incremental_result.recomputed,
        "incremental_skipped": incremental_result.skipped_unchanged,
        "recomputation_reduction_percent": round(
            (1 - incremental_result.recomputed / full_result.recomputed) * 100, 2
        ),
        "full_seconds": round(full_seconds, 4),
        "incremental_seconds": round(incremental_seconds, 4),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accounts", type=int, default=10000)
    parser.add_argument("--correction-ratio", type=float, default=0.01)
    parser.add_argument("--output")
    args = parser.parse_args()
    result = benchmark(args.accounts, args.correction_ratio)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")


if __name__ == "__main__":
    main()

