"""Tests for TACP Installation Experience and Scripts (Category K)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_install_script_syntax(repo_root: Path) -> None:
    """Verify install.sh is syntactically valid bash."""
    install_sh = repo_root / "install.sh"
    assert install_sh.exists()
    assert os.access(install_sh, os.X_OK)

    result = subprocess.run(
        ["bash", "-n", str(install_sh)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"install.sh syntax error: {result.stderr}"


def test_install_script_help_flag(repo_root: Path) -> None:
    """Verify install.sh handles --help cleanly."""
    install_sh = repo_root / "install.sh"
    result = subprocess.run(
        ["bash", str(install_sh), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert "TACP" in result.stdout


def test_install_script_unknown_flag_fails(repo_root: Path) -> None:
    """Verify install.sh rejects unknown options."""
    install_sh = repo_root / "install.sh"
    result = subprocess.run(
        ["bash", str(install_sh), "--invalid-flag-12345"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Unknown option" in result.stderr or "Unknown option" in result.stdout


def test_doctor_script_syntax(repo_root: Path) -> None:
    """Verify doctor script is syntactically valid bash."""
    doctor_sh = repo_root / "doctor"
    assert doctor_sh.exists()
    assert os.access(doctor_sh, os.X_OK)

    result = subprocess.run(
        ["bash", "-n", str(doctor_sh)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"doctor syntax error: {result.stderr}"


def test_verify_script_syntax(repo_root: Path) -> None:
    """Verify verify script is syntactically valid bash."""
    verify_sh = repo_root / "verify"
    assert verify_sh.exists()
    assert os.access(verify_sh, os.X_OK)

    result = subprocess.run(
        ["bash", "-n", str(verify_sh)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"verify syntax error: {result.stderr}"


def test_doctor_script_execution(repo_root: Path) -> None:
    """Verify running doctor in current environment exits 0."""
    result = subprocess.run(
        ["./doctor"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Summary:" in result.stdout
    assert "Issues: 0" in result.stdout
