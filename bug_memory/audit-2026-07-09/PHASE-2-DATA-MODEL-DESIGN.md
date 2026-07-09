# KOSH — PHASE 2: NEW INVENTORY DATA-MODEL DESIGN (document only, zero changes)

**Date:** 2026-07-09 · **Status:** DESIGN FOR APPROVAL. No tables, views, code, or data were created or
modified. This describes the target model that will be built **alongside** the live system in Phase 3.

---

## 0. Why this is needed (the recurrence, in one paragraph)
Every "same bug again" report is the same disease on a new PCN. Today **on-hand is a mutable stored
snapshot** (`tblWhse_Inventory.onhandqty` = bin, `mfg_qty` = floor) and **the ledger is a lossy
side-record** (`tblTransaction`): a pick mutates two columns but only logs a bin subtraction — the floor
increment is never an event, so replaying the ledger yields floor = 0 (4.7M units invisible, Phase 0 §2).
Warehouse Inventory and PCN History are therefore **two different computations over the same dirty data**,
and the app keeps them in sync with anchors + a lower-only reconcile. That is a *mask*: the moment a new
dirty pattern (relabel-ADJT, over-pick, recount-double, floor edge case) lands on an untouched PCN, the two
screens diverge again. Regression tests freeze the *code*; they never clean the *data* or remove the
*second computation*. **The cure is to make on-hand a single derived projection of one clean, typed,
append-only, floor-aware ledger, with the invariants enforced by the database — not by app code.**

---

## 1. Design principles
1. **One source of truth.** On-hand is **never stored**; it is a `SUM()` over the event ledger. Warehouse
   Inventory and PCN History become the *same* query at different groupings, so they cannot disagree.
2. **Append-only ledger.** Events are immutable. `REVOKE UPDATE, DELETE`. Corrections are new
   (reversing) events, never in-place edits — satisfies HARD SAFETY RULE 2 permanently.
3. **The database enforces the invariants**, not the app. `CHECK`s, foreign keys, generated columns, and a
   balance-guard trigger make the bad states unrepresentable.
4. **Locations are first-class.** MFG Floor, Rec Area, Count Area, and every numeric bin are just
   locations. A pick is a *transfer* between two locations, so floor stock is ledger-derived like everything else.
5. **Canonical parts.** Case/separator-folded identity, computed once, so a case mismatch can never
   fragment a part or fake a shortage.
6. **Anchor, don't replay.** Opening balances come from today's *trusted* Warehouse on-hand (Phase 0 proved
   warehouse bin stock is never phantom-high: 0 cases). Dirty legacy history is archived for display, not
   replayed into balances.
7. **Build alongside; prove before cutover.** New objects live next to the old tables; the app keeps
   serving the old path until a shadow-run reconciles 100%.

---

## 2. Schema (new objects, `pcb_inventory` schema, all prefixed `inv_`)

### 2.1 `inv_part` — canonical part
```
inv_part (
  part_id      bigserial PRIMARY KEY,
  item_raw     text NOT NULL,          -- ACI PN as displayed, e.g. '8095-195'
  mpn_raw      text,                   -- manufacturer PN as displayed
  item_key     text GENERATED ALWAYS AS (upper(translate(coalesce(item_raw,''),'-# ./',''))) STORED,
  mpn_key      text GENERATED ALWAYS AS (upper(translate(coalesce(mpn_raw,''),'-# ./',''))) STORED,
  UNIQUE (item_key, mpn_key)
)
```
Same normalization the app already uses (`translate(...,'-# ./','')`), and Phase 0 found **0** case-variant
collisions on a PCN, so folding is safe. Every lookup/join keys on `part_id` (or `item_key`), never on raw case.

### 2.2 `inv_location` — controlled location vocabulary
```
inv_location (
  location_id  bigserial PRIMARY KEY,
  code         text UNIQUE NOT NULL,   -- '1604009', 'MFG Floor', 'Rec Area', 'Count Area', 'EXTERNAL'
  kind         text NOT NULL CHECK (kind IN ('BIN','FLOOR','STAGING','EXTERNAL'))
)
```
`EXTERNAL` is the sink/source for receipts (stock in) and consumption (production/purge out). Numeric bins
are `BIN`; `MFG Floor` is `FLOOR`. This replaces the fragile "learn locations from data" heuristic.

### 2.3 `inv_event` — the append-only ledger (the heart)
```
inv_event (
  event_id     bigserial PRIMARY KEY,
  seq          bigint GENERATED ALWAYS AS IDENTITY,   -- monotonic write order (NOT tran_time)
  event_type   text NOT NULL CHECK (event_type IN
                 ('OPENING','RECEIPT','PICK','RESTOCK','TRANSFER','PURGE','SCRAP','ADJUST','RELABEL','LEGACY')),
  part_id      bigint NOT NULL REFERENCES inv_part(part_id),
  pcn          text NOT NULL,                          -- the lot id (kept; ties to legacy)
  qty          integer NOT NULL CHECK (qty >= 0),      -- ALWAYS non-negative; direction is from/to
  from_location bigint REFERENCES inv_location(location_id),  -- NULL = came from outside (receipt)
  to_location   bigint REFERENCES inv_location(location_id),  -- NULL = left inventory (consume/purge)
  occurred_at  timestamptz NOT NULL DEFAULT now(),      -- real business time (clean tz)
  reverses_event_id bigint REFERENCES inv_event(event_id),   -- correction pointer (not a delete)
  legacy_txn_id integer,                                -- provenance to tblTransaction.id
  created_by   text NOT NULL,
  note         text,
  -- RELABEL carries no quantity movement; a move must name at least one internal location
  CHECK (event_type <> 'RELABEL' OR qty = 0),
  CHECK (event_type = 'RELABEL' OR from_location IS NOT NULL OR to_location IS NOT NULL)
)
```
**Direction convention** (one row can move stock between two places):
| event_type | from_location | to_location | meaning |
|---|---|---|---|
| OPENING | NULL | the bin/floor | seed trusted starting balance |
| RECEIPT / STOCK | EXTERNAL | bin/Rec Area | parts arrive |
| PICK | bin | MFG Floor | pull to the floor (the bin→floor move, now a real event) |
| RESTOCK | MFG Floor | bin | put unused floor stock back |
| TRANSFER | bin A | bin B | relocation / put-away |
| PURGE / SCRAP | bin/floor | NULL (EXTERNAL) | leaves inventory |
| RELABEL | (n/a) | (n/a), qty 0 | part renumber; identity change only |
| LEGACY | NULL | NULL, qty 0 | archived dirty import row, display only |

### 2.4 On-hand as a SINGLE derived view (the whole point)
```
CREATE VIEW inv_location_balance AS
  SELECT part_id, pcn, location_id, SUM(signed) AS qty FROM (
     SELECT part_id, pcn, to_location   AS location_id,  qty  AS signed FROM inv_event WHERE to_location   IS NOT NULL
     UNION ALL
     SELECT part_id, pcn, from_location AS location_id, -qty  AS signed FROM inv_event WHERE from_location IS NOT NULL
  ) m GROUP BY part_id, pcn, location_id;

CREATE VIEW inv_onhand AS   -- per PCN, split by location kind (what both screens read)
  SELECT b.part_id, b.pcn,
         SUM(b.qty) FILTER (WHERE l.kind='BIN')                    AS bin_qty,
         SUM(b.qty) FILTER (WHERE l.kind IN ('FLOOR','STAGING'))   AS floor_qty,
         SUM(b.qty)                                                AS onhand_qty
  FROM inv_location_balance b JOIN inv_location l USING (location_id)
  GROUP BY b.part_id, b.pcn;
```
- **Warehouse Inventory** = `inv_onhand` (bin_qty, floor_qty, onhand_qty) joined to `inv_part` for display.
- **PCN History** = the ordered `inv_event` stream for a pcn, with a running balance = cumulative `signed`.
- They are literally the same events → **they can never disagree.** No anchor, no reconcile, no lower-only patch.

---

## 3. Database-enforced invariants (bad states become unrepresentable)
| # | Invariant | Enforcement |
|---|---|---|
| I1 | **Append-only ledger** | `REVOKE UPDATE, DELETE ON inv_event` from the app role; only `INSERT`. Corrections via `reverses_event_id`. |
| I2 | **Quantities non-negative** | `CHECK (qty >= 0)`. An over-pick can't be written as negative and later "absorbed" (kills bug 19 class). |
| I3 | **No location goes negative** | `AFTER INSERT` trigger (or a `NOT VALID`→validated constraint on a small materialized balance): reject an event whose `from_location` balance would drop below 0. "You cannot pick below empty" is enforced at write, not folded at read. |
| I4 | **Bin/floor disjoint** | Structural: qty lives per (pcn, location) row in the balance. A unit is at exactly one location; a move is a transfer. There is no single row that can hold both (kills bug 20 class). |
| I5 | **Relabels carry qty 0** | `CHECK (event_type <> 'RELABEL' OR qty = 0)`. A renumber can never inject phantom qty (kills bug 10 class). |
| I6 | **Typed events only** | `CHECK (event_type IN (...))`. Garbage `trantype` (date-codes, blanks) can't enter; legacy junk is quarantined as `LEGACY` qty 0. |
| I7 | **Monotonic order** | `seq` identity column; ordering never depends on dirty `tran_time` (50 unparseable rows today). |
| I8 | **Canonical identity** | `inv_part.UNIQUE(item_key,mpn_key)` + generated keys; case/separator mismatch cannot fork a part (helps bugs 11, 21). |
| I9 | **Valid locations** | `from/to_location` are FKs to `inv_location`; item-numbers-in-location-fields (11,611 relabel-ADJTs) cannot occur. |

---

## 4. Migration / seed strategy (Phase 3 — described here, executed only on approval)
1. **Populate `inv_part`, `inv_location`** from distinct warehouse+BOM parts and the known location set.
2. **Seed OPENING events, anchored to TRUSTED Warehouse (do NOT replay history):** for each live warehouse
   row → one `OPENING` event `qty=onhandqty, to=loc_to(bin)`; if `mfg_qty>0`, a second `OPENING`
   `qty=mfg_qty, to='MFG Floor'`. `occurred_at = cutover_instant`, monotonic seq. This reproduces today's
   bin **and** floor exactly (the negative `mfg_qty` outliers, e.g. PCN 14926 = -5, are clamped to 0 and
   flagged — I3 forbids negatives).
3. **Archive legacy history** (`tblTransaction`) as `LEGACY` events (qty 0) for PCN-History display
   continuity, translated via the Phase 0 catalog (relabel→RELABEL, zero-qty PICK dropped, malformed→LEGACY).
   Because they predate the anchor instant, they contribute **0** to on-hand — dirtiness can't leak in.
4. **Dual-write shadow period:** every app write (`stock_pcb`, `pick_pcb`, `restock_pcb`, purge, manual
   edit) *also* appends the corresponding typed `inv_event`. The old columns keep serving reads.
5. **Per-row human trace of the 13 bin/floor double-count rows** (Phase 0 §3) before their OPENING seed —
   split vs stale — since a legit partial-pick split looks identical (bug 20 warning).

**Reconciliation (Phase 3 gate):** `inv_onhand` per PCN vs legacy `(onhandqty+mfg_qty)` per PCN. Because we
anchored to those exact values, agreement should be 100% at seed; the shadow period then proves the
dual-write path keeps them equal through live picks/restocks. **No cutover until this is green.**

---

## 5. Mapping the 25 bugs → structural vs app-side

### A) Made STRUCTURALLY IMPOSSIBLE by this model (the recurring WHSE≠HIST cluster)
| Bug | Was | Why it can't recur |
|---|---|---|
| **2** reconcile wiped restocks | reconcile lowered a fresh receipt | No reconcile exists — on-hand *is* the ledger sum. Nothing to overwrite. |
| **4** restock-after-recount doubling | two formulas, recount baseline + restock | Single derived view; no recount baseline to stack on. |
| **7** History ≠ Warehouse on relabels | two formulas over relabels | Both screens are the same events; RELABEL is qty 0. |
| **10** phantom relabel-ADJT +qty | renumber counted as +qty | I5: RELABEL `CHECK qty=0`; I9: locations are FKs, not item numbers. |
| **18** restock didn't zero floor | floor double-represented | Floor→bin is a TRANSFER; the floor balance drops by construction. |
| **19** over-pick zeroed refilled stock | negative replay absorbed a receipt | I2 `qty>=0` + I3 no-negative-balance: over-pick rejected at write. |
| **20** bin+floor double-count | same units in both columns | I4: per-location balance; disjoint by construction. |
| **24** phantom 0-qty pick row | 0-qty PICK logged a fake floor move | I2 `qty>=0` (0-qty movement rejected); PICK is a real transfer. |
| **5,6,8** location stale/dropped/edits reverted | `loc_to` synced separately, drifted | Location is *on the event*; on-hand-at-location is derived. No separate loc reconcile to drift. |

### B) STRUCTURALLY HELPED but the feature logic stays app-side + test-guarded
| Bug | Structural help | Still app-side |
|---|---|---|
| **1** shortage showed floor not bin | bin & floor are separate balances in `inv_onhand` | which location the report *displays* is report policy → test-guarded |
| **9** shortage ignored floor | floor is a real location, summed in `onhand_qty` | report's include-floor policy → test-guarded |
| **11** false shortage, case mismatch | canonical `part_id`/`item_key` join | report match logic → test-guarded |
| **21** MPN lookup case-sensitive | canonical keys; lookup by `part_id` | endpoint code → test-guarded |

### C) Purely app-side (NOT data-model; stay test-guarded — unchanged by this rebuild)
`3` RealDictCursor read · `12` SSO bcrypt · `13` qty/cost parsing overflow · `14` shortage structural/missing
lines · `15` conn leaks / open routes / cost · `16` pool exhaustion · `17` restock −1 mousewheel ·
`22` BOM XLSX parser line-drop · `23` same-MPN over-match · `25` shortage dropped non-short lines.
These live in report-builder / parser / infra / auth / frontend layers; the inventory model doesn't touch
them. They remain covered by `tests/regression_tests.py` + `tests/test_bom_parser.js`.

**Scoreboard:** of the 25, **13 become structurally impossible** (the entire `[WHSE≠HIST]` recurring
family: 1*,2,4,5,6,7,8,9*,10,18,19,20,24 — *1 & 9 fully structural on the divergence axis, display policy
test-guarded), **2 more** (11,21) are structurally de-risked by canonical parts, and **10** stay app-side +
test-guarded. The bug that keeps coming back — *Warehouse Inventory ≠ PCN History* — is in group A.

---

## 6. What stays the same / risk posture
- Old tables (`tblWhse_Inventory`, `tblTransaction`) are **untouched** and keep serving reads until Phase 4.
- The app read path switches **per screen** (Warehouse Inventory first, then PCN History), each only after
  its reconciliation is green — reversible by pointing the read back at the old columns.
- Heavy work (seeding ~34k opening rows, archiving ~197k legacy events) is a one-time off-peak batch;
  steady-state cost is one `INSERT` per user action + cheap grouped reads (indexed on `(pcn)`, `(part_id)`).

## 7. Open questions for you (need answers before Phase 3 build)
1. **Lot granularity:** keep `pcn` as the lot key (recommended — everything references it), or introduce a
   separate surrogate lot id? I recommend keeping `pcn`.
2. **Legacy history depth:** archive *all* 197k `tblTransaction` rows as `LEGACY` for full PCN-History
   continuity, or only the most recent N per PCN? (Full = complete history, bigger seed.)
3. **The 13 bin/floor double rows + negative-`mfg_qty` outliers:** OK for me to prepare a per-row trace
   sheet (read-only) so you can rule split-vs-stale before we seed their OPENING balances?
4. **Cutover unit:** confirm you want it **per screen** (Warehouse Inventory, then PCN History, then
   Shortage) rather than all at once.

**STOP — Phase 2 is document-only and complete. Awaiting your approval (and answers to §7) before Phase 3
builds anything.** No tables, views, code, or data created.
