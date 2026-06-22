#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

VENV_DIR="$ROOT_DIR/.venv-raspi"
VENV_PYTHON="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "======================================"
echo "PCA-HMI Raspberry Pi runner"
echo "======================================"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python was not found. Install Python 3 first."
  exit 1
fi

if [ ! -x "$VENV_PYTHON" ] || ! "$VENV_PYTHON" --version >/dev/null 2>&1; then
  echo "Creating virtual environment: $VENV_DIR"
  rm -rf "$VENV_DIR"
  if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    echo "Failed to create venv."
    echo "On Raspberry Pi OS, try: sudo apt install python3-venv"
    exit 1
  fi
fi

echo "Installing requirements..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$ROOT_DIR/requirements.txt"

echo ""
echo "Starting Flask server..."
echo "Local: http://localhost:5000"
echo "Raspberry Pi LAN: http://<raspberry-pi-ip>:5000"
echo "Press Ctrl+C to stop."
echo "======================================"
echo ""

exec "$VENV_PYTHON" "$ROOT_DIR/app/main.py"
