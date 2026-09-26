"""Benchmark database connection, transactions, audit inserts, and integrity verification."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from benchmarks.common import (
    MetricSummary,
    compute_metrics,
    get_current_rss_mb,
    save_benchmark_result,
    time_callable,
)
from tacp.core.audit_service import AuditService
from tacp.domain.audit import AuditEvent
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    db = Database(config.db_path)
    conn = db.connect()
    audit_service = AuditService(db)

    metrics: List[MetricSummary] = []

    # 1. Connection Open / Connect Overhead
    def _test_connect() -> None:
        d = Database(config.db_path)
        c = d.connect()
        d.close()

    d_conn = time_callable(_test_connect, iterations=30)
    metrics.append(compute_metrics("db_connection_open_close", d_conn))

    # 2. Simple SELECT query on indexed table
    def _test_query() -> None:
        c = db.connect()
        c.execute("SELECT count(*) FROM workspaces").fetchone()

    d_query = time_callable(_test_query, iterations=100)
    metrics.append(compute_metrics("db_simple_select_query", d_query))

    # 3. Audit Event Insert + Hash Chain Calculation
    def _test_audit_insert() -> None:
        ev = AuditEvent(
            capability="bench.db",
            action="bench.db.action",
            policy_decision="ALLOWED",
            result="SUCCESS",
            duration_ms=1,
            principal="bench-db-principal",
            request_id="bench-db-req",
        )
        audit_service.record_event(ev)

    d_insert = time_callable(_test_audit_insert, iterations=50)
    metrics.append(compute_metrics("db_audit_insert_with_hash_chain", d_insert))

    # 4. Audit Hash Chain Verification
    d_verify = time_callable(lambda: audit_service.verify_integrity(), iterations=20)
    metrics.append(compute_metrics("db_audit_chain_verify_integrity", d_verify))

    save_benchmark_result(
        suite_name="benchmark_database",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(
            f"{m.name:34} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms"
        )
