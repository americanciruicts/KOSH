# KOSH Shortage Report — Issues Reported July 21, 2026

Reported verbally by Preet. All five are about the **shortage report** being wrong.
Written in plain language here; the formal tracking IDs are in `BUG HISTORY.md`.

---

## The 5 issues

**1. The report shows the wrong ACI part number AND the wrong line-item number.**
Example: on a job (order 12345-6, work order 2358-5) the BOM is loaded and the shortage
report runs. A part (MPN) that is really in the system, but tied to a *different* ACI part
number / line, shows up on the report under *that* wrong ACI part number and line number —
not the actual ACI part number and line item for the job.
(Tracked as **SR-3**.)

**2. The report shows the location as "MFG FLOOR" when it shouldn't.**
The location column on the shortage report comes back as "MFG Floor." That location should
not appear there. "MFG Floor" just means a part is out on the floor for a job — it is a
status, not a place where stock is kept.
(Tracked as **SR-8** — new today.)

**3. The on-hand quantity is bin + MFG floor added together, not the real on-hand.**
Example: for PCN 4848, the on-hand number on the report is the bin quantity *plus* the MFG
floor quantity combined. That is not the true on-hand — it double-counts. The report should
show the one real on-hand number.
(Tracked as **SR-9** — new today.)

**4. When one MPN has several PCNs, each PCN should be its own line.**
Example: MPN abccc2124bcdef has multiple PCNs. On the shortage report each PCN should appear
as a separate line showing the quantity for that PCN — not lumped into one combined total.
(Tracked as **SR-4**.)

**5. A ZSUB (substitute) from the BOM does not show as a ZSUB.**
If the uploaded BOM has a ZSUB substitute, it does not carry through as a ZSUB — not in what
KOSH displays and not on the shortage report. The ZSUB label is lost.
(Tracked as **SR-1**.)

---

## The order these get fixed (and why)

The shortage report can't be right until the inventory numbers underneath it are right. So
we fix the foundation first, then the report reads correctly on top of it:

1. Make on-hand ONE number that both screens agree on (fixes the double-count — this is what
   makes issue #3 possible to fix).
2. Make a renamed/renumbered part keep its stock, so the report points at the right ACI part
   number and line (issue #1).
3. Then fix the shortage report itself:
   - Show the real single on-hand, not bin + floor (issue #3).
   - Stop showing "MFG FLOOR" as a location (issue #2).
   - List each PCN on its own line (issue #4).
   - Keep the ZSUB label on substitutes (issue #5).

Nothing is marked "fixed" until it's proven on staging and Theresa confirms it on her own
real jobs.
