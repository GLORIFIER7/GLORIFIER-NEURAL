#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

mode="${1:-preview}"
case "$mode" in
  preview|deploy|--prepare-only) ;;
  *)
    echo "Usage: bash ./worker-build.sh [preview|deploy|--prepare-only]" >&2
    exit 64
    ;;
esac

# Pywrangler vendors the production Pyodide packages into python_modules/.
# Its host virtual environments are build tools, not Worker runtime modules.
uv run --locked pywrangler sync

test -f python_modules/app/api.py
test -f python_modules/app/database/neon.py
test -f python_modules/asyncpg/__init__.py

# Prevent Wrangler from bundling CPython and Pyodide build environments beside
# the intended python_modules/ package tree (which causes duplicate dist-info).
rm -rf -- .venv .venv-workers

if [[ -e .venv || -e .venv-workers ]]; then
  echo "Temporary Python environments remain inside the Worker bundle root." >&2
  exit 1
fi

if [[ "$mode" == "--prepare-only" ]]; then
  echo "Worker dependencies are vendored and build-only environments are removed."
  exit 0
fi

exec npx wrangler "$mode"
