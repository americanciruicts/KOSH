# Bug #18 - Restock: Qty Autofill / MFG-Floor Not Zeroed
## 🟨 Medium - Double-Represented Stock
**Date:** 05/18/2026 | **Status:** ✅ FIXED

## The Bug
Restock pre-filled wrong quantity. Floor stock not cleared when stock went back to bin → double-represented.

## Root Cause
Qty autofill convenience + not zeroing mfg_qty on restock.

## The Fix
- Removed autofill
- Zero mfg_qty on restock (keeps onhandqty + mfg_qty consistent)

**Commit:** f5ab95b | **Verified:** 2026-06-25
