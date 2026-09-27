from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request

from app.models import ReconciliationReport, ReconciliationRequest
from app.reconcile import reconcile_batch
from app.store import ReportStore


def create_app(database_path: str | None = None) -> FastAPI:
    store = ReportStore(database_path or os.getenv("SETTLE_RECON_DB", "data/reconciliation.db"))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store
        yield

    app = FastAPI(
        title="SettleRecon",
        version="1.0.0",
        description="证券成交与清算记录的确定性对账及异常分流服务",
        lifespan=lifespan,
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "settle-recon"}

    @app.post("/v1/reconciliations", response_model=ReconciliationReport)
    def create_reconciliation(
        reconciliation: ReconciliationRequest, request: Request
    ) -> ReconciliationReport:
        existing = request.app.state.store.get(reconciliation.batch_id)
        if existing is not None:
            return existing
        return request.app.state.store.save_if_absent(reconcile_batch(reconciliation))

    @app.get("/v1/reconciliations/{batch_id}", response_model=ReconciliationReport)
    def get_reconciliation(batch_id: str, request: Request) -> ReconciliationReport:
        report = request.app.state.store.get(batch_id)
        if report is None:
            raise HTTPException(status_code=404, detail="未找到该对账批次")
        return report

    return app


app = create_app()

