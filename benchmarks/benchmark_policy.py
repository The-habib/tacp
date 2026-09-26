"""Benchmark policy evaluation, token verification, and capability resolution."""

from __future__ import annotations

import sys
import time
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
from tacp.backends.manager import BackendManager
from tacp.control.auth import TokenService
from tacp.control.identity import Principal, RequestContext
from tacp.control.policy import PolicyEngine
from tacp.engine.registry import CapabilityRegistry
from tacp.engine.resolver import CapabilityResolver
from tacp.infrastructure.config import TacpConfig
from tacp.infrastructure.database import Database


def run_benchmark(output_dir: Path) -> List[MetricSummary]:
    config = TacpConfig.load()
    db = Database(config.db_path)
    db.connect()

    policy_engine = PolicyEngine(
        read_only_enforced=config.read_only,
        mutation_enabled=config.mutation_enabled,
        trust_profile="BALANCED",
    )
    token_service = TokenService(db)

    # Ensure a benchmark token exists
    test_tok, raw_sec = token_service.create_token(
        name="bench_token",
        scopes=["tacp.read", "tacp.files.read"],
    )

    principal = Principal.remote_ai(agent_id="bench_agent")
    ctx_read = RequestContext(capability="system.inspect", principal=principal, request_id="req-1")
    ctx_mutate = RequestContext(capability="workspace.patch", principal=principal, request_id="req-2")

    metrics: List[MetricSummary] = []

    # 1. Policy check: read-only capability
    d_pol_read = time_callable(lambda: policy_engine.evaluate_request(ctx_read), iterations=100)
    metrics.append(compute_metrics("policy_evaluate_read_only", d_pol_read))

    # 2. Policy check: mutating capability under read-only rule
    d_pol_mutate = time_callable(lambda: policy_engine.evaluate_request(ctx_mutate), iterations=100)
    metrics.append(compute_metrics("policy_evaluate_mutation_denied", d_pol_mutate))

    # 3. Token verification: validate_token (SHA-256 hash + SQLite select)
    d_tok = time_callable(lambda: token_service.validate_token(raw_sec), iterations=50)
    metrics.append(compute_metrics("token_verify_hash_and_db", d_tok))

    # 4. Capability resolution: CapabilityResolver.resolve()
    bm = BackendManager()
    reg = CapabilityRegistry(bm)
    cap_def = reg.get("system.inspect")
    if cap_def:
        d_res = time_callable(lambda: reg.resolver.resolve(cap_def), iterations=50)
        metrics.append(compute_metrics("capability_resolve_backend", d_res))

    # Cleanup bench token
    token_service.revoke_token(test_tok.id)

    save_benchmark_result(
        suite_name="benchmark_policy",
        metrics=metrics,
        output_dir=output_dir,
        extra={"rss_mb": get_current_rss_mb()},
    )
    return metrics


if __name__ == "__main__":
    out = Path("artifacts/benchmarks")
    results = run_benchmark(out)
    for m in results:
        print(f"{m.name:32} | P50: {m.p50_ms:6.3f} ms | P95: {m.p95_ms:6.3f} ms | Max: {m.max_ms:6.3f} ms")
