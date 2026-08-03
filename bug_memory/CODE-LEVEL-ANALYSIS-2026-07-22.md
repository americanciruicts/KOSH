# KOSH — Code-Level Defect Analysis (where the bug is, what it does now, what changes)

**Date:** 2026-07-22. **Method:** three read-only passes over the actual source
(`app.py` 10,188 lines, `ledger.py`, `wh_ops.py`, templates, docker config) + git history.
No files were modified. Every claim below is anchored to a real `file:line`.

## The one fact that reframes the whole list

Production runs the `inventory-rebuild-ledger` branch (per `deploy.sh`), tip `c90f731`
(2026-07-16). The working tree (`main` @ `84b6f2e`, 2026-07-17) differs by ~20 lines. So the
code the agents read ≈ what is deployed. Consequences:

- KOSH was **rebuilt around a ledger** (`ledger.py`: append-only `inventory_txn` +
  `inventory_balance`); `tblWhse_Inventory.onhandqty`/`mfg_qty` are now a same-transaction
  *projection* of that ledger (`ledger.project_warehouse`).
- Because of that rebuild, **SR-3, RS-1, PH-1 already have fixes in the deployed code**, and the
  **fuzzy-MPN match (SR-2) is already gone**. These are "verify it holds," not "write new code."
- The **destructive reconcilers are already OFF** — `_sync_onhand_from_transactions` and its
  `reconcile_*` helpers are defined but **never threaded** (dead code, `app.py:3259-3399`, with a
  "do not reintroduce" note at `3401-3408`). The only background job still mutating inventory is
  `_floor_janitor` (daily, `app.py:3607`).
- **The real remaining root cause, in code terms:** for PK-1 / WI-1 / WI-2 the **read path and the
  write path use different sources** (snapshot vs ledger; bin-only vs bin+floor). That single class
  of mismatch is the live core bug — not "numbers being overwritten in the background."

This strongly supports **fix-forward**: a revert to March throws away the deployed ledger fixes
(SR-3/RS-1/PH-1) and the reconciler shutdown, and would not run against the renamed schema.

---

## A. Shortage report — `app.py:5241` (saved report) AND `app.py:8546` (job-detail live table)

The report logic is **duplicated**. Every fix below must be applied in **both** query bodies or
the report and the job page will disagree. Route: `GET/POST /shortage_report*`,
`_persist_shortage_report()` (5344); job copy inside `job_detail()`.

| ID | Where | What the code does now | Exact change |
|---|---|---|---|
| SR-1 | `5243` `DISTINCT ON (b.aci_pn)` + qty-DESC `5250`; col list `5244`; insert `5416` | Deliberately keeps only the primary BOM row and **throws the "ZSUB FOR ABOVE" alternate away**; no substitute/ZSUB column is read or stored anywhere | Stop collapsing substitute rows; read a substitute/ZSUB flag from `tblBOM` and persist it into `tblShortageReportItems`. (Substitute handling does not exist today — this is net-new.) |
| SR-2 | main join `5270` `UPPER(w.item)=UPPER(bl.aci_pn)`; visibility branch `5314/5330` | **No fuzzy match remains** — main stock is matched by exact ACI PN. Only residual: the normalized branch strips `- # . / space`, so two MPNs differing only by those chars could merge | Likely already resolved. Confirm against Theresa's real example; if it's the separator-collapse, force `p.mpn = bl.bom_mpn` at `5314/5330` |
| SR-4 | `5271` `GROUP BY bl.aci_pn`; `5261` `SUM(...)`; `5262` `array_agg(pcn)[1]` | All PCNs/lots of a part are **summed into one number**; only one PCN survives | `GROUP BY bl.aci_pn, w.pcn` → one line per PCN; turn the `array_agg[...][1]` picks into plain columns. Review downstream cost-dedupe `seen_lines` (`5394`) which assumes one row per part |
| SR-5 | `5243` `DISTINCT ON (b.aci_pn)`; job_rev filter `5248-5249` | Two BOM lines sharing an `aci_pn` **collapse to one** → lines vanish; revision predicate can also exclude rows | Key the DISTINCT on `b.line` (not `aci_pn`); re-check the `job_rev` predicate |
| SR-6 | `5285` `CASE WHEN bl.qty ~ '^[0-9]+([.][0-9]+)?$' THEN ... ELSE 0`; REQ `5383` | Any BOM qty with a comma (`"1,000"`), unit (`"2 EA"`), or space **fails the regex → 0**; REQ = `ceil(qty*order_qty)` then also 0 | Tolerant qty parse (strip commas/units/space); ensure `order_qty` is a real value before `5383` |
| SR-7 | join `5270` `UPPER(w.item)=UPPER(bl.aci_pn)`; job copy `8587` is **case-sensitive** | The line's own stock is found **only** if recorded under the exact ACI PN string; the job-detail copy's case-sensitive join is an outright bug vs `5270` | Broaden/normalize the match for the line's own stock; fix the case-sensitive `8587` |
| SR-8 | `5264` `array_agg(COALESCE(w.loc_to,'') ORDER BY ...)[1]` | When a line's only stock with qty is a floor lot, the chosen location is `'MFG Floor'` and it shows on the report | Exclude/deprioritize floor lots from the location pick (`5264` / `8584`) |
| SR-9 | `5261` `SUM(onhandqty + CASE WHEN mfg_qty~int THEN mfg_qty ELSE 0 END)` | **Intentionally** adds bin + floor (comment defends it as "bug 9: floor counts as on-hand") | Drop the `+ mfg_qty` term → on-hand = bin only. NOTE: this **reverses a prior deliberate decision** — confirm with Preet/Theresa first |

---

## B. Inventory write paths

| ID | Where | What the code does now | Exact change | Verdict |
|---|---|---|---|---|
| PK-1 | gate `app.py:1229-1245`; write `ledger.pick` `1305`; `ledger.py:135` | The availability gate reads **snapshot `onhandqty`** (bin projection), but the write subtracts from the **ledger `inventory_balance`** at bin `a_bin`. If the ledger holds the balance under a different location/part than the snapshot shows, one says "available" and the other raises `insufficient stock at bin` | Make the gate read/lock the **same ledger balance at the target bin** the write mutates | **Real bug — fix** |
| RS-1 | `restock_pcb` `1390`; `ledger.restock_physical` `1557`; guard `1542` | Restock is **no longer** a floor→bin delta — a part with zero floor still restocks (shortfall booked as `FOUND`). There is **no "qty at zero" string** in the codebase. The remaining blocker is the "already been restocked" guard at `1542` | The delta/SET defect is **already fixed** (commit `d2e675b`, 7/15). If still failing, it's the `1542` guard — reproduce on staging | **Verify** |
| WI-1 | `update_warehouse_item` `4909`; read-back `5046-5058`; empty-bin `5037`→`ledger.py:375` | After save, the projected `onhandqty` = **SUM of all non-floor balances** for the PCN, but the verify compares it to the **single value typed for one bin** and rolls back on mismatch (esp. when `edit_bin` resolves empty, so the qty never lands) | Verify against what the ledger actually produced (balance at `edit_bin`), not the raw typed number; guard the empty-`edit_bin` case | **Real bug — fix** |
| PH-1 | pick `ledger.py:180-193`, projection `506`; header `app.py:6652`; anchor fallback `6685-6687` | Pick is one bin→floor transfer; projection sets `onhandqty=non-floor`, `mfg_qty=floor` (**disjoint**). Live path does not double-count. Residual is **legacy dirty rows** with both `>0`, shown in two columns / summed in the pre-ledger anchor fallback | Code path already fixed. Re-project dirty PCNs through the ledger; stop the `6685-6687` bin+floor fallback sum for legacy rows (**data cleanup, not logic**) | **Verify + data** |
| SR-3 | `part_number_change` `4303`; fix `4362-4364`; `ledger.relabel_pcn` `ledger.py:381` | Rename updates the snapshot `item` **and** moves the ledger balance to the new part in the same transaction (qty-neutral) — "bug 28" | **Already fixed** (commit `c90f731`, 7/16). Stock is not stranded in current code. Caveat: relabel keeps the old MPN — item-number-only renames are covered, MPN changes are not | **Verify** |

Ledger call sites: stock `957`, **pick `1305`**, **restock `1557`**, reverse_pick `1692`, floor
janitor consume `3570`, **relabel `4362`**, **warehouse edit `5039`**, PCN generate `6915`,
delete `7229`.

---

## C. Read paths / reconcilers / session

| ID | Where | What the code does now | Exact change |
|---|---|---|---|
| WI-2 | Warehouse Inv read `app.py:4599/4685` (template `warehouse_inventory.html:160`); PCN History `6682-6694` + `compute_anchored_history_balances` `3237` | **Two sources, two definitions.** Warehouse Inventory shows stored **bin-only** `onhandqty`; PCN History anchors to `SUM(inventory_balance.qty)` = **bin+floor** (the ledger). Even with a perfect projection, a floor part reads 0 on one screen and N on the other. Route computes `TotalOnHand` at `4688` but the template never renders it | Point Warehouse Inventory at the **same ledger source** and display the combined `TotalOnHand` — one source, one definition |
| Reconcilers | live: `_floor_janitor` `3607`; dormant: `_sync_onhand_from_transactions` `3259`, `reconcile_*` `3363/3373/3382` | The on-hand/location/floor reconcilers are **defined but never started** — dead code. Only `_floor_janitor` (daily) still mutates inventory (lowers >6-month-stale floor via `ledger.consume`, audited for reversal) | Delete/guard the dormant reconciler so it can't be re-enabled; decide whether `_floor_janitor` stays on (`FLOOR_JANITOR_ENABLED`) |
| SO-1 | `SECRET_KEY` `47`; cookie `51-53`; `require_auth` `2624`; `sso_callback` `6110-6111`; `handle_csrf_error` `9373` | **Not secret rotation** (stable hardcoded key + single gunicorn worker per `Dockerfile.webapp`). Logout is `require_auth`→FORGE SSO firing when the session cookie isn't returned; the **alternation** comes from `sso_callback` running `session.clear()` (rotating `csrf_token`) against `SESSION_COOKIE_SECURE`/`SameSite=Lax` over the http tunnel — the already-rendered kitting form then carries a stale token and the next submit bounces | Fix cookie `Secure`/`SameSite` vs the scheme users actually hit; stop rotating `csrf_token` on same-user SSO re-entry (`6110-6111`); pin an explicit `SECRET_KEY` env (defensive) |

---

## D. GP-1 (today's hotfix)

Qty cap raised **10,000 → 100,000** at `app.py:204, 244, 847, 1043, 1395, 6845`. Done in the
working tree (uncommitted). Needs the staging container rebuilt (`sudo docker compose build
web_app && up -d web_app`) and Theresa to confirm a >10k PCN generates.

---

## E. What this means for build-forward vs revert

**Fix-forward, keep the ledger, unify read/write sources.** Reasons, all code-verified:
- The deployed ledger already fixes SR-3, RS-1, PH-1 and removed the fuzzy MPN match (SR-2); the
  destructive reconcilers are already off. A revert to March discards all of that.
- March's code won't run against the renamed schema (163 `pcb_inventory` refs), and lacks Reel
  Change / ACI Numbers.
- The live core bug is narrower than "everything drifts": it's **read-source ≠ write-source**
  (PK-1, WI-1, WI-2). Fixing that + rebuilding the shortage report + the SO-1 cookie config is the
  bulk of the real remaining work.

**Open question that must be answered before trusting the "already fixed" rows:** confirm the
commit production actually serves, and reproduce SR-3/RS-1/PH-1 on staging with Theresa's real
scenarios. "Fixed in the deployed code" is only real once she can't reproduce it at her desk.
