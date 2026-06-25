#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

ENV_FILE="${ENV_FILE:-$ROOT_DIR/vehicle.env}"

if [ -f "$ENV_FILE" ]; then
  echo "Loading environment: $ENV_FILE"
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
else
  echo "Environment file not found: $ENV_FILE"
fi

if [ -z "${VENV_DIR:-}" ]; then
  if [ -d "$ROOT_DIR/venv" ]; then
    VENV_DIR="$ROOT_DIR/venv"
  else
    VENV_DIR="$ROOT_DIR/.venv-raspi"
  fi
fi

VENV_PYTHON="$VENV_DIR/bin/python"
PYTHON_BIN="${PYTHON_BIN:-python3}"

is_true() {
  case "${1:-}" in
    1|true|TRUE|True|yes|YES|Yes|on|ON|On) return 0 ;;
    *) return 1 ;;
  esac
}

setup_can() {
  if ! is_true "${CAN_ENABLED:-False}"; then
    echo "CAN setup skipped: CAN_ENABLED is not true."
    return 0
  fi

  local channel="${CAN_CHANNEL:-can0}"
  local bitrate="${CAN_BITRATE:-500000}"
  local dbitrate="${CAN_DBITRATE:-2000000}"
  local restart_ms="${CAN_RESTART_MS:-100}"
  local txqueuelen="${CAN_TXQUEUELEN:-1000}"

  if ! command -v ip >/dev/null 2>&1; then
    echo "CAN setup skipped: ip command was not found."
    return 0
  fi

  if ! ip link show "$channel" >/dev/null 2>&1; then
    echo "CAN setup skipped: $channel was not found."
    return 0
  fi

  echo "Configuring CAN interface: $channel"
  sudo ip link set "$channel" down 2>/dev/null || true
  sudo ip link set "$channel" txqueuelen "$txqueuelen"

  if is_true "${CAN_FD:-False}"; then
    sudo ip link set "$channel" type can bitrate "$bitrate" dbitrate "$dbitrate" fd on restart-ms "$restart_ms"
    echo "CAN FD: channel=$channel bitrate=$bitrate dbitrate=$dbitrate restart-ms=$restart_ms txqueuelen=$txqueuelen"
  else
    sudo ip link set "$channel" type can bitrate "$bitrate" restart-ms "$restart_ms"
    echo "Classical CAN: channel=$channel bitrate=$bitrate restart-ms=$restart_ms txqueuelen=$txqueuelen"
  fi

  sudo ip link set "$channel" up
  ip -details link show "$channel"
}

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

setup_can

echo ""
echo "Starting Flask server..."
echo "Local: http://localhost:5000"
echo "Raspberry Pi LAN: http://<raspberry-pi-ip>:5000"
echo "Press Ctrl+C to stop."
echo "======================================"
echo ""

exec "$VENV_PYTHON" "$ROOT_DIR/app/main.py"
