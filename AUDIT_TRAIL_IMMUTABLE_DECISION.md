# Audit Trail Immutability Decision
**Date:** October 29, 2025
**Decision:** PCN History & Database table remains IMMUTABLE
**Status:** ✅ IMPLEMENTED AND TESTED

---

## Executive Summary

After careful consideration, we decided that the **PCN History & Database table should NOT sync with the Inventory table** when edits are made. This preserves the integrity of the audit trail and ensures historical accuracy.

---

## The Question

**Should editing an inventory item also update related PCN History records?**

### Two Options Considered:

**Option A: Sync (Keep Consistent)**
- When inventory job changes from "6432" → "NEW-6432"
- All PCN history transactions also update to show "NEW-6432"
- Everything looks consistent across all pages

**Option B: Don't Sync (Preserve History)**
- When inventory job changes from "6432" → "NEW-6432"
- Inventory shows "NEW-6432"
- PCN history still shows "6432" (what it was called when transaction happened)
- Creates new UPDATE log with "NEW-6432"

---

## Decision: Option B (Immutable Audit Trail)

**Reason:** The PCN History & Database table is an **audit trail**, not a current status display. Audit trails should be immutable to maintain historical accuracy and compliance.

---

## Benefits of Immutable Audit Trail

### 1. Historical Accuracy
**What it means:** You can see what things were actually called at any point in time

**Example:**
```
January 5, 2025:  Job was called "6432"
                  → Transaction logs: item="6432"

February 10, 2025: Renamed to "NEW-6432"
                   → Inventory shows: "NEW-6432"
                   → Old transactions still show: "6432" (historical fact)
                   → New UPDATE log shows: "NEW-6432" (current name)
```

**Why it matters:** You can prove what the job was called when the transaction happened.

---

### 2. Audit Trail Integrity
**What it means:** Transaction logs are never modified after creation

**Benefits:**
- ✅ Compliant with audit standards
- ✅ Immutable record of events
- ✅ Cannot be tampered with
- ✅ Trustworthy for investigations

**Example:**
```
If someone claims "we stocked 100 units of job NEW-6432 in January"
You can check the log and see:
  → January transaction shows item="6432" (not NEW-6432)
  → Proves the claim is inaccurate
```

---

### 3. Regulatory Compliance
**What it means:** Many industries require unchangeable transaction logs

**Industries that require this:**
- Manufacturing (FDA, ISO audits)
- Finance (SOX compliance)
- Healthcare (HIPAA)
- Any business with external audits

**Why it matters:** If auditors see that historical transactions change when inventory is edited, they may reject the audit trail as unreliable.

---

### 4. Track Name Changes Over Time
**What it means:** You can see the evolution of item names

**Example:**
```
PCN 12345 Transaction History:
- Jan 5:  STOCK   item="6432"        qty=100
- Feb 10: UPDATE  item="NEW-6432"    qty=100  (name change)
- Mar 15: PICK    item="NEW-6432"    qty=50   (using new name)
```

You can clearly see:
- Original name: "6432"
- Name changed on Feb 10
- New transactions use new name

---

## Trade-offs (What We Accept)

### 1. Data Appears "Inconsistent"
**Issue:** Inventory shows "NEW-6432" but old transactions show "6432"

**Why This is OK:**
- This is **historically accurate**, not inconsistent
- The transaction happened when it was called "6432"
- That's the correct historical record

**How to Handle:**
- Educate users that history shows original names
- Use UPDATE logs to track name changes
- Current inventory always shows current name

---

### 2. Searching is Harder
**Issue:** If you search for "NEW-6432" in PCN history, you won't find transactions from when it was called "6432"

**Workaround:**
- Look at the current inventory to find the PCN
- Search PCN history by PCN number (not job name)
- PCN never changes, so you'll find all transactions

**Example:**
```
1. Check inventory: "NEW-6432" has PCN 12345
2. Search PCN history: Search for PCN "12345"
3. Find all transactions, even old ones with different names
```

---

## Implementation Details

### Stored Procedure: `pcb_inventory.update_inventory()`

**What it does:**
1. ✅ Updates inventory record (job, quantity, location, etc.)
2. ✅ Creates NEW transaction log with current values
3. ❌ Does NOT update old transaction records

**Code (Lines 339-352 in init_functions.sql):**
```sql
-- Update the inventory record
UPDATE pcb_inventory."tblPCB_Inventory"
SET
    job = p_job,
    pcb_type = p_pcb_type,
    qty = p_quantity,
    location = p_location,
    pcn = COALESCE(p_pcn, pcn),
    migrated_at = CURRENT_TIMESTAMP
WHERE id = p_id;

-- Log the update as a NEW transaction (historical transactions remain unchanged)
-- This preserves audit trail integrity - old transactions show what actually happened
INSERT INTO pcb_inventory."tblTransaction" (
    trantype, item, pcn, tranqty, loc_from, loc_to, userid, migrated_at
) VALUES (
    'UPDATE',
    p_job,
    COALESCE(p_pcn, v_old_pcn),
    p_quantity - v_old_qty,
    v_old_location,
    p_location,
    p_username,
    CURRENT_TIMESTAMP
);
```

**Key Points:**
- No UPDATE query on transaction table
- Only INSERT (create new log)
- Old logs remain unchanged forever

---

## Testing Results

### Test Case: Job Name Change

**Setup:**
- Inventory ID 1038: job="37358-UPDATED", pcn=43294
- Existing transactions:
  - ID 165842: item="37358-UPDATED" (UPDATE log)
  - ID 165834: item="37358-UPDATED" (STOCK log)

**Action:**
```sql
SELECT pcb_inventory.update_inventory(
    1038,              -- id
    '37358-FINAL',     -- new job name
    'Bare',            -- pcb_type
    11,                -- quantity
    '8000-8999',       -- location
    43294,             -- pcn
    'test_revert'      -- username
);
```

**Result:**
```
Inventory:
  id=1038, job="37358-FINAL", pcn=43294  ✅ UPDATED

Transactions:
  ID 165843: UPDATE   item="37358-FINAL"   userid="test_revert"  ✅ NEW LOG
  ID 165842: UPDATE   item="37358-UPDATED" userid="test_user"    ✅ UNCHANGED
  ID 165834: STOCK    item="37358-UPDATED" userid="guest"        ✅ UNCHANGED
```

**Verification:** ✅ PASS
- Inventory updated to new name
- New UPDATE log created with new name
- Old transactions remain unchanged
- Audit trail integrity preserved

---

## User Workflow

### Editing Inventory:

**Step 1:** User edits inventory item
- Goes to Inventory tab
- Clicks yellow pencil (edit button)
- Changes job from "6432" to "NEW-6432"
- Clicks Save

**Step 2:** What happens:
- ✅ Inventory updates to "NEW-6432"
- ✅ New UPDATE transaction created in history
- ✅ Old transactions remain unchanged

**Step 3:** Viewing results:
- Inventory page shows: "NEW-6432" (current)
- PCN History page shows:
  - Old transactions: item="6432" (historical)
  - New UPDATE log: item="NEW-6432" (current)

---

### Understanding the History:

**If user sees different names in PCN history:**

**Question:** "Why does the history show '6432' but inventory shows 'NEW-6432'?"

**Answer:**
- The transaction happened when it was called "6432"
- That's what it was actually called at that time
- The name was later changed to "NEW-6432"
- Look for UPDATE transactions to see name changes
- This is historically accurate, not an error

---

## Comparison: Before vs After

### Before This Decision:
❓ Undefined behavior - could go either way

### After This Decision:
✅ Clear policy: Transaction history is immutable

### If We Had Chosen to Sync:
❌ Audit trail unreliable
❌ Historical data changed retroactively
❌ Compliance issues
❌ Cannot track name changes

### With Immutable Approach:
✅ Audit trail reliable
✅ Historical data preserved
✅ Compliance-friendly
✅ Can track all changes over time

---

## Related Components

### Tables Affected:

**1. `pcb_inventory.tblPCB_Inventory`**
- **Behavior:** Always shows current values
- **Updates:** When user edits via yellow pencil
- **Example:** job="NEW-6432" (current name)

**2. `pcb_inventory.tblTransaction`**
- **Behavior:** Immutable logs of past events
- **Updates:** Only INSERT (never UPDATE old records)
- **Example:** Old logs show "6432", new logs show "NEW-6432"

### Pages Affected:

**1. Inventory Tab**
- Shows current inventory values
- Edit feature updates inventory only
- Displays most recent information

**2. PCN History & Database Tab**
- Shows historical transaction logs
- Displays what actually happened at that time
- May show old item names (this is correct)

**3. Generate PCN Page**
- PCN History & Database table at bottom
- Shows all transactions for PCN
- Name evolution visible through UPDATE logs

---

## Documentation for Users

### Key Points to Communicate:

1. **Inventory = Current Status**
   - Always shows the latest information
   - What things are called RIGHT NOW

2. **PCN History = Historical Record**
   - Shows what happened BACK THEN
   - Names reflect what they were called at that time
   - This is correct and intentional

3. **UPDATE Logs = Change Records**
   - Look for trantype="UPDATE" to see changes
   - Shows before → after values
   - Tracks when names/quantities changed

4. **Search by PCN**
   - Best way to find all related transactions
   - PCN never changes, so finds everything
   - More reliable than searching by job name

---

## Alternative Considered and Rejected

### Sync Approach (Rejected)

**What it would do:**
- Update old transaction records when inventory changes
- Make everything look consistent

**Why we rejected it:**
❌ Loses historical accuracy
❌ Violates audit principles
❌ Cannot prove what happened in the past
❌ Compliance risk
❌ Data integrity concerns

**Example of the problem:**
```
January:  Stock 100 units of "6432"
          → Transaction: item="6432", qty=100

March:    Rename to "NEW-6432" in inventory
          → Transaction CHANGES to: item="NEW-6432", qty=100

Problem:  Now it looks like we stocked "NEW-6432" in January
          But that name didn't exist in January!
          Historical record is now false.
```

---

## Future Considerations

### If Requirements Change:

**Scenario:** Business decides they need synced data after all

**Migration Path:**
1. Keep immutable transaction log as primary audit trail
2. Create SEPARATE "current inventory movements" view
3. This view would show all transactions with current names
4. Use it for operational purposes
5. Keep original log for compliance

**This way you get both:**
- Immutable audit trail (compliance)
- Synchronized view (operational convenience)

---

## Maintenance Notes

### For Developers:

**DO:**
- ✅ Always INSERT new transaction logs
- ✅ Never UPDATE old transaction records
- ✅ Preserve migrated_at timestamps
- ✅ Log the username who made changes

**DON'T:**
- ❌ Update historical transaction records
- ❌ Delete transaction logs (only in exceptional cases with approval)
- ❌ Modify timestamps on existing records
- ❌ Skip logging transactions

### Code Review Checklist:

When reviewing changes to `update_inventory()`:
- [ ] Does it UPDATE old transaction records? (Should be NO)
- [ ] Does it INSERT a new transaction log? (Should be YES)
- [ ] Are old records left unchanged? (Should be YES)
- [ ] Is username captured? (Should be YES)
- [ ] Is timestamp automatic? (Should be YES)

---

## References

### Standards & Best Practices:

**Audit Trail Requirements:**
- GAAP (Generally Accepted Accounting Principles)
- SOX (Sarbanes-Oxley Act)
- ISO 9001:2015 (Quality Management)
- 21 CFR Part 11 (FDA Electronic Records)

**Key Principle:**
> "Audit trail records should be time-stamped, secure, and **not modifiable** after creation."

---

## Conclusion

The decision to keep PCN History & Database immutable is the correct choice for:
- ✅ Data integrity
- ✅ Audit compliance
- ✅ Historical accuracy
- ✅ Regulatory requirements
- ✅ Business credibility

**Trade-off:** Slightly less convenient searching, but this is far outweighed by the benefits of a reliable audit trail.

---

**Decision Made:** October 29, 2025
**Implemented:** October 29, 2025
**Tested:** October 29, 2025
**Status:** 🟢 **PRODUCTION READY**
**Approach:** ✅ **IMMUTABLE AUDIT TRAIL**
