#!/usr/bin/env bash
# Single entry point. Run: bash run.sh [web|research|both|check|setup]
set -Eeuo pipefail
exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/start.sh" "$@"
