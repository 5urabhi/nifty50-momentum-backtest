#!/usr/bin/env bash
# Local-only React/Vite frontend with Python FastAPI research engine.
# No external deployment, broker orders, or Redis/Docker service.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"

info() { printf '\n==> %s\n' "$*"; }
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# Preserve the existing Ubuntu setup logic; it installs Node/npm and a Python
# virtual environment and runs a TypeScript build before starting any servers.
info "Preparing Python and React environments"
bash scripts/start.sh setup

test -x .venv/bin/uvicorn || fail "FastAPI dependencies missing from .venv"
# The setup tool may provision Node as a local, ignored portable installation.
if ! command -v npm >/dev/null 2>&1; then
  NODE_PATH="$ROOT/.local-tools/node-v22.16.0-linux-$(case "$(uname -m)" in x86_64|amd64) echo x64;; aarch64|arm64) echo arm64;; esac)/bin"
  test -x "$NODE_PATH/node" || fail "Node unavailable after setup"
  export PATH="$NODE_PATH:$PATH"
fi

API_PID=""
cleanup() {
  if [ -n "$API_PID" ]; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

info "Starting local Python research API at http://127.0.0.1:8765"
.venv/bin/uvicorn workstation_api.app:app --host 127.0.0.1 --port 8765 &
API_PID=$!
# Check that Python's import and startup succeeded before opening the UI.
for i in $(seq 1 40); do
  kill -0 "$API_PID" 2>/dev/null || fail "Python API exited during startup"
  if curl --fail --silent --max-time 1 http://127.0.0.1:8765/api/health >/dev/null; then
    break
  fi
  if [ "$i" -eq 40 ]; then fail "Python API health endpoint not ready"; fi
  sleep 0.25
done

info "Starting the React/Vite RESEARCH WORKSTATION"
info "Open http://127.0.0.1:5173"
info "Press Ctrl+C to stop both local servers"
exec npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
