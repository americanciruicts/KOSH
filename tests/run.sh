#!/usr/bin/env bash
# ── KOSH TEST GATE (rebuilt 2026-07-17) ── STAGING ONLY ──────────────────────
# Replaces the old suite that silently rotted (pinned to a renamed schema /
# dropped scratch DB) and once leaked 70 phantom units into prod. Two parts:
#
#   1. INTEGRITY SCOREBOARD  — READ-ONLY, runs against $SCORE_DB (default: kosh).
#      Starts RED on today's real numbers and must reach 0 as phases land.
#   2. BEHAVIORAL TESTS      — drive the REAL ledger code; run against kosh_test
#      (never kosh/prod). Auto-discovered from tests/behavioral/*.py.
#
# Exit code = number of FAILED gates (0 = all green).
#
# Usage:   PGPASSWORD=<kosh pw> tests/run.sh
# Env:     PGHOST(localhost) PGPORT(5434) PGUSER(aci) SCORE_DB(kosh) TEST_DB(kosh_test)

set -uo pipefail
export PGHOST="${PGHOST:-localhost}" PGPORT="${PGPORT:-5434}" PGUSER="${PGUSER:-aci}"
SCORE_DB="${SCORE_DB:-kosh}"
TEST_DB="${TEST_DB:-kosh_test}"
BEH_DIR="$(dirname "$0")/behavioral"

[ -z "${PGPASSWORD:-}" ] && { echo "ERROR: export PGPASSWORD (the kosh DB password) first."; exit 99; }
[ "$TEST_DB" = "kosh" ] && { echo "REFUSING: TEST_DB=kosh. Committing tests must use kosh_test."; exit 99; }

Q(){ psql -d "$SCORE_DB" -tAc "$1" 2>/dev/null; }
TBL(){ psql -d "$SCORE_DB" -tAc "SELECT to_regclass('$1') IS NOT NULL" 2>/dev/null; }
fails=0
gate(){ if [ "$3" = "$2" ]; then printf "  \033[32mPASS\033[0m  %-26s %s\n" "$1" "$3"
        else printf "  \033[31mFAIL\033[0m  %-26s %s  (want %s)\n" "$1" "$3" "$2"; fails=$((fails+1)); fi; }
info(){ printf "  %-26s %s\n" "$1" "$2"; }

echo "════════ INTEGRITY SCOREBOARD  ($SCORE_DB @ $PGHOST:$PGPORT) ════════"
gate "double_count (PH-1)" 0 "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\" WHERE COALESCE(onhandqty,0)>0 AND mfg_qty ~ '^[1-9][0-9]*\$'")"
gate "negative_bin (I1)"   0 "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\" WHERE COALESCE(onhandqty,0)<0")"
gate "negative_floor (I1)" 0 "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\" WHERE mfg_qty ~ '^-[0-9]+\$'")"

# LEDGER REMOVED 2026-07-22: the whse_vs_ledger / cache_vs_ledger gates compared the
# snapshot against the abandoned inventory_balance/inventory_txn ledger tables. On-hand
# is now the single stored onhandqty, so those checks are obsolete and were removed.
# The bin XOR floor invariant is enforced by the DB trigger + the checks below.
gate "floor_with_bin_onhand" 0 "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\" WHERE COALESCE(loc_to,'')='MFG Floor' AND COALESCE(onhandqty,0)<>0")"
gate "bin_with_floor_qty"    0 "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\" WHERE COALESCE(loc_to,'')<>'MFG Floor' AND mfg_qty ~ '^[1-9][0-9]*\$'")"

# PH-1 / WI-2 — Phase 2's exit gate, which nothing enforced until 2026-07-29: PCN
# History's newest on-hand must equal Warehouse Inventory. It silently drifted for weeks
# because the page replayed the ABANDONED ledger model (PCN 46559 showed 60,900 against a
# stored 300). The behavioral test below owns the real check; this line keeps the failure
# visible on the scoreboard even if someone deletes the test.
gate "pcn_history_vs_whse"   0 "$(PGPASSWORD="$PGPASSWORD" SCORE_DB="$SCORE_DB" python3 "$(dirname "$0")/behavioral/p2_pcn_history_matches_warehouse.py" >/dev/null 2>&1; echo $?)"
echo "  ---- info (not gated) ----"
info "stale_floor_rows"     "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\" WHERE COALESCE(onhandqty,0)=0 AND mfg_qty ~ '^[1-9][0-9]*\$'")"
info "total_inventory_rows" "$(Q "SELECT count(*) FROM warehouse.\"tblWhse_Inventory\"")"

echo ""
echo "════════ BEHAVIORAL TESTS  (real ledger code → $TEST_DB) ════════"
shopt -s nullglob
ran=0
for t in "$BEH_DIR"/*.py; do
  ran=1; name=$(basename "$t" .py)
  if PGPASSWORD="$PGPASSWORD" TEST_DB="$TEST_DB" python3 "$t" >/tmp/kosh_beh_$$ 2>&1; then
    printf "  \033[32mPASS\033[0m  %s\n" "$name"
  else
    printf "  \033[31mFAIL\033[0m  %s\n" "$name"; fails=$((fails+1))
  fi
  sed 's/^/      /' /tmp/kosh_beh_$$; rm -f /tmp/kosh_beh_$$
done
[ $ran -eq 0 ] && echo "  (no behavioral tests yet)"

echo "  ---- issue coverage ----"
for m in "SR-1|Phase5" "SR-2|Phase5" "SR-3|Phase1" "SR-4|Phase5" "WI-1|Phase1" \
         "WI-2|Phase2" "PK-1|Phase1" "SO-1|Phase4" "PH-1|Phase2" "RS-1|Phase3"; do
  IFS='|' read -r id phase <<< "$m"
  if grep -rql "$id" "$BEH_DIR"/*.py 2>/dev/null; then
    printf "  \033[32mCOVERED\033[0m  %-6s (%s)\n" "$id" "$phase"
  else
    printf "  \033[33mPENDING\033[0m  %-6s (%s)\n" "$id" "$phase"
  fi
done

echo ""
echo "════════ RESULT: $fails failed gate(s) ════════"
exit $fails
