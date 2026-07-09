#!/usr/bin/env bash
# VerifAI — one-command local runner for the API server.
# Creates a virtualenv, installs deps, and starts the API on :8000.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"

if [ ! -d ".venv" ]; then
  echo "→ creating virtualenv (.venv) ..."
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "→ installing dependencies (first run only) ..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo "→ starting VerifAI API on http://localhost:${PORT}  (Ctrl-C to stop)"
echo "  interactive docs: http://localhost:${PORT}/docs"
exec python main.py serve --host "$HOST" --port "$PORT"
