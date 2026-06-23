# Bug #2 - On-Hand Reconcile Wiped Fresh Restocks
## 🟥 Critical - Inventory / Reconcile

---

## Quick Summary

**Date Reported:** 06/22/2026  
**Reported By:** Preet  
**Status:** ✅ Fixed & Deployed

**Issue:** Fresh restocks were being silently zeroed hours after saving

**Impact:** 62 rows backfilled, all future restocks protected

**Fix:** Never lower rows whose latest transaction is RESTOCK/STOCK

---

## Files in This Folder

```
bug02-onhand-reconcile-wiped-fresh-restocks/
├── README.md                         (this file - quick reference)
├── BUG-02-SUMMARY.md                 (executive summary)
├── BUG-02-COMPLETE-ANALYSIS.md       (full technical analysis)
└── bug-02-verification-queries.sql    (7 SQL validation queries)
```

---

## The Bug Explained

### What Was Happening

The on-hand reconcile process works by replaying the transaction ledger to compute stock levels. However:

1. **Historical ledger has gaps** (more PICKs than stock-ins from Access migration)
2. **Replay goes negative** for parts with incomplete history
3. **Clamped to 0** (can't have negative stock)
4. **Lower-only guard** sees 0 < current_qty
5. **Overwrites fresh restock** to 0 ❌

**Example:**
- **07:30** - User restocks PCN 42137 to 15 units ✓
- **11:31** - Reconcile runs, replays ledger → computes 0 (incomplete history) → **zeros the restock** ❌

### The Fix

**Protection logic added:**

```sql
-- Check latest transaction type
latest_event AS (
    SELECT pcn, mpn_key, trantype AS last_type
    FROM tblTransaction
    WHERE ...
    ORDER BY tran_time DESC
    LIMIT 1 PER (pcn, mpn_key)
)

-- Guard: Don't lower if latest is fresh receipt
AND COALESCE(latest_event.last_type, '') NOT IN ('RESTOCK', 'STOCK')
```

**Result:**
- Latest = RESTOCK/STOCK → **protected** (keep warehouse value)
- Latest = PICK/PURGE → **allowed** (can lower for phantom correction)

---

## Verification

### Fix Location

**File:** `app.py`  
**Line:** 3237

```sql
AND COALESCE(le.last_type, '') NOT IN ('RESTOCK','STOCK')
```

**Verified:** 2026-06-23 ✅

### Run Verification Queries

```bash
psql -U aci -d kosh -f bug-02-verification-queries.sql
```

**Critical checks:**
- Query #1: Show protected rows (latest = RESTOCK/STOCK)
- Query #2: Find parts with incomplete ledger
- Query #4: Recent restocks that would have been zeroed

---

## Impact

### Immediate
- **62 rows backfilled** (audit: `restock_wipe_backfill_20260622`)
- All future restocks protected from reconcile zeroing

### Long-term
- ✅ User edits now persist reliably
- ✅ No silent data loss
- ✅ Warehouse Inventory = PCN History consistency
- ✅ False shortages prevented

---

## How to Test

### Manual Test

1. Find a part with incomplete ledger:
   ```sql
   -- Use Query #7 from verification queries
   ```

2. Manually restock to known quantity (e.g., 20 units)

3. Note the time

4. Wait for reconcile to run (or trigger manually)

5. Check quantity

**Expected:** Quantity remains 20 (not zeroed) ✅

---

## Technical Details

### Root Cause

**Incomplete ledger data:**
- Access migration imported transactions
- Some parts have more PICKs than stock-ins
- Ledger replay: stock-ins (+30) - picks (-50) = **-20** → clamped to 0
- Reconcile saw: computed 0 < warehouse 15 → lowered to 0 ❌

### The Protection

**Latest transaction check:**
- `DISTINCT ON (pcn, mpn_key)` + `ORDER BY tran_time DESC`
- Gets most recent material transaction
- If RESTOCK/STOCK → warehouse value is authoritative
- If PICK/PURGE → ledger replay is authoritative

### Edge Cases

| Scenario | Latest Event | Protected? | Behavior |
|----------|--------------|------------|----------|
| Fresh restock | RESTOCK | ✅ Yes | Keep warehouse value |
| Sequential restocks | RESTOCK (latest) | ✅ Yes | Keep latest value |
| Restock then pick | PICK | ❌ No | Allow correction |
| Only picks, no restocks | PICK | ❌ No | Allow correction |
| New part, no txns | NULL | ❌ No | Normal operation |

---

## Related Bugs

This fix works with:
- **Bug #4:** RESTOCK-after-recount doubling (anchored history)
- **Bug #10:** Phantom stock (relabel neutralization)

---

## Data Remediation

**Backfill performed:** 2026-06-22

```sql
-- 62 rows identified as zeroed by reconcile
-- Restored from PCN History transaction log
-- Audit trail: restock_wipe_backfill_20260622
```

**Verification method:**
- Cross-checked warehouse qty vs PCN History
- Verified against latest RESTOCK/STOCK transaction
- Physical inventory confirmation (sample)

---

## Lessons Learned

### What Went Wrong
1. Assumed ledger was complete and authoritative
2. Didn't distinguish fresh updates from historical values
3. No logging for reconcile actions (silent failure)

### What We Fixed
1. Context-aware reconciliation (check latest transaction)
2. Protect fresh receipts, correct phantom stock
3. Surgical fix (only affects RESTOCK/STOCK latest)

### Prevention
- ✅ Consider data quality of legacy imports
- ✅ Distinguish fresh authoritative updates from computed values
- ✅ Test with incomplete ledger scenarios
- ✅ Monitor for "edits not saving" user complaints

---

## Questions & Support

**For code questions:** Review `BUG-02-COMPLETE-ANALYSIS.md`  
**For verification:** Run `bug-02-verification-queries.sql`  
**For deployment:** Already deployed in commit `1958a08`

---

## Timeline

| Date | Event |
|------|-------|
| 06/22/2026 | Bug reported by Preet |
| 06/22/2026 | Root cause identified (incomplete ledger) |
| 06/22/2026 | Fix developed and deployed (commit `1958a08`) |
| 06/22/2026 | 62 rows backfilled (audit trail created) |
| 06/23/2026 | Fix verified in production code |
| _____ | 30-day monitoring (ongoing) |

---

**Status:** ✅ **FIXED AND DEPLOYED**

**Verified by:** Engineering Team  
**Date:** 06/23/2026
