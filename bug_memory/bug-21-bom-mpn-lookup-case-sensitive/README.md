# Bug 21 — Generate-PCN MPN dropdown empty (case-sensitive BOM lookup)

**Date:** 2026-06-29 · **Severity:** High · **Area:** BOM Loader / Generate PCN · **Status:** ✅ Fixed & deployed (commit `73d51e8`)

## Issue
On the Generate PCN page the MPN dropdown populated with nothing ("No MPNs found in BOM for this part"), so the user couldn't pick an MPN and the form blocked submission — even though the same line's MPN was visible on the job/BOM display.

## Example
BOM part `8805L-5` (MPN `CMF50221R00FHEB`). The endpoint returned `[]` for `8805l-5` (lower-case, e.g. scanned) but the right MPN for exact case.

## Root cause
`/api/bom/mpns/<part>` (`api_get_mpns_for_part` in `app.py`) matched with a **case-sensitive** `WHERE aci_pn = %s`. Every other part lookup in KOSH normalizes with `UPPER()`; this endpoint was the lone holdout.

## Fix
`WHERE UPPER(aci_pn) = UPPER(%s)`. Code-only, no data migration.

> ⚠️ This was a real latent fix but was NOT the root cause of the user's
> original "BOM Loader not working" report — see **bug 22** for the actual cause
> (the parser dropping lines). Kept because it's a genuine bug.

## Guards
- `tests/regression_tests.py::test_bom_mpns_lookup_is_case_insensitive`
- `verify-bug-21-fix.py` (this folder) — run inside the container.

## Verify
```
docker cp verify-bug-21-fix.py stockandpick_webapp:/tmp/ && \
docker exec stockandpick_webapp python3 /tmp/verify-bug-21-fix.py
```
