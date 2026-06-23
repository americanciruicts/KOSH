# KOSH Bug Memory

Permanent, version-controlled record of **every bug fixed in KOSH** — what the issue
was, an example, what was fixed, when, and whether it actually handled it. Lives in the
repo so the history can never be lost (the recurring-bug problem was partly *because*
fixes lived only in code/conversation and weren't written down).

## Files
- **`BUG_HISTORY.md`** — the full log (newest bug at top). One entry per distinct bug.

## Entry template (for a NEW distinct bug)
Prepend a new block to `BUG_HISTORY.md`:

```
## YYYY-MM-DD — <short title>   [status: FIXED | PARTIAL | RECURRING | OPEN]
- **Issue (what was wrong):** the symptom the user saw.
- **Example:** concrete PCNs/jobs/numbers that show it.
- **Root cause:** the actual underlying reason.
- **Fixed (what changed):** the change (file/function) and the key idea.
- **When:** YYYY-MM-DD | commit `<hash>` | Deployed: yes/no + date.
- **Did it handle it?:** yes / partly — how it was verified.
- **Guard:** regression test name (so it can't silently come back).
- **Scope/impact:** rows/jobs/PCNs affected; any data backfill (separate from code fix).

### Recurrences / new case reports
<!-- Same bug reported again? APPEND a dated line here. NEVER edit/remove the
     original issue, example, or fix above — stack the new occurrence below. -->
```

## THE KEY RULE — recurrences go UNDER the old entry (never delete old fix/example)
When a bug you already logged is **reported again** (a new job, a new PCN, a new
variation), do **NOT** create a fresh top-level entry and do **NOT** rewrite or remove
the original fix/example. Instead, append a dated line to that bug's **Recurrences /
new case reports** sub-section:

```
- YYYY-MM-DD — reported by <who>; example <PCN/job>; same root cause? <yes/no>;
  what was still broken; additional fix (commit `<hash>`, deployed Y/N).
```

This makes recurring bugs visible at a glance — if an entry's Recurrence list keeps
growing, the underlying fix isn't holding and the problem is likely **data-model
level** (see the "Warehouse Inventory != PCN History" and "Recurring root cause"
sections in `BUG_HISTORY.md`), which is what the inventory/PCN/transaction rebuild is for.

## Other rules
1. **One entry per distinct bug.** Recurrences stack under it (above rule).
2. Always note the **regression test**. No test = it will come back.
3. **Code fix ≠ data fix.** Rewriting buggy code stops new bad data; bad data already
   in prod needs a separate remediation pass — record it (query, rows, audit tag).
4. Keep root-cause honest; link recurring ones to the underlying dirty Access-import
   data model so the redesign stays informed.
