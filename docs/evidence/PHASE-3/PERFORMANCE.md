# Phase 3 Evidence — Performance & Resource Footprint Benchmark

**Document ID**: TACP-EV-P3-11  
**Status**: VERIFIED  
**Platform**: Android Termux arm64 / Python 3.14  

## 1. Measured Latency Benchmarks
| Operation | Measured Latency | Target Threshold | Status |
| :--- | :--- | :--- | :--- |
| Lock Acquire + Release | **0.11 ms** | < 10 ms | **PASS** |
| Patch Simulation (Dry-Run) | **1.01 ms** | < 20 ms | **PASS** |
| Patch Live Execution (16 Stages) | **10.87 ms** | < 50 ms | **PASS** |
| Single Patch Rollback | **2.58 ms** | < 30 ms | **PASS** |
| Audit Chain Full Verification | **1.13 ms** | < 20 ms | **PASS** |

## 2. Resource Footprint
- Peak Resident Set Size (RSS): **26.4 MB** (well below the 100 MB budget for mobile environments).
- Startup Time: < **25 ms** to handle initial stdio request.
