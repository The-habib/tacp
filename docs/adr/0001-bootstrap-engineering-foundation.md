# ADR-0001: Bootstrap Engineering Foundation & Factory Architecture

**Status**: ACCEPTED  
**Date**: 2026-09-10  
**Deciders**: Antigravity Principal Architect, Lead Staff Engineer, Human Owner  

---

## 1. Context & Problem Statement
TACP requires an autonomous AI-native development factory operating directly within Termux on Android. Without a formal constitution, reproducible Python quality toolchain, independent reviewer rules, and deterministic local verification, autonomous agents could create architectural drift, leak secrets, or produce unverified code.

## 2. Considered Alternatives
- Option A: Implement TACP runtime immediately without governance framework.
- Option B: Rely on external development environments (e.g. Replit or remote VM).
- Option C: Establish an on-device, constitutionally governed engineering factory inside Termux before implementation.

## 3. Decision & Selected Approach
Adopted Option C: Establish a strict, reproducible engineering factory governed by the Project Constitution (*"AI may be autonomous, but AI must never be sovereign"*), local canonical verification (`./verify`, `./doctor`), standard documentation (Docs 00-13), and strict evidence grading (E0-E7).

## 4. Consequences
- Positive: Guarantees auditability, reproducible checkouts, high security posture, and strict human ownership.
- Trade-offs: Requires upfront investment before application feature coding begins.

## 5. Security Implications
Establishes zero-secret invariant, default-deny policy, and path sandboxing from day zero.

## 6. Operational & Migration Implications
Completely reproducible on any standard Termux installation via `uv` and native packages.
