# KOSH — Data Model & Invariants (clean rebuild)

This is the design that makes the entire KOSH bug history **impossible by construction**.

## The one idea

KOSH's old bugs almost all trace to **one flaw**: "how much do we have" was computed **two
different ways** — a stored snapshot (`tblWhse_Inventory.onhandqty` + `mfg_qty`) *and* a
replayed ledger (PCN History). Two computations over the same dirty data drift apart. Every
"Warehouse Inventory ≠ PCN History" complaint, the phantom stock, the double-counts, the
restock-that-adds-to-a-non-empty-bin — all of it is that drift.

**The rebuild has exactly one source of truth: an append-only ledger.**
Everything else — Warehouse Inventory, PCN History, on-hand, valuation — is *derived from
that one ledger*. Two screens that read the same ledger can never disagree.

## Core tables

| Table | What it is | Truth? |
|---|---|---|
| `part` | a part number (ACI PN + MPN, case-insensitive) | master data |
| `pcn` | one physical lot/label of a part (the barcode) | master data |
| `location` | a place stock can sit — a numeric **bin**, or a named place (`MFG Floor`, `Receiving Area`, `Count Area`, `Stock Room`) | master data |
| **`inventory_txn`** | **append-only ledger** — every movement of stock | ✅ **the single source of truth** |
| `inventory_balance` | current qty per `(pcn, location)` — a cache kept in the **same DB transaction** as every ledger write | derived (never independent) |

### There is no `onhandqty` + `mfg_qty` pair

This is the key change. "On the MFG Floor" is **just another location** (`kind='FLOOR'`).
Stock is always *somewhere*, and only in **one** place. A part's on-hand is:

```
total_on_hand(pcn) = SUM(qty) over all locations for that pcn
```

There is **one** on-hand number. The bin/floor split is still visible (it's the per-location
breakdown), but it is a *view of one number*, never two numbers that can disagree.

## Movements (every ledger row is a movement)

Each `inventory_txn` moves `qty` units **from** one location **to** another. Applying it
adjusts two balances in the *same* transaction:

```
if from_location: balance[pcn, from] -= qty     (must have >= qty, else REJECTED)
if to_location:   balance[pcn, to]   += qty
```

| txn_type | from → to | effect |
|---|---|---|
| `STOCK` | (external) → bin | receive into a bin |
| `PICK` | bin → MFG Floor | **transfer** — bin goes down, floor goes up, total unchanged |
| `RESTOCK` | MFG Floor → bin | transfer back |
| `SHIP` / `PURGE` | floor/bin → (external) | consume / remove |
| `TRANSFER` | bin → bin | relocate |
| `ADJUST` | (external)→loc or loc→(external) | manual signed correction at **one** location |

Because a PICK is a *transfer that decrements the bin*, the impossible state
`bin 3000 + floor 3000` **cannot be written**. Restock always lands on a bin that the pick
already emptied, so "190 comes back as 190, not 3190" is automatic.

## The invariants (and the KOSH bug each one kills)

| # | Invariant | Enforced by | Kills KOSH bug |
|---|---|---|---|
| **I1** | on-hand at any `(pcn, location)` is **never negative** | `CHECK (qty >= 0)` on `inventory_balance` **+** service checks availability before writing | **#19** over-pick zeroing; can't pick below empty |
| **I2** | a unit is in **exactly one** location; bin & floor are disjoint; total is conserved by every transfer | data model — floor is a location, PICK/RESTOCK are transfers | **#20** & the "Total On Hand" patch (e1d4a69) double-count |
| **I3** | Warehouse Inventory (balances) and PCN History (ledger replay) are the **same number** | both derive from `inventory_txn`; balance cache written in the same txn as the ledger row | the whole **"Warehouse ≠ PCN History"** class (#2,4,7,8,10,24) |
| **I4** | part / MPN matching is **case-insensitive** everywhere | `CITEXT` columns (`part.aci_pn`, `part.mpn`, `pcn.mpn`, `app_user.username`) | **#11, #21** case-mismatch lookups |
| **I5** | corrections **never delete** history | reversals write an *inverse* txn + set `reversed=TRUE`; queries filter `reversed=false` | #24 phantom rows, audit integrity |
| **I6** | quantities are typed integers, validated `> 0` | `INTEGER CHECK (qty > 0)` + Pydantic validation | **#13** qty/cost parse overflow/crash |
| **I7** | a manual warehouse edit cannot fill "both places" | an edit is an `ADJUST` scoped to **one** location; there is no two-number row to desync | the manual-edit path that created bug #20 doubles |
| **I8** | relabels/renumbers are **quantity-neutral** | a relabel is metadata (`part`/`pcn` change), it is **not** a `+qty` ledger row | **#10** the ~15.3M phantom units from relabel-ADJTs |

## Why there is no 5-minute "reconcile" cleaner anymore

KOSH ran three background reconcilers every 5 minutes to *repair* drift after the fact — and
the drift kept coming back because the underlying two-number model kept generating it (the
cleaner even skipped rows whose location wasn't literally "MFG Floor", so phantoms survived).

In the clean model **there is nothing to reconcile**: the balance cache is written inside the
same database transaction as the ledger row, so it can never be out of step with the ledger.
No nightly repair, no "lower-only" heuristics, no pendulum of fixes.

## Migration from the old dirty data (Phase 1.5)

A one-time importer reads the legacy `kosh` DB and, per `(pcn, mpn)`:
1. drops relabel-`ADJT` rows (item numbers in the location fields) — they were never stock (I8),
2. rebuilds a clean ledger with a **running floor at 0** (an over-pick can't drive on-hand
   negative — the dip is absorbed, later receipts rebuild from 0), and
3. collapses any `onhand+mfg` double into a single per-location balance (I2).

Real inventory is preserved; only the corruption is dropped. This is a separate, reviewable
script — production data is never touched by the app's normal write path.
