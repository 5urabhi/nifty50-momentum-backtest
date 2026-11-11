#!/usr/bin/env bash
# Local-only convenience launcher. GitHub never executes this script.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-help}"
case "$MODE" in
  setup)
    if [ ! -d .venv ]; then python3 -m venv .venv; fi
    .venv/bin/python -m pip install -r dashboard/requirements.txt
    ;;
  tests)
    .venv/bin/python -m unittest discover -s tests -v
    ;;
  synthetic)
    .venv/bin/python -m index_research.cli make-fixture --output-dir data/synthetic_example
    .venv/bin/python -m index_research.cli run --input-dir data/synthetic_example --output-dir results/synthetic --config config/research_momentum.json
    ;;
  legacy)
    .venv/bin/python scripts/prepare_legacy_demo.py
    .venv/bin/python -m index_research.cli run --input-dir data/legacy_static_demo --output-dir results/legacy_static_demo --config config/research_legacy_demo.json
    ;;
  visuals)
    .venv/bin/python scripts/export_visual_validation.py --output-dir results/visual_validation
    ;;
  empirical-help)
    .venv/bin/python scripts/prepare_research_data.py --help
    ;;
  dashboard)
    .venv/bin/streamlit run dashboard/app.py
    ;;
  acceptance)
    .venv/bin/python scripts/local_acceptance.py
    ;;
  *)
    echo "Usage: bash scripts/run_local.sh {setup|tests|synthetic|legacy|dashboard|acceptance|empirical-help}"
    ;;
esac
