#!/usr/bin/env bash
# Ubuntu local-first one-command bootstrap and launcher.
# Usage: bash scripts/start.sh [research|evaluate|check|web|both|setup]
# No Redis, Docker, global npm packages, GitHub Actions or Dhan token needed.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-research}"
case "$MODE" in
  web|research|both|check|setup|evaluate) ;;
  -h|--help|help)
    cat <<'HELP'
Usage: bash scripts/start.sh [web|research|both|check|setup]

  research  DEFAULT: install Python dependencies and start your local research lab.
  web       Optional: install Node/Vite, build and start the presentation website.
  both      Install both stacks; launch both apps together.
  check     Run complete Python unit and mathematical tests. No servers.
  evaluate  Run tests, math checks, synthetic research and visual reports,
            writing artifacts to results/. No servers.
  setup     Prepare Python and frontend dependencies; start no servers.

Stop running servers with Ctrl+C.
Never paste Dhan tokens here; place them in the ignored .env file.
HELP
    exit 0 ;;
  *) printf 'Unknown mode: %s\n' "$MODE" >&2; exit 2 ;;
esac

info() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
fail() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
command_exists() { command -v "$1" >/dev/null 2>&1; }

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  fail "Run this command as a normal user (not sudo). The script uses sudo only when required to install system packages."
fi
if ! command_exists apt-get; then
  fail "This automated bootstrap currently supports Ubuntu/Debian with apt-get. See GETTING_STARTED.md for other systems."
fi


install_apt_missing() {
  local packages=() package
  for package in "$@"; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
      packages+=("$package")
    fi
  done
  if [ "${#packages[@]}" -gt 0 ]; then
    command_exists sudo || fail "System packages missing (${packages[*]}) and sudo unavailable."
    info "Installing missing OS packages: ${packages[*]} (sudo may ask for password)"
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
  fi
}

info "Inspecting operating-system dependencies"
install_apt_missing git curl ca-certificates xz-utils

if [ "$MODE" != web ]; then
install_apt_missing python3 python3-venv python3-pip

PYTHON=python3
"$PYTHON" - <<'PY' || fail "Python >=3.11 is required. Update your distribution's Python interpreter."
import sys
assert sys.version_info >= (3,11), f"Python 3.11+ required; got {sys.version}"
PY

info "Preparing isolated Python research environment"
if [ ! -x .venv/bin/python ]; then
  "$PYTHON" -m venv .venv || fail "Unable to create .venv (check python3-venv package)."
fi
if ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  fail "Virtualenv pip missing. Remove .venv only if it contains no personal data, then retry."
fi

mkdir -p .local-state
REQ_HASH="$(sha256sum requirements.txt | awk '{print $1}')"
PY_TAG="$(.venv/bin/python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
REQ_MARKER=".local-state/python-requirements.sha256"
EXPECTED_PY="$REQ_HASH:$PY_TAG"
CURRENT_PY="$(cat "$REQ_MARKER" 2>/dev/null || true)"
if [ "$CURRENT_PY" != "$EXPECTED_PY" ] || ! .venv/bin/python -c 'import numpy,pandas,scipy,streamlit,plotly,reportlab,dotenv' >/dev/null 2>&1; then
  info "Installing/updating local Python packages"
  .venv/bin/python -m pip install -r requirements.txt
  printf '%s\n' "$EXPECTED_PY" > "$REQ_MARKER"
else
  info "Python dependencies already available"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  chmod 600 .env
  info "Created private .env template (Dhan token optional; edit with nano .env)"
fi
if [ -f .env ]; then chmod 600 .env; fi
fi

# Research-only operation must not depend on npm, Vite or the web build.
if [ "$MODE" = research ]; then
  info "Opening YOUR quantitative research lab on http://127.0.0.1:8501"
  info "Sidebar: Index Research -> enable synthetic example -> Run experiment"
  info "Press Ctrl+C to stop"
  exec .venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
fi

if [ "$MODE" = check ] || [ "$MODE" = evaluate ]; then
  info "Running end-to-end Python and Streamlit workstation acceptance"
  .venv/bin/python scripts/local_acceptance.py
  info "Running mathematical acceptance (persistent HTML and JSON reports)"
  .venv/bin/python scripts/verify_mathematics.py --output-dir results/math_acceptance
  if [ "$MODE" = evaluate ]; then
    info "Running labeled synthetic factor experiment"
    # The synthetic generator is deterministic; existing files are retained.
    if [ ! -f data/synthetic_example/prices.csv ]; then
      .venv/bin/python -m index_research.cli make-fixture --output-dir data/synthetic_example
    fi
    # Experiments may refuse overwriting an existing output directory.
    RUN_DIR="results/synthetic_$(date +%Y%m%d_%H%M%S)"
    .venv/bin/python -m index_research.cli run --input-dir data/synthetic_example --output-dir "$RUN_DIR" --config config/research_multifactor.json
    info "Generating 2D/3D analytical validation report"
    .venv/bin/python scripts/export_visual_validation.py --output-dir results/visual_validation
    info "Experiment output: $RUN_DIR"
    info "Mathematics report: results/math_acceptance/mathematics_acceptance.html"
    info "Visual report directory: results/visual_validation"
  fi
  info "Python research checks completed"
  exit 0
fi

# The public website needs no Redis or application server. Node is used
# only to build and serve local development assets.
node_suitable() {
  command_exists node && command_exists npm &&
    node -e 'const s=process.versions.node.split(".").map(Number);process.exit((s[0]>22||(s[0]===22&&s[1]>=12)||(s[0]===20&&s[1]>=19))?0:1)' 2>/dev/null
}
if ! node_suitable; then
  info "Installing a verified portable Node.js runtime in .local-tools"
  # Fixed reviewed LTS release. No curl | bash, no third-party installers.
  NODE_VERSION="v22.16.0"
  MACHINE="$(uname -m)"
  case "$MACHINE" in
    x86_64|amd64) NODE_ARCH="x64" ;;
    aarch64|arm64) NODE_ARCH="arm64" ;;
    *) fail "Unsupported Node architecture: $MACHINE (install a supported Node LTS manually)" ;;
  esac
  NODE_DIST="node-${NODE_VERSION}-linux-${NODE_ARCH}"
  NODE_DIR="$ROOT/.local-tools/$NODE_DIST"
  if [ ! -x "$NODE_DIR/bin/node" ]; then
    mkdir -p "$ROOT/.local-tools"
    TMP="$(mktemp -d)"
    trap 'rm -rf "${TMP:-}"' EXIT
    BASE_URL="https://nodejs.org/dist/$NODE_VERSION"
    curl --fail --location --silent --show-error --retry 3 --connect-timeout 15       "$BASE_URL/SHASUMS256.txt" -o "$TMP/SHASUMS256.txt" ||
      fail "Cannot reach official Node.js HTTPS distribution. Check connectivity."
    curl --fail --location --silent --show-error --retry 3 --connect-timeout 15       "$BASE_URL/$NODE_DIST.tar.xz" -o "$TMP/$NODE_DIST.tar.xz" ||
      fail "Unable to download official Node.js runtime."
    (cd "$TMP" &&
      grep "  $NODE_DIST.tar.xz$" SHASUMS256.txt > selected.sha &&
      sha256sum -c selected.sha) || fail "Node.js checksum verification failed"
    tar -xJf "$TMP/$NODE_DIST.tar.xz" -C "$ROOT/.local-tools"
    rm -rf "$TMP"
    trap - EXIT
  fi
  export PATH="$NODE_DIR/bin:$PATH"
fi
node_suitable || fail "Node/npm unavailable or not recent enough after setup."
info "Using Node $(node --version) and npm $(npm --version)"

mkdir -p .local-state
PKG_HASH="$(sha256sum package.json | awk '{print $1}')"
LOCK_HASH="none"
if [ -f package-lock.json ]; then LOCK_HASH="$(sha256sum package-lock.json | awk '{print $1}')"; fi
NPM_EXPECTED="$PKG_HASH:$LOCK_HASH:$(node --version)"
NPM_MARKER=".local-state/npm-dependencies.sha256"
if [ "$(cat "$NPM_MARKER" 2>/dev/null || true)" != "$NPM_EXPECTED" ] || [ ! -x node_modules/.bin/vite ] || [ ! -x node_modules/.bin/tsc ]; then
  info "Installing/updating Vite/React packages"
  if [ -f package-lock.json ]; then
    npm ci --no-audit --no-fund
  else
    npm install --no-audit --no-fund
  fi
  LOCK_HASH="none"
  if [ -f package-lock.json ]; then LOCK_HASH="$(sha256sum package-lock.json | awk '{print $1}')"; fi
  printf '%s\n' "$PKG_HASH:$LOCK_HASH:$(node --version)" > "$NPM_MARKER"
else
  info "Vite/React dependencies already available"
fi

info "Checking frontend TypeScript and production Vite build"
npm run build

if [ "$MODE" = setup ]; then
  info "Setup and build complete. Run: bash scripts/start.sh"
  exit 0
fi

if [ "$MODE" = check ]; then
  info "Running all local Python tests"
  .venv/bin/python -m unittest discover -s tests -v
  info "Running mathematical acceptance"
  .venv/bin/python scripts/verify_mathematics.py --output-dir results/math_acceptance
  info "All local checks passed"
  exit 0
fi

STREAMLIT_PID=""
stop_all() {
  if [ -n "$STREAMLIT_PID" ]; then
    kill "$STREAMLIT_PID" 2>/dev/null || true
    wait "$STREAMLIT_PID" 2>/dev/null || true
  fi
}
trap stop_all EXIT INT TERM

if [ "$MODE" = research ] || [ "$MODE" = both ]; then
  info "Starting local Streamlit research laboratory on http://127.0.0.1:8501"
  if [ "$MODE" = research ]; then
    exec .venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501
  fi
  .venv/bin/streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501 &
  STREAMLIT_PID=$!
  sleep 2
  kill -0 "$STREAMLIT_PID" 2>/dev/null || fail "Streamlit failed to start; check terminal output above."
fi

info "Starting React/Vite research website (normally http://127.0.0.1:5173)"
info "Press Ctrl+C to stop"
npm run dev -- --port 5173 --strictPort
