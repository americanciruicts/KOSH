# SR-5 investigation — "shortage report drops BOM lines" (2026-07-22)

**Verdict: the proposed fix (key `DISTINCT` on `b.line` instead of `b.aci_pn`) is a
REGRESSION, not a fix. The current query drops ZERO genuinely-distinct real BOM lines.
The "missing/extra lines" come from LEGACY migration debris, not the query.**

Investigated read-only against the real staging DB (`kosh`, localhost:5434). No code changed.

---

## The proposed change and why it's wrong

Proposal: in `_SHORTAGE_MATCH_SQL` (and the two job_detail copies) change
`SELECT DISTINCT ON (b.aci_pn)` → `DISTINCT ON (b.line)` so "every line survives."

ACI part numbers are `job-line` (e.g. `6846-35` **is** line 35). For clean data `aci_pn`
and `line` are **1:1**, so `DISTINCT ON (aci_pn)` and `DISTINCT ON (line)` produce the same
rows — **except** on corrupted rows, where `DISTINCT ON (line)` makes things worse.

Every row that `DISTINCT ON (aci_pn)` collapses is one of two kinds, and **both should be
collapsed**:

1. **Parser/migration phantoms** — a multi-line DESCRIPTION cell was split into extra rows,
   dumping description text into the `line` column. Real examples on live data:
   - `7584-82`  : real line `82`  + phantom line `{MAX. TEMP 260°C FOR 5 SEC`
   - `8532L-360`: real line `360` + phantom line `(USE WITH ITEM 50`
   - `6846-35`  : real line `35`  + phantom line `(PLACED BOTTOM SIDE`
   - fully column-shifted debris: `aci_pn='2'`, `mpn='7584-103'`, `line=<description>`
2. **ZSUB substitutes** — e.g. job `8727L`, part `8727L-10` is ONE terminal-ring position
   (line 3) with FOUR ZSUB alternates (lines 4–7, DESC = "ZSUB").

`DISTINCT ON (aci_pn) ... ORDER BY qty DESC` correctly keeps the real row (qty>0) and drops
the phantom/ZSUB. Keying on `b.line` would instead:
- turn phantom rows into **fake line items** (a "line" literally named `(USE WITH ITEM 50`), and
- **duplicate ZSUB positions** (job 8727L's one terminal ring would appear 5×).

## Proof no real line is missing today
Ran the actual `_SHORTAGE_MATCH_SQL` for job **6846**:
- 65 real numeric BOM lines in the raw BOM → report emits **all 65** (plus 1 leaked debris
  row for `aci_pn='2'`). **Real lines missing: NONE.**

## The phantoms are LEGACY, not a live bug
- 6846 real rows created **2026-03-03**; its phantom rows created **2026-04-03** (separate event).
- Phantom rows (non-numeric `line`) created per month: **Mar 12, Apr 1,678, May 0, Jun 0, Jul 0.**
- The April 2026 bulk import (Access/MDB migration) created essentially all debris. The
  current openpyxl uploader (`api_bom_parse`, reads cells `values_only`) does **not** split
  multi-line cells and has produced **zero** phantoms since May 2026.

## job_rev predicate
Not the culprit. It keeps the latest revision by `created_at` (e.g. `6858L` rev Q→T), which
is correct. Most "multi-rev" jobs are themselves migration corruption (the `job_rev` column
holding other job numbers / manufacturer names).

---

## Recommended path (nothing changed yet)
1. **Do NOT change the DISTINCT key.** It is correct; the change regresses the report.
2. **Get Theresa's specific example** of a job + line she says is missing. On every job I can
   inspect, no real line is missing — so we need her actual case to know what she sees.
3. **Optional staging-only data cleanup** (destructive → needs Preet's OK): delete the ~1,690
   legacy debris rows (non-numeric `line`, column-shifted) from `tblBOM` so they can never
   leak onto a report as junk. Validate on staging first; it must remove ONLY debris and zero
   real lines (real lines all have numeric `line`).

This is filed instead of a "fix" on purpose: per the KOSH trust history, marking SR-5 fixed
with a change that actually makes the report worse is the exact whack-a-mole pattern to avoid.

---

## FIX APPLIED 2026-07-22 — the real SR-5 cause was a mislabeled COUNT, not dropped lines

Investigating job **6588L** pinned it down: the report header over-counted. `_persist_shortage_report`
set `total_lines` from `SELECT COUNT(*) FROM tblBOM` (raw rows = **115**), but the report body
enumerates one row per real BOM line (**83**). The 32-row gap is ZSUB/alternate substitute rows.
So the banner read *"35 of 115 BOM lines"* while showing 83 — i.e. it **looked like 32 lines were
missing**. That is the "missing several lines" perception; no line was ever actually dropped.

**Change:** `total_lines` now stores the number of line items the report actually enumerates
(`len(report_items)`), so header == body. The raw `COUNT(*)` is kept ONLY to detect a job with no
BOM at all. The `DISTINCT ON (aci_pn)` line collapsing is UNCHANGED (it is correct).

**The job_detail "form" was already correct** — it counts `len(set(line_no))` over the collapsed
set, not raw rows. No change needed there.

**Verified (staging):**
- 6588L: header 115 → **83**, body 83 → MATCH. 40-line job 6366L: **40 → 40** (no ZSUBs, unchanged).
- Neither job drops any real line (all real numeric lines emitted); 0 phantom rows on both.
- Behavioral gate green (p1/p2/p5). Rebuilt + redeployed staging web image (docker compose); end-to-end
  report generation for both jobs confirms header == body. Existing SAVED reports keep their old stored
  count until regenerated (the value is a snapshot).

Still NOT confirmed by Theresa; still staging-only. The ~1,690 legacy debris rows remain (optional
cleanup, needs Preet's OK) but they do not drop real lines.
