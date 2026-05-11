// Shared label-print helpers for KOSH.
// Tries Zebra Browser Print first (true silent print), then falls back to a
// modal-style iframe preview pointing at /print-label/<pcn>. Generate PCN,
// Part Number Change, and any other page that needs to print a PCN label
// after an action should call window.silentPrint(pcnNumber).

(function () {
    function generateZPL(data) {
        const pcn = data.pcn_number || data.pcn || '';
        const item = data.item || data.job || data.part_number || '';
        const mpn = data.mpn || '';
        const po = data.po_number || '';
        const vendor = data.vendor_name || '';
        const qty = data.quantity || '0';
        const dc = data.date_code || '';
        const msd = data.msd || data.msd_level || '';

        // Uniform 26pt body text across every detail line. Single stamp
        // (no bold double-print) so long values like Item No don't overflow.
        const F = '^A0N,26,26';
        const stamp = (x, y, text) => `^FO${x},${y}${F}^FD${text}^FS`;

        let zpl = `^XA
${stamp(15, 6, `PCN: ${pcn}`)}

^FO170,4^BY2,2,45^BCN,45,N,N,N^FD${pcn}^FS

${stamp(490, 6, 'QTY')}
${stamp(490, 34, `${qty}`)}

^FO15,68^GB579,0,2^FS

${stamp(20, 75, `Job: ${item}`)}
${dc ? stamp(400, 75, `DCC: ${dc}`) : ''}

${mpn ? stamp(20, 108, `MPN: ${mpn}`) : ''}

${po ? stamp(20, 141, `PO: ${po}`) : ''}
${msd ? stamp(420, 141, `MSD: ${msd}`) : ''}

^XZ`;
        return zpl;
    }

    function showPrintPreview(pcnNumber) {
        try {
            const existingIframe = document.getElementById('printIframe');
            const existingBackdrop = document.getElementById('printBackdrop');
            if (existingIframe) existingIframe.remove();
            if (existingBackdrop) existingBackdrop.remove();

            const backdrop = document.createElement('div');
            backdrop.id = 'printBackdrop';
            backdrop.style.cssText = `
                position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background-color: rgba(0,0,0,0.7); z-index: 9999;
                display: flex; align-items: center; justify-content: center;
            `;

            const iframe = document.createElement('iframe');
            iframe.id = 'printIframe';
            iframe.style.cssText = `
                width: 900px; height: 700px; border: 3px solid #333;
                border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.4);
                background-color: white;
            `;

            backdrop.onclick = function () {
                iframe.remove();
                backdrop.remove();
            };

            document.body.appendChild(backdrop);
            backdrop.appendChild(iframe);
            iframe.src = `/print-label/${pcnNumber}`;
        } catch (error) {
            console.error('ERROR creating print preview:', error);
            alert('Error opening print preview: ' + error.message);
        }
    }

    window.silentPrint = async function (pcnNumber) {
        if (!pcnNumber) {
            alert('Error: No PCN number provided');
            return;
        }

        try {
            if (typeof BrowserPrint === 'undefined') {
                showPrintPreview(pcnNumber);
                return;
            }

            const response = await fetch(`/api/pcn/details/${pcnNumber}`);
            if (!response.ok) throw new Error('Failed to fetch PCN details');
            const result = await response.json();
            if (!result.success) throw new Error('PCN not found');

            BrowserPrint.getDefaultDevice('printer', function (printer) {
                if (printer && printer.name) {
                    const zpl = generateZPL(result);
                    printer.send(zpl, function () {
                        // sent successfully
                    }, function (error) {
                        console.error('Print error:', error);
                        showPrintPreview(pcnNumber);
                    });
                } else {
                    showPrintPreview(pcnNumber);
                }
            }, function (error) {
                console.warn('Zebra printer detection failed:', error);
                showPrintPreview(pcnNumber);
            });
        } catch (error) {
            console.error('silentPrint error:', error);
            showPrintPreview(pcnNumber);
        }
    };

    window.showPrintPreview = showPrintPreview;
})();
