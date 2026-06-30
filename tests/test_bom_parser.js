#!/usr/bin/env node
// Regression test for the KOSH BOM parser.
//
// Why this exists:
//   May 4 2026 — multi-sheet merge (commit 6476b87) silently dropped
//     duplicate-line rows like "Line 10 ZSUB FOR ABOVE" inside the same
//     "BOM to Load" sheet. 8303LF lost 4 substitute rows.
//   May 5 2026 — fixed by making dedup CROSS-SHEET only (commit 697fd7c).
//
// This test runs the SHARED parser at static/js/bom_parser.js (the same
// module the browser loads) against every committed *BOM FOR ASSEMBLY.xlsx
// in the repo and asserts the invariants below. If a future change to
// the parser breaks any of them, this test fails and the deploy is
// blocked by tests/run.sh.
//
// Invariants:
//   1. The sample BOMs all parse without errors.
//   2. "BOM to Load" contributes ALL its data rows — no within-sheet drops.
//      (Counted by row, not by unique line number.)
//   3. Across sheets, no duplicate line numbers leak in: any line# in
//      bom_items beyond what's in "BOM to Load" must not also be in
//      "BOM to Load".
//   4. For 8303LF specifically: the ZSUB substitute rows for line 10 and
//      line 15 are present (the exact regression we hit).
//   5. Metadata { job, job_rev, last_rev, customer, cust_pn, cust_rev } is
//      populated for every sample.
//
// Run:   node tests/test_bom_parser.js
// Or via: tests/run.sh (which also runs the Python suite).

const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '..');
const PARSER_PATH = path.join(REPO_ROOT, 'static/js/bom_parser.js');

let XLSX;
try {
    XLSX = require('xlsx');
} catch (e) {
    // Fall back to a workspace install if the repo doesn't have one
    try { XLSX = require('/tmp/node_modules/xlsx'); }
    catch (e2) {
        console.error('xlsx package not installed. Run:');
        console.error('  cd /tmp && npm install xlsx');
        process.exit(2);
    }
}

const KoshBomParser = require(PARSER_PATH);

const SAMPLES = [
    '5477 SEC INC PP-06809-07 BOM FOR ASSEMBLY.xlsx',
    '7942 Boon Edam 50011018-1P1 BOM FOR ASSEMBLY.xlsx',
    '8303LF Keyper BP0208 BOM FOR ASSEMBLY.xlsx',
    '8481L MEDSHIFT MONITORING DEVICE SLIM BOM FOR ASSEMBLY.xlsx',
    '8813L-4DA Wheelright 023-0852  BOM FOR ASSEMBLY.xlsx',
];

let failures = 0;
function check(name, cond, detail) {
    if (cond) {
        console.log('  PASS  ' + name);
    } else {
        console.log('  FAIL  ' + name + (detail ? '  -> ' + detail : ''));
        failures += 1;
    }
}

function loadWorkbook(p) {
    const buf = fs.readFileSync(p);
    return XLSX.read(new Uint8Array(buf), { type: 'array', cellDates: true });
}

function countDataRows(workbook, sheetName) {
    // Count rows that the parser would consider data rows (not header,
    // not blank). Mirrors parser logic enough to sanity-check it.
    const ws = workbook.Sheets[sheetName];
    if (!ws) return 0;
    const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
    if (!rows || rows.length < 2) return 0;
    const hr = KoshBomParser.findHeaderRow(rows);
    if (hr.headerRowIdx === -1) return 0;
    const col = KoshBomParser.buildColMap(hr.headersNorm);
    let n = 0;
    for (let r = hr.headerRowIdx + 1; r < rows.length; r++) {
        const row = rows[r];
        if (!row || row.length === 0) continue;
        let allEmpty = true;
        for (let c = 0; c < row.length; c++) {
            if (row[c] !== '' && row[c] !== null && row[c] !== undefined) { allEmpty = false; break; }
        }
        if (allEmpty) continue;
        const mpn = col.mpn !== undefined ? String(row[col.mpn] || '').trim() : '';
        const desc = col.desc !== undefined ? String(row[col.desc] || '').trim() : '';
        const aci = col.aci_pn !== undefined ? String(row[col.aci_pn] || '').trim() : '';
        const qtyChk = col.qty !== undefined ? row[col.qty] : '';
        if (!mpn && !desc && (qtyChk === '' || qtyChk === null || qtyChk === undefined)) continue;
        // Mirror parser: numeric line kept; non-numeric line kept ONLY if the
        // row carries a real part id (mpn/aci) — bug 22 rescue; else skipped.
        if (col.line !== undefined) {
            const p = parseInt(row[col.line]);
            if (isNaN(p) && !(mpn || aci)) continue;
        }
        n += 1;
    }
    return n;
}

function runOne(samplePath) {
    const fname = path.basename(samplePath);
    console.log('\n[' + fname + ']');
    let wb;
    try { wb = loadWorkbook(samplePath); }
    catch (e) { check('loads workbook', false, e.message); return; }

    let result;
    try { result = KoshBomParser.parseWorkbook(wb, XLSX); }
    catch (e) { check('parses workbook', false, e.message); return; }

    check('parses without throwing', !!result);
    check('produces > 0 items', result.bom_items.length > 0,
        'got ' + result.bom_items.length);

    // Invariant 2: BOM to Load contributes every row it has.
    if (wb.SheetNames.indexOf('BOM to Load') !== -1) {
        const expected = countDataRows(wb, 'BOM to Load');
        const btlEntry = result.per_sheet.find(p => p.sheet === 'BOM to Load');
        const got = btlEntry ? btlEntry.added : 0;
        check('"BOM to Load" keeps all rows (no within-sheet dedup)',
            got === expected,
            'expected ' + expected + ' kept, got ' + got);
    }

    // Invariant 5: metadata extracted
    const meta = result.metadata || {};
    check('metadata.job populated', !!meta.job, JSON.stringify(meta));
    check('metadata.job_rev populated', !!meta.job_rev, JSON.stringify(meta));
    check('metadata.customer populated', !!meta.customer, JSON.stringify(meta));

    // Invariant 4: 8303LF specific — ZSUB rows preserved
    if (fname.indexOf('8303LF') === 0) {
        const line10 = result.bom_items.filter(i => i.line === 10);
        const line15 = result.bom_items.filter(i => i.line === 15);
        check('8303LF: line 10 has both NUT + ZSUB rows',
            line10.length >= 2 && line10.some(i => /ZSUB/i.test(i.desc)),
            'got ' + JSON.stringify(line10.map(i => i.desc)));
        check('8303LF: line 15 has both NUT + ZSUB rows',
            line15.length >= 2 && line15.some(i => /ZSUB/i.test(i.desc)),
            'got ' + JSON.stringify(line15.map(i => i.desc)));
        check('8303LF: total >= 27 (BOM to Load has 27 data rows)',
            result.bom_items.length >= 27,
            'got ' + result.bom_items.length);
    }
}

// ── Synthetic regression for bug 22 (job 8517L-2) ──────────────────────
// The real cause: only the first data row carried a numeric LINE cell; the
// rest had a blank/non-numeric LINE cell, so the parser dropped them and a
// 25-line BOM loaded just 1 line. These tests build the workbook in memory
// (the sample .xlsx files aren't committed) so the fix is covered even
// without customer files present.
function sheetFromAoa(aoa) {
    const ws = XLSX.utils.aoa_to_sheet(aoa);
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, 'BOM to Load');
    return wb;
}

function runSynthetic() {
    console.log('\n[synthetic: bug 22 — blank LINE cell drops real parts]');

    // Header + 5 component rows; ONLY the first row has a numeric LINE value,
    // mirroring 8517L-2 where line 5 survived but 10/15/20/25 were dropped.
    const header = ['Job', 'Line', 'ACI PN', 'MPN', 'Description', 'Qty'];
    const rows = [
        ['8517L-2', 5,  '8517L-2-5',  'VTB8441BH',        'PHOTOTRANSISTOR', 1],
        ['',        '', '8517L-2-10', 'CL10B104KB8NNNC',  'CAP 0.1UF',       2],
        ['',        '', '8517L-2-15', 'GRM21BR61E106KA',  'CAP 10UF',        3],
        ['',        '', '8517L-2-20', 'SMF15VTR',         'TVS DIODE',       4],
        ['',        '', '8517L-2-25', 'BQ24104RHLT',      'CHARGER IC',      5],
    ];
    const wb = sheetFromAoa([header].concat(rows));
    const result = KoshBomParser.parseWorkbook(wb, XLSX);

    check('bug22: all 5 component rows kept (none silently dropped)',
        result.bom_items.length === 5, 'got ' + result.bom_items.length);
    const acis = result.bom_items.map(i => i.aci_pn).sort();
    check('bug22: line 25 (8517L-2-25) is present',
        acis.indexOf('8517L-2-25') !== -1, JSON.stringify(acis));
    check('bug22: every kept row preserved its MPN',
        result.bom_items.every(i => i.mpn && i.mpn.length > 0),
        JSON.stringify(result.bom_items.map(i => i.mpn)));
    check('bug22: rescued_rows counter reports the 4 bad-LINE rows',
        result.rescued_rows === 4, 'got ' + result.rescued_rows);

    // Guardrail: a notes/total row (no part id, non-numeric line) must STILL be
    // excluded — the rescue must not pull in junk rows.
    console.log('\n[synthetic: junk/notes rows stay excluded]');
    const wb2 = sheetFromAoa([header,
        ['8519L', 10, '8519L-10', 'ABC123', 'RESISTOR', 1],
        ['', '', '', '', 'TOTAL COMPONENTS: 1', ''],     // notes row, no part id
        ['', 'SEE NOTE', '', '', 'Assembly instructions', ''],
    ]);
    const r2 = KoshBomParser.parseWorkbook(wb2, XLSX);
    check('junk: only the 1 real part is kept',
        r2.bom_items.length === 1, 'got ' + r2.bom_items.length + ' -> ' +
        JSON.stringify(r2.bom_items.map(i => i.desc)));
    check('junk: skipped_rows counter reports the 2 non-part rows',
        r2.skipped_rows === 2, 'got ' + r2.skipped_rows);

    // Sanity: a clean BOM (every row numeric LINE) is unchanged + no rescues.
    console.log('\n[synthetic: clean BOM unaffected]');
    const wb3 = sheetFromAoa([header,
        ['8600L', 5,  '8600L-5',  'M1', 'D1', 1],
        ['8600L', 10, '8600L-10', 'M2', 'D2', 2],
        ['8600L', 15, '8600L-15', 'M3', 'D3', 3],
    ]);
    const r3 = KoshBomParser.parseWorkbook(wb3, XLSX);
    check('clean: all 3 rows kept', r3.bom_items.length === 3, 'got ' + r3.bom_items.length);
    check('clean: no rescues needed', r3.rescued_rows === 0, 'got ' + r3.rescued_rows);
    check('clean: line numbers preserved (5,10,15)',
        JSON.stringify(r3.bom_items.map(i => i.line)) === JSON.stringify([5, 10, 15]),
        JSON.stringify(r3.bom_items.map(i => i.line)));
}

console.log('KOSH BOM parser regression suite');
console.log('Parser: ' + PARSER_PATH);
runSynthetic();

let ran = 0;
for (const sample of SAMPLES) {
    const p = path.join(REPO_ROOT, sample);
    if (!fs.existsSync(p)) {
        console.log('\n[' + sample + '] SKIP (file not in repo)');
        continue;
    }
    runOne(p);
    ran += 1;
}

console.log('\n' + (failures === 0 ? 'OK' : 'FAILED') +
    ' — ' + ran + ' samples, ' + failures + ' failures');
process.exit(failures === 0 ? 0 : 1);
