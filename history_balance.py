#!/usr/bin/env python3
"""PCN History's on-hand trail, on the ONE-NUMBER model.

Kept OUT of app.py (which builds a Flask app and a DB pool at import) so tests can
import and run the REAL logic instead of a copy — the same reason shortage_sql.py
exists. No Flask, no psycopg2, no side effects.

WHY THIS WAS REWRITTEN (2026-07-29, Preet — PCN 46559 and 46602)
----------------------------------------------------------------
PCN History was the last place in KOSH still running the abandoned CONSERVATION
(ledger) model. Its predecessor, `_history_delta`, returned a signed delta per
transaction — `+qty` for STOCK/RESTOCK/INDF, `-qty` for a PICK — and the trail was
replayed FORWARD from zero by summing them. The `inv_*` tables and ledger.py were
deleted in Phase 6, but this arithmetic survived, so the page kept computing on-hand
the old way while every other screen read the stored number:

  * PCN 46559 — two STOCKs of 30000 and two RESTOCKs of 50 were ADDED together. The
    page showed 60,900. `tblWhse_Inventory.onhandqty` was 300.
  * PCN 46602 — 30000 generated, then a PICK of 10000 was subtracted to show 20,000.
    A pick ZEROES the PCN, so the stored value was 0.

Roughly 8% of sampled PCNs disagreed with Warehouse Inventory this way. It was
display-only — nothing picked or ordered off those numbers — but a history that
contradicts the inventory screen is precisely what costs the warehouse its trust in
KOSH, so "display-only" is not "harmless".

Worse, the call site claimed the opposite of what the code did: it said the trail was
"anchored… walking backward from tblWhse_Inventory" so the two views "always agree",
while the function replayed forward and never touched the anchor it was handed.

THE MODEL (locked 2026-07-17, bug_memory/ACTION-PLAN.md) — consume-and-recount, not
conservation. A transaction does not nudge a balance; it STATES what the number now is:

  | Pick                  | on-hand becomes 0 — the parts went out to the floor |
  | Restock               | SETS on-hand to the qty entered (a fresh recount)   |
  | Stock / receipt       | SETS on-hand to the received qty                    |
  | PCN Generation / INDF | SETS the opening qty                                |
  | ADJT at one location  | a signed recount DELTA (+/-) — the only additive one |
  | pure location move    | no change to the number                             |

Replayed this way both examples land exactly on the stored value (46559 -> 300,
46602 -> 0), because the ADJT rows record the real deltas the app applied.

ANCHORING. The imported Access trail is incomplete for older PCNs, so a replay can
still miss. `compute_anchored_history_balances` therefore FORCES the newest row to
the stored on-hand and reports whether the replay agreed. The two screens now agree
by construction — what the call site always claimed — and a disagreement is surfaced
as a known data gap instead of being shown as fact.
"""

FLOOR = 'MFG Floor'

# A transaction that STATES the resulting on-hand rather than adjusting it.
_SETTERS = ('INDF', 'STOCK', 'PCN Generation', 'RESTOCK')


def _qty(row):
    try:
        return int(str(row.get('tranqty') or '').strip())
    except (TypeError, ValueError):
        return None


def apply_txn(running, row):
    """Return the bin on-hand AFTER `row`, given the balance before it.

    Bin on-hand counts only stock in a real location — never the MFG Floor, which is
    a status, not a place stock is kept."""
    if bool(row.get('reversed')) or row.get('is_relabel'):
        return running                      # never happened / renumber: quantity-neutral
    qty = _qty(row)
    if qty is None:
        return running                      # unparseable: leave the balance alone
    tt = (row.get('trantype') or '').strip()
    lf = (row.get('loc_from') or '').strip()
    lt = (row.get('loc_to') or '').strip()
    to_floor, from_floor = (lt == FLOOR), (lf == FLOOR)

    # RULE ORDER IS LOAD-BEARING — do not "obviously" improve it without measuring.
    # Two tweaks were tried and REVERTED on 2026-07-30 (WI-2):
    #   (a) checking _SETTERS before the to-floor rule, so a `RESTOCK … -> MFG Floor`
    #       states its qty instead of zeroing (fixes PCN 45284: stored 14, replayed 0);
    #   (b) treating ADJT as a signed delta wherever it is booked, not only when
    #       loc_from == loc_to (fixes PCN 45287: stored 130, replayed 100).
    # Measured over all 34,807 PCNs: +496 newly matching, but **23 PCNs that already
    # agreed broke** — e.g. 10425 and 40003 end on `RESTOCK … -> MFG Floor` with a stored
    # 0, the exact shape 45284 needs read the opposite way, and 37072's
    # `ADJT -50, Count Area -> 14041023` must NOT apply its delta. Gains and regressions
    # are both KOSH-written, so gating on `userid LIKE '%@%'` does not separate them.
    # The legacy trail is not self-consistent: identical rows mean different things.
    # The real fix is to replay (bin, floor) as a PAIR the way the DB trigger normalizes
    # them, not a single bin number — see PROGRESS-LOG 2026-07-30. Until then the anchor
    # is what guarantees PCN History and Warehouse Inventory agree on screen.
    if tt == 'PICK' or (to_floor and not from_floor):
        return 0                            # out to the floor -> nothing available here
    if tt in ('PURGE', 'SCRA'):
        return 0                            # left inventory entirely
    if tt in _SETTERS:
        return qty                          # receipt / recount / opening STATES the number
    if tt == 'ADJT' and lf == lt:
        return max(0, running + qty)        # manual recount at one location: signed delta
    if from_floor and not to_floor:
        return qty                          # came back off the floor = a recount
    return running                          # pure location move


def qty_display(row):
    """The quantity RECORDED on this transaction, as the history table should print it.
    Returns None when the row carries no readable number (print a dash).

    WHY THIS EXISTS (Theresa, PCN 44956, 2026-07-30)
    ------------------------------------------------
    The table's quantity column used to render `tranqty` ONLY for PICK rows; every other
    transaction printed a literal dash. So a RESTOCK/RNDT/PTWY/ADJT showed no quantity at
    all, and the only number on the row was the "On Hand" column — a computed BALANCE.
    Reading a balance as a quantity is then unavoidable, and that is exactly what happened:

        PCN 44956, put away 03/18/26 — recorded qty 46 (matching the printed label),
        the trail's own row said 46, and the page showed "150" (the balance).
        Reported as "history shows restock at 150", i.e. the system losing 104 parts.

    The 46 was in the database, on that row, the whole time. 155,692 rows across 35,134
    PCNs had their quantity hidden this way, so this is not one PCN's problem.

    ALWAYS UNSIGNED (Preet, 2026-08-03: "the qty should never ever come as negative")
    ----------------------------------------------------------------------------------
    Every transaction type prints the magnitude only. This column answers "how many parts
    did this transaction move", and a count of parts is never a negative number — a "-17"
    under a quantity heading reads as broken data to the floor (reported on PCN 24996,
    an ADJT -17 that zeroed a bin before a purge).

    The DIRECTION is not lost, it is just carried by the rest of the row: the On Hand
    column shows the resulting balance (17 -> 0 for that ADJT), and From/To show where the
    parts went. Only the display is unsigned — `_qty`/`apply_txn` still read the SIGNED
    tranqty, so an ADJT of -17 still subtracts 17 from the balance. Never route the
    balance math through this function.

    RESTOCK PRINTS 0 (Preet, 2026-08-03)
    ------------------------------------
    "when restocked the pick qty should be zero and on hand get a number." A restock is
    stock coming back IN, so nothing was picked on that row and the quantity column — which
    the floor reads as a pick quantity — shows 0. The number itself is not lost: a restock
    SETS the bin balance, so the On Hand column on the same row carries it (restock 49 ->
    On Hand 49), and Warehouse Inventory shows the same 49.

    This is deliberately narrower than the pre-14b44fc behaviour, which blanked the
    quantity on EVERY non-PICK type. PTWY/RNDT/INDF/ADJT still print their own quantity,
    so the PCN 44956 case — a put-away of 46 that read as the balance 150 — stays fixed."""
    if (row.get('trantype') or '').strip() == 'RESTOCK':
        return 0
    raw = str(row.get('tranqty') if row.get('tranqty') is not None else '').strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return abs(n)


def compute_anchored_history_balances(transactions, anchor):
    """Assign row['balance'] = bin on-hand AFTER each transaction, oldest -> newest,
    then ANCHOR the newest row to `anchor` (the stored Warehouse Inventory on-hand) so
    PCN History and Warehouse Inventory always agree on the current number.

    Returns (transactions, replay_matched_anchor). replay_matched_anchor is False when
    the imported trail could not reproduce the stored value — a real data gap in the
    history, which callers should surface rather than hide. Mutates in place."""
    def _sort_key(r):
        st = r.get('sort_time')
        return (0 if st is None else 1,
                st.timestamp() if st is not None else 0.0,
                r.get('id') or 0)

    ordered = sorted(transactions, key=_sort_key)      # oldest -> newest
    running = 0
    for row in ordered:
        running = apply_txn(running, row)
        row['balance'] = running

    if not ordered:
        return transactions, True

    matched = (running == anchor)
    if not matched:
        # The trail cannot reproduce the stored number (incomplete Access import).
        # The stored number is authoritative, so the newest row shows it; older rows
        # keep their replayed shape and the caller flags the trail as incomplete.
        ordered[-1]['balance'] = anchor
    return transactions, matched
