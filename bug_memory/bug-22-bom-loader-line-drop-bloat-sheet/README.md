# Bug 22 — BOM Loader: dropped lines, template bloat, and cross-sheet merge

**Date:** 2026-06-30 · **Severity:** High · **Area:** BOM Loader / client parser (`static/js/bom_parser.js`) · **Status:** ✅ Fixed & deployed

This entry covers three related BOM-Loader fixes from the same session, all the
symptom "the BOM won't load / shows MPN not available":

## 22a — Lines silently dropped (commit `12d525c`)
- **Issue:** generating a PCN for a line said "MPN not available"; most lines were never saved.
- **Proof (prod logs):** job `8517L-2` loaded with `total_items=1` — only line 5 reached `tblBOM`; the user then hammered `/api/bom/mpns/8517L-2-25` ~40× (line 25 never loaded).
- **Cause:** `parseSheet` dropped any row whose detected LINE cell wasn't a clean integer (`isNaN(parseInt(...)) -> continue`).
- **Fix:** a row carrying a real part id (`mpn` or `aci_pn`) is never dropped for a bad LINE cell — kept with a fallback line number. Added `rescued_rows`/`skipped_rows` + a loud partial-parse warning on `/jobs`.

## 22b — Template bloat stalled the in-browser parse (commit `5032bbc`)
- **Issue:** `8517L-2 PARATA 320-0121 BOM FOR ASSEMBLY.xlsx` "would not load".
- **Cause:** its "Assy BOM" tab declared range **A1:AI6588** (6,588 rows) but held only ~11 real rows; the 3.9 MB file made `sheet_to_json` materialize thousands of empty rows, freezing the browser parse. (Server load was fine — this BOM genuinely has only line 5.)
- **Fix:** `parseSheet` recomputes a TIGHT range from the cells that actually exist (`tightRange`) before reading — oversized declared ranges now cost nothing (~96ms → ~7ms on this file).

## 22c — Read ONLY the "BOM to Load" sheet + drop the "job exists" popup (commit `b9c2e89`)
- **Per Preet:** load ONLY the curated "BOM to Load" sheet (no more merging extra lines from "Assy BOM"; falls back to all sheets only if there's no "BOM to Load" tab). And re-uploading an existing job no longer pops the "Job Already Exists" modal — the Load step just replaces (delete-then-insert).

## Note on bug 21
The first attempt at this report shipped a case-insensitive MPN-lookup fix (**bug 21**) — real but the WRONG root cause; the actual fix is 22a above.

## Guards
- `tests/test_bom_parser.js` synthetic fixtures: `bug22:*` (rescue), `junk:*`, `clean:*`, `bloat:*`, `onlyBTL:*`.
- `tests/regression_tests.py::test_bom_load_inserts_every_item_received`, `::test_bom_python_parser_finds_lines_across_sheets`.
- `verify-bug-22-fix.js` (this folder) — runs the shipped parser against the real BOM files + synthetic edge cases.

## Verify (host, needs node + xlsx)
```
NODE_PATH=/tmp/node_modules node verify-bug-22-fix.js
```
