<h1 align="center">🐞 KOSH — BUG HISTORY</h1>

<p align="center">
  <b>Reframed 2026-07-17 from the user's own reports — Theresa's 5 emails + the 7-16 issue list.</b><br>
  <span style="color:#c0392b"><b>STATUS: 🔴 ALL ISSUES UNFIXED.</b></span><br>
  <span style="color:#7f8c8d">The prior per-bug "fixed" folders, verify scripts and audit docs were deleted —
  they claimed fixes that did not hold. This file is now the single record, and it tracks
  what the <b>user</b> actually sees, not what the code was believed to do.</span>
</p>

---

## Why this file was rewritten

Every bug in the old log was marked ✅ "Fixed & deployed." The user (Preet) and the
primary user (**Theresa**, Inventory Specialist) report that the same problems keep
coming back or turn into new ones. A fix ships, and either the bug returns or something
else breaks. So **nothing here is treated as fixed.** An item is closed only when the
exact complaint below is impossible *and* Theresa confirms it at her desk.

> **The core issue is trust, not any single bug.** Theresa was satisfied with KOSH
> before. She no longer trusts it. In her words:
>
> - *"I no longer trust it."* — 2026-06-23
> - *"Up until today I believed that the shortage report could be trusted. After the
>   issues I found, I do not trust the validity of the data being created in this
>   report."* — 2026-06-03

---

## 📎 Source evidence (the only authority for this file)

All in the `KOSH/` folder:

| File | Date | What it reports |
|------|------|-----------------|
| `KOSH ISSUES 7-16-26.xlsx` | 2026-07-16 | Theresa's **current** issue list (see below) |
| `KOSH SHORTAGE REPORT.eml` | 2026-06-03 | Shortage report QTY/REQ columns blank; missing lines; same-MPN PCNs not included; "trust was lost" |
| `KOSH.eml` | 2026-06-17 | Warehouse Inventory still not showing the latest transactions seen in History |
| `SHORTAGE REPORT.eml` | 2026-06-17 | Shortage report data wrong on 9 lines she hand-verified |
| `LATEST SHORTAGE REPORT.eml` | 2026-06-23 | A line item missing from the report; a listed line "not actually in stock"; trust lost |
| `KOSH HISTORY VERSUS WAREHOUSE INVENTORY.eml` | 2026-07-01 | Warehouse Inventory not reflecting the last entry in PCN History |
| Verbal — Preet | 2026-07-21 | 5 more shortage-report defects (SR-3 line-item #, SR-8 location, SR-9 on-hand sum, SR-4 per-PCN lines, SR-1 ZSUB) |

---

# 🔧 FIX ORDER — the sequence issues get fixed in

Fix the **inventory foundation first**, then the shortage report reads correctly on top of
it. This is why the report bugs are late in the list even though they're what Purchasing
sees — most of them can't be right until on-hand is one number. Aligned to
`ACTION-PLAN.md` phases.

| # | Bug | What it is | Phase |
|:--:|:--|:--|:--:|
| 1 | **PH-1** | Same qty shown as on-hand AND picked (double-count) | 2 |
| 2 | **WI-2** | Warehouse Inventory ≠ PCN History | 2 |
| 3 | **WI-1** | Can't edit quantities (save-verify fails) | 1→2 |
| 4 | **PK-1** | Can't pick: "insufficient qty" though stock is there | 1 |
| 5 | **SR-3** | Wrong ACI PN **and** line-item # on the report | 1 (surfaces in 5) |
| 6 | **RS-1** | Restock refuses parts in hand ("qty at zero") | 3 |
| 7 | **SO-1** | Signed out after each kitting action | 4 |
| 8 | **SR-9** | Report on-hand = bin + MFG floor summed, not real on-hand | 5 (needs one-number) |
| 9 | **SR-8** | Report location wrongly shows "MFG FLOOR" | 5 |
| 10 | **SR-1** | Substitutes not generated / **ZSUB** not labeled as ZSUB | 5 |
| 11 | **SR-2** | Lists "like" MPNs instead of the exact match | 5 |
| 12 | **SR-4** | Multiple PCNs per MPN lumped, not separate lines | 5 |
| 13 | **SR-5** | Report drops BOM lines | 5 |
| 14 | **SR-6** | QTY / REQ show 0 instead of real numbers | 5 |
| 15 | **SR-7** | Line's own stock left off the report | 5 |

---

# 🔴 CURRENT OPEN ISSUES — from `KOSH ISSUES 7-16-26.xlsx` (2026-07-16)

These are the live, unfixed issues, in Theresa's own categories.

## 🟠 GENERATE PCN — URGENT, blocking Theresa right now

### 🟠 GP-1 — Cannot generate a PCN (qty column capped at 10,000)
- **Reported:** 2026-07-21 (Theresa, email: *"I ended last night with not being able to
  generate a PCN. I started this morning with the same problem."*). Diagnosed by Preet as the
  **qty column cap**.
- **What she sees:** generating a PCN fails when the quantity entered is over **10,000** —
  the qty column was capped at 1–10,000, so a larger qty is rejected and no PCN is created.
- **Fix applied in code (2026-07-21):** raised the qty cap from **10,000 → 100,000** in all
  five validation sites in `app.py` (shared `validate_quantity`, the API decorator, and the
  `stock` / `pick` / `restock` paths) plus the PCN-generate endpoint. **NOT yet deployed / NOT
  yet confirmed by Theresa** — stays open until deployed and she generates the PCN live.
- **Caveat:** this removes the qty-cap blocker specifically. If her failure was a *different*
  cause, we still need her exact quantity and the on-screen error to confirm.

## 🔴 SHORTAGE REPORT

### 🔴 SR-1 — Does not generate Substitute parts listed on the BOM
- **Reported:** 2026-07-16 (xlsx). **Status: UNFIXED.**
- **What she sees:** substitute/alternate parts that ARE on the BOM are not produced on
  the shortage report, so Purchasing can miss valid alternatives.
- **Also (2026-07-21, Preet):** a **ZSUB** substitute in the uploaded BOM does not carry
  through as a ZSUB — neither in what KOSH displays nor on the shortage report; the ZSUB
  designation is lost.

### 🔴 SR-2 — Lists "like" MPNs instead of the exact match
- **Reported:** 2026-07-16 (xlsx); also 2026-06-03 (`KOSH SHORTAGE REPORT.eml`). **Status: UNFIXED.**
- **What she sees:** the report pulls in MPNs that merely resemble the line's MPN, padding
  it with parts that are not the same component.

### 🔴 SR-3 — Wrong ACI PN in the first column (not the job's line item)
- **Reported:** 2026-07-16 (xlsx). **Status: UNFIXED.**
- **What she sees:** the ACI PN column shows the wrong part. *Her example: it shows
  `6366L-9` where `6390L-8` is what should be.* Stock renamed/renumbered is left filed
  under the old part number, so the report points at the wrong one.
- **Also (2026-07-21, Preet):** it's not only the ACI PN — the **line-item number** on the
  report is wrong too. On a job (e.g. order `12345-6`, work order `2358-5`) an MPN that IS in
  the system but tied to some other ACI PN/line shows up on the report under **that** ACI PN
  and line number, instead of the job's real ACI PN and line item.

### 🔴 SR-4 — Multiple PCNs per line not listed, only the total quantity
- **Reported:** 2026-07-16 (xlsx). **Status: UNFIXED.**
- **What she sees:** when a line item has 3 different PCNs, the report shows only the
  combined quantity available, not each PCN — so she can't tell where the stock is.
- **Also (2026-07-21, Preet):** for one MPN with multiple PCNs, each PCN must appear as its
  **own line with the qty for that PCN** — not one lumped total.

### 🔴 SR-5 — Report drops lines: "missing several lines of data"
- **Reported:** 2026-06-03 (`KOSH SHORTAGE REPORT.eml`) and again 2026-06-23
  (`LATEST SHORTAGE REPORT.eml`). **Status: UNFIXED.**
- **What she sees:** a report for a job came back **missing several BOM lines** that had been
  there when she ran the same job the day before; and a line item that was in inventory
  **did not show on the report at all**. Purchasing therefore never sees those parts.
- **Her words:** *"This report was missing several lines of data needed to inform Purchasing
  about parts needed… **This is where trust was lost**."*

### 🔴 SR-6 — QTY and REQ columns show "0" instead of the real numbers
- **Reported:** 2026-06-03 (`KOSH SHORTAGE REPORT.eml`). **Status: UNFIXED.**
- **What she sees:** on some (not all) line items the **QTY** and **REQ** columns read `0`, so
  she has to open the BOM to find out how many are needed to build. Notably the *same job* ran
  correctly for Preet the same morning — so it depends on the data, not the job.

### 🔴 SR-7 — A line's OWN stock is left out of the report
- **Reported:** 2026-06-03 (`KOSH SHORTAGE REPORT.eml`). **Status: UNFIXED.**
- **What she sees:** the report failed to include other PCNs holding the same MPN — **and the
  line item's own stock as well** — so parts she has are reported as missing.

### 🔴 SR-8 — Report shows the location as "MFG FLOOR" when it shouldn't
- **Reported:** 2026-07-21 (Preet). **Status: UNFIXED.**
- **What he sees:** the part's **location** on the shortage report comes back as **MFG
  FLOOR**, a location that should not appear there. ("MFG Floor" is a status label meaning the
  PCN is out on the floor, not a stock location — see the inventory-model note in
  `ACTION-PLAN.md`.)

### 🔴 SR-9 — Report on-hand = bin + MFG floor added together, not the real on-hand
- **Reported:** 2026-07-21 (Preet). **Status: UNFIXED.**
- **What he sees:** for a PCN (e.g. `4848`) the **on-hand qty** on the shortage report is the
  **sum of bin on-hand + MFG floor**, not the true on-hand. This is the same double-count as
  PH-1 leaking onto the report; under the one-number model a picked PCN reads 0 and the floor
  is never added.

### 🔴 SR-10 — Report offers PCNs whose MPN is NOT the line's part
- **Reported:** 2026-07-27, Theresa handwritten note (`Shortage Report updates.jpg`), marked
  **LIVE**. **Status: FIXED ON STAGING — awaiting Theresa.**
- **What she sees:** on `7946L-30` the report offers **PCNs 29534, 28800, 36430** — *"not
  options, MPN does not match."*
- **Root cause:** on-hand and the per-PCN rows matched stock on the **ACI part number alone**
  and never compared the MPN. PCNs 29534/28800 hold `CM316X5R475K50AT` and 36430 holds
  `C0805C471K5RAC7800` (that is line **355's** part), all filed under `7946L-30`. The line read
  **1720** when only **1270** was the BOM part `C1206C475K5PACTU`. SR-2's exact-MPN fix only
  ever touched the cross-part-number search — the own-part path had no MPN comparison to
  tighten, so it was missed.
- **Fix:** `line_mpns` (the BOM's primary MPN + its ZSUB alternates, current job_rev) now
  gates every stock lookup, SR-2's exact-string rule unchanged. Excluded stock is **not
  dropped** — `unmatched_pcn_rows_by_acipn()` still surfaces it. **2026-07-29 (Preet):** those
  rows were removed from the **shortage report and its Excel pull sheet** — an MPN that is not
  on the BOM must never appear on a shortage report, full stop. They remain on the **job tab**.
  Trade-off accepted knowingly: on the report a line's on-hand can now drop (7946L-30:
  1720 → 1270) with nothing on the page saying where the other 450 units went. Same guard applied to the **job-detail**
  query, which had the identical bug and would otherwise have shown 1720 next to the
  report's 1270.

### 🔴 SR-11 — Per-PCN rows print the BOM's MPN over each PCN's real MPN
- **Reported:** 2026-07-27, same note. **Status: FIXED ON STAGING — awaiting Theresa.**
- **What she sees:** on `7946L-55`, a PCN with a *"different MPN NO dash, system put dash in."*
- **Root cause:** the report prints **one** MPN per line, taken from the BOM, and stamped it
  onto every per-PCN sub-row. PCN **31639** really holds `EEEFC1E101P` (no dash); the BOM says
  `EEE-FC1E101P`. Its own MPN was read from the database, then thrown away and overwritten
  with the dashed one. Not a matching bug — a display bug, in the web view, the Excel pull
  sheet and the job tab.
- **Fix:** every per-PCN row prints its OWN mpn (already being fetched, just discarded).
  ZSUB lots carry a `ZSUB` badge; the main row prefers a lot of the line's primary MPN so it
  stays self-consistent.

### 🔴 SR-12 — Approved ZSUB stock under another part number is invisible
- **Reported:** 2026-07-27, same note. **Status: FIXED ON STAGING — awaiting Theresa.**
- **What she sees:** `7946L-10` — *"sub has 3 more PCN's available. Not shown on Shortage
  Report."*
- **Root cause:** a hole between two paths with opposite blind spots. The own-part path could
  not see other part numbers; the cross-part-number path could, but only ever searched the
  line's **primary** MPN. So *approved ZSUB under someone else's PN* was covered by neither.
  207 units of the approved ZSUB `C0603C104M5RACTU` sat in bins under `8019-3` (PCN 11807,
  100), `8041-3` (PCN 11806, 100) and `8188L-5` (PCN 11805, 7) — her exact three.
- **Fix:** the cross-part-number search now covers the line's whole approved-MPN set and tags
  each row `is_zsub`, so those rows read "ZSUB @ another PN" instead of looking like the
  primary part.

> **Scope: the guard is system-wide, not per-job.** `line_mpns` is built per job from
> `tblBOM`, so every job gets it automatically. Verified read-only across the whole DB
> (2026-07-27): **5,471 jobs / 31,831 BOM lines**, and the invariant holds everywhere —
> **0 lines where on-hand was invented, 0 where units were lost** (counted + flagged always
> equals what the old part-number-only rule blindly summed). Four surfaces were carrying the
> bug and all four now share the rule: the shortage report, its Excel pull sheet, the **job
> tab**, and the **job-tab Excel export** (`job_export`, found last and fixed in the same
> pass — it would otherwise have printed 1720 where the report printed 1270).

> **Data debt this exposed (needs Theresa/Preet, not code):** system-wide, **2,816,473 units
> across 2,209 lines in 642 jobs** were being counted as the BOM part while the bin actually
> holds a different MPN — 30% of all stock attributed to BOM lines. Only **15,301 units (27
> jobs)** are mere formatting differences fixable by an `UPDATE` (`EEEFC1E101P` vs
> `EEE-FC1E101P`, `74HC14D,653` vs `74HC14D, 653`). The other **2.80M units need a human
> ruling**, and they are not one kind of problem:
> - **Cross-manufacturer / packaging equivalents** — almost certainly legitimate alternates
>   never recorded as ZSUBs: `0402YD104KAT2A` (AVX) vs `GRM155R71C104KA88J` (Murata), both
>   0.1µF 0402, 28,000 units on job 7918; `CRCW12061R43FKEA` vs `...FKTA` (same Vishay part,
>   different packaging code); `GRM1555C1E390JA01` vs the same with a `D` packaging suffix.
>   These belong on the BOM as ZSUBs, after which they count again automatically.
> - **Genuinely wrong stock** — e.g. `6980-19` is an LED (`LTST-C150CKT`) but the bin holds
>   `ERJ-2RKF4992X`, a 49.9k resistor (8,700 units); `ERA-2AED102X` (1k 0.1%) vs
>   `ERJ-2GEJ152X` (1.5k 5%) — different value *and* tolerance.
>
> Before this fix all 2.8M of those units read as available BOM stock on every shortage
> report — a direct, quantified explanation for the recurring *"the report said we had it"*
> complaints. **Do not "fix" this by loosening MPN matching**: only 0.5% of it is a separator
> difference, and separator-blind normalization is what SR-2 removed for merging `1.5KE15`
> with `1.5KE150CA` (15V vs 150V).

> **Shortage-report history (emails):** 2026-06-03 — QTY and REQ columns showed "0" on
> some lines (had to consult the BOM); a re-run of the same job was missing several
> lines; same-MPN PCNs not included → *"trust was lost."* 2026-06-17 — data wrong on 9
> hand-checked lines. 2026-06-23 — a line missing entirely, and a listed line "not
> actually in stock" per PCN History. These are the same shortage-report failures,
> recurring for 6+ weeks.

## 🔴 WAREHOUSE INVENTORY

### 🔴 WI-1 — Unable to edit quantities
- **Status 2026-07-30: root cause found and FIXED on staging, UNVALIDATED.** It was still
  live. Preet's 2026-07-29 check on PCN 46606 passed only because that PCN was in bin
  `1251457` by then; the failure is specific to a PCN whose `loc_to` is `MFG Floor`, where
  the `trg_bin_xor_floor` guard (added for PH-1) forces `onhandqty = 0` and the post-save
  check compared the typed number against that 0, 500'd, and rolled the edit back.
  **12,851 rows** sit on the MFG Floor. Fix verifies against the bucket the location
  dictates and rejects the ambiguous case with an actionable message.
  Test `tests/behavioral/warehouse_qty_edit_on_floor.py`.
- **Reported:** 2026-07-16 (xlsx). **Status: UNFIXED.**
- **What she sees:** editing a quantity in Warehouse Inventory fails (a save-verification
  error). Stock filed under a renamed part inflates the expected number, so the save is
  refused.

### 🔴 WI-2 — PCN History and Warehouse Inventory do not match
- **Reported:** 2026-07-16 (xlsx, "last week"); 2026-06-17 (`KOSH.eml`); 2026-07-01
  (`KOSH HISTORY VERSUS WAREHOUSE INVENTORY.eml`). **Status: UNFIXED.**
- **What she sees:** Warehouse Inventory shows a PCN as picked, while PCN History shows
  the item still in stock (or vice-versa). The two screens disagree.

## 🔴 PICK

### 🔴 PK-1 — Cannot pick line items to a job: "insufficient qty available"
- **Reported:** 2026-07-16 (xlsx). **Status: UNFIXED.**
- **What she sees:** the pick is refused with *insufficient quantity available* even when
  the stock is physically there — because the stock is filed under a renamed part number.

### 🔴 PK-2 — Pick success toast reports the WRONG "Remaining"
- **Reported:** 2026-07-30 by **Preet** (screenshot `image.png`, staging, PCN 46607).
  **Status: fixed on staging 2026-07-30, UNVALIDATED.**
- **What he saw:** picked all 50000 units of PCN 46607 (item 7942-16); the toast read
  *"Successfully picked 50000 units of 7942-16. Remaining: 2000"*.
- **Root cause:** `new_qty` was the **item total across every PCN**. The 2000 was PCN
  45082, a different PCN still in bin 1605010 that the pick never touched. Meanwhile the
  pre-pick confirm dialog reads the PCN row (pick.html:999) and said *"Remaining After
  Pick: 0"* — two screens contradicting each other on one operation, which reads as units
  going missing.
- **Second defect found with it:** `pick_pcb` never returned `pcn`/`mpn`/`loc_from`, so
  **every** pick's history detail line recorded literally `PCN: -, MPN: -, From: -`
  (app.py:4207) — the audit trail lost which PCN and which bin the pick came from.
- **Fix:** per-PCN remaining added (app.py:1511) and the PCN/MPN/source bin echoed back;
  the toast now names **only the PCN that was picked** (Preet, 2026-07-30: the item total
  must not appear at all). Test `tests/behavioral/pick_message_reports_picked_pcn.py`.

## 🔴 SIGN OUT

### 🔴 SO-1 — System signs her out after each transaction while kitting
- **Reported:** 2026-07-16 (xlsx). **Status: UNFIXED.**
- **What she sees:** during kitting, roughly every other action dumps her back to the
  login screen.

## 🔴 PCN HISTORY

### 🔴 PH-1 — Shows the same quantity on-hand and picked
- **Reported:** 2026-07-16 (xlsx, "last week"). **Status: UNFIXED.**
- **What she sees:** PCN History shows the same number as both on-hand and picked — which
  should never happen, especially on the same date as the transaction. (Double-count.)
- **RE-REPORTED 2026-07-30** (email, screenshot `pickqty-onhand.jpg`, PCN 44598): *"The
  other problem, still … On Hand Qty and Pick Qty show on the same transaction line. What
  the system is doing, now is adding both together. There is no way for me to rectify the
  PCN I am currently dealing with."* Her screenshot is **production**
  (`aci-kosh.vercel.app`) — a PICK row showing Pick Qty 20 / On Hand 24.
- **Staging status 2026-07-30:** the additive replay is gone on staging (rewritten
  `history_balance.py`, 2026-07-29). Swept **all 34,808 PCNs** / 198,368 transaction rows
  through the real code: **0** where the displayed On Hand differs from Warehouse
  Inventory, **0** PICK rows with a computed non-zero On Hand. Same PCN 44598, same
  02/04/26 PICK row: production 24, staging 0. **Still live in production** until the
  deploy. Stays 🔴 — Theresa closes it, not us.
- **Caveat she may still object to:** 2,156 PICK rows do display a non-zero On Hand, but
  every one is the **newest** row anchored to the stored Warehouse value (0 are computed).
  The number shown is the warehouse's own, never a sum — but the *shape* she complained
  about (both columns filled on a PICK line) still appears.

## 🔴 RESTOCK — flagged by Theresa as a REOCCURRING PAST ISSUE

### 🔴 RS-1 — Restock stops working: "qty at zero"
- **Reported:** 2026-07-16 (xlsx), marked **REOCCURRING**. **Status: UNFIXED.**
- **What she sees:** the restock function refuses parts she is physically holding,
  erroring that the quantity is at zero. She flagged this as a past issue that has
  come back.

### 🔴 RS-2 — A PCN can be restocked twice with no pick in between
- **Reported:** 2026-07-30 (email). **Status: guard implemented on staging 2026-07-30,
  UNVALIDATED.**
- **In her words:** *"I had a PCN showing as '0' on hand and 20 in MFG QTY in Whse Inv.
  PCN History showed this PCN had been restocked on 3/18/26. I attempted to Restock the
  parts, which since it was already restocked, should not have allowed this transaction
  and it did. Whenever a PCN is restocked, I should never be allowed to restock it again
  without being picked first. The restock function, at one time, would not allow restock
  of a PCN twice without a pick function being performed first. I am not sure how this
  function disappeared, but it will need to be reinstated."*
- **Why it disappeared:** removed deliberately on **2026-07-22** with the ledger, on the
  reasoning that a restock SETs on-hand so a repeat cannot double-count. That protects the
  arithmetic, not the process — the second restock silently overwrites the first count and
  nothing records that two different numbers were claimed for one PCN. Note `pick_pcb`
  kept its mirror guard (app.py:1373), so the two paths were asymmetric.
- **Confirmed on staging before the fix:** restocked one scratch PCN **3× in a row**, all
  succeeded, 3 RESTOCK rows written. 906 PCNs were in that state; 7 restock-after-restock
  events already exist in the staging trail.
- **Fix (app.py:1729):** restock is rejected when the PCN's stored on-hand > 0 — on the
  snapshot model that IS "restocked and not yet picked" (restock sets it above zero, a
  pick zeroes it), so it needs no userid/legacy-trantype guessing and holds for
  Access-imported PCNs. Test `tests/behavioral/restock_blocked_until_picked.py`.
- **Deliberate exception:** 0 on hand + stock on the MFG Floor stays restockable (the
  parts are not in a bin, so putting them back is legitimate, and no PCN may become both
  un-pickable and un-restockable). **This means her own PCN 44598 would still not be
  blocked** — its 3/18 rows are legacy `PTWY`/`RNDT` put-aways and it had 0 on hand.
- **Trade-off to tell her:** restock was the recount path ("type what you're holding, it
  overwrites"). That is now closed for the 19,889 PCNs sitting in bins; corrections must
  go through the Warehouse Inventory quantity edit, which records an ADJT delta.

### 🔴 RS-3 — "PCN History is not communicating with Whse Inventory"
- **Reported:** 2026-07-30 (email, same message as RS-2). **Status: root cause identified,
  NOT fixable by code.**
- **In her words:** *"The fact that transactions which appear in PCN History are not being
  updated in Whse Inventory is a huge problem … Could we please figure out why PCN History
  is not communicating with Whse Inv? This will become detrimental with a new ERP system."*
- **Finding (staging, PCN 44598):** the 3/18/26 movement she read as a restock is an
  `RNDT` (MFG Floor → Count Area) + `PTWY` (Count Area → bin 2103303) pair, qty 8. Those
  two transaction types are **100% Access imports — KOSH has never written one**: PTWY
  72,892 rows / 0 by KOSH, RNDT 24,549 / 0 by KOSH. So that movement never passed through
  KOSH and was never applied to Warehouse Inventory, which still reflects the 02/04/26
  PICK (0 on hand, 20 on the floor).
- A restock done **in KOSH** updates `tblWhse_Inventory` and `tblTransaction` in one
  transaction, so this is a legacy-import gap, not a live write failure. Repairing the
  restock function will not fix it.
- Related scale: **3,276 PCNs (9.4%)** have a trail that cannot reproduce the stored
  on-hand unaided. PCN History anchors the newest row to the stored value and flags the
  trail as incomplete rather than presenting a computed number as fact.

---

# 🧭 The one root cause behind all of it

KOSH computes on-hand more than one way and the answers drift:

- **Warehouse Inventory** = a stored snapshot.
- **PCN History** = a balance derived from the transaction trail.
- Plus rebuilt data models that were added but never fully cut over.

Two (now three) sources of truth over dirty imported data will always disagree. Every
past fix guarded one of them, and the side effect became the next complaint — which is
exactly the "fix one thing, break another" pattern Theresa keeps hitting. On top of
that, renamed/renumbered parts leave their stock filed under the old number, which is
what drives SR-3, WI-1, and PK-1 together.

### Live-data check (staging `kosh`, dump 2026-07-17, read-only) — confirms UNFIXED
- **33** rows count the same units in both a bin and the MFG floor (double-count; PH-1) —
  up from 13 on 2026-07-09.
- **10,230 of 34,808 PCNs** disagree between the snapshot and the rebuilt ledger — a gap
  of **3,758,849 units** (WI-2).
- **46** balance rows disagree with their own transaction log.
- **2,854** rows hold floor stock with an empty bin (~905K units), never cleared.

---

## 🏷️ LABEL PRINT — barcode unscannable + MSD/PO cut off (2026-08-03)

Reported by Preet from the floor, in this order: (1) barcode and PCN clipped at the top
of the label, (2) after a fix attempt, **MSD and PO cut off the bottom**, (3) **barcode
would not scan at all**. (2) and (3) were caused by the fix attempts, not the original
complaint.

**Root cause of (2) and (3) — one bug, two symptoms.** In `templates/pcn/print_label.html`
the barcode was changed to `height: 22, marginTop: 0, marginBottom: 0` to reclaim a few
px of vertical space. **JsBarcode resolves `marginTop`/`marginBottom` with a falsy check,
so `0` does not mean "no margin" — it falls back to the default `margin: 10`.** The SVG
rendered at **42px** (22 + 10 + 10), not 22px. Verified by rendering both configs under
jsdom against the exact CDN build the page loads:

| config | SVG height |
|---|---|
| `height:25, margin:2` (original) | 29px |
| `height:22, marginTop/Bottom:0` | **42px** |

So the barcode **grew 13px instead of shrinking 4px**. It pushed the detail grid down
13px — MSD/PO off the bottom — and at 42px inside a 1in `overflow:hidden` label the bars
were clipped, so there was nothing valid left to scan. Every layout measurement taken
during the fix attempts was against a 22px barcode that never existed.

**Fixed:** barcode restored to `width: 1, height: 18, margin: 0` — the values the label
used before commit `7f7fb3c`. Preet then reported the bars printing "too bold": `7f7fb3c`
had also raised `width` (the bar MODULE width) from 1 to 1.5, making every bar 50%
thicker. On a thermal printer thick bars bleed together and the reader loses the pattern,
so that bump is a plausible contributor to the scan failure independent of the 42px bug.
Module width is now 0.265mm (CODE128 minimum is 0.25mm). Do not tune these for layout.

**Also found and kept (a genuine, separate defect):** `.label-details` is `flex: 1` with
`align-content: space-evenly`, so it absorbs all leftover height and spreads its three
rows across it, parking MSD/PO hard against the bottom edge — and every attempt to shrink
the header handed the grid *more* height and pushed that row *lower*. Changed to
`align-content: start`, which packs the rows under the separator and leaves the slack as
bottom margin. Typical label bottom clearance ~3px → ~12px.

**Reverted:** the ZPL label (`app.py`, `generate_zpl_label`) was modified twice chasing
this and was never at fault; it is back at its original coordinates. Evidence the floor
prints via the browser **Print Label** button, not Download ZPL: restoring the ZPL to
original did not change the reported symptom.

**Rule overlapping the barcode (same day, my regression):** raising the bar height to 26px
made the barcode taller than the PCN/QTY block (25.2px), so it defined the row height —
and `padding-bottom` had already been removed to close the QTY gap, so the rule landed on
the bars. The two requirements only conflict while both are centred in the row: `.info-left`
is now `align-self: flex-end` (QTY sits on the rule regardless of barcode height) and
`.barcode-section` has `padding-bottom: 4px` (bars clear the rule).

**Verified by rendering, not by arithmetic.** Every earlier attempt was reasoned from a
pixel budget and each one shipped a regression. The label is now rendered headlessly
(Chrome, `templates/pcn/print_label.html` with sample data) and inspected, and the barcode
is decoded from the raster with @zxing/library:

| render | result |
|---|---|
| typical MPN, 4x | layout correct, no overlap, MSD/PO clear |
| long wrapping MPN, 4x | layout correct, MSD/PO clear |
| 203dpi (printer's real resolution) | **CODE128 decodes → "46891"** |
| 1x (worst case) | **CODE128 decodes → "46891"** |

So the symbol KOSH generates is valid and rasterizes cleanly at print resolution. If a
PRINTED label still will not scan, the remaining causes are physical, not in this code:
thermal darkness set too high (bars bleed together — consistent with the "too bold"
report), print scale not 100% in the browser dialog (any "fit to page" distorts the module
widths), or the wrong paper size selected.

**Still open:** a long MPN that wraps to two lines leaves ~2.9px bottom clearance — fits,
but with little margin. The original top-clipping report is addressed in the browser path
only; no ZPL-printed label has been confirmed bad.

---

# ✅ Definition of done (what "fixed" will finally mean)

An issue is closed ONLY when all of the following hold — no exceptions, no "deployed =
done":

1. One on-hand number, one source of truth; Warehouse Inventory and PCN History always
   equal (kills WI-2, PH-1).
2. A part is in exactly one place — bin **or** floor, never both (kills the double-count).
3. Renaming a part carries its stock with it, so pick/edit/shortage all see it (kills
   SR-3, WI-1, PK-1).
4. Shortage report is accurate: exact MPN only, real BOM substitutes included (ZSUB shown
   as ZSUB), correct ACI PN **and line-item number**, individual PCNs on their own lines,
   real on-hand (not bin+floor summed), and no bogus "MFG FLOOR" location
   (kills SR-1..SR-4, SR-8, SR-9).
5. Restock never refuses parts physically in hand (kills RS-1).
6. Kitting never signs her out (kills SO-1).
7. Proven on a copy of real data on staging, then **Theresa signs off** against this
   exact list.

Until every one of these is true, everything above stays 🔴 **UNFIXED.**
