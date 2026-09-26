"""Master benchmark runner. Executes all benchmark suites and aggregates reports."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import benchmarks.benchmark_companion as b_comp
import benchmarks.benchmark_concurrency as b_conc
import benchmarks.benchmark_database as b_db
import benchmarks.benchmark_execution as b_exec
import benchmarks.benchmark_filesystem as b_fs
import benchmarks.benchmark_mcp as b_mcp
import benchmarks.benchmark_policy as b_pol
import benchmarks.benchmark_remote as b_rem
import benchmarks.benchmark_tools as b_tools
from benchmarks.common import MetricSummary, get_current_rss_mb, get_env_metadata


def run_all(output_dir: Path, report_prefix: str = "baseline-report") -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_metrics: List[MetricSummary] = []
    env_info = get_env_metadata()

    suites = [
        ("MCP Protocol", b_mcp.run_benchmark),
        ("Tool Execution", b_tools.run_benchmark),
        ("Filesystem Jail & Reads", b_fs.run_benchmark),
        ("Policy & Auth", b_pol.run_benchmark),
        ("Database & Audit", b_db.run_benchmark),
        ("Process Execution", b_exec.run_benchmark),
        ("Remote & Transports", b_rem.run_benchmark),
        ("Companion & Backends", b_comp.run_benchmark),
        ("Concurrency & Contention", b_conc.run_benchmark),
    ]

    print("============================================================")
    print(f" RUNNING BENCHMARK SUITE ({report_prefix})")
    print(f" Target Device: {env_info['platform']} (Python {env_info['python_version']})")
    print("============================================================")

    for name, runner in suites:
        print(f"[*] Running {name} benchmark...")
        t0 = time.time()
        try:
            res = runner(output_dir)
            all_metrics.extend(res)
            print(f"    [OK] {name} completed in {time.time() - t0:.2f}s ({len(res)} metrics)")
        except Exception as e:
            print(f"    [FAIL] {name} failed: {e}", file=sys.stderr)

    env_info["final_rss_mb"] = round(get_current_rss_mb(), 2)

    # Output consolidated JSON
    data = {
        "report": report_prefix,
        "environment": env_info,
        "metrics": {m.name: m.to_dict() for m in all_metrics},
    }
    json_path = output_dir / f"{report_prefix}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Output consolidated Markdown
    md_lines = [
        f"# TACP Comprehensive Benchmark Report: {report_prefix.upper()}",
        f"- **Timestamp:** {env_info['timestamp']}",
        f"- **Platform:** {env_info['platform']}",
        f"- **Architecture:** {env_info['arch']}",
        f"- **Python Version:** {env_info['python_version']}",
        f"- **Base RSS:** {env_info['rss_mb']} MB | **Final RSS:** {env_info['final_rss_mb']} MB",
        "",
        "| Metric / Operation | Iterations | Min (ms) | P50 (ms) | P95 (ms) | P99 (ms) | Max (ms) | Mean (ms) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in all_metrics:
        md_lines.append(
            f"| `{m.name}` | {m.iterations} | {m.min_ms:.3f} | {m.p50_ms:.3f} | {m.p95_ms:.3f} | {m.p99_ms:.3f} | {m.max_ms:.3f} | {m.mean_ms:.3f} |"
        )
    md_lines.append("")

    md_path = output_dir / f"{report_prefix}.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"\n[OK] Benchmark reports written to:")
    print(f"     - {json_path}")
    print(f"     - {md_path}")
    print("============================================================\n")
    return data


if __name__ == "__main__":
    prefix = sys.argv[1] if len(sys.argv) > 1 else "baseline-report"
    out_dir = Path("artifacts/audit")
    run_all(out_dir, report_prefix=prefix)
