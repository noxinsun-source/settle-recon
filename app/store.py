from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from app.models import ReconciliationReport


class ReportStore:
    def __init__(self, database_path: str) -> None:
        if database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS reconciliation_reports (
                batch_id TEXT PRIMARY KEY,
                report_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def save_if_absent(self, report: ReconciliationReport) -> ReconciliationReport:
        with self._lock:
            existing = self.get(report.batch_id)
            if existing is not None:
                return existing
            self._connection.execute(
                "INSERT INTO reconciliation_reports VALUES (?, ?, ?)",
                (report.batch_id, report.model_dump_json(), report.created_at.isoformat()),
            )
            self._connection.commit()
            return report

    def get(self, batch_id: str) -> ReconciliationReport | None:
        row = self._connection.execute(
            "SELECT report_json FROM reconciliation_reports WHERE batch_id = ?",
            (batch_id,),
        ).fetchone()
        return None if row is None else ReconciliationReport.model_validate_json(row["report_json"])

