# Bug #3 - PCN History Page Crashed
## 🟨 Medium - PCN History

---

## Quick Summary

**Date Reported:** 06/18/2026  
**Status:** ✅ Fixed & Deployed

**Issue:** PCN History page crashed with "Error loading PCN history: 0" for every real PCN

**Fix:** Changed from index access `row[0]` to dict access `row['total']` for RealDictCursor

**Impact:** PCN History 100% functional again

---

## The Bug Explained

### What Was Happening

Users searched for any PCN in PCN History and got this error:

> Error loading PCN history: 0

**The code:**
```python
# Using RealDictCursor (returns dict)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Query without alias
cur.execute("SELECT COALESCE(SUM(onhandqty), 0) ...")
anchor_row = cur.fetchone()

# ❌ Trying to access dict by index!
anchor = int(anchor_row[0])  # KeyError: 0
```

**Why it failed:**
- RealDictCursor returns `{'coalesce': 123}` (dict)
- Code tried `row[0]` (index access)
- Dicts don't have integer keys → KeyError!

### The Fix

```python
# 1. Add explicit alias
SELECT COALESCE(SUM(onhandqty), 0) AS total  # ✅

# 2. Access by key name
anchor = int(anchor_row['total'])  # ✅
```

---

## Verification

### Fix Location

**File:** `app.py`  
**Lines:** 6556, 6561

```python
# Line 6556: Query with alias
SELECT COALESCE(SUM(onhandqty), 0) AS total

# Line 6561: Read by alias
anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0
```

**Verified:** 2026-06-23 ✅

### Manual Test

1. Navigate to PCN History page
2. Enter any real PCN (e.g., 42137)
3. Click "Search"

**Expected:** Transaction history displays (no error) ✅  
**Before fix:** "Error loading PCN history: 0" ❌

---

## Root Cause

### Cursor Type Mismatch

| Cursor Type | fetchone() Returns | Access Method |
|-------------|-------------------|---------------|
| Regular | `(123,)` tuple | `row[0]` ✅ |
| RealDictCursor | `{'col': 123}` dict | `row['col']` ✅ |

**The bug:**
- Tests used **regular cursor** → `row[0]` worked
- Production used **RealDictCursor** → `row[0]` failed

---

## Technical Details

### Why RealDictCursor?

RealDictCursor is useful for returning rows as dicts:

```python
# Regular cursor:
row = cursor.fetchone()
name = row[0]  # Must remember column order!

# RealDictCursor:
row = cursor.fetchone()
name = row['name']  # Self-documenting!
```

### The Catch

Must access by **column name**, not index:

```python
# ✅ GOOD - with alias
SELECT COUNT(*) AS total
row['total']

# ❌ BAD - no alias
SELECT COUNT(*)  
row['count']  # Key name unpredictable!

# ❌ WORSE - index access
row[0]  # KeyError on RealDictCursor!
```

---

## Prevention

### Best Practices

**Always use column aliases:**
```python
# ✅ Good
SELECT SUM(qty) AS total_qty FROM ...

# ❌ Bad
SELECT SUM(qty) FROM ...
```

**Test with production cursor type:**
```python
# ✅ Good
cursor = conn.cursor(cursor_factory=RealDictCursor)  # Match production

# ❌ Bad
cursor = conn.cursor()  # Different from production
```

---

## Related Files

- `BUG-03-COMPLETE-ANALYSIS.md` - Full technical analysis
- `BUG-03-SUMMARY.md` - Executive summary
- `bug-03-verification-queries.sql` - Test queries
- `test-bug-03.py` - Automated tests

---

## Timeline

| Date | Event |
|------|-------|
| 06/18/2026 | Bug discovered (PCN History crashes) |
| 06/18/2026 | Root cause identified (cursor type mismatch) |
| 06/18/2026 | Fix deployed (commit `069819e`) |
| 06/23/2026 | Fix verified, documentation created |

---

**Status:** ✅ **FIXED AND DEPLOYED**

**Verified by:** Engineering Team  
**Date:** 06/23/2026
