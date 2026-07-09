# PHASE 3 — BUILD ALONGSIDE + SHADOW RECONCILIATION (no cutover)

**Date:** 2026-07-09 · **Live tables: NEVER written.** All writes went to new `inv_`-prefixed objects only.
Live `tblWhse_Inventory` / `tblTransaction` were read with `ACCESS SHARE` (compatible with the app's
writes) under `lock_timeout=2s` + `statement_timeout=60–180s`, so nothing could block Theresa.
**Theresa was actively picking throughout** (PCNs 45717/45792/45798) — every one succeeded → proof of zero
interference.

## What was built (all reversible by DROP)
| Object | Kind | Rows |
|---|---|---|
| `inv_location` | table | 2,841 (2,829 BIN, 10 STAGING, 1 FLOOR, 1 EXTERNAL) |
| `inv_part` | table (canonical, case/sep-folded) | 29,174 |
| `inv_event` | append-only ledger | 229,990 (32,708 OPENING + 197,282 LEGACY) |
| `inv_location_balance`, `inv_onhand` | views (derived on-hand) | — |

- **OPENING** events (32,708) = 20,014 bin + 12,694 floor, anchored to **trusted current warehouse**
  (not replayed from dirty history). Total seeded on-hand = **20,274,700 units**.
- **LEGACY** events (197,282) archived at **qty 0** (from/to NULL) → **zero** on-hand impact; carry
  `legacy_txn_id`, parsed `occurred_at`, and a human-readable `note` for PCN-History display continuity.
  97 blank-item + 78 blank-pcn junk rows (catalog P6) were intentionally not archived.

## Reconciliation: new `inv_onhand` vs old warehouse (`onhandqty + mfg_qty`) per PCN
| Metric | Value |
|---|---|
| Total PCNs | 34,687 |
| **Exact match** | **34,672** |
| Differ | 15 |
| &nbsp;&nbsp;↳ **intended** stale-double corrections (per trace sheet) | **12** |
| &nbsp;&nbsp;↳ **live drift** (Theresa's picks after the seed instant) | **3** |
| &nbsp;&nbsp;↳ genuine seed errors | **0** ✅ |

### The 12 intended corrections (net −5,278 units, all documented in the trace sheet)
`25972 −3000` (⚠️ 2,810-unit call — confirm nothing physically on floor), 34300 −1110, 26133 −980,
44500 −340, 14196 −220, 43341 −100, 8229 −60, 44623 −50, 37846 −48, 45299 −10, 43344 −9, 36361 −1.
Row 46152's genuine 1-unit bin/floor split was **kept** (matches). Negative-`mfg_qty` (85 rows) seeded as
floor 0 → produced **no** PCN-level difference.

### The 3 live-drift PCNs (NOT errors)
45717, 45792, 45798 — all 8847L parts with a live transaction timestamped **at/after** the seed instant
(16:45:46 UTC). The new model froze the seed-instant value; the live warehouse moved when Theresa picked.
**This is the exact behaviour the shadow period exists to close:** until the app dual-writes each live
action into `inv_event`, the snapshot drifts. That is a cutover-prerequisite, not a data problem.

## What this proves
1. **On-hand can be a single derived projection** and it matches the trusted warehouse to the unit
   (34,672/34,687 exact; the 15 exceptions are fully explained).
2. **The floor is now first-class** — 4.74M floor units live as real OPENING events at `MFG Floor`, so
   `inv_onhand.floor_qty` is ledger-derived, not a snapshot column.
3. **Dirty history cannot leak in** — 197,282 legacy rows contribute 0; the relabel/over-pick/phantom
   patterns from Phase 0 have no effect on the new on-hand.

## NOT done (correctly deferred — needs your approval + a code deploy)
- **Dual-write**: wiring `stock/pick/restock/purge` to also append `inv_event`. Requires an app code
  change + Docker rebuild → explicit approval (Phase 4 prep).
- **Go-forward invariants** `REVOKE UPDATE/DELETE` on `inv_event` and the no-negative-balance trigger:
  deferred so they don't slow the bulk seed; added at cutover.
- **No read cutover** — the app still serves 100% from the old path. Warehouse Inventory / PCN History are
  unchanged for users.

## Rollback (removes everything Phase 3 built; live data untouched either way)
```sql
DROP VIEW  pcb_inventory.inv_onhand, pcb_inventory.inv_location_balance;
DROP TABLE pcb_inventory.inv_event, pcb_inventory.inv_part, pcb_inventory.inv_location CASCADE;
```

**STOP — Phase 3 complete. Awaiting your go-ahead before Phase 4 (dual-write + per-screen cutover).**
Also please confirm the **25972** ruling (drop 2,810 stale floor units, keep 190 in bin) — the only
material judgment call in the seed.
