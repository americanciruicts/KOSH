#!/usr/bin/env bash
# Runs the KOSH regression smoke suite inside the running webapp container.
# Exit code = number of failed tests (0 == all green).
#
# Use before every deploy:
#   /home/tony/KOSH/tests/run.sh && \
#     docker compose build --no-cache && docker compose up -d && \
#     vercel --prod --yes
#
# If any test fails, fix the regression BEFORE shipping.

set -e
cd "$(dirname "$0")/.."

CONTAINER=stockandpick_webapp
if ! docker ps --filter "name=${CONTAINER}" --format '{{.Names}}' | grep -q "${CONTAINER}"; then
    echo "Container ${CONTAINER} is not running. Start it first:"
    echo "  docker compose up -d"
    exit 99
fi

# --- BOM parser regression (runs on host, no container needed) ---
# Catches the bug class that bit Preet on May 4-5 2026: parser changes
# silently dropping rows from "BOM to Load" (e.g. ZSUB substitutes).
if command -v node >/dev/null 2>&1; then
    if [ ! -d /tmp/node_modules/xlsx ]; then
        echo "Installing xlsx for parser test..."
        (cd /tmp && npm install --silent xlsx >/dev/null 2>&1) || true
    fi
    NODE_PATH=/tmp/node_modules node tests/test_bom_parser.js
else
    echo "WARN: node not on PATH — skipping BOM parser regression test."
fi

# --- Postgres data-shape regressions (run inside the container) ---
docker cp tests/regression_tests.py "${CONTAINER}:/app/tests/regression_tests.py"
docker exec "${CONTAINER}" python /app/tests/regression_tests.py
