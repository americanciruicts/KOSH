# SYSTEMIC FINDING — stale MFG-Floor counts inflate on-hand (2026-07-09)

Reported by Preet via PCN 25972 ("on hand was never 6000, always 3000, picked, came back as 190 not 3190").
Confirmed at scale by read-only audit. **This is bigger than the 13 double-count rows.**

## The pattern
When a job PICKs parts, KOSH moves them bin → MFG Floor (`mfg_qty += qty`). The floor count is then only
ever cleared by a **RESTOCK** (parts returned to a bin). **There is NO event for "consumed by production."**
So when a WO consumes the parts (the normal case), the floor count is **never decremented — it stays frozen
at the picked quantity forever.** `mfg_qty` therefore accumulates stale "picked-and-consumed" quantities.

## Scale (floor-only rows: bin=0, last event = PICK, never restocked)
| Last pick age | PCNs | Floor units (likely stale) |
|---|--:|--:|
| 3+ years | 5,181 | 1,853,237 |
| 2–3 years | 548 | 294,546 |
| 1–2 years | 1,700 | 580,796 |
| 6–12 months | 2,392 | 967,703 |
| <6 months | 2,815 | 941,707 (likely still legitimately staged) |
| **6mo+ total (high confidence stale)** | **9,821** | **3,696,282** |

Plus 23 exact-25972 rows (floor>0 with a RESTOCK after the last pick → 3,984 units).

Tell-tale: `floor_qty == pick_qty` exactly, tied to a WO. Examples: 43600 8119L-115 floor 30000 = PICK 30000
for WO 23826-3 (2025-11); 25054/25055 8080L-1-565 floor 16000 = PICK 16000 for WO 21161-1 in **2021**.

## Why it matters for the rebuild
The rebuild ANCHORED `inv_onhand` to the warehouse (bin+floor), trusting `mfg_qty` as real floor stock. If
~3.7M floor units are stale, `inv_onhand` inherits the over-statement. In Phase 0 the ledger computed **0**
for these (PICK removes, no floor-add event) and I judged the ledger "can't see floor" — but for consumed
picks the ledger's 0 is actually CORRECT and the warehouse floor is the error.

## Root cause = a workflow/data gap, not just dirty legacy data
KOSH records STOCK/PICK/RESTOCK but **not consumption**. Floor stock only clears on RESTOCK. Going forward the
new real-time events have the SAME gap unless we add a "consumed / WO-close" event (or treat floor as
WO-committed and clear it when the WO closes).

## NOT auto-fixable — needs Preet's domain rule + verification
3.7M units across 9,821 PCNs is far too large and consequential to auto-zero. Decisions needed:
1. **The rule for "stale":** is floor stock consumed once its WO is closed? Is there WO-status data to join?
   Or is age the proxy (e.g., 3+ years = definitely gone)?
2. **Go-forward fix:** add a consumption/WO-close event so floor self-clears (stops the bleed).
3. **Back-fix:** phased, oldest-first (3+ yrs = 1.85M units, highest confidence), audit-logged + reversible,
   spot-verified — NOT a blanket zero.
