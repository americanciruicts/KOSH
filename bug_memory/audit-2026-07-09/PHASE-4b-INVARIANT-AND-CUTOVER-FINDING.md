# PHASE 4b — DB-ENFORCED INVARIANT + read-cutover finding

**Date:** 2026-07-09 · Prod changes touched only the NEW `inv_event` table; live tables + user paths untouched.

## Delivered: append-only invariant on `inv_event` (prod, explicitly approved)
Trigger `inv_event_no_mutate` (`BEFORE UPDATE OR DELETE`) raises, so the ledger is **structurally immutable** —
corrections must be new reversing events, never in-place edits. This is design invariant **I1**, now enforced
by the database rather than convention.
- Proven on `kosh_test` first: ✅ INSERT allowed · ❌ UPDATE blocked · ❌ DELETE blocked.
- Prod verified: UPDATE and DELETE both rejected; the shadow-sync (INSERT-only) is unaffected and still
  reconciles **0 differ**; app healthy throughout.
- Controlled maintenance path exists: `ALTER TABLE … DISABLE TRIGGER inv_event_no_mutate` (for a deliberate,
  audited correction), then re-enable. Rollback: `DROP TRIGGER inv_event_no_mutate`.

## Key finding: Warehouse Inventory read-cutover is the WRONG target
Reading the actual code changed the plan:
- **Warehouse Inventory is row-granular** (per `tblWhse_Inventory.id`) and reads `onhandqty`/`mfg_qty`
  **synchronously — always fresh**. `inv_onhand` is PCN-granular and lags ≤60s behind the shadow.
- The two screens **already agree today** (both anchor to warehouse). Flipping only Warehouse Inventory (or
  only PCN History) to the *lagged* projection would **re-introduce** "Warehouse ≠ PCN History" during the
  lag window — the exact bug we are eliminating — with no offsetting benefit and a staleness risk to Theresa.

**Conclusion:** a read-cutover is only safe/valuable once on-hand is **truly event-derived with no lag**, so
BOTH screens can switch together and stay consistent. That requires real-time events at operation time.

## Approved next step: real-time write-path events
Add fail-safe event writes to `pick_pcb`/`restock_pcb`/`stock_pcb`/purge/`reverse_pick` (emit the typed
`inv_event` at the moment of the operation, inside a SAVEPOINT so a shadow-write error can never break the
real op). Validate on `kosh_test`, deploy zero-downtime. Then on-hand is event-derived with zero staleness and
BOTH screens can be cut over together — the durable structural end of the recurring complaint. The 60s
background shadow-sync stays as a self-healing backstop + divergence monitor.

## State after Phase 4b
- New model live alongside old: `inv_part`/`inv_location`/`inv_event`(append-only)/`inv_onhand`.
- Shadow-sync tracking the live warehouse (reconcile 0 differ), deployed zero-downtime.
- App still serves 100% from the old read path — **users see exactly what they saw before.**
- Pending (each needs explicit approval): real-time write-path events → dual-screen read cutover;
  applying the 12 stale-double warehouse corrections; baking the code into the image (off-peak).
