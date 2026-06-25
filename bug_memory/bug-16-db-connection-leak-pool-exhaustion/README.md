# Bug #16 - DB Connection Leak → Pool Exhaustion (Outage)
## 🟥 Critical - App Hung After Page Views
**Date:** 05/29/2026 | **Status:** ✅ FIXED

## The Bug
Whole app hung after enough page views. Pool exhausted at maxconn=15.

## Root Cause
Routes handed raw psycopg2.connect connections to return_connection, which putconn rejected and dropped → leaked until pool exhausted.

## The Fix
- return_connection now CLOSES rejected connections
- Moved to gunicorn (1 worker / 8 gthreads)
- Pool 15→20

**Commits:** 9ee8436, 9ff6c81, 961275b, e0d7324 | **Verified:** 2026-06-25
