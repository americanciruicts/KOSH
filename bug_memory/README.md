# KOSH Bug Memory

Permanent, version-controlled record of **every bug fixed in KOSH** — what the bug
was, the root cause, what fixed it, and how it's guarded. Lives in the repo so the
history can never be lost (the recurring-bug problem was partly *because* fixes
lived only in code/conversation and weren't written down).

## Files
- **`BUG_HISTORY.md`** — the full chronological log (newest at top). Add a new entry
  every time a bug is fixed.

## How to add an entry (do this for EVERY bug fix, going forward)
Prepend a new block to `BUG_HISTORY.md` using this template:

```
## YYYY-MM-DD — <short title>
- **Reported by:** <who / how>
- **Symptom:** what the user saw.
- **Root cause:** the actual underlying reason.
- **Fix:** what was changed (file/function), and the key idea.
- **Scope/impact:** rows/jobs/PCNs affected; any data backfill done.
- **Guard:** regression test name (so it can't silently come back).
- **Commit:** <hash>  |  **Deployed:** <yes/no + date>
```

## Rules
1. **One entry per fix**, even small ones — recurring bugs are how we got here.
2. Always note the **regression test** that locks the fix. No test = it will come back.
3. **Code fix ≠ data fix.** If the bug already created bad data in production, record
   the separate data-remediation pass (what query, how many rows, audit tag).
4. Keep root-cause honest — link recurring ones to the underlying data-model issue
   (the incomplete/ambiguous imported Access ledger) so the redesign stays informed.
