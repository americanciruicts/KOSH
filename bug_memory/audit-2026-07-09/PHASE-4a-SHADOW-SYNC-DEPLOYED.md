# PHASE 4a — SHADOW-SYNC DEPLOYED LIVE (no read cutover)

**Date:** 2026-07-09 · **Deployed to prod `stockandpick_webapp` at 17:16 UTC via zero-downtime graceful reload.**
Theresa was working throughout; **zero downtime, zero user-path change, zero interference.**

## What shipped
- **New module `inv_shadow.py`** — a background daemon that every 60s keeps the event-derived
  `inv_onhand` aligned to the authoritative warehouse by emitting typed `ADJUST` events into `inv_event`.
  One-time full pass on boot, then incremental (only PCNs with a new `tblTransaction` id since last pass).
- **3-line hook in `app.py`** (after the existing reconcile thread) that imports the module and starts the
  thread inside a `try/except`.

## Why it could not hurt Theresa (design)
- **No user write path changed** — `stock_pcb`/`pick_pcb`/`restock_pcb`/purge/`reverse_pick` are byte-for-byte
  identical. The sync is a separate thread on its own pooled connection.
- **Live tables read-only** (`ACCESS SHARE`, compatible with her INSERT/UPDATE) + `lock_timeout=3s` so it can
  never queue ahead of her. **Writes only to the new `inv_event` table.**
- **Fail-safe:** any pass error rolls back and logs; the app never sees it.
- **No read cutover:** every screen still serves from the old path. Nothing she sees changed.

## Deploy method (zero downtime)
`docker cp app.py inv_shadow.py → container`, then `docker kill --signal=HUP stockandpick_webapp`
(gunicorn has no `--preload`, so HUP boots a new worker with the new code and gracefully retires the old one;
the master's listening socket never closes). Verified: app served HTTP 302 in ~4ms across the reload.

## Validation
**Isolated `kosh_test` DB first (zero prod risk):**
- Full sync → **34,586/34,586 PCNs match, 0 differ.**
- Simulated live pick (bin→floor) → incremental pass wrote exactly 2 ADJUST (bin −20/floor +20), **0 differ.**
- Idempotent re-run → 0 new events. Regression suite in the test container → **31/31 pass.**

**Live prod after deploy:**
- First full pass: 30 ADJUST across 21 PCNs → **all 34,687 PCNs match warehouse, 0 differ.**
- A REAL live transaction landed (txn id 206091→206092); the incremental pass tracked it with 2 ADJUST,
  reconcile stayed **0 differ**. App healthy (302, ~5ms), no errors on any pass.

## Result
`inv_onhand` (the single event-derived projection) now tracks the live warehouse in real time. Once reads are
cut over (Phase 4b), Warehouse Inventory and PCN History will both read this one value → **they can never
disagree**, which is the structural end of the recurring "Warehouse ≠ PCN History" complaint.

## ⚠️ Two follow-ups
1. **Persist the image (off-peak):** the change is live via `docker cp` + reload but NOT baked into the image.
   A container *recreate* would revert to the old code (harmless — the shadow thread just stops; no data harm).
   Rebuild the image off-peak (`docker compose build --no-cache web_app && … up -d`) to bake it in. Repo files
   `app.py` + `inv_shadow.py` are already updated, so a rebuild will pick them up. (Not committed/pushed yet.)
2. **The 12 stale-double corrections** are currently mirrored back to warehouse's values (faithful mirror).
   To make those corrections real, apply them at the warehouse source (a small, audited, reversible update
   like bug 20) — pending your approval.

## Rollback
Revert `app.py` (remove the 3-line hook) + remove `inv_shadow.py`, `docker cp` + HUP → thread gone.
Optionally `DELETE FROM pcb_inventory.inv_event WHERE created_by='shadow_sync';`. Full teardown = the Phase 3
`DROP` statements. Live tables and user paths were never modified, so rollback is clean either way.

**STOP — Phase 4a done. Phase 4b (point Warehouse Inventory's READ path at `inv_onhand`) changes what
Theresa sees, so it needs separate explicit approval.**
