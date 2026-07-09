# PHASE 4c — REAL-TIME WRITE-PATH EVENTS (DEPLOYED TO PROD ✅)

**Date:** 2026-07-09 · **Status:** DEPLOYED to prod 2026-07-09 ~14:17 EDT (zero-downtime), verified on LIVE ops.
Deployed via `scripts/deploy_realtime_shadow.sh` (self-verify + auto-rollback); `docker cp` + `HUP` reload.

**LIVE VERIFICATION:** two real picks by `parts@` (PCN 46480 q12, 46481 q39) emitted typed `PICK` events
(`created_by=parts@…`, `note=realtime`) the instant they committed; `inv_onhand` == warehouse for both
(0/12, 0/39); overall reconcile **0 differ**; **0** fail-safe skips; app 302; users undisturbed.

_Original readiness notes (pre-deploy) below._

## What's built (in the repo, ready to deploy)
- **`inv_shadow.py`**: `sync_pcns()` / `sync_scope()` / `realtime_sync()` — reconcile `inv_onhand` to warehouse
  for specific PCNs on the caller's cursor, emitting **typed** events. `realtime_sync()` wraps it in a
  `SAVEPOINT` so any error is contained.
- **`app.py`**: 5 fail-safe hooks, each right before the operation's `conn.commit()`, each in an inner
  `try/except` **and** the internal SAVEPOINT (two isolation layers):
  | Function | Event | Scope |
  |---|---|---|
  | `stock_pcb` | RECEIPT | `[pcn]` |
  | `pick_pcb` (pick) | PICK | `[pcn]` or all PCNs of the item (FIFO) |
  | `pick_pcb` (purge) | PURGE | `[pcn]` or item |
  | `restock_pcb` | RESTOCK | `[pcn]` |
  | `reverse_pick` | RESTOCK | `[pcn]` |

## Validation (kosh_test, isolated)
- End-to-end real ops via `db_manager`: stock 100 → pick 30 → restock 30 produced typed events
  `RECEIPT 100 / PICK 30 / PICK 30 / RESTOCK 30 / RESTOCK 30`, and `inv_onhand` = **100 bin / 0 floor ==
  warehouse (100, 0)**. On-hand updates the instant the op commits (no 60s lag).
- **Fail-safe proven:** an earlier enum mismatch made the shadow event violate a CHECK; the operation still
  returned success and on-hand self-corrected on the next op. A shadow error cannot break a user operation.
- Regression suite on the new code: **31/31 pass**. Both files compile.

## Off-peak deploy plan (zero-downtime, when approved)
1. `docker cp app.py inv_shadow.py stockandpick_webapp:/app/`
2. `docker kill --signal=HUP stockandpick_webapp` (graceful reload; no restart, no downtime)
3. Verify: thread starts, app 302, drive/observe a live op → typed event lands, reconcile 0-differ.
4. Bake the image (`docker compose build --no-cache web_app && … up -d`) at the SAME off-peak window so the
   change survives a container recreate. (Repo files already updated; not committed/pushed.)

## Rollback
Revert `app.py`/`inv_shadow.py` + HUP. The realtime events are `created_by=<username>`; the append-only
trigger means removal is via `DISABLE TRIGGER` + delete or full DROP of `inv_*`. Live tables/user paths were
never modified by this phase (hooks are additive + fail-safe).

**Waiting for the user's go-ahead to deploy at an off-peak time.**
