# PHASE 3.1 — Trace sheet: 13 bin/floor double-count rows (+ negative-mfg outliers)

**Read-only.** Purpose: rule **split** (both bin & floor are real) vs **stale** (mfg_qty is a leftover the
restock never zeroed) for each row BEFORE its opening balance is seeded. Nothing written here.

## The dominant pattern (10 of 13 = STALE)
`PICK n → MFG Floor` → `RNDT` recount → `RESTOCK m → a numeric bin`. The RESTOCK is supposed to zero the
floor (bug 18 semantics: "any difference between picked and restocked was consumed in production"), but on
these rows `mfg_qty` was left equal to the old pick qty. **The bin (`onhandqty`) is the truth; `mfg_qty` is
stale → seed bin only, floor = 0.** This is exactly bug 20's bin-class resolution.

| PCN | Item | Bin | Floor | Ledger tail | Ruling | Seed |
|---|---|--:|--:|---|---|---|
| 34300 | 6163L-9 | 1120 | 1110 | PICK1110→flr, RNDT1120, RESTOCK1120→bin | **STALE** | bin 1120, floor 0 |
| 26133 | 6163L-8 | 970 | 980 | PICK980→flr, RNDT970, RESTOCK970 | **STALE** | bin 970, floor 0 |
| 44500 | 8098-1-135 | 290 | 340 | PICK340→flr, RNDT290, RESTOCK290→1603002 | **STALE** | bin 290, floor 0 |
| 14196 | 6163L-7 | 210 | 220 | PICK220→flr, RNDT210, RESTOCK210→1603002 | **STALE** | bin 210, floor 0 |
| 8229 | 6163L-11 | 140 | 60 | PICK60→flr, RNDT140, RESTOCK140→1603002 | **STALE** | bin 140, floor 0 |
| 43341 | 7620-75 | 95 | 100 | PICK100→flr, RESTOCK95 | **STALE** (5 consumed) | bin 95, floor 0 |
| 36361 | 8620ML-265 | 30 | 1 | PICK1→flr, RNDT30, RESTOCK30→1603002 | **STALE** | bin 30, floor 0 |
| 44623 | 7620-20 | 20 | 50 | PICK50→flr, RESTOCK20 | **STALE** (30 consumed) | bin 20, floor 0 |
| 37846 | 7620-15 | 20 | 48 | PICK48→flr, RESTOCK20 | **STALE** (28 consumed) | bin 20, floor 0 |
| 43344 | 6163L-3 | 8 | 9 | PICK9→flr, RNDT8, RESTOCK8→2103504 | **STALE** | bin 8, floor 0 |

## Genuine SPLIT (1 of 13 — keep both)
| PCN | Item | Bin | Floor | Ledger tail | Ruling | Seed |
|---|---|--:|--:|---|---|---|
| 46152 | 8567ML-20 | 1 | 1 | PCN-Gen 2, PICK **1** → MFG Floor (no restock) | **SPLIT** — 1 in bin, 1 genuinely on floor, total 2 | bin 1, **floor 1** |

## ⚠️ FLAG for physical confirmation (2 of 13)
| PCN | Item | Bin | Floor | Why flagged | Recommended seed |
|---|---|--:|--:|---|---|
| **25972** | ACI-8182 | 190 | **3000** | PICK **3000**→floor (06/2022), then a partial `RESTOCK 190` (04/2026, 4 yrs later). Almost certainly the 3000 were consumed in production and 190 returned → floor stale. **But it's 2,810 units** — worth a physical check that nothing sits on the floor. | bin 190, floor 0 *(pending your OK)* |
| 45299 | 7593-16 | 90 | 10 | PICK100→floor, `RESTOCK 90`→1504004; 10 is the un-restocked remainder. Per restock semantics = consumed. Trivial qty. | bin 90, floor 0 |

## Negative `mfg_qty` outliers (whole table)
**85 rows**, every one `mfg_qty = -1` (sum −85). A negative floor is impossible (the new `qty >= 0` CHECK
forbids it). **Seed rule:** floor = 0, bin = `onhandqty` (unchanged). Impact ≈ 0 units. Examples: 8731
ACI-5199 (bin 4000), 3087 6970-4A-18 (bin 3450), 492 7918-25 (bin 800). These are cosmetic −1s from prior
arithmetic, not real stock.

## Net effect of these rulings on the seed
- 12 rows seed **bin-only** (stale/consumed floor dropped); 1 row (46152) seeds **bin + 1 floor**.
- 85 negative-mfg rows seed **bin-only** (−1 floor ignored).
- The reconciliation report (Phase 3.6) will list all of these as **intentional corrections** (new on-hand <
  old bin+floor) so you can see and reverse any before cutover. **25972's 2,810-unit drop is the only
  material one — call it out for me if you want it kept on the floor instead.**
