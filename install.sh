#!/data/data/com.termux/files/usr/bin/env bash
# ==============================================================================
# TACP 0.1 — Termux AI Control Plane Installer
# ==============================================================================
# Performs safe, deterministic bootstrap of TACP inside Termux or POSIX Linux.
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

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
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
VENV_PIP="$SCRIPT_DIR/.venv/bin/pip"

# 3. Install TACP package in editable mode
echo "[*] Installing TACP in editable mode..."
if command -v uv >/dev/null 2>&1; then
  uv pip install --link-mode=copy -e .
else
  "$VENV_PIP" install -e .
fi

# 4. Initialize Data Directory and Run Doctor
echo "[*] Initializing TACP database and running diagnostics..."
"$SCRIPT_DIR/.venv/bin/tacp" doctor

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
