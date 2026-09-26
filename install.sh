#!/bin/sh
# shellcheck shell=bash
if [ -z "$BASH_VERSION" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    fi
fi
# ==============================================================================
# TACP 0.1 — Termux AI Control Plane Installer
# ==============================================================================
# Performs safe, deterministic bootstrap of TACP inside Termux or POSIX Linux.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

show_help() {
  cat <<EOF
Usage: ./install.sh [OPTIONS]

TACP (Termux AI Control Plane) Installation Script.

Options:
  -h, --help       Show this help message and exit
  --dry-run        Check prerequisites without modifying system
  --no-doctor      Skip post-installation doctor diagnostics
EOF
}

DRY_RUN=false
SKIP_DOCTOR=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      show_help
      exit 0
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --no-doctor)
      SKIP_DOCTOR=true
      shift
      ;;
    *)
      echo "[ERROR] Unknown option: $1" >&2
      show_help >&2
      exit 1
      ;;
  esac
done

echo "============================================================"
echo " TACP 0.1 — Termux AI Control Plane Installation"
echo "============================================================"


# 1. Environment and Python check
PYTHON_BIN=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ver=$("$cmd" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)
    major=$(echo "$ver" | cut -d. -f1)
    minor=$(echo "$ver" | cut -d. -f2)
    if [[ "$major" -ge 3 && "$minor" -ge 11 ]]; then
      PYTHON_BIN="$cmd"
      echo "[OK] Found suitable Python runtime: $cmd (v$ver)"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "[ERROR] Python 3.11 or higher is required. Please install Python in Termux (pkg install python)."
  exit 1
fi

if [[ "$DRY_RUN" == "true" ]]; then
  echo "[OK] Dry run prerequisite check passed. No changes made."
  exit 0
fi

# 2. Virtual Environment Setup
if [[ ! -d ".venv" ]]; then
  echo "[*] Creating virtual environment (.venv)..."
  if command -v uv >/dev/null 2>&1; then
    uv venv .venv --python "$PYTHON_BIN"
  else
    "$PYTHON_BIN" -m venv .venv
  fi
  echo "[OK] Virtual environment created."
else
  echo "[OK] Existing virtual environment found (.venv)."
fi

# Activate venv
VENV_PIP="$SCRIPT_DIR/.venv/bin/pip"

# 3. Install TACP package in editable mode
echo "[*] Installing TACP in editable mode..."
if command -v uv >/dev/null 2>&1; then
  uv pip install --link-mode=copy -e .
else
  "$VENV_PIP" install -e .
fi

# 4. Initialize Data Directory and Run Doctor
if [[ "$SKIP_DOCTOR" != "true" ]]; then
  echo "[*] Initializing TACP database and running diagnostics..."
  "$SCRIPT_DIR/.venv/bin/tacp" doctor
fi

# 5. Ensure Default Workspace
echo "[*] Registering current directory as default workspace..."
"$SCRIPT_DIR/.venv/bin/tacp" workspace add "$SCRIPT_DIR" --name "tacp-repo" >/dev/null 2>&1 || true

# 6. User helper instructions
BIN_DIR="${PREFIX:-/data/data/com.termux/files/usr}/bin"
if [[ -d "$BIN_DIR" && -w "$BIN_DIR" ]]; then
  ln -sf "$SCRIPT_DIR/.venv/bin/tacp" "$BIN_DIR/tacp"
  echo "[OK] Created global symlink: $BIN_DIR/tacp"
else
  echo "[NOTE] To use 'tacp' globally, add this alias to your shell rc:"
  echo "       alias tacp=\"$SCRIPT_DIR/.venv/bin/tacp\""
fi

echo "============================================================"
echo " [SUCCESS] TACP 0.1 installed successfully!"
echo " "
echo " Test your installation:"
echo "   tacp version"
echo "   tacp capabilities"
echo "   tacp status"
echo "   tacp doctor"
echo "   tacp serve       (Starts stdio MCP server)"
echo "============================================================"
