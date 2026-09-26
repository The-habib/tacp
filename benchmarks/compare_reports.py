import json
from pathlib import Path

baseline_file = Path('artifacts/audit/baseline-report.json')
final_file = Path('artifacts/audit/final-report.json')

if not baseline_file.exists() or not final_file.exists():
    print("Files not found")
    exit(1)

baseline = json.loads(baseline_file.read_text())['metrics']
final = json.loads(final_file.read_text())['metrics']

print("| Metric / Operation | Baseline P50 (ms) | Final P50 (ms) | Speedup / Factor | Baseline P95 (ms) | Final P95 (ms) | Iterations |")
print("|---|---|---|---|---|---|---|")

for k in sorted(final.keys()):
    f = final[k]
    f_p50 = f['p50_ms']
    f_p95 = f['p95_ms']
    iters = f['iterations']
    if k in baseline:
        b = baseline[k]
        b_p50 = b['p50_ms']
        b_p95 = b['p95_ms']
        if 'throughput' in k:
            speedup = f"{f_p50:.1f} rps"
        elif f_p50 > 0:
            ratio = b_p50 / f_p50
            if ratio >= 1.05:
                speedup = f"**{ratio:.2f}x faster**"
            elif ratio <= 0.95:
                speedup = f"{ratio:.2f}x"
            else:
                speedup = "~parity"
        else:
            speedup = "N/A"
        print(f"| `{k}` | {b_p50:.3f} | {f_p50:.3f} | {speedup} | {b_p95:.3f} | {f_p95:.3f} | {iters} |")
    else:
        if 'throughput' in k:
            speedup = f"{f_p50:.1f} rps"
        else:
            speedup = "*new metric*"
        print(f"| `{k}` | *(new)* | {f_p50:.3f} | {speedup} | *(new)* | {f_p95:.3f} | {iters} |")
