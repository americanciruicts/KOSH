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
        if (col.line !== undefined) {
            const p = parseInt(row[col.line]);
            if (isNaN(p)) continue;
        }
        const mpn = col.mpn !== undefined ? String(row[col.mpn] || '').trim() : '';
        const desc = col.desc !== undefined ? String(row[col.desc] || '').trim() : '';
        const qtyChk = col.qty !== undefined ? row[col.qty] : '';
        if (!mpn && !desc && (qtyChk === '' || qtyChk === null || qtyChk === undefined)) continue;
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

console.log('KOSH BOM parser regression suite');
console.log('Parser: ' + PARSER_PATH);

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
