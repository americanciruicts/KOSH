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

# --- Guard: only ONE place parses BOMs, the shared module ---
# May 5 2026: we discovered /jobs had its OWN inline parser that none of
# our fixes ever touched. From now on, the shared module is the only
# allowed parser. If a template re-introduces inline XLSX parsing, fail
# the deploy here so the user never gets two divergent parsers again.
echo "[bom-parser-guard] checking for inline XLSX parsing in templates…"
# XLSX.read (file -> workbook) is fine in templates; XLSX.utils.sheet_to_json
# is what makes a parser a parser, and that must live in the shared module.
LEAK=$(grep -ln "XLSX\.utils\.sheet_to_json" templates/ 2>/dev/null \
       | grep -v "^templates/_test/" || true)
if [ -n "${LEAK}" ]; then
    echo "FAIL: inline Excel parsing found outside static/js/bom_parser.js:"
    echo "${LEAK}" | sed 's/^/  /'
    echo "Templates must call KoshBomParser.parseWorkbook(workbook, XLSX) instead."
    echo "Move the logic into static/js/bom_parser.js so the test suite covers it."
    exit 4
fi
echo "[bom-parser-guard] OK — only the shared module parses BOMs."

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
# These isolate with SAVEPOINT/ROLLBACK + test PCNs >=99000, so they are safe against
# the live DB. Everything ledger-related is below, on the test DB, because it commits.
docker cp tests/regression_tests.py "${CONTAINER}:/app/tests/regression_tests.py"
docker exec "${CONTAINER}" python /app/tests/regression_tests.py

# --- Ledger acceptance suites (test DB only — they COMMIT real movements) ---
# 2026-07-15: these had been pinned to a `kosh_rebuild` scratch DB that was later
# dropped, so all four silently stopped running (same rot that had regression_tests.py
# pointing at the renamed `pcb_inventory` schema). They now target kosh_test and
# REFUSE to run against production (tests/testdb.py).
TEST_CONTAINER=kosh_test_webapp
if docker ps --filter "name=${TEST_CONTAINER}" --format '{{.Names}}' | grep -q "${TEST_CONTAINER}"; then
    echo "[ledger-acceptance] running against ${TEST_CONTAINER} (kosh_test)…"
    docker exec "${TEST_CONTAINER}" mkdir -p /app/tests
    for f in testdb.py acceptance_found.py acceptance_b.py acceptance_extra.py acceptance_app.py; do
        docker cp "tests/${f}" "${TEST_CONTAINER}:/app/tests/${f}"
    done
    for s in acceptance_found acceptance_b acceptance_extra acceptance_app; do
        echo "  --- ${s}"
        docker exec "${TEST_CONTAINER}" python "/app/tests/${s}.py"
    done
    echo "[ledger-acceptance] OK — all ledger suites green."
else
    echo "WARN: ${TEST_CONTAINER} not running — SKIPPING the ledger acceptance suites."
    echo "      The ledger (restock/pick/FOUND, Warehouse==History) is NOT covered by"
    echo "      this run. Start it to get full coverage before shipping ledger changes."
fi
