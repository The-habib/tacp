# Phase 3 Evidence — Patch Parser Security & Differential Audit

**Document ID**: TACP-EV-P3-08  
**Status**: VERIFIED  

## 1. Security Invariants & Edge Cases
- Prefix validation: Rejects non-unified diff prefixes (only `' '`, `'+'`, `'-'`, `'\\'` accepted).
- Hunk validation: Rejects invalid hunk headers, empty diffs, hunk line count discrepancies.
- Overlap detection: Rejects overlapping or out-of-order hunk offsets.
- Line endings: Transparently handles LF and CRLF line endings.
- Multi-byte UTF-8: Correctly preserves multibyte characters and emoji glyphs without offset drift.

## 2. Differential Testing
- Differential testing against Python `difflib.unified_diff` passes across multiple test structures with 100% byte fidelity.
- Replay defense verified: Re-executing an already-applied patch raises `TacpConflictError` due to base checksum mismatch.
