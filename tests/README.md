# KOSH test gate (rebuilt 2026-07-17)

The old suite was deleted (archived to `backups/old_tests_removed_20260717/`). It had
silently rotted — pinned to a renamed schema / dropped scratch DB — so "verified" meant
nothing, and it once leaked 70 phantom units into prod. This gate is built to fail loudly.

## Run it
```bash
PGPASSWORD='<kosh db password>' tests/run.sh
```
Exit code = number of FAILED gates (0 = all green).

## Two parts
1. **Integrity scoreboard** — READ-ONLY, runs against `SCORE_DB` (default `kosh`).
   Checks the invariants that map to Theresa's issues:
   - `double_count (PH-1)` — rows with bin AND floor both > 0 → must be 0
   - `negative_bin/floor (I1)` — no negative stock
   - `whse_vs_ledger (WI-2)` — Warehouse total vs rebuilt-ledger total per PCN → 0
   - `cache_vs_ledger` — `inventory_balance` vs replay of `inventory_txn` → 0
   It starts RED on today's real numbers and must reach 0 as phases land.
2. **Per-issue behavioral tests** — COMMIT real operations, so they run ONLY against
   `kosh_test` (a clone of `kosh`), never the live copy. Each issue (SR-1..RS-1) has a
   slot that prints `PENDING` until its phase drops a `tests/behavioral/<name>.sh` that
   reproduces the bug RED on old code and proves it GREEN on the fix.

## Databases
- `kosh` — staging copy of production (what humans validate). Scoreboard reads it.
- `kosh_test` — throwaway clone for committing tests. Recreate with:
  ```bash
  PGPASSWORD=<postgres pw> pg_dump -h localhost -p 5434 -U postgres -Fc kosh -f /tmp/k.dump
  psql -U postgres -c 'DROP DATABASE IF EXISTS kosh_test; CREATE DATABASE kosh_test OWNER aci;'
  pg_restore -U postgres --no-owner -d kosh_test /tmp/k.dump
  ```
The gate refuses to run committing tests against `kosh`.
