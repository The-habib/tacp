"""Phase 18 Screen Capture Pipeline Benchmark.

Measures:
capture buffer -> encode -> transport framing -> MCP response

Profiles:
- Small image (320x640)
- 720p image (720x1280)
- 1080p image (1080x2400 - physical device resolution)
- Large image (1440x3200)

Evaluates:
- Raw buffer memory
- Base64 encoding CPU & latency
- MCP JSON packaging latency
- Output bytes
"""

import base64
import json
import os
import time
from pathlib import Path

def benchmark_resolution(width: int, height: int, name: str):
    # 4 bytes per pixel (RGBA32)
    raw_size = width * height * 4
    # Create deterministic synthetic byte pattern mimicking UI screen with text/shapes
    raw_pattern = os.urandom(min(raw_size, 65536))
    raw_data = (raw_pattern * (raw_size // len(raw_pattern) + 1))[:raw_size]

    # 1. Base64 encoding (simulating MCP standard inline image encoding)
    t0 = time.perf_counter()
    b64_str = base64.b64encode(raw_data[:raw_size // 4]).decode("ascii") # simulated compressed PNG/JPEG payload
    t_b64 = (time.perf_counter() - t0) * 1000

    # 2. JSON-RPC response framing
    t1 = time.perf_counter()
    mcp_resp = {
        "jsonrpc": "2.0",
        "id": "screen-bench",
        "result": {
            "content": [
                {
                    "type": "image",
                    "data": b64_str,
                    "mimeType": "image/png",
                }
            ]
        }
    }
    raw_json = json.dumps(mcp_resp).encode("utf-8")
    t_frame = (time.perf_counter() - t1) * 1000

    return {
        "resolution": f"{width}x{height}",
        "tier": name,
        "raw_rgba_mb": round(raw_size / (1024 * 1024), 2),
        "compressed_payload_kb": round(len(b64_str) * 3 / 4 / 1024, 2),
        "b64_encoded_kb": round(len(b64_str) / 1024, 2),
        "mcp_json_bytes": len(raw_json),
        "b64_latency_ms": round(t_b64, 3),
        "json_framing_ms": round(t_frame, 3),
        "total_pipeline_ms": round(t_b64 + t_frame, 3),
    }

def run_suite():
    resolutions = [
        (320, 640, "Thumbnail / Preview"),
        (720, 1280, "720p HD"),
        (1080, 2400, "1080p FHD+ (Native Device)"),
        (1440, 3200, "1440p QHD+"),
    ]

    print("=== PHASE 18 SCREEN CAPTURE ENCODING BENCHMARK ===")
    results = []
    for w, h, name in resolutions:
        res = benchmark_resolution(w, h, name)
        results.append(res)
        print(f"[{res['tier']:26}] Raw: {res['raw_rgba_mb']:5.2f} MB | JSON: {res['mcp_json_bytes']/1024:6.1f} KB | B64: {res['b64_latency_ms']:5.2f} ms | Frame: {res['json_framing_ms']:5.2f} ms | Total: {res['total_pipeline_ms']:5.2f} ms")

    out_file = Path("artifacts/phase2/benchmark_screen_capture.json")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out_file}")

if __name__ == "__main__":
    run_suite()
