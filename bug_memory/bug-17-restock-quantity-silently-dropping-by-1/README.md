# Bug #17 - Restock Quantity Silently Dropping by 1
## 🟨 Medium - Mouse Wheel Decremented Qty
**Date:** 05/29/2026 | **Status:** ✅ FIXED

## The Bug
Restock saved one less unit than typed (type 50 → save 49).

## Root Cause
Mouse wheel over number input decremented value before submit.

## The Fix
Neutralize wheel events on quantity inputs.

**Commit:** 9a258f1 | **Verified:** 2026-06-25
