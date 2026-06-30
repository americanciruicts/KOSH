# Bug 23 — Shortage report same-MPN visibility over-matched (1234 also showed 12345/123456)

**Date:** 2026-06-30 · **Severity:** High · **Area:** Shortage report / same-MPN visibility · **Status:** ✅ Fixed & deployed (commit `9a41bfe`)

## Issue
The "same-MPN stock under a different part number" rows on the shortage report listed parts whose MPN merely **started with** the BOM line's MPN — so a line showed piles of unrelated parts ("pages and pages" of 12345/123456 noise under a 1234 line).

## Example (real data)
BOM MPN `1.5KE15` (15 V TVS) pulled in stock `1.5KE150CA` (150 V — a different part); `ERJ6ENF249` pulled in `ERJ6ENF2491V / 2492V / 2493V`. Job `8858L` line `2N7002` pulled in 18 distinct variants (2N7002DW-7-F, 2N7002K-TP, …).

## Root cause
The match used normalized exact **OR a directional prefix** `char_length(bom_key) >= 6 AND p.nmpn LIKE bom_key || '%'`. Normalization strips separators (`-# ./`), so the prefix branch couldn't tell a reel suffix from a value-continuation — for numeric/short MPNs it matched longer DISTINCT parts.

## Fix
Removed the prefix branch — **EXACT match only**. Chemring = strict exact-string; all other customers = normalized exact (`p.nmpn = bl.bom_key`). Decision confirmed with Preet ("Exact MPN only"). Two spots in `_SHORTAGE_MATCH_SQL`. Read-path only, no data mutated.

## Guards
- `tests/regression_tests.py::test_shortage_report_same_mpn_is_exact_not_prefix`
- `verify-bug-23-fix.py` (this folder).

## Verify
```
docker cp verify-bug-23-fix.py stockandpick_webapp:/tmp/ && \
docker exec stockandpick_webapp python3 /tmp/verify-bug-23-fix.py
```
(Runs entirely inside a rolled-back transaction — persists nothing.)
