// KOSH BOM parser. Pure logic — no DOM, no FileReader, no network.
// Loaded by templates/bom_loader.html (browser global) and by
// tests/test_bom_parser.js (Node require). DO NOT inline this back into
// the template or duplicate it elsewhere; the regression suite only
// protects code that lives here.
//
// Input:  a SheetJS workbook object (XLSX.read result)
// Output: { metadata, bom_items, total_items, per_sheet, headers_norm }
//
// Invariants the test suite enforces:
//   * Within a single sheet, every data row is kept (duplicate line
//     numbers like "10 NUT" + "10 ZSUB FOR ABOVE" both load).
//   * Across sheets, line numbers contributed by an earlier (preferred)
//     sheet win — later sheets only add line numbers not yet seen.
//   * "BOM to Load" is always preferred when present.

(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.KoshBomParser = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {

    function normHeaders(row) {
        return (row || []).map(function (h) {
            return String(h == null ? '' : h).trim().toUpperCase().replace(/\s+/g, ' ');
        });
    }

    function findHeaderRow(rows) {
        for (var hr = 0; hr < Math.min(rows.length, 30); hr++) {
            var candidate = normHeaders(rows[hr]);
            var hasLine = false, hasMpnish = false;
            for (var ci = 0; ci < candidate.length; ci++) {
                var c = candidate[ci];
                if (c === 'LINE' || c === 'LINE #' || c === 'LINE NO' || c === 'ITEM' || c === '#' || c === 'NO' || c === 'NO.' || c === 'SR' || c === 'SR NO' || c === 'S.NO' || c === 'S NO') hasLine = true;
                if (c === 'MPN' || c.indexOf('MFG PN') >= 0 || c.indexOf('MFR PN') >= 0 || c.indexOf('PART NUMBER') >= 0 || c === 'PN' || c === 'P/N' || c.indexOf('DESC') >= 0) hasMpnish = true;
            }
            if (hasLine && hasMpnish) return { headerRowIdx: hr, headersNorm: candidate };
        }
        return { headerRowIdx: -1, headersNorm: [] };
    }

    function buildColMap(headersNorm) {
        var col = {};
        for (var i = 0; i < headersNorm.length; i++) {
            var h = headersNorm[i];
            if (col.line === undefined && (h === 'LINE' || h === 'LINE #' || h === 'LINE NO' || h === 'LINE NUMBER' || h === 'ITEM' || h === 'ITEM #' || h === 'ITEM NO' || h === '#' || h === 'NO' || h === 'NO.' || h === 'ROW' || h === 'SEQ' || h === 'SR' || h === 'SR.' || h === 'SR NO' || h === 'S.NO' || h === 'S NO')) col.line = i;
            else if (col.desc === undefined && h.indexOf('DESC') >= 0) col.desc = i;
            else if (col.man === undefined && (h === 'MAN' || h === 'MANUFACTURER' || h === 'MFG' || h === 'MFR' || h === 'MAKER' || h === 'BRAND')) col.man = i;
            else if (col.mpn === undefined && (h === 'MPN' || h === 'MFG PN' || h === 'MFG P/N' || h === 'MANUFACTURER PN' || h === 'MANUFACTURER P/N' || h === 'MFR PN' || h === 'MFR P/N' || h === 'MFR PART' || h === 'MFR PART #' || h === 'MFR PART NO' || h === 'MFR PART NUMBER' || h === 'MFG PART' || h === 'MFG PART #' || h === 'MFG PART NO' || h === 'MFG PART NUMBER' || h === 'PART NUMBER' || h === 'PART #' || h === 'PART NO' || h === 'PART NO.' || h === 'PN' || h === 'P/N' || h === 'PART')) col.mpn = i;
            else if (col.aci_pn === undefined && h.indexOf('ACI') >= 0) col.aci_pn = i;
            else if (col.qty === undefined && (h.indexOf('QTY') >= 0 || h === 'QUANTITY' || h === 'QTY/UNIT' || h === 'QTY PER' || h === 'EXT QTY')) col.qty = i;
            else if (col.pou === undefined && h.indexOf('POU') >= 0) col.pou = i;
            else if (col.loc === undefined && h.indexOf('LOC') >= 0 && h.indexOf('LAST') < 0) col.loc = i;
            else if (col.cost === undefined && (h.indexOf('COST') >= 0 || h.indexOf('PRICE') >= 0)) col.cost = i;
            else if (col.job_rev === undefined && (h.indexOf('JOB REV') >= 0 || h === 'JOBREV' || h === 'JOB REVISION')) col.job_rev = i;
            else if (col.last_rev === undefined && (h.indexOf('LAST REV') >= 0 || h === 'LASTREV' || h === 'LAST REVISION')) col.last_rev = i;
            else if (col.cust_rev === undefined && (h.indexOf('CUST REV') >= 0 || h === 'CUSTREV' || h === 'CUSTOMER REV')) col.cust_rev = i;
            else if (col.cust_pn === undefined && (h.indexOf('CUST PN') >= 0 || h.indexOf('CUST P/N') >= 0 || h === 'CUSTOMER PN' || h === 'CUSTOMER P/N')) col.cust_pn = i;
            else if (col.cust === undefined && (h === 'CUST' || h === 'CUSTOMER')) col.cust = i;
            else if (col.job === undefined && h === 'JOB') col.job = i;
            else if (col.job_rev === undefined && h === 'REV') col.job_rev = i;
        }
        return col;
    }

    function parseSheet(workbook, XLSX, sheetName) {
        var ws = workbook.Sheets[sheetName];
        if (!ws) return null;
        var rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
        if (!rows || rows.length < 2) return null;

        var hr = findHeaderRow(rows);
        if (hr.headerRowIdx === -1) return null;
        var col = buildColMap(hr.headersNorm);

        var sheetMeta = {};
        var sheetItems = [];
        var metaFieldsLocal = { job: 'job', job_rev: 'job_rev', last_rev: 'last_rev', cust: 'customer', cust_pn: 'cust_pn', cust_rev: 'cust_rev' };
        var autoLineLocal = 0;

        for (var r = hr.headerRowIdx + 1; r < rows.length; r++) {
            var row = rows[r];
            if (!row || row.length === 0) continue;
            var allEmpty = true;
            for (var ci2 = 0; ci2 < row.length; ci2++) {
                if (row[ci2] !== '' && row[ci2] !== null && row[ci2] !== undefined) { allEmpty = false; break; }
            }
            if (allEmpty) continue;

            var lineNum;
            if (col.line !== undefined) {
                var p = parseInt(row[col.line]);
                if (isNaN(p)) continue;
                lineNum = p;
            } else {
                autoLineLocal += 1;
                lineNum = autoLineLocal;
            }

            var mpnVal = col.mpn !== undefined ? String(row[col.mpn] || '').trim() : '';
            var descVal = col.desc !== undefined ? String(row[col.desc] || '').trim() : '';
            var qtyChk = col.qty !== undefined ? row[col.qty] : '';
            if (!mpnVal && !descVal && (qtyChk === '' || qtyChk === null || qtyChk === undefined)) continue;

            for (var mk in metaFieldsLocal) {
                var metaKey = metaFieldsLocal[mk];
                if (!sheetMeta[metaKey] && col[mk] !== undefined && row[col[mk]]) {
                    var v = row[col[mk]];
                    if (v instanceof Date) sheetMeta[metaKey] = v.toISOString().split('T')[0];
                    else sheetMeta[metaKey] = String(v).trim();
                }
            }

            var qty = parseInt(col.qty !== undefined ? row[col.qty] : 0) || 0;
            var cost = parseFloat(col.cost !== undefined ? row[col.cost] : 0) || 0;
            var rowLastRev = col.last_rev !== undefined ? row[col.last_rev] : '';
            if (rowLastRev instanceof Date) rowLastRev = rowLastRev.toISOString().split('T')[0];
            else rowLastRev = String(rowLastRev || '').trim();

            sheetItems.push({
                line: lineNum,
                desc: descVal,
                man: col.man !== undefined ? String(row[col.man] || '').trim() : '',
                mpn: mpnVal,
                aci_pn: col.aci_pn !== undefined ? String(row[col.aci_pn] || '').trim() : '',
                qty: qty,
                pou: col.pou !== undefined ? String(row[col.pou] || '').trim() : '',
                loc: col.loc !== undefined ? String(row[col.loc] || '').trim() : '',
                cost: cost,
                job: col.job !== undefined ? String(row[col.job] || '').trim() : '',
                job_rev: col.job_rev !== undefined ? String(row[col.job_rev] || '').trim() : '',
                last_rev: rowLastRev,
                cust: col.cust !== undefined ? String(row[col.cust] || '').trim() : '',
                cust_pn: col.cust_pn !== undefined ? String(row[col.cust_pn] || '').trim() : '',
                cust_rev: col.cust_rev !== undefined ? String(row[col.cust_rev] || '').trim() : ''
            });
        }
        return { items: sheetItems, metadata: sheetMeta, headersNorm: hr.headersNorm, col: col, headerRowIdx: hr.headerRowIdx };
    }

    function parseWorkbook(workbook, XLSX) {
        var preferredOrder = ['BOM to Load'].concat(workbook.SheetNames.filter(function (n) { return n !== 'BOM to Load'; }));
        var bomItems = [];
        var seenLines = {};
        var metadata = {};
        var headersNorm = [];
        var col = {};
        var perSheet = [];

        for (var si = 0; si < preferredOrder.length; si++) {
            var sn = preferredOrder[si];
            var parsed = parseSheet(workbook, XLSX, sn);
            if (!parsed) { perSheet.push({ sheet: sn, status: 'skip' }); continue; }
            if (sn === 'BOM to Load') { headersNorm = parsed.headersNorm; col = parsed.col; }

            var added = 0;
            var sheetLines = {};
            for (var ii = 0; ii < parsed.items.length; ii++) {
                var it = parsed.items[ii];
                var key = String(it.line);
                if (seenLines[key] && !sheetLines[key]) continue;
                sheetLines[key] = true;
                bomItems.push(it);
                added += 1;
            }
            Object.keys(sheetLines).forEach(function (k) { seenLines[k] = true; });
            perSheet.push({ sheet: sn, added: added, total: parsed.items.length });

            Object.keys(parsed.metadata || {}).forEach(function (k) {
                if (!metadata[k] && parsed.metadata[k]) metadata[k] = parsed.metadata[k];
            });
        }

        bomItems.sort(function (a, b) { return (a.line || 0) - (b.line || 0); });

        if (metadata.job && metadata.job.endsWith && metadata.job.endsWith('.0')) {
            metadata.job = metadata.job.slice(0, -2);
        }

        return {
            metadata: metadata,
            bom_items: bomItems,
            total_items: bomItems.length,
            per_sheet: perSheet,
            headers_norm: headersNorm,
            col: col
        };
    }

    return {
        parseWorkbook: parseWorkbook,
        parseSheet: parseSheet,
        findHeaderRow: findHeaderRow,
        buildColMap: buildColMap
    };
}));
