#!/usr/bin/env python3
"""Shortage-report SQL, kept OUT of app.py so tests can import the REAL query.

app.py builds a Flask app and a DB connection pool at module scope, so a test that
wanted to check the shipped SQL used to have to keep its own copy of the predicate —
which is how a test can stay green while the query it claims to cover drifts. This
module has no Flask, no psycopg2 and no side effects: `import shortage_sql` is safe
from anywhere, so tests/behavioral/p5_shortage_bom_mpn_set.py runs the same string
the report runs.

Nothing here executes SQL; callers own the cursor and the params.
"""

# How a BOM line's PRIMARY row is chosen out of the rows sharing one ACI PN.
# Defined ONCE and imported by every copy (shortage report + the two job-detail
# queries) — when only one copy was tightened before, the job tab and the report
# disagreed about the same line, which is the class of bug that cost us trust.
#
# 1. non-ZSUB first  — a "ZSUB FOR ABOVE" alternate is never the line's identity.
# 2. NUMERIC LINE first (SR-3) — the BOM importer splits wrapped description text
#    into its own row, leaving prose in `line` ("350°C FOR 3 SECONDS", "(SEE
#    PICTURE") against the same aci_pn/mpn/qty as the real row. Those rows are
#    import artifacts, not BOM lines. Preferring a numeric `line` makes the real
#    line win explicitly instead of by accident: the old ordering fell through to
#    a plain text sort of `line`, so which row won depended on DB COLLATION
#    (en_US folds punctuation, so "(SEE PICTURE" happened to sort after "120" —
#    under C collation '(' sorts FIRST and the artifact would have won, printing
#    prose as the line number).
# 3. then real qty, 4. then line in NUMERIC order (so 9 precedes 10, not 100).
BOM_PRIMARY_ORDER_BY = """
        ORDER BY b.aci_pn,
                 (b."DESC" ILIKE '%%ZSUB%%'),
                 (b.line !~ '^[0-9]+$'),
                 CASE WHEN b.qty ~ '^[0-9]+([.][0-9]+)?$' THEN b.qty::numeric ELSE 0 END DESC,
                 CASE WHEN b.line ~ '^[0-9]+$' THEN b.line::int ELSE 999999 END,
                 b.line
"""


LINE_MPNS_CTE = """
    line_mpns AS (
        SELECT DISTINCT b.aci_pn, b.mpn, (b."DESC" ILIKE '%%ZSUB%%') AS is_zsub
        FROM warehouse."tblBOM" b
        WHERE b.job = %s
          AND (b.job_rev = (SELECT job_rev FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != '' ORDER BY created_at DESC LIMIT 1)
               OR NOT EXISTS (SELECT 1 FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != ''))
          AND COALESCE(b.mpn, '') != ''
    )
"""


def mpn_approved(item, mpn, fallback=True):
    """SQL predicate: is the stock row (`item`, `mpn`) an MPN this BOM line approves?
    Requires LINE_MPNS_CTE in scope. Takes 1 param (strict_mpn bool).

    fallback=True adds an escape hatch for the ~114 BOM rows that carry NO mpn at
    all: a line with nothing declared cannot judge its stock, so it keeps the old
    part-number-only behaviour rather than silently reading 0. Use fallback=False
    wherever the predicate is the ONLY filter (the cross-part-number search) — there,
    "this line declares no MPN" must match NOTHING, not the whole warehouse."""
    hatch = (f"""
            OR NOT EXISTS (SELECT 1 FROM line_mpns lm0 WHERE UPPER(lm0.aci_pn) = UPPER({item}))"""
             if fallback else '')
    return f"""(
            EXISTS (SELECT 1 FROM line_mpns lm
                     WHERE UPPER(lm.aci_pn) = UPPER({item})
                       AND CASE WHEN %s THEN lm.mpn = {mpn} ELSE UPPER(lm.mpn) = UPPER({mpn}) END){hatch}
        )"""




# SR-6, second half: QTY/REQ must never SILENTLY read 0.
#
# The parse itself is now tolerant (commas stripped, first numeric token taken), so
# "1,000" and "2 EA" resolve to their real value. What remains is the qty that holds
# no number AT ALL — the importer's column-shift leaves description text there
# ("ADHESIVE-BACKED", "AMPMODU RECEPTACLE"). Those still parse to 0, and a 0 that
# means "we could not read the BOM" is indistinguishable on screen from a 0 that
# means "none required" — Theresa's complaint exactly.
#
# So flag them. This returns the aci_pn + the RAW text for every line whose displayed
# primary row carries an unreadable qty, and the surfaces render it loudly instead of
# printing a bare 0. It reuses BOM_PRIMARY_ORDER_BY verbatim, so it can only ever flag
# the row the report actually shows.
#
# Deliberately NOT flagging a blank/empty qty: those are legitimately-empty reference
# lines, and flagging them would bury the real signal in noise.
# Takes 3 params (job, job, job).
UNPARSEABLE_QTY_SQL = """
    WITH primary_line AS (
        SELECT DISTINCT ON (b.aci_pn) b.aci_pn, b.qty, b.line
        FROM warehouse."tblBOM" b
        WHERE b.job = %s
          AND (b.job_rev = (SELECT job_rev FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != '' ORDER BY created_at DESC LIMIT 1)
               OR NOT EXISTS (SELECT 1 FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != ''))""" \
    + BOM_PRIMARY_ORDER_BY + """
    )
    SELECT aci_pn, qty AS raw_qty, line
    FROM primary_line
    WHERE COALESCE(btrim(qty), '') != ''
      AND regexp_match(replace(qty, ',', ''), '[0-9]+(?:[.][0-9]+)?') IS NULL
"""


PCN_ROWS_SQL = """
    WITH bom_pns AS (
        SELECT DISTINCT UPPER(aci_pn) AS aci_pn_u FROM warehouse."tblBOM"
        WHERE job = %s
          AND (job_rev = (SELECT job_rev FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != '' ORDER BY created_at DESC LIMIT 1)
               OR NOT EXISTS (SELECT 1 FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != ''))
    ),{line_mpns}
    SELECT UPPER(w.item) AS aci_pn, w.pcn,
           SUM(COALESCE(w.onhandqty,0)) AS qty,
           (array_agg(COALESCE(w.loc_to,'') ORDER BY COALESCE(w.onhandqty,0) DESC NULLS LAST))[1] AS location,
           -- each PCN's OWN mpn: the renderers must print THIS, not the line's BOM mpn
           (array_agg(w.mpn ORDER BY COALESCE(w.onhandqty,0) DESC NULLS LAST))[1] AS mpn,
           bool_or(EXISTS (SELECT 1 FROM line_mpns lz
                            WHERE UPPER(lz.aci_pn) = UPPER(w.item)
                              AND UPPER(lz.mpn) = UPPER(w.mpn) AND lz.is_zsub)) AS is_zsub
    FROM warehouse."tblWhse_Inventory" w
    WHERE UPPER(w.item) IN (SELECT aci_pn_u FROM bom_pns)
      AND COALESCE(w.loc_to,'') != 'MFG Floor'   -- SR-8/9: only real bin PCNs
      AND {negate}{approved}
    GROUP BY UPPER(w.item), w.pcn
    HAVING SUM(COALESCE(w.onhandqty,0)) > 0
    ORDER BY UPPER(w.item), qty DESC
"""




SHORTAGE_MATCH_SQL = """
    WITH """ + LINE_MPNS_CTE.strip() + """,
    bom_lines AS (
        SELECT DISTINCT ON (b.aci_pn)
            b.line, b.aci_pn, b.mpn as bom_mpn, b.man, b."DESC", b.qty, b.cost
        FROM warehouse."tblBOM" b
        WHERE b.job = %s
            AND (b.job_rev = (SELECT job_rev FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != '' ORDER BY created_at DESC LIMIT 1)
                 OR NOT EXISTS (SELECT 1 FROM warehouse."tblBOM" WHERE job = %s AND job_rev IS NOT NULL AND job_rev != ''))
        -- Pick the PRIMARY part per line, deterministically. A BOM line stores its
        -- primary + ZSUB substitute alternates as separate rows sharing the same
        -- aci_pn AND the same qty, so the old "qty DESC" tiebreak was a coin-flip:
        -- it returned "ZSUB FOR ABOVE" descriptions and substitute MPNs, and picked
        -- DIFFERENT rows on different runs (the report and job-detail form disagreed
        -- on the same line). Ordering rules live in BOM_PRIMARY_ORDER_BY (above), the
        -- single copy this and both job-detail queries share.""" + BOM_PRIMARY_ORDER_BY + """
    ),
    inv AS (
        SELECT
            bl.aci_pn,
            -- On-hand counts ONLY real bin stock (SR-8/SR-9). A row located at
            -- 'MFG Floor' is parts already picked/out for a job — a STATUS, not
            -- available stock — so it never counts (excluded in the JOIN below).
            -- mfg_qty is ignored entirely: floor rows are already excluded, and a
            -- BIN row that carries mfg_qty is bad data we must not add.
            COALESCE(SUM(COALESCE(w.onhandqty,0)), 0) as qty_on_hand,
            -- The pcn/location printed on the MAIN row must belong to a lot of the
            -- line's PRIMARY mpn where one exists, so the row is self-consistent:
            -- it prints bl.bom_mpn, and pointing that at an approved-ZSUB lot would
            -- put the primary's MPN over a substitute's PCN. ZSUB lots get their own
            -- labelled per-PCN rows instead. Bin qty breaks the remaining ties.
            (array_agg(w.pcn ORDER BY (UPPER(w.mpn) = UPPER(bl.bom_mpn)) DESC, COALESCE(w.onhandqty,0) DESC NULLS LAST))[1] as pcn,
            (array_agg(w.mpn ORDER BY (UPPER(w.mpn) = UPPER(bl.bom_mpn)) DESC, COALESCE(w.onhandqty,0) DESC NULLS LAST))[1] as inv_mpn,
            (array_agg(COALESCE(w.loc_to, '') ORDER BY (UPPER(w.mpn) = UPPER(bl.bom_mpn)) DESC, COALESCE(w.onhandqty,0) DESC NULLS LAST))[1] as location
        FROM bom_lines bl
        LEFT JOIN warehouse."tblWhse_Inventory" w
            -- Case-insensitive (inventory stores mixed case, e.g. BOM '6779ML-97'
            -- vs stock '6779ml-97') AND MFG-Floor rows excluded (floor = picked/out,
            -- never available). A line whose stock is all on the floor reads 0.
            ON UPPER(w.item) = UPPER(bl.aci_pn)
           AND COALESCE(w.loc_to, '') != 'MFG Floor'
            -- 2026-07-27: and the MPN must be one the BOM APPROVES for this line
            -- (primary or a ZSUB alternate). Matching on the part number alone made
            -- 7946L-30 read 1720 when only 1270 was the BOM part — the other 450
            -- units were a CM316X5R475K50AT and a C0805C471K5RAC7800 filed under the
            -- same ACI PN. Excluded units are surfaced by
            -- unmatched_pcn_rows_by_acipn(), never silently dropped.
           AND """ + mpn_approved('bl.aci_pn', 'w.mpn') + """
        GROUP BY bl.aci_pn, bl.bom_mpn
    ),
    -- Normalized stock pool for the same-MPN visibility row entries below, computed
    -- ONCE (MFG Floor + non-positive qty excluded). Materializing here avoids
    -- recomputing translate() over the whole warehouse for every BOM line.
    mpn_pool AS MATERIALIZED (
        SELECT item, pcn, onhandqty, mpn, loc_to
        FROM warehouse."tblWhse_Inventory"
        WHERE COALESCE(loc_to, '') != 'MFG Floor' AND onhandqty > 0
    )
    SELECT
        bl.line as line_no, bl.aci_pn, inv.pcn,
        -- Show the BOM's PRIMARY MPN (bl.bom_mpn is now the primary row via the
        -- ZSUB-aware ordering), so the line matches the customer BOM instead of a
        -- stocked substitute or a distributor-prefixed inventory variant. Fall back
        -- to the stocked MPN only when the BOM row has no MPN at all.
        COALESCE(NULLIF(bl.bom_mpn, ''), inv.inv_mpn) as mpn,
        -- SR-6: parse qty tolerantly. The strict regex zeroed any qty with a comma
        -- ("1,000"), a unit ("2 EA"), or a space. Strip commas, then take the first
        -- numeric token, so those parse to their real value instead of 0. REQ (ceil
        -- qty*order_qty, computed in Python) follows automatically.
        COALESCE((regexp_match(replace(bl.qty, ',', ''), '[0-9]+(?:[.][0-9]+)?'))[1]::numeric, 0) as qty,
        inv.qty_on_hand, bl.aci_pn as item,
        COALESCE(inv.location, '') as location,
        CASE WHEN bl.cost ~ '^[0-9]+([.][0-9]+)?$' AND length(split_part(bl.cost, '.', 1)) <= 6 THEN bl.cost::numeric(10,4) ELSE 0 END as unit_cost,
        bl.man as manufacturer, bl."DESC" as description,
        -- VISIBILITY ONLY (does NOT change the shortage math): stock of the SAME
        -- MPN sitting under a DIFFERENT job's part number. The shortage qty above
        -- still counts only this job's own part (UPPER(w.item)=UPPER(aci_pn)) so
        -- we never double-allocate another job's committed stock — but Purchasing can now
        -- see what Theresa used to hand-search in Warehouse Inventory.
        -- other_mpn_onhand is the running total (kept for the regression guard);
        -- other_mpn_locations is a JSON breakdown rendered as indented ROW ENTRIES
        -- under each BOM line in the view + export (the old two-column display was
        -- removed 2026-06-12 at report users' request — see CHANGELOG).
        -- MPN match mode (SR-2, 2026-07-22): EXACT MPN ONLY, no normalization.
        --   • Chemring jobs (strict_mpn=true): case-SENSITIVE exact string
        --     (p.mpn = bl.bom_mpn) — defense traceability, must match byte-for-byte.
        --   • Every other customer: case-INSENSITIVE exact string
        --     (UPPER(p.mpn) = UPPER(bl.bom_mpn)) — inventory stores the same MPN in
        --     mixed case, so we fold case but change NOTHING else.
        -- Previously the non-Chemring path used a NORMALIZED match (also stripping
        -- -, #, space, ., /), which merged DISTINCT MPNs differing only by those
        -- characters, so the report listed "like" parts that are not the same
        -- component — the exact thing Theresa flagged. The earlier directional
        -- prefix match was already removed for over-matching numeric/short MPNs
        -- (e.g. '1.5KE15'→'1.5KE150CA' (15V vs 150V), 'ERJ6ENF249'→'ERJ6ENF2491V');
        -- separator-normalization has the same failure mode because the separator
        -- info that tells a reel suffix from a value-continuation is destroyed. So
        -- separators now always distinguish parts; only letter case is folded.
        -- 2026-07-27: searches EVERY mpn the BOM approves for this line, not just the
        -- primary. Theresa's "sub has 3 more PCN's available. Not shown on Shortage
        -- Report" (7946L-10): 207 units of the approved ZSUB C0603C104M5RACTU sat in
        -- bins under 8019-3 / 8041-3 / 8188L-5. The own-PN path couldn't see them
        -- (different part number) and this path only looked for the PRIMARY mpn — so
        -- approved substitute stock under another PN was invisible to both.
        COALESCE((
            SELECT SUM(p.onhandqty) FROM mpn_pool p
            WHERE UPPER(p.item) <> UPPER(bl.aci_pn)
              AND """ + mpn_approved('bl.aci_pn', 'p.mpn', fallback=False) + """
        ), 0) as other_mpn_onhand,
        (
            SELECT json_agg(json_build_object(
                       'item', s.item, 'pcn', s.pcn, 'qty', s.qty,
                       'location', s.location, 'mpn', s.mpn, 'is_zsub', s.is_zsub)
                       ORDER BY s.qty DESC)
            FROM (
                SELECT p.item AS item, p.pcn AS pcn, SUM(p.onhandqty) AS qty,
                       (array_agg(COALESCE(p.loc_to, '') ORDER BY p.onhandqty DESC NULLS LAST))[1] AS location,
                       (array_agg(p.mpn ORDER BY p.onhandqty DESC NULLS LAST))[1] AS mpn,
                       -- so the row can be labelled "ZSUB @ another PN" rather than
                       -- reading as if the primary part were sitting over there
                       bool_or(EXISTS (SELECT 1 FROM line_mpns lz
                                        WHERE UPPER(lz.aci_pn) = UPPER(bl.aci_pn)
                                          AND UPPER(lz.mpn) = UPPER(p.mpn) AND lz.is_zsub)) AS is_zsub
                FROM mpn_pool p
                -- Same ACI PN under another PCN (any case) is THIS job's own
                -- stock, already counted above — never list it as an arrow entry.
                WHERE UPPER(p.item) <> UPPER(bl.aci_pn)
                  AND """ + mpn_approved('bl.aci_pn', 'p.mpn', fallback=False) + """
                GROUP BY p.item, p.pcn
                ORDER BY SUM(p.onhandqty) DESC
                LIMIT 20
            ) s
        ) as other_mpn_locations
    FROM bom_lines bl
    JOIN inv ON inv.aci_pn = bl.aci_pn
    ORDER BY
        CASE WHEN bl.line ~ '^[0-9]+$' THEN CAST(bl.line AS INTEGER) ELSE 999999 END,
        bl.line
"""
