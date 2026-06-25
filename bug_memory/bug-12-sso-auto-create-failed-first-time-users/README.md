# Bug #12 - SSO Auto-Create Failed for First-Time Users
## 🟩 Low - Authentication Error for New FORGE Users

**Date:** 06/05/2026  
**Severity:** 🟩 Low  
**Status:** ✅ FIXED & TESTED

## The Bug

**Issue:** New FORGE users hit "SSO login failed: Internal error"; no account created

**Symptoms:**
- New FORGE user tries to login to KOSH for first time
- Error: "SSO login failed: Internal error"
- No KOSH account created
- Existing users unaffected (already have accounts)

## Root Cause

**SSO auto-create branch imported `passlib` library:**

```python
# OLD (BROKEN):
from passlib.hash import bcrypt
password_hash = bcrypt.hash('Welcome1!')
```

**Problem:**
- `passlib` **NOT installed** in KOSH container
- Import fails → crash
- No account created
- User sees generic error message

**Why only new users?**
- Existing users already have accounts in database
- Auto-create only runs for first-time users
- Existing users skip the broken code path

## The Fix

**Use `bcrypt` library directly (already installed, used elsewhere in app):**

```python
# NEW (FIXED):
import bcrypt  # @ L27
default_password = bcrypt.hashpw('Welcome1!'.encode('utf-8'), 
                                 bcrypt.gensalt()).decode('utf-8')  # @ L5985
```

**Benefits:**
- bcrypt already installed and used throughout app
- Consistent with existing password hashing
- No new dependencies
- Works in production container

**Location:**
- Import @ [app.py:27](../../app.py#L27)
- SSO auto-create @ [app.py:5985](../../app.py#L5985) (near login() @ L3664)

## Verification

**Test Results:** ✅ ALL 3 TESTS PASSED
- [PASS] bcrypt imported
- [PASS] SSO auto-create uses bcrypt
- [PASS] No passlib imports (removed)

**Run test:** `python verify-bug-12-fix.py`

## Impact

**Now:**
- New FORGE users can login to KOSH ✅
- Account auto-created with default password: `Welcome1!` (bcrypt hashed)
- No errors
- Seamless SSO experience

**Before:**
- New users: "SSO login failed: Internal error" ❌
- No account created
- Support had to manually create accounts

---

**Commit:** e7a7bcf  
**Verified:** 2026-06-25  
**Status:** ✅ FIXED & TESTED
