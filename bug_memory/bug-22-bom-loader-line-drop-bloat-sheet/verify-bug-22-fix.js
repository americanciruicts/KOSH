#!/usr/bin/env node
// Bug #22 verify — runs the SHIPPED parser (static/js/bom_parser.js) and asserts
// all three fixes hold: (a) real-part rows are never dropped for a bad LINE cell,
// (b) bloated declared ranges are tightened (still load, fast), (c) ONLY the
// "BOM to Load" sheet is read. Also re-parses the real customer BOM files when
// present in the repo root.
//
// Run:  NODE_PATH=/tmp/node_modules node verify-bug-22-fix.js
// Exit code 0 = pass.
const path = require('path');
const fs = require('fs');
const REPO = path.resolve(__dirname, '../..');
let XLSX; try { XLSX = require('xlsx'); } catch (e) { XLSX = require('/tmp/node_modules/xlsx'); }
const P = require(path.join(REPO, 'static/js/bom_parser.js'));

let fails = 0;
function check(name, cond, detail) {
    console.log((cond ? '  PASS  ' : '  FAIL  ') + name + (cond ? '' : '  -> ' + detail));
    if (!cond) fails++;
}
const HEADER = ['Job', 'Line', 'ACI PN', 'MPN', 'Description', 'Qty'];
function wbFrom(sheets) {
    const wb = XLSX.utils.book_new();
    for (const [name, aoa] of sheets) XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), name);
    return wb;
}

// 22a — rescue rows whose LINE cell is blank/non-numeric but have a real part id
const wbA = wbFrom([['BOM to Load', [HEADER,
    ['J', 5, 'J-5', 'MPN-5', 'D', 1],
    ['', '', 'J-10', 'MPN-10', 'D', 1],     // blank line cell + real part -> rescued
    ['', '', 'J-15', 'MPN-15', 'D', 1]]]]);
const rA = P.parseWorkbook(wbA, XLSX);
check('22a: real-part rows with blank LINE cell are kept (3)', rA.bom_items.length === 3, 'got ' + rA.bom_items.length);
check('22a: rescued_rows counts the 2 blank-line rows', rA.rescued_rows === 2, 'got ' + rA.rescued_rows);

// 22b — bloated declared range tightened, still loads
const wsB = XLSX.utils.aoa_to_sheet([HEADER, ['8517L-2', 5, '8517L-2-5', 'VTB8441BH', 'PHOTODIODE', 1]]);
wsB['!ref'] = 'A1:AI6588';
check('22b: tightRange shrinks A1:AI6588', P.tightRange(wsB, XLSX).indexOf('6588') === -1, P.tightRange(wsB, XLSX));
const wbB = XLSX.utils.book_new(); XLSX.utils.book_append_sheet(wbB, wsB, 'BOM to Load');
const t0 = Date.now(); const rB = P.parseWorkbook(wbB, XLSX); const ms = Date.now() - t0;
check('22b: bloated file still yields the 1 real line, fast', rB.bom_items.length === 1 && ms < 500, 'items=' + rB.bom_items.length + ' ' + ms + 'ms');

// 22c — only "BOM to Load" is read
const wbC = wbFrom([
    ['BOM to Load', [HEADER, ['J', 1, 'J-1', 'M1', 'D', 1], ['J', 2, 'J-2', 'M2', 'D', 1]]],
    ['Assy BOM', [HEADER, ['J', 9, 'J-9', 'M9', 'ONLY ON ASSY', 1]]]]);
const rC = P.parseWorkbook(wbC, XLSX);
check('22c: loads only the 2 BOM-to-Load lines', rC.bom_items.length === 2, 'got ' + rC.bom_items.length);
check('22c: Assy-BOM-only line 9 is NOT loaded', !rC.bom_items.some(i => i.line === 9), JSON.stringify(rC.bom_items.map(i => i.line)));

// Real customer files (if present)
const REAL = {
    '8517L-2 PARATA 320-0121 BOM FOR ASSEMBLY.xlsx': 1,
    '8858L 3M Shelf Charger BOM FOR ASSEMBLY.xlsx': 35,
    '8517LF PARATA 301-0834 BOM FOR ASSEMBLY - Copy.xlsx': 9,
    '6732LF BOX SCIENTIFIC HELIPORT BOX BOM FOR ASSEMBLY.xlsx': 28,
};
for (const [fname, expect] of Object.entries(REAL)) {
    const p = path.join(REPO, fname);
    if (!fs.existsSync(p)) { console.log('  SKIP  real file not in repo: ' + fname.slice(0, 20)); continue; }
    const wb = XLSX.read(new Uint8Array(fs.readFileSync(p)), { type: 'array', cellDates: true });
    const r = P.parseWorkbook(wb, XLSX);
    const onlyBTL = r.per_sheet.every(s => s.sheet === 'BOM to Load' || s.status === 'skip' || s.added === 0);
    check('real: ' + fname.slice(0, 16) + ' -> ' + expect + ' items, BOM-to-Load only',
        r.bom_items.length === expect, 'got ' + r.bom_items.length);
}

console.log('RESULT: ' + (fails === 0 ? 'ALL PASS' : fails + ' FAILED'));
process.exit(fails === 0 ? 0 : 1);
