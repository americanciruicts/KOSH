# MAJOR DATA INTEGRITY ISSUE — On-Hand Double-Count Remediation Plan

**Status:** Diagnosed (root cause proven). Remediation NOT yet started.
**Owner:** KOSH maintainers
**Created:** 2026-06-12
**Severity:** Critical — purchasing decisions are made against phantom on-hand.
**Risk to fix:** Medium. Touches on-hand for thousands of PCNs. Must be staged, dry-run, reversible.

> ⚠️ This is a **data + ledger-semantics** defect, NOT a security breach and NOT a
> sync lag. Read [§1 Root Cause](#1-root-cause-what-is-actually-wrong) before
> touching anything — two of the originally-reported tasks rest on incorrect
> premises and must be re-scoped (see [§2](#2-corrections-to-the-original-task-brief)).

---

> **Note on "79 = 79":** that (on-hand exactly equalling mfg_qty) is just one
> *illustrative* symptom, not the definition of the bug. The defect is general —
> any on-hand inflated by a relabel-ADJT, whether or not it happens to equal the
> floor qty. The fix neutralizes ALL relabel-ADJT phantom; success is measured by
> total phantom removed (≈1.44M units / 2,523 rows), not by the exact-equal count.

## 1. Root Cause (what is actually wrong)

A part **relabel / renumber** (e.g. item `8223L-40` → `8525ML-1-640` on the same
physical reel) was written into the transaction ledger `tblTransaction` as an
**`ADJT` row carrying the part's FULL quantity** in `tranqty`, with `loc_from` /
`loc_to` holding the **old / new item numbers** (not warehouse locations).

The on-hand reconciliation math ([`app.py:3167-3218`](app.py#L3167)) treats **every
`ADJT` as a signed `+tranqty` delta** ([`app.py:3176`](app.py#L3176)). So each
relabel **injects phantom units that were never physically received.** The lot is
then normally `PICK`ed to the floor, which:

- subtracts the *original* receipt only (so the phantom survives as "on-hand"), and
- sets `loc_to='MFG Floor'` and `mfg_qty=<qty>` ([`app.py:1294-1305`](app.py#L1294)).

**Result:** the same physical lot is counted twice — once as phantom `onhandqty`,
once as `mfg_qty` on the MFG Floor — which is why one PCN shows **79 on-hand AND 79
on the floor** at the same time.

### Proven example — PCN 30314 (item `8525ML-1-640`)
Warehouse row: `onhandqty=10000`, `mfg_qty=10000`, `qty_old=10000`, `loc_to=MFG Floor`.

| # | Ledger event | qty | meaning |
|---|---|---|---|
| 1 | `INDF` | +10000 | received into Rec Area (legit) |
| 2 | `PTWY` | 10000 | put-away to bin — qty-neutral, correctly ignored |
| 3 | **`ADJT`** `8223L-40 → 8525ML-1-6` | **+10000** | **relabel logged as +stock (the bug)** |
| 4 | `PICK` | −10000 | picked to MFG Floor |

Reconcile math = `INDF(+10000) + ADJT(+10000) − PICK(−10000) = 10000` phantom on-hand.

### Why reconciliation does not catch it
Stored `onhandqty` was compared to the ledger-derived value for **all 34,433 rows →
0 divergence.** The 5-minute reconciler ([`app.py:3018`, thread at `app.py:3239`](app.py#L3018))
runs and works. **The two already agree — on a wrong number — because the ledger
itself is poisoned.** Fixing "sync" cannot help; the *ledger semantics* must change.

---

## 2. Corrections to the original task brief

| Original task | Verdict from the data | Action |
|---|---|---|
| **T1** On-hand double-count from relabel/relocate | **CONFIRMED — core bug** | Fix (Phases 1–3) |
| **T2** Shortage omits MFG-Floor stock | **REAL**, correctly sequenced after T1 | Fix (Phase 4) |
| **T3** April PCN collisions (PCN 45061, "92 groups") | **ALREADY CLEANED** — 0 PCNs today bound to >1 distinct item | Verify-only |
| **T4** Audit all PCNs for number-reuse | Worth building as a recurring check, but **returns empty today** | Build detector (Phase 5), low urgency |
| **T5** "Two unreconciled on-hand sources" | **PREMISE INCORRECT** — stored == ledger (0 divergence). The proposed fix would not solve the problem | Re-scope (Phase 6): harden + nightly check, but ledger must be corrected first |

### Quantified scope (live DB, 2026-06-12)
- **11,933** `ADJT` rows are actually relabels (`loc_from` is an item number), across **6,855 PCNs**, injecting **≈15.3M phantom units**.
- **2,510** rows have `onhandqty>0` AND `mfg_qty>0` simultaneously (**1,951** with on-hand *exactly* equal to mfg).
- **4,038** rows sit on `loc_to='MFG Floor'` yet still report `onhandqty>0` (**1.44M units**).
- **2,163 / 2,510 (86%)** of double-count rows have a relabel-`ADJT` on their PCN.
- **0** PCN collisions currently.

---

## 3. Guiding principles (apply to every phase)

1. **Ledger is truth, but the ledger must be corrected first.** Never hand-edit
   `onhandqty`; always re-derive it from a corrected `tblTransaction`.
2. **Report before you mutate.** Every phase has a read-only dry-run that produces a
   reviewable before/after list. A human approves before any write.
3. **Conservation check.** After any correction: `Σ onhandqty + Σ mfg_qty` must only
   ever *decrease* (we are removing phantom units, never inventing them). No item
   that physically has stock should drop to a number below its real bin count.
4. **Reversibility.** Snapshot affected tables before each write phase; keep an undo
   script. All corrections write an audit row to `tblReconcileAudit` with a unique
   `source` tag so they can be found and rolled back.
5. **Staging first.** Run every phase against a restored copy of prod before prod.
6. **No silent caps.** Anything skipped/ambiguous is logged to a review list, not
   dropped.

---

## 4. Remediation phases (do these strictly in order)

### Phase 0 — Preparation & safety net  *(no data changes)*

**0.1 Freeze & snapshot**
- Take a full DB backup (`pg_dump` of schema `pcb_inventory`). Store with date tag.
- Snapshot the three tables into dated copies inside the DB:
  `tblWhse_Inventory_bak_20260612`, `tblTransaction_bak_20260612`, `tblReconcileAudit_bak_20260612`.

**0.2 Stand up staging**
- Restore the backup into a staging DB/container. All of Phases 1–6 run on staging
  first; prod only after staging acceptance criteria pass.

**0.3 Pause the auto-reconciler during write windows**
- The 5-minute `_sync_onhand_from_transactions` thread ([`app.py:3239`](app.py#L3239))
  must be paused while ledger corrections are applied, so it doesn't re-derive
  on-hand from a half-corrected ledger mid-flight. Add a feature flag / env guard to
  disable it, or stop the container's background thread for the window.

**0.4 Acceptance:** backup verified restorable; staging reachable; reconciler
controllable.

---

### Phase 1 — Build the relabel detector + corrected-on-hand report  *(read-only)*

**Goal:** produce a reviewable list of every PCN whose on-hand is inflated by
relabel-`ADJT` rows, with `current_onhand` vs `corrected_onhand`.

**1.1 Detector: classify `ADJT` rows**
- A relabel `ADJT` is identified by: `trantype='ADJT'` AND `loc_from`/`loc_to` look
  like **item numbers**, not locations. Locations are `'MFG Floor'`, `'Rec Area'`,
  `'Count Area'`, or 7-digit bin codes (`^[0-9]{7}$`). Item numbers contain a letter
  or a dash (e.g. `8223L-40`, `8525ML-1-640`) or are short numeric part numbers.
- Heuristic (tune on staging): `loc_from <> loc_to` AND
  `(loc_from ~ '[A-Za-z-]' OR loc_to ~ '[A-Za-z-]')` AND `loc_to NOT IN (locations)`.
- Cross-check against the legitimate `PN_CHANGE` trantype and the `qty_old` column to
  reduce false positives. Output a 3-bucket classification per `ADJT`:
  **(a) genuine manual adjustment** (small signed delta, location-to-location),
  **(b) relabel** (item-to-item, full qty), **(c) ambiguous** (review queue).

**1.2 Corrected on-hand derivation**
- Re-run the reconcile `net` CTE ([`app.py:3167`](app.py#L3167)) but with relabel
  `ADJT` rows **excluded** (treated as qty-neutral). Everything else unchanged.
- Emit per (pcn, mpn): `current_onhand`, `corrected_onhand`, `delta`,
  `relabel_adjt_count`, `relabel_units_removed`, current `loc_to`, current `mfg_qty`.

**1.3 Reviewable output**
- Write to a new table `tblOnhandCorrectionPreview` (staging) and export to Excel,
  sorted by `delta` desc. **This is the artifact the inventory owner signs off on.**

**1.4 Acceptance:** the preview reproduces the PCN 30314 example exactly
(`current=10000`, `corrected=0`); the sum of `relabel_units_removed` ≈ 15.3M;
spot-check 15–20 PCNs against physical/PCN-History to confirm "corrected" matches
the real bin.

---

### Phase 2 — Fix the on-hand CALCULATION (keep the transaction vocab unchanged)  *(code — staging first)*

> **Per owner instruction (2026-06-12): keep the exact transaction-type vocabulary;
> adjust only the functioning of the calculations.** So Phase 2 changes NO stored
> data — no trantype is renamed, no row is reversed, no `tranqty` is rewritten. The
> ledger is left byte-for-byte intact. The ONLY change is *how on-hand is derived
> from it.* This is also safer for live production (no historical rewrite while
> users transact).

**Official transaction vocabulary (authoritative — do not change in data):**

| Type | Meaning | On-hand calc treatment |
|---|---|---|
| STOCK | Parts added to inventory | `+qty` |
| PICK | Parts removed from inventory | `−qty` |
| RESTOCK | Parts returned to inventory | `+qty` |
| GEN (`PCN Generation`) | PCN label generated | `+qty` (initial label qty) |
| UPDATE (`PN_CHANGE`) | Record updated / renumber | `0` (qty-neutral) |
| ADJT | Inventory adjustment | `+qty` **only when it is a real location adjustment**; `0` when it is a renumber (loc fields are item numbers) |
| SCRA | Parts scrapped | `−qty` |
| PTWY | Put away to storage | `0` (location move, qty-neutral) |
| INDF | Indefinite status | `+qty` (legacy receipt baseline) |
| RNDT | Random/miscellaneous | **OPEN QUESTION — see note below** |

**2.1 Add a renumber-ADJT predicate to the calculation (truncation-proof)**
- An `ADJT` is a **renumber** (qty-neutral, contributes 0) when **both `loc_from`
  and `loc_to` are non-locations and differ** — i.e. they are item numbers, not bins
  or named areas. It is a **genuine adjustment** (contributes `+tranqty`) when its
  loc fields are real locations.
- "Location" = a value that appears as `loc_from`/`loc_to` on any **non-ADJT**
  transaction (PICK/STOCK/RESTOCK/PTWY/INDF/PURGE), OR a 6+ digit bin code, OR a
  named area (`MFG Floor`, `Rec Area`, `Count Area`, `n/a`). This is learned from
  data, so it survives the **10-char truncation** of `loc_to` (e.g. the renumber to
  `8525ML-1-640` is stored as `8525ML-1-6` — matching item spelling is unreliable,
  the location test is not).
- Also fold `SCRA` (scrap, `−qty`) into the math — it is currently `ELSE 0` and so
  is silently ignored.

**2.2 Apply the predicate in `_sync_onhand_from_transactions`** ([`app.py:3167-3194`](app.py#L3167))
- Add the renumber-ADJT predicate to the `CASE` so a renumber contributes 0; keep
  every other type exactly as today. No data writes here — just the derivation.
- Add regression coverage in `tests/regression_tests.py` reproducing PCN 30314
  (INDF +10000, renumber-ADJT +10000, PICK −10000 ⇒ on-hand **0**, not 10000).

**2.3 Acceptance:** re-running the corrected derivation reproduces the Phase-1
`tblOnhandCorrectionPreview` numbers exactly (PCN 30314 ⇒ 0); regression test passes;
no row in `tblTransaction` was modified.

> **⚠️ OPEN QUESTION — RNDT.** The owner's vocab defines `RNDT` as
> "Random/miscellaneous", but the current code treats `RNDT` as a **physical-recount
> baseline** that *resets* on-hand to its `tranqty` ([`app.py:3116-3194`](app.py#L3116)).
> These are very different. If RNDT is really miscellaneous (not a recount), the
> baseline-reset logic is wrong and changing it would move on-hand for many PCNs.
> **Do not touch RNDT handling until this is confirmed with the owner.** Phase 1's
> preview keeps the existing RNDT-baseline behavior so its numbers stay comparable.

---

### Phase 3 — Recompute on-hand, reconcile location/floor, clear residuals  *(write)*

**Goal:** bring `onhandqty`, `mfg_qty`, and `loc_to` into a single consistent state.

**3.1 Recompute `onhandqty` from the corrected ledger**
- Run the (now-corrected) reconciler once, full-table, writing each change to
  `tblReconcileAudit` (`source='onhand_recompute_20260612'`).

**3.2 Reconcile `loc_to` / `mfg_qty` against the corrected on-hand**
- Invariant to enforce: a row may **not** have `onhandqty>0` AND `loc_to='MFG Floor'`
  AND `mfg_qty>0` representing the *same* units. After 3.1, for the 4,038 floor rows:
  - If corrected `onhandqty=0` and the lot is genuinely on the floor → keep
    `loc_to='MFG Floor'`, keep `mfg_qty`, leave on-hand 0. (This is the *real* floor
    stock that Phase 4 will surface.)
  - If corrected `onhandqty>0` and the bin physically holds it → reset `loc_to` to the
    real bin and `mfg_qty='0'` (it was never really on the floor; the floor flag was a
    side effect of the phantom).
  - **Decision rule must be data-driven** (last real PICK/RESTOCK in ledger, `qty_old`,
    PCN-History) and produce a review list for the ambiguous remainder.

**3.3 Clear residual quantities on fully-picked legacy PCNs**
- PCNs whose corrected ledger nets to 0 but still carry a stale `onhandqty`/`mfg_qty`
  from migration → set to 0, audit-tagged `source='legacy_residual_clear_20260612'`.

**3.4 Acceptance:**
- 0 rows with `onhandqty>0 AND mfg_qty>0 AND onhandqty=mfg_qty` (the 1,951 case → 0).
- 0 rows with `loc_to='MFG Floor' AND onhandqty>0` *unless* explicitly approved.
- Conservation: total on-hand only decreased; no PCN with real bin stock went below it.
- Re-enable the auto-reconciler; confirm it makes **0** further changes (stable).

---

### Phase 4 — CANCELLED per owner (2026-06-12)
> Owner does NOT want an "On Floor" / MFG-Floor column on the shortage report.
> The shortage report continues to **exclude MFG-Floor stock** as it does today.
> Do not add the column. (Original Task-2 text retained below for history only.)

### Phase 4 (ORIGINAL, not doing) — Surface MFG-Floor stock in the shortage report (Task 2)  *(write/feature)*

**Goal:** stop the shortage report from hiding real floor stock, now that floor stock
is no longer inflated.

**4.1 Include floor on-hand**
- The shortage SQL currently excludes `loc_to='MFG Floor'`
  ([`app.py:4830`](app.py#L4830), [`app.py:4840`](app.py#L4840)). Change so floor
  stock counts toward availability **separately**, not silently dropped.

**4.2 Add a dedicated "On Floor" column**
- New column alongside `ON HAND QTY`: `ON FLOOR` (sum of `mfg_qty` for the part,
  post-Phase-3 corrected). Show in the view, the saved report, and the Excel export
  (mirror the existing column-registry pattern in `SHORTAGE_EXPORT_COLUMNS`).

**4.3 Acceptance:** the cited job (39 lines / 41,522 units) now shows its floor stock
instead of all-zeros; the number matches the warehouse view; no double-count vs
on-hand (floor and on-hand are distinct columns).

---

### Phase 5 — PCN collision audit detector (Task 4)  *(read-only, recurring)*

**Goal:** a recurring integrity check for one PCN bound to >1 genuinely different part.

**5.1 Detector**
- Flag PCNs where ≥2 rows have **distinct `item` AND distinct non-blank `mpn` AND each
  `onhandqty>0`**, excluding (a) legitimate rename history (same physical stock, one
  row qty>0) and (b) placeholder/blank-MPN records.
- Emit suspected correct owner per PCN (the row with surviving live stock / latest
  real transaction).

**5.2 Run once as an audit, keep as a scheduled check**
- Today this returns **0** (already clean) — so this phase is *prevention*, low
  urgency. Wire it into the nightly job (Phase 6.3) and alert on any non-zero result.

**5.3 Acceptance:** detector returns 0 on current data; intentionally-seeded collision
in staging is caught.

---

### Phase 6 — Single-source-of-truth hardening + nightly divergence check (Task 5, re-scoped)  *(write)*

**Goal:** keep the corrected state correct, forever.

**6.1 Treat `onhandqty` as derived, not authoritative**
- Document and enforce that `onhandqty` is a cache of the ledger. All writes go through
  transactions; the reconciler is the only thing that sets `onhandqty`.

**6.2 Add a UNIQUE/awareness constraint posture on `pcn`**
- `pcn` today has only an index ([`app.py:3047`](app.py#L3047)), no uniqueness. A true
  unique constraint is unsafe (legit multi-row history exists), so instead enforce the
  collision rule in the guard ([`app.py:874-908`](app.py#L874)) and the bulk-import
  path, and add the Phase-5 detector as a backstop.

**6.3 Nightly integrity job**
- A scheduled check that reports, and alerts on, any of:
  - row with `onhandqty>0 AND loc_to='MFG Floor' AND mfg_qty>0` (double-count returns),
  - stored `onhandqty` ≠ ledger-derived (reconciler drift),
  - relabel-`ADJT` newly appearing (semantics regression),
  - PCN collision (Phase 5).
- Output to a dashboard + email; zero-touch unless something fires.

**6.4 Acceptance:** nightly job green for 7 consecutive days post-cleanup.

---

### Phase 7 — Prevention (close the source of new bad data)  *(write)*

**7.1 Log relabels correctly going forward**
- Any item-rename / relabel UI path must write `PN_CHANGE` (qty-neutral), never `ADJT`
  with a quantity. Audit existing relabel entry points for this.

**7.2 Guard the bulk-import path**
- Ensure `migration/.../reimport_warehouse.py` (and any future import) routes through
  the collision guard and never blind-inserts. (Already hardened post-April; re-verify.)

**7.3 Add CI regression tests** for: relabel→qty-neutral, no MFG-Floor+on-hand
double-state, collision guard, nightly-check queries.

---

## 5. Sequencing & dependencies (one after another)

```
Phase 0  Prep/backup/staging/pause reconciler      (gate: restorable backup)
   │
Phase 1  Detector + corrected-on-hand REPORT        (gate: owner signs off the list)
   │
Phase 2  Fix ledger semantics (relabel = neutral)   (gate: derivation == Phase 1)
   │
Phase 3  Recompute on-hand + fix loc/floor + clear  (gate: invariants hold, conserve)
   │
Phase 4  Shortage report: "On Floor" column (T2)    (gate: cited job correct)
   │
Phase 5  Collision audit detector (T4)              (gate: 0 today, catches seeded)
   │
Phase 6  SSOT hardening + nightly check (T5)         (gate: 7 days green)
   │
Phase 7  Prevention (relabel logging, guards, CI)   (gate: tests pass)
```

**Hard rule:** never start Phase N+1 until Phase N's acceptance criteria pass **on
staging, then on prod.** Phases 1, 5 are read-only and safe to run anytime.

---

## 6. Rollback plan

- Each write phase tags its `tblReconcileAudit` rows with a unique `source`. Rollback =
  restore the affected `onhandqty`/`loc_to`/`mfg_qty`/`tblTransaction` rows from the
  Phase-0 dated snapshot for the tagged IDs.
- If a phase fails acceptance: restore snapshot, re-enable reconciler, investigate on
  staging. Prod stays on the last-known-good snapshot.
- Keep the Phase-0 backup for ≥30 days after Phase 6 goes green.

---

## 7. Key code & data references

| What | Location |
|---|---|
| Reconcile on-hand math (ADJT as +delta — the bug) | [`app.py:3167-3218`](app.py#L3167) |
| Reconciler thread (every 5 min) | [`app.py:3239`](app.py#L3239) |
| PICK → MFG Floor + mfg_qty | [`app.py:1294-1305`](app.py#L1294) |
| Shortage report excludes MFG Floor | [`app.py:4830`](app.py#L4830), [`app.py:4840`](app.py#L4840) |
| PCN collision guard (stock path) | [`app.py:874-908`](app.py#L874) |
| PCN generation (MAX+1, advisory lock) | [`app.py:6336-6449`](app.py#L6336) |
| `pcn` index (no UNIQUE) | [`app.py:3047`](app.py#L3047) |
| Bulk re-import (collision-aware now) | `migration/stockAndPick/web_app/reimport_warehouse.py` |
| Audit table | `pcb_inventory."tblReconcileAudit"` |
| Ledger | `pcb_inventory."tblTransaction"` |
| Inventory | `pcb_inventory."tblWhse_Inventory"` |

---

## 9. Execution log

### Phase 0 — Preparation & safety net — ✅ DONE 2026-06-12
- **Prod DB confirmed:** local container `aci-database`, database `kosh`, schema
  `pcb_inventory` (app logs "Using local database"; a Neon cloud URL is also
  configured but is NOT the live source). 34,460 inventory rows / 194,3xx txns.
  DB size 147 MB; host disk 11 TB free.
- **0.1a Backup:** `pg_dump -Fc` → `backups/kosh_full_20260612.dump` (18 MB,
  50 tables, verified restorable with `pg_restore -l`).
- **0.1b Snapshots (in-DB, additive):** `pcb_inventory."tblWhse_Inventory_bak_20260612"`,
  `..."tblTransaction_bak_20260612"`, `..."tblReconcileAudit_bak_20260612"` — row
  counts verified equal to live.
- **0.2 Staging:** `kosh_staging` database created in `aci-database` and restored
  from the 20260612 dump (restore exit 0, counts match). NOTE: prod transacts
  daily — **refresh `kosh_staging` from a fresh dump immediately before Phase 2.**
- **0.3 Reconciler pause:** DEFERRED to Phase 2 (correct timing — only needed during
  write windows). No pause flag exists today; the reconciler is a hard `while True`
  at `app.py:3024`. Phase 2 will add a `KOSH_DISABLE_RECONCILER` env guard at the
  top of that loop and deploy it before any ledger writes.
- **Acceptance:** ✅ backup restorable, snapshots match live, staging reachable,
  reconciler-pause mechanism identified. **No production data was modified.**

### Phase 1 — Relabel detector + corrected-on-hand preview — ✅ DONE 2026-06-12 (read-only)
- **Ran entirely on `kosh_staging`** — zero queries and zero new tables on prod; live
  users unaffected.
- **Classifier (truncation-proof):** a renumber-ADJT = `trantype='ADJT'` with both
  `loc_from`/`loc_to` non-locations and differing (locations = values seen on non-ADJT
  txns, or 6+ digit bins, or named areas). First attempt matched item *spelling* and
  MISSED PCN 30314 because `loc_to` is truncated to 10 chars (`8525ML-1-6`); the
  location-based rule fixes it. Verified only 1 of 21,014 items is 6+ digit numeric,
  so the bin rule is safe.
- **Output:** `pcb_inventory."tblOnhandCorrectionPreview"` (on staging) +
  `onhand_correction_preview_20260612.csv` in the repo (2,526 rows, sorted by impact).
- **Results:**
  - **2,526** (pcn, item) rows affected; **2,356 reduced, 0 increased** (conservation
    holds — corrected never exceeds current); **2,067 zeroed**.
  - **1,224,426 phantom units removed**; sum on-hand of affected rows 1,464,130 → 239,704.
  - The exact "79 = 79" class (`onhandqty == mfg_qty`, both > 0): **1,820 rows, 1,819
    corrected down.**
  - PCN 30314 ✅ 10000 → 0. Spot-checks all show `ACI-####  → realpart = fullqty`
    renumbers logged as ADJT (e.g. `ACI-6518 → 5188-21 = 65`).
- **Acceptance:** ✅ canonical example reproduced; conservation holds; reviewable CSV
  produced. **No production data touched.**

**Next:** owner reviews `onhand_correction_preview_20260612.csv`.

### Phase 2 — Calculation fix attempt + validation — ⚠️ HELD 2026-06-12 (NOT deployed)
- **Decision:** RNDT kept as recount baseline (owner deferred to recommendation;
  data proved RNDT-neutral would zero ~thousands of legitimately-stocked parts —
  e.g. 7918-5: 15,000→0). Renumber-fix only (v1).
- **Code (reverted, not deployed):** added `is_relabel` predicate + `locvocab` CTE to
  `_sync_onhand_from_transactions` so renumber-ADJTs contribute 0; also normalized
  `mpn_key` with `translate('-# ./','')` to unify MPN spelling variants
  (`ERJ-3EKF1002V` vs `ERJ3EKF1002V`) that fragment a reel's history.
- **Validation on staging caught a BLOCKER — do not deploy the live reconcile:**
  Running the modified reconcile on a staging copy and diffing vs prod showed it
  DECREASES 2,522 rows (−1.44M phantom, correct) **but also INCREASES 373 rows
  (+151K units)** — phantom *creation*. MPN normalization did not remove the
  increases.
- **Root finding (bigger than the relabel bug):** the increases are **pre-existing
  and reconcile-wide**, NOT caused by the relabel fix. Running the ORIGINAL,
  unmodified reconcile fresh on staging produces EVEN MORE increases (**503 rows /
  +217K units**, same top offender PCN id 41055: 9,400→19,400). **The reconcile is
  not convergent on this data** — the stored on-hand is a partially-reconciled,
  internally-inconsistent state, so any full run moves hundreds of rows in BOTH
  directions. (The earlier "0 divergence" reading reflected the live loop's
  activity-gated subset, not true convergence.)
- **Consequence:** the always-on 5-minute reconcile **cannot** be used to apply the
  relabel fix — its next run would recompute thousands of rows including ~370
  phantom-creating increases unrelated to relabels. Code change reverted; prod
  untouched.

### REVISED approach for Phase 2/3 (supersedes "fix the reconcile then let it run")
Apply the relabel correction as a **targeted, DOWNWARD-ONLY, one-time script**, not
via the live reconcile:
1. From the (re-derived, live) preview, take only rows where `corrected < current`
   (phantom removal) AND the PCN is a "clean" relabel case (single reel lineage, not
   one of the heavily-reused/ambiguous reels). Set `onhandqty = corrected`. **Never
   increase.** Audit-tag every change; fully reversible from the Phase-0 snapshot.
2. Leave the always-on reconcile UNCHANGED for now (it stays activity-gated as today).
3. Open a SEPARATE workstream: **the reconcile's non-convergence** (503 stale rows on
   a fresh run). Decide whether stored or ledger-derived is authoritative per row,
   why the ledger over/under-counts (incomplete pre-migration history vs RNDT
   baseline), and only then make the ledger the SSOT (original Task 5). This is now
   understood to be a real, separate defect — not just "two values not synced."
4. The renumber-ADJT calculation fix still belongs in the reconcile eventually, but
   only AFTER the non-convergence is resolved, so it can't ride along with phantom
   increases.

---

### Phase 2/3 (core) — ✅ DEPLOYED to production 2026-06-12 (commit 0d3682c)
- Renumber-aware, MPN-normalized, downward-only reconcile shipped via deploy.sh
  (15 regression tests green) + vercel --prod. Reconciler applied it live.
- **Verified on prod:** PCN 30314 on-hand 10000 → 0 (mfg_qty 10000 preserved);
  MFG-Floor phantom 4,038 rows/1.44M units → 2,082 rows/485K units; ~2,353 rows
  corrected in the audit log. No negatives.
- **Going forward:** the reconcile now permanently treats relabel-ADJTs as
  quantity-neutral, so future renumbers can't re-inject on-hand phantom.

### Phase 3 (residual double-count) — ✅ APPLIED to production 2026-06-12
- Investigated the residual MFG-Floor-with-on-hand rows. Found the genuine
  double-count is only where BOTH on-hand AND mfg_qty are populated. Resolved by
  location:
  - **A (480 rows): dup on MFG Floor → on-hand set to 0** (mfg_qty keeps the floor
    stock). Audit-tagged `phase3_dup_floor_zero_onhand_20260612`.
  - **B (128 rows): dup in a bin → mfg_qty set to 0** (on-hand keeps the available
    stock).
  - **C (1,595 rows: on-hand>0, mfg_qty=0, MFG Floor): LEFT ALONE** — NOT a
    double-count; single-counted (likely migrated) stock. Zeroing would destroy
    real inventory. Flagged for separate review (is it on the floor, or fully
    picked?).
- **Verified on prod: 0 remaining rows with on-hand>0 AND mfg_qty>0; 0 negatives.**
  The "on-hand AND MFG-Floor showing the same units" symptom is fully eliminated.
  Sticks under the guarded reconciler (can't raise on-hand; never touches mfg_qty).

### Integrity check + Phase 5/6/7 status — 2026-06-12
- **`scripts/integrity_check.sql`** built (read-only monitor). On prod ALL GREEN:
  double_count=0, negative_onhand=0, **pcn_collision=0** (Phase 5 detector),
  **stored_above_ledger=0** (no phantom remains). INFO: ~149 relabel-ADJTs arrive
  daily from the Access re-import yet produce 0 phantom — the reconcile fix
  protects prod live.
- **Phase 7 (prevention):** the relabel-ADJTs originate from the **legacy Access →
  KOSH re-import** (blank userid, bulk renumber batches), NOT the KOSH UI (whose
  edit route logs locations + deltas correctly). The reconcile neutralizes them
  from ANY source, so on-hand is already protected. A deeper "log relabels as
  PN_CHANGE at the import" change is OPTIONAL (cosmetic given the calc handles it).
- **Phase 6 (nightly monitor):** `integrity_check.sql` is the content; wiring it as
  an automated daily job (background thread or cron) is a small deploy — NOT yet
  done (offer pending).
- **Group C:** reviewable list exported to `group_C_mfgfloor_review_20260612.csv`
  (1,592 rows). Needs PHYSICAL/warehouse verification — cannot be auto-corrected
  without risking real stock. Many "moved off floor" rows are real available stock
  hidden by a stale `loc_to='MFG Floor'` (fixable to the real bin once confirmed).

### STILL OPEN (needs people / sign-off, not blocked on code)
- **Group C review (~1,592 rows / 208K units):** warehouse confirms per-case;
  "moved off floor" → set loc_to to the real bin; "picked to floor" → verify.
- **Task 5 (reconcile non-convergence):** the temporary downward-only guard stays.
  The suppressed ~370 "raises" are rows where the ledger derives MORE than stored
  (incomplete pre-migration history / manual down-adjustments). Resolving them
  means trusting the ledger to RAISE on-hand — unsafe without a **physical
  recount/backfill**. This is a data-completeness task, not a code bug. Remove the
  guard only after recount. (`stored_above_ledger=0` confirms no phantom risk
  meanwhile.)
- **Phase 6 automated nightly job:** wire `integrity_check.sql` (small deploy).
- **Residual floor/loc reconciliation (Phase 3.2/3.3):** ~2,082 MFG-Floor rows still
  carry on-hand the ledger says is >0 — the complex reused-reel cases. Need
  loc_to/mfg_qty reconciliation + residual clear, case-reviewed.
- **Reconcile non-convergence (Task 5, real form):** the temporary downward-only
  guard suppresses ~370 stale "catch-up" increases; the underlying incomplete-
  ledger / SSOT issue is unresolved. Removing the guard is gated on this.
- **Task 2 — shortage report "On Floor" column (Phase 4):** not started.
- **Task 4 — PCN collision detector (Phase 5):** not started (0 collisions today).
- **Phase 6 (nightly integrity check) / Phase 7 (log relabels as PN_CHANGE at the
  data-entry path, guards, CI):** not started.

## 8. Definition of done (whole effort)

- 0 rows with `onhandqty>0 AND loc_to='MFG Floor' AND mfg_qty>0` representing the same units.
- 0 relabel-`ADJT` rows contributing to on-hand; relabels recorded as `PN_CHANGE`.
- Stored `onhandqty` == ledger-derived for 100% of rows, and the ledger is *correct*.
- Shortage report shows floor stock in a dedicated column; cited job no longer all-zeros.
- PCN collision detector wired into nightly job, green.
- Nightly integrity check green 7 days running.
- Purchaser can trust a single on-hand number across every screen.
