# Bug #3 - Executive Summary
## 🟨 PCN History Page Crashed for Every Real PCN

**Completed:** 06/18/2026

---

## 🎯 The Fix in 30 Seconds

**Problem:** PCN History crashed with "Error loading PCN history: 0" for every real PCN

**Root cause:** RealDictCursor returns dict, code tried to access by index `[0]` → KeyError

**Fix:** Added column alias + read by name: `anchor_row['total']` instead of `anchor_row[0]`

**Impact:** 100% of PCN History searches fixed

**Risk:** 🟢 Very Low (simple type fix)

**Status:** ✅ Fixed & Deployed (commit `069819e`)

---

## 🔧 What Changed

### Code Change (2 lines at 1 location)

```python
# BEFORE (buggy):
SELECT COALESCE(SUM(onhandqty), 0)  # No alias
...
anchor = int(anchor_row[0])  # Index access ❌

# AFTER (fixed):
SELECT COALESCE(SUM(onhandqty), 0) AS total  # ✅ Add alias
...
anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0  # ✅ Dict access
```

**File modified:**
- `app.py` @ L6556, L6561

---

## ✅ Verification

### Fix is Active in Production

**Location:** `app.py` line 6561

```python
anchor = int(anchor_row['total']) if anchor_row and anchor_row.get('total') is not None else 0
```

**Verified:** 2026-06-23 ✅

---

## 📊 Impact

| Metric | Value |
|--------|-------|
| PCN History searches working | 100% (was 0%) |
| Users affected | All (page was completely broken) |
| Crash rate | 0% (was 100%) |

---

## 🔍 Root Cause

**Cursor type mismatch:**

```python
# RealDictCursor returns dict, not tuple:
cursor = conn.cursor(cursor_factory=RealDictCursor)
row = cursor.fetchone()
# row is {'total': 123}, NOT (123,)

# Accessing by index fails:
row[0]  # ❌ KeyError: 0 (dict has no integer keys)

# Accessing by name works:
row['total']  # ✅ Returns 123
```

---

## 🎓 Key Learnings

### Why Tests Didn't Catch It
- Unit tests used **plain cursor**
- Production used **RealDictCursor**
- Different cursor types, different behavior

### Prevention
- ✅ Always use column aliases (`SELECT expr AS name`)
- ✅ Test with same cursor type as production
- ✅ Access dict results by key, not index

---

## 📁 File Structure

```
bug03-pcn-history-page-crashed/
├── README.md
├── BUG-03-SUMMARY.md (this file)
├── BUG-03-COMPLETE-ANALYSIS.md
├── bug-03-verification-queries.sql
└── test-bug-03.py
```

---

## ✅ Status: COMPLETE

**Bug #3:** ✅ **FIXED, VERIFIED, DOCUMENTED**

---

**Last updated:** 06/23/2026  
**Version:** 1.0
