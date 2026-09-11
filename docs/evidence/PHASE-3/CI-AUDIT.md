# Phase 3 Evidence — CI & Workflow Hardening Audit

**Document ID**: TACP-EV-P3-02  
**Status**: VERIFIED  

## 1. GitHub Actions Immutable Pinning
All GitHub Actions in `.github/workflows/ci.yml` and `.github/workflows/security.yml` are pinned to immutable 40-character commit SHAs:
- `actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683` (v4.2.2)
- `astral-sh/setup-uv@1edb51283c070b6741716439c7bc938d38392a46` (v5.3.0)
- `actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38` (v5.4.0)

## 2. Dependency Locking
- GitHub Actions enforce `uv sync --locked --all-extras`.
- `./verify` Stage 1 executes `uv lock --check`.
- `uv.lock` is deterministically synchronized with `pyproject.toml`.

## 3. Device Test Exclusion in Virtual CI
- Device-specific tests requiring physical Termux / Android environments are decorated with `@pytest.mark.device`.
- CI runners execute `pytest -m "not device"`.
- Real device testing is executed locally on Android Termux arm64.
