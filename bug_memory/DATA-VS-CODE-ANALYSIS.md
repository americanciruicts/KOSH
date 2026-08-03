# KOSH — Data problems vs Code problems, and the March 11 baseline

**The challenge (Preet, 2026-07-20):** *"You said it's a data fix, but the data issues are
stemming from KOSH features not working. How can you differentiate data from code issues at
this time?"*

**Answer: yes — precisely, and per row.** Not by judgement, but because every automated change
to inventory recorded (a) the process that made it and (b) the value it replaced. The system
documented its own damage. This file joins two analyses:
- **the CODE** — what the system looked like on 11 March 2026 vs today, and what was added;
- **the DATA** — exactly what each added piece then did to the numbers.

**A concession first:** my earlier framing ("the code will be right but the data still needs
physical verification") over-separated the two and made the data sound like an independent
problem to solve separately. That was wrong. **Most of the data damage is a direct, traceable,
reversible consequence of the code.** Only one narrow question genuinely needs a physical count
(§7), and there is a specific reason for it.

---

## 1. The method — how the two are told apart

For any suspect number, ask these in order. The first "yes" classifies it.

| # | Test | If YES → |
|---|------|----------|
| 1 | Was it last written by an automated process? (`tblReconcileAudit`, `stale_floor_fix_audit`, `floor_janitor_audit`, `part_relabel_fix_audit`, `inventory_audit`) | **CODE-caused — attributed & reversible** (the audit row holds the prior value) |
| 2 | Does it contradict the user's own transaction history? (last action was RESTOCK 30, stored value isn't 30) | **CODE-caused** — something overwrote a user action |
| 3 | Is it an impossible state? (negative qty, same units in two places, one PCN bound to two parts) | **CODE-caused** — no legitimate operation produces it |
| 4 | Do two parts of the system disagree? (Warehouse vs PCN History vs ledger) | **CODE-caused** — a second computation exists |
| 5 | None of the above — internally consistent, traceable to a real user action | **Only physical reality can judge it** (§7) |

Tests 1–4 are answerable **today, from inside the database, with no physical count.**

---

## 2. THE CODE — 11 March 2026 vs today

Compared via a read-only `git worktree` (baseline `a76c8af`, 2026-03-11) against `84b6f2e`
(2026-07-17, = production + one access change). Production was never touched.

| Measure | 11 Mar 2026 | Today | Change |
|---|---|---|---|
| `app.py` | 6,869 lines | 10,188 lines | **+3,319 (+48%)** |
| Background threads | **0** | 7 | +7 |
| Reconcilers that rewrite inventory | **0** | 4 | +4 |
| Separate models holding on-hand | **1** | 3 | +2 |
| `ledger.py` | does not exist | 1,000+ lines | NEW |
| DB schema | `pcb_inventory` (163 refs) | `warehouse` (281 refs) | renamed |
| Commits since | — | 221 | 298 files changed |

**On 11 March a pick was ONE statement against ONE table:**
```
UPDATE pcb_inventory."tblWhse_Inventory"
   SET onhandqty = GREATEST(0, onhandqty - qty_to_pick),
       mfg_qty   = (COALESCE(mfg_qty::integer,0) + qty_to_pick)::text,
       loc_to    = 'MFG Floor'
```
One number, changed by the user's action, and **nothing else could alter it.**

Today a pick runs through `ledger.pick()` → event log → balance cache → projection back into
`tblWhse_Inventory`, and then **four background jobs can rewrite the result minutes later.**

*(Note: March was not perfect either — `mfg_qty` accumulated and was never cleared, because
there was no "consumed" event. That is the seed of the stale-floor problem, already present.
The target is March's SHAPE plus the corrected rule: pick → 0, restock → SET.)*

---

## 3. THE DATA — every automated write is attributed

`tblReconcileAudit` stores `prior_qty`, `new_qty`, and `source`, so the damage is itemised:

| Source (the process that changed inventory) | Rows | PCNs | Period | Net units |
|---|--:|--:|---|--:|
| `auto_reconcile` (the 5-min reconciler) | 5,686 | 3,250 | 2026-04-24 → 06-22 | **+179,089** |
| `neutralize_absolute_adjt` | 929 | 641 | 2026-04-24 | — |
| `backfill_mpn` | 820 | 532 | 2026-04-24 | — |
| `backfill_notif` | 653 | 646 | 2026-04-24 | — |
| `phase3_dup_floor_zero_onhand_20260612` | 480 | 480 | 2026-06-12 | **−275,711** |
| `orphan_time_fix` | 289 | 265 | 2026-04-24 | — |
| `backfill_warehouse_edit` | 282 | 264 | 2026-04-24 | — |
| `dupe_mark_reversed` | 265 | 260 | 2026-04-24 | — |
| `restock_wipe_backfill_20260622` | 62 | 62 | 2026-06-22 | +10,991 |
| `bug20_bin_stale_mfg_zeroed_20260709` | 33 | 11 | 2026-07-09 | −2,928 |
| `floor_onhand_dedupe` | 19 | 19 | 2026-06-26 | −1,637 |

Plus the single largest event, in its own table (`stale_floor_fix_audit`, with `prior_floor`):

| Run | Rows | Units zeroed |
|---|--:|--:|
| `stale_floor_fix_20260714` | **9,859** | **3,693,334** |

**Note `restock_wipe_backfill_20260622`** — that is literally a script written to put back the
restocks the reconciler had wiped. The audit trail contains code destroying a user's saved work,
and a second script repairing it. That single row answers the question: the data damage *is*
code damage, and it is on the record.

---

## 3b. THE DATA — 16 April 2026 (pre-machinery) vs today

A snapshot table `tblWhse_Inventory_backup_20260416` survives in the database. Its date matters:
**16 April is BEFORE the first reconciler was added (20 April) and before it began writing
(24 April).** So it is effectively the data as it stood under the March-11 model.

| Measure | 16 Apr 2026 (pre-machinery) | Today | Change |
|---|--:|--:|--:|
| Inventory rows | 33,465 | 34,809 | +1,344 (normal growth) |
| **BIN units (on-hand)** | 13,635,574 | 15,650,364 | **+2,014,790** |
| **FLOOR units** | 4,196,773 | 891,201 | **−3,305,572** |
| Rows with BOTH bin + floor | **468** | **33** | −435 (**better**) |
| Rows floor-only (picked, never returned) | **10,996** | 2,834 | −8,162 |
| Negative rows | **8** | **0** | −8 (**better**) |
| PCNs whose on-hand was changed | — | **7,389** | net **+1,913,490** units |

### This forces an honest correction to the story

**The pre-machinery data was ALREADY dirty.** In April — under the simple March model, before any
reconciler existed — there were already **468** rows double-counting bin+floor, **10,996**
floor-only rows, and **8** negative rows. That dirt came from the legacy Access import, not from
the machinery. So "the data was fine before and the machinery broke it" is **not true**, and
rolling back to old data would not give a clean starting point.

**And the machinery genuinely fixed some real problems:** double-count rows 468 → 33, negatives
8 → 0, floor-only rows 10,996 → 2,834. Those are real improvements, not damage.

**So what actually went wrong is narrower and sharper than "the machinery ruined the data":**
1. It changed **7,389 PCNs** (21% of the inventory) **invisibly, in the background**, including
   overwriting values users had saved (the 62 wiped restocks are documented in §3).
2. It moved **3.3 million floor units** out of the numbers on an inferred rule ("older than 6
   months ⇒ consumed"), which may be right for most and wrong for some — and nobody could tell
   which, because consumption was never recorded (§7).
3. It introduced the **second and third computations** of on-hand, so screens began disagreeing.

The destruction of trust came from **(1) and (3)** — numbers changing under the user, and screens
contradicting each other — far more than from the cleanups themselves. That is the precise thing
the rebuild removes.

---

## 4. JOINING THEM — machinery added → damage done → complaint received

This is the causal chain, with dates from git history, the audit tables, and Theresa's emails.

| Date | Code added | Data it then changed | Theresa |
|---|---|---|---|
| **2026-03-11** | *baseline: 0 threads, 1 model* | — | *(no complaints)* |
| 2026-04-20 | `_sync_onhand_from_transactions` — **first reconciler** (08c5b00) | | |
| 2026-04-24 | | `auto_reconcile` begins rewriting inventory (first audit rows) | |
| **2026-06-03** | | | **"This is where trust was lost"** — shortage report |
| 2026-06-12 | | `phase3_dup_floor_zero` −275,711 units | |
| 2026-06-17 | `reconcile_warehouse_locations` (3fb6463) | | **Warehouse ≠ History; 9 lines wrong** |
| 2026-06-18 | `compute_anchored_history_balances` + `reconcile_onhand_from_ledger` (5b1967c) | | |
| 2026-06-22 | | `restock_wipe_backfill` restores **62 wiped restocks** | |
| **2026-06-23** | | | **"I no longer trust it"** |
| 2026-06-26 | `reconcile_floor_onhand` (cd542da) | `floor_onhand_dedupe` −1,637 units, same day | |
| **2026-07-01** | | | **Warehouse not reflecting last History entry** |
| 2026-07-09 | | `bug20_bin_stale_mfg_zeroed` −2,928 units | |
| 2026-07-13 | **`ledger.py`** introduced (f7d7665) | | |
| 2026-07-14 | `_floor_janitor` (8ae9274) | `stale_floor_fix` zeroes **3,693,334 units** across 9,859 PCNs | |
| **2026-07-16** | | | **Can't pick, can't edit qty, restock fails, signed out** |

Every complaint is preceded by new machinery, and every piece of machinery is followed by data
changing underneath her. The pattern is not ambiguous.

---

## 5. The three categories, with counts

**A — code-caused, attributed, REVERSIBLE.** Everything in §3: ~**9,859** PCNs from the
stale-floor sweep + ~**4,244** PCNs from the reconcile audit (with overlap), out of **34,809**
inventory rows. Each has the process, date, and prior value recorded.

**B — code-caused, detectable by contradiction.** Impossible states found with no audit needed:
rows with both a bin and a floor quantity (33), stored value disagreeing with the transaction
history, negatives (0 today), PCN collisions (0 today). The scoreboard in `tests/run.sh` catches these.

**C — genuinely not answerable from inside.** One question only — see §7.

---

## 6. What this changes about the rollback recommendation

The **code** reasons against reverting to March 11 stand, and are verifiable:
- the schema was renamed; the March code's **163** `pcb_inventory` references would not run
  against today's database at all;
- **Reel Change** and **ACI Numbers** do not exist in the March code (0 references) — they would
  have to be rebuilt;
- the 221 commits include the connection-leak fix (that one caused a full outage) and locking
  down publicly reachable data routes.

But the **data** half of my argument was weaker than I presented. I implied the data damage was
a separate, murky problem. It is not — it is itemised, attributed, and largely reversible. That
**strengthens fixing forward**: stop the writers, fix the model, then undo the specific damage by
source, rather than starting over and re-earning four months of work.

---

## 7. The one thing no analysis can settle

**Were the parts picked long ago actually consumed, or are they still on the floor?**

Nothing in the database can answer this, because **KOSH never recorded a "consumed" event.** The
information was never captured by *any* system, so it cannot be recovered by analysis, rollback,
or a better data model. This is the only place a physical count is genuinely required — and it is
one narrow question about picked-and-never-returned stock, not "the whole warehouse is suspect."

Under the locked model this stops being an open wound going forward: **pick → 0** means picked
stock is no longer carried as available, so nothing new goes stale.

---

## 8. The corrected sequence

1. **Freeze** — remove the reconcilers/janitor so nothing is written automatically. Until this is
   done, any reversal can simply be overwritten again.
2. **Fix the model** — one number, pick → 0, restock → SET, both screens reading it (Phase 2).
3. **Report the damage per source** — read-only, reviewable before anything changes.
4. **Reverse selectively.** Some automated changes were legitimate (real phantom stock removed).
   Judge each `source` on its merits with Preet/Theresa; the 3.69M-unit stale-floor sweep is the
   largest and gets its own decision. Every reversal is itself audit-tagged.
5. **Physically verify only the §7 residual**, on high-value parts.

**Not:** "the code is fine, go count the warehouse."
