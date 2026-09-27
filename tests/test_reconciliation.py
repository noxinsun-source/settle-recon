from fastapi.testclient import TestClient

from app.main import create_app


def internal(trade_id, **overrides):
    data = {
        "trade_id": trade_id,
        "account_id": "ACC-001",
        "instrument": "600000.SH",
        "side": "BUY",
        "quantity": 100,
        "price": "10.00",
        "trade_date": "2026-09-25",
        "expected_settlement_date": "2026-09-26",
    }
    data.update(overrides)
    return data


def clearing(clearing_id, trade_id=None, **overrides):
    data = {
        "clearing_id": clearing_id,
        "trade_id": trade_id,
        "account_id": "ACC-001",
        "instrument": "600000.SH",
        "side": "BUY",
        "quantity": 100,
        "net_amount": "1000.00",
        "settlement_date": "2026-09-26",
    }
    data.update(overrides)
    return data


def reconcile(internal_trades, clearing_records, **overrides):
    payload = {
        "batch_id": overrides.pop("batch_id", "BATCH-001"),
        "amount_tolerance": overrides.pop("amount_tolerance", "0.01"),
        "date_tolerance_days": overrides.pop("date_tolerance_days", 0),
        "internal_trades": internal_trades,
        "clearing_records": clearing_records,
    }
    payload.update(overrides)
    with TestClient(create_app(":memory:")) as api:
        return api.post("/v1/reconciliations", json=payload)


def test_exact_reference_match():
    report = reconcile([internal("T-001")], [clearing("C-001", "T-001")]).json()
    assert report["summary"]["matched"] == 1
    assert report["results"][0]["match_method"] == "TRADE_ID"


def test_unique_composite_key_fallback():
    report = reconcile([internal("T-001")], [clearing("C-001")]).json()
    assert report["results"][0]["status"] == "MATCHED"
    assert report["results"][0]["match_method"] == "COMPOSITE_KEY"


def test_amount_mismatch_is_not_silently_matched():
    report = reconcile(
        [internal("T-001")],
        [clearing("C-001", "T-001", net_amount="998.00")],
    ).json()
    assert report["results"][0]["status"] == "AMOUNT_MISMATCH"


def test_settlement_date_mismatch_is_reported():
    report = reconcile(
        [internal("T-001")],
        [clearing("C-001", "T-001", settlement_date="2026-09-29")],
    ).json()
    assert report["results"][0]["status"] == "DATE_MISMATCH"


def test_missing_records_are_reported_on_both_sides():
    report = reconcile(
        [internal("T-001"), internal("T-002", instrument="000001.SZ")],
        [clearing("C-001", "T-001"), clearing("C-003", account_id="ACC-999")],
    ).json()
    statuses = {result["status"] for result in report["results"]}
    assert "MISSING_CLEARING" in statuses
    assert "MISSING_INTERNAL" in statuses


def test_ambiguous_candidates_require_human_review():
    report = reconcile(
        [internal("T-001"), internal("T-002")],
        [clearing("C-001")],
    ).json()
    assert any(result["status"] == "NEEDS_REVIEW" for result in report["results"])


def test_duplicate_identifiers_fail_validation():
    response = reconcile(
        [internal("T-001"), internal("T-001")],
        [clearing("C-001", "T-001")],
    )
    assert response.status_code == 422


def test_batch_retry_returns_stored_report():
    app = create_app(":memory:")
    with TestClient(app) as api:
        payload = {
            "batch_id": "BATCH-RETRY",
            "internal_trades": [internal("T-001")],
            "clearing_records": [clearing("C-001", "T-001")],
        }
        first = api.post("/v1/reconciliations", json=payload).json()
        payload["clearing_records"][0]["net_amount"] = "900.00"
        second = api.post("/v1/reconciliations", json=payload).json()
        assert first == second

