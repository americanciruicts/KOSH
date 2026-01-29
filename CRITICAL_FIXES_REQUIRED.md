# CRITICAL FIXES REQUIRED FOR PRODUCTION

## STATUS: IMPLEMENTATION IN PROGRESS

These fixes MUST be implemented before KOSH goes to production to prevent data corruption, race conditions, and system glitches.

---

## PRIORITY 1: CRITICAL DATABASE INTEGRITY (MUST FIX)

### 1. Pick Function Race Condition **[CRITICAL]**
**File:** `migration/stockAndPick/web_app/app.py` lines 567-810
**Risk Level:** 🔴 CRITICAL - Can cause negative quantities

**Problem:**
- Two users can pick from same inventory simultaneously
- Check-then-update pattern allows race condition
- Example: 10 units available, User A picks 10, User B picks 10 → result = -10 units

**Required Fix:**
- Add `SERIALIZABLE` transaction isolation level
- Use `FOR UPDATE` row locks
- Make quantity check and update atomic in single query

**Implementation:**
```python
conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_SERIALIZABLE)
# Lock rows with FOR UPDATE before any operations
```

---

### 2. Stock Function Race Condition **[HIGH]**
**File:** `migration/stockAndPick/web_app/app.py` lines 461-566
**Risk Level:** 🟠 HIGH - Can cause incorrect quantities

**Problem:**
- Multiple concurrent stocks to same PCN can cause incorrect totals
- No row locking before updates

**Required Fix:**
- Add `SERIALIZABLE` isolation
- Use `FOR UPDATE` when checking existing inventory
- Ensure atomic read-modify-write

---

### 3. Restock Validation Missing **[HIGH]**
**File:** `migration/stockAndPick/web_app/app.py` lines 811-930
**Risk Level:** 🟠 HIGH - Allows impossible restocks

**Problem:**
- Can restock more than what's on MFG floor
- Comment says "Allow restocking even if quantity exceeds MFG qty"
- Causes data inconsistency

**Required Fix:**
- Validate `mfg_qty >= quantity` before restocking
- Return clear error if insufficient MFG quantity
- Only allow override with special permission flag

---

## PRIORITY 2: INPUT VALIDATION (PREVENT ATTACKS)

### 4. Missing Backend Validation **[HIGH]**
**Files:** All database functions
**Risk Level:** 🟠 HIGH - Security vulnerability

**Problem:**
- Form validation can be bypassed via direct POST requests
- Database functions don't re-validate inputs

**Required Fix:**
```python
# Add to EVERY database function:
if not isinstance(quantity, int) or quantity < 1 or quantity > 10000:
    return {'success': False, 'error': 'Invalid quantity'}

if not job or len(job) > 50:
    return {'success': False, 'error': 'Invalid job identifier'}
```

---

## PRIORITY 3: FRONTEND STABILITY (PREVENT USER ERRORS)

### 5. Double-Click Prevention Missing **[MEDIUM]**
**Files:** `stock.html`, `pick.html`, `restock.html`
**Risk Level:** 🟡 MEDIUM - Can create duplicate transactions

**Problem:**
- Users can click submit button multiple times
- Each click submits the form
- Creates duplicate stock/pick records

**Required Fix:**
```javascript
let isSubmitting = false;
form.addEventListener('submit', function(e) {
    if (isSubmitting) {
        e.preventDefault();
        return false;
    }
    isSubmitting = true;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Processing...';
});
```

---

### 6. Native Confirm Dialog Unsafe **[MEDIUM]**
**File:** `pick.html` line 789
**Risk Level:** 🟡 MEDIUM - Weak confirmation

**Problem:**
- Uses native `confirm()` dialog
- Can be auto-clicked by scripts
- No state management

**Required Fix:**
- Replace with Bootstrap custom modal
- Add confirmation state tracking
- Disable confirm button after first click

---

## PRIORITY 4: CONNECTION MANAGEMENT

### 7. Inconsistent Cursor Cleanup **[MEDIUM]**
**File:** `app.py` throughout
**Risk Level:** 🟡 MEDIUM - Can leak resources

**Problem:**
- Some functions close cursors, some don't
- Order of cursor.close() vs return_connection() varies

**Required Fix:**
- Standardize all database functions
- Always close cursor in finally block
- Always return connection in finally block
- Handle exceptions in cleanup code

---

### 8. No Connection Pool Monitoring **[LOW]**
**File:** `app.py` lines 366-397
**Risk Level:** 🟢 LOW - Hard to debug issues

**Problem:**
- No visibility into connection pool state
- Can't tell if pool is exhausted

**Required Fix:**
- Add pool statistics tracking
- Create `/health/database` endpoint
- Log connection acquire/return events

---

## IMPLEMENTATION CHECKLIST

### Phase 1: Critical (This Week)
- [ ] Add SERIALIZABLE isolation to pick_pcb
- [ ] Add FOR UPDATE locks to pick_pcb
- [ ] Make pick operation atomic
- [ ] Add SERIALIZABLE isolation to stock_pcb
- [ ] Add FOR UPDATE locks to stock_pcb
- [ ] Add MFG quantity validation to restock_pcb
- [ ] Add input validation to all database functions
- [ ] Test concurrent operations

### Phase 2: High Priority (Next Week)
- [ ] Add double-click prevention to all forms
- [ ] Replace native confirm with custom modal
- [ ] Standardize connection/cursor cleanup
- [ ] Add comprehensive error handling
- [ ] Create unit tests for race conditions

### Phase 3: Medium Priority (Week 3)
- [ ] Add connection pool monitoring
- [ ] Create health check endpoints
- [ ] Add performance logging
- [ ] Create load tests

---

## TESTING REQUIREMENTS

### Must Test Before Production:
1. **Concurrent Pick Test:** 50 concurrent picks from 10-unit inventory
   - Expected: 10 succeed, 40 fail, final quantity = 0

2. **Concurrent Stock Test:** 100 concurrent stocks of 1 unit
   - Expected: Final quantity = initial + 100

3. **Double-Click Test:** Click submit 10 times rapidly
   - Expected: Only 1 transaction created

4. **Validation Bypass Test:** Send POST with invalid data
   - Expected: Rejected with validation error

5. **Connection Leak Test:** 1000 operations
   - Expected: All connections returned to pool

---

## ROLLBACK PLAN

If issues occur:
1. Revert Docker image: `docker-compose down && git checkout <tag> && docker-compose up -d`
2. Database state is safe (no schema changes)
3. Notify team immediately
4. Review logs for root cause

---

## NEXT STEPS

1. Start with Pick Function (most critical)
2. Add transaction isolation and row locking
3. Test thoroughly with concurrent users
4. Move to Stock Function
5. Continue through checklist

**Estimated Time:** 2-3 weeks for all critical fixes
**Risk if not fixed:** Data corruption, negative quantities, duplicate transactions
**Production Readiness:** NOT READY until Phase 1 complete

---

Last Updated: 2026-01-23
Status: Implementation Started
