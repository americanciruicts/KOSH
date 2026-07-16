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

# Every Postgres suite below COMMITS (db_manager.restock_pcb commits internally, so
# SAVEPOINT/rollback cannot contain it) — so they ALL run against the kosh_test
# container, never production. This used to point at stockandpick_webapp/`kosh`, which
# broke Preet's standing rule ("no generate-and-delete PCN tests on prod") and on
# 2026-07-15 leaked 70 phantom units into the prod ledger across PCNs 99001/99002/99005
# (the legacy cleanup didn't know about inventory_txn/inventory_balance).
CONTAINER=kosh_test_webapp
if ! docker ps --filter "name=${CONTAINER}" --format '{{.Names}}' | grep -q "${CONTAINER}"; then
    echo "FAIL: test container ${CONTAINER} is not running — the DB suites cannot run."
    echo "      Refusing to pass: a green run with no DB coverage is how the gate"
    echo "      silently rotted in the first place. Start it (kosh_test DB), e.g.:"
    echo "        docker run -d --name ${CONTAINER} --network db-consolidation_aci-network \\"
    echo "          -p 5056:5000 -e POSTGRES_DB=kosh_test -e POSTGRES_HOST=aci-database \\"
    echo "          -e POSTGRES_USER=aci -e POSTGRES_PASSWORD=... kosh-web_app"
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

# --- Postgres data-shape regressions (kosh_test only — this suite COMMITS) ---
echo "[regressions] running against ${CONTAINER} (kosh_test)…"
docker exec "${CONTAINER}" mkdir -p /app/tests
docker cp tests/regression_tests.py "${CONTAINER}:/app/tests/regression_tests.py"
docker exec "${CONTAINER}" python /app/tests/regression_tests.py

# --- Ledger acceptance suites (also kosh_test — they COMMIT real movements) ---
# 2026-07-15: these had been pinned to a `kosh_rebuild` scratch DB that was later
# dropped, so all four silently stopped running (same rot that had regression_tests.py
# pointing at the renamed `pcb_inventory` schema). They now target kosh_test and
# REFUSE to run against production (tests/testdb.py).
echo "[ledger-acceptance] running against ${CONTAINER} (kosh_test)…"
for f in testdb.py acceptance_found.py acceptance_b.py acceptance_extra.py acceptance_app.py; do
    docker cp "tests/${f}" "${CONTAINER}:/app/tests/${f}"
done
for s in acceptance_found acceptance_b acceptance_extra acceptance_app; do
    echo "  --- ${s}"
    docker exec "${CONTAINER}" python "/app/tests/${s}.py"
done
echo "[ledger-acceptance] OK — all ledger suites green."

# --- Part Number Change must take the stock with it (bug 28, 2026-07-16) ---------
# The rename used to update only the legacy snapshot, leaving the ledger balance filed
# under the OLD part_id: pick then read 0 against a full bin ("insufficient quantity")
# and project_warehouse added the orphan on top of any edit ("expected 80, got 280").
echo "[pn-change-ledger] running against ${CONTAINER} (kosh_test)…"
docker cp tests/test_part_number_change_ledger.py "${CONTAINER}:/app/tests/test_part_number_change_ledger.py"
docker exec "${CONTAINER}" python /app/tests/test_part_number_change_ledger.py
echo "[pn-change-ledger] OK — a relabel keeps its stock, and mints none."

# --- Auth/CSRF regression (bug 27, 2026-07-16) -----------------------------------
# Kitting means two tabs (/pick + /part-number-change). A same-user SSO round-trip
# used to session.clear(), rotating csrf_token and breaking the OTHER tab's form —
# which bounced it back through SSO, breaking the first tab. Read-only: no commits.
echo "[csrf-pingpong] running against ${CONTAINER} (kosh_test)…"
docker cp tests/test_csrf_pingpong.py "${CONTAINER}:/app/tests/test_csrf_pingpong.py"
docker exec "${CONTAINER}" python /app/tests/test_csrf_pingpong.py
echo "[csrf-pingpong] OK — SSO round-trip no longer signs the user out."
