# Stock Page Implementation - Quick Reference

## Files You Need to Know

### Frontend (User Interface)
- **Stock Page:** `/home/tony/ACI Invertory/templates/stock.html` (1113 lines)
  - Barcode scanning code: Lines 454-503 (USB HID), 624-821 (parsing), 824-893 (Quagga camera)
  - Form definition: Lines 42-293
  - Recent Stock Operations: Lines 903-953

- **Pick Page:** `/home/tony/ACI Invertory/templates/pick.html`
  - Mirror of stock but removes parts instead of adding

- **Inventory Page:** `/home/tony/ACI Invertory/templates/inventory.html`
  - Browse and search all inventory with filters

### Backend (Flask Routes)
- **app.py - Main Application:** `/home/tony/ACI Invertory/app.py` (4000+ lines)
  - Stock route: `1125-1185` (`@app.route('/stock')`)
  - Pick route: `1187-1229` (`@app.route('/pick')`)
  - Inventory route: `1231-1320` (`@app.route('/inventory')`)
  - API Stock: `1700-1734` (`@app.route('/api/stock')`)
  - API Inventory: `1688-1698` (`@app.route('/api/inventory')`)
  - API PCN Details: `2124-2197` (`@app.route('/api/pcn/details/<pcn>')`)

### Database (Backend)
- **Stored Procedures:** `/home/tony/ACI Invertory/init_functions.sql`
  - `stock_pcb()` function with 14 parameters
  - `pick_pcb()` function with 7 parameters
  - PCN generation and validation

## Barcode Format

### Standard Format (Pipe-Delimited)
```
PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
```

**Example:**
```
00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001|8000-8999|Completed|2025W42|Level 3
```

### Supported Formats
1. Pipe-delimited (|) - PRIMARY
2. Comma-delimited (,)
3. Semicolon-delimited (;)
4. Space-delimited (spaces)
5. Tab-delimited (\t)
6. Newline-delimited (\n)
7. JSON format ({...})
8. Single values (PCN, part number, MPN)

## Key API Endpoints

### POST /api/stock
Stock parts in inventory
```bash
curl -X POST http://localhost:5002/api/stock \
  -H "Content-Type: application/json" \
  -d '{
    "job": "TEST-PART-001",
    "part_number": "PART-001",
    "pcb_type": "Completed",
    "quantity": 100,
    "location": "8000-8999",
    "itar_classification": "NONE"
  }'
```

### GET /api/inventory
Get all inventory (sorted most recent first)
```bash
curl http://localhost:5002/api/inventory
```

### GET /api/pcn/details/<pcn_number>
Get PCN details for auto-populating form
```bash
curl http://localhost:5002/api/pcn/details/00045
```

### POST /api/pick
Remove parts from inventory
```bash
curl -X POST http://localhost:5002/api/pick \
  -H "Content-Type: application/json" \
  -d '{
    "job": "TEST-PART-001",
    "pcb_type": "Completed",
    "quantity": 50
  }'
```

## Barcode Scanning Integration

### Hardware Scanner (USB HID)
1. Plug in USB barcode scanner
2. On stock page, have focus anywhere outside form fields
3. Scan barcode - scanner types it rapidly + Enter
4. JavaScript detects rapid keystrokes + Enter
5. Parses barcode format
6. Auto-fills form fields
7. If PCN detected, fetches additional data from DB

### Camera Scanner
1. Click "Scan" button (if available)
2. Quagga.js modal opens with camera feed
3. Point camera at barcode
4. Library auto-detects and closes modal
5. Form auto-fills

## Form Submission Flow

```
User Input/Scan
    ↓
Form Validation (required fields, quantity range, PCB type)
    ↓
ITAR Check (user must have permission for ITAR items)
    ↓
POST to /stock with form data
    ↓
Backend calls PostgreSQL stock_pcb() function
    ↓
Database updates tblPCB_Inventory
    ↓
Transaction logged to tblTransaction
    ↓
Success response with new PCN
    ↓
Flash message displayed
    ↓
Redirect to /stock
    ↓
Recent Stock Operations loads from /api/inventory
    ↓
New item appears at top of table
```

## Database Fields

### Primary Inventory Table (tblPCB_Inventory)
- `id` - Record ID
- `pcn` - Part Control Number
- `job` - Job number (item identifier)
- `pcb_type` - Bare, Partial, Completed, Ready to Ship
- `qty` - Quantity
- `location` - Storage location
- `migrated_at` - Last update timestamp

### Barcode Data Stored
- `barcode_data` field in pcn_records table
- Format: PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
- Used for generating labels with barcodes

## Code Examples

### Parse Pipe-Delimited Barcode
```javascript
const barcodeString = "00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001||Completed|2025W42|Level 3";
const fields = barcodeString.split('|');

const data = {
    pcn: fields[0],           // "00045"
    item: fields[1],          // "TEST-PART-001"
    mpn: fields[2],           // "TEST-MPN-123"
    partNumber: fields[3],    // "PART-001"
    quantity: fields[4],      // "100"
    po: fields[5],            // "PO-2025-001"
    location: fields[6],      // "" (empty)
    pcbType: fields[7],       // "Completed"
    dateCode: fields[8],      // "2025W42"
    msd: fields[9]            // "Level 3"
};
```

### Auto-Fill Form from Parsed Data
```javascript
if (data.pcn) document.getElementById('pcnInput').value = data.pcn;
if (data.item) document.getElementById('partNumberInput').value = data.item;
if (data.mpn) document.getElementById('mpnInput').value = data.mpn;
if (data.quantity) document.getElementById('quantity').value = data.quantity;
if (data.po) document.getElementById('poInput').value = data.po;
if (data.location) document.getElementById('location').value = data.location;
if (data.pcbType) document.getElementById('pcb_type').value = data.pcbType;
if (data.dateCode) document.getElementById('dc').value = data.dateCode;
if (data.msd) document.getElementById('msd').value = data.msd;
```

## Important Form Fields

| Field | Type | Required | Validation |
|-------|------|----------|-----------|
| Part Number | Text | Yes | 1-50 chars |
| Quantity | Number | Yes | 1-10,000 |
| PCB Type | Select | Yes | Bare/Partial/Completed/Ready to Ship |
| Location | Text | Yes | Max 20 chars |
| PCN Number | Text | No | Auto-generated if blank |
| MPN | Text | No | Max 50 chars |
| PO | Text | No | Max 50 chars |
| Date Code | Text | No | Max 50 chars |
| MSD | Text | No | Max 50 chars |
| ITAR Classification | Select | No | NONE/EAR99/SENSITIVE/ITAR |
| Export Control Notes | Text | No | Shown only for ITAR items |

## Common Issues & Solutions

### Issue: Barcode scans but doesn't fill form
- Check if PCN field auto-focus is working
- Verify form fields have correct IDs (pcnInput, mpnInput, etc.)
- Check browser console for JavaScript errors
- Ensure barcode format includes pipe delimiters

### Issue: Form submits but nothing happens
- Check if stored procedure stock_pcb() exists in DB
- Verify user role permissions
- Check for ITAR authorization if stocking ITAR items
- Look at application logs: `docker logs stockandpick_webapp`

### Issue: Recent Stock Operations not showing
- Verify /api/inventory endpoint returns data
- Check if database has any inventory records
- Ensure migrated_at timestamp is set correctly
- Check browser console for fetch errors

### Issue: PCN lookup fails
- Verify PCN exists in pcn_records or pcn_history tables
- Ensure PCN is padded to 5 digits (e.g., "00045")
- Check if /api/pcn/details/<pcn> returns 404 or error

## Testing Commands

### Test Stock Operation
```bash
# Via SQL
docker exec stockandpick_postgres psql -U stockpick_user -d pcb_inventory \
  -c "SELECT pcb_inventory.stock_pcb('TEST', 'Bare', 10, 'A1', 'NONE', 'USER', false, 'test', NULL, NULL, NULL, NULL, NULL, NULL);"

# Via API
curl -X POST http://localhost:5002/api/stock \
  -H "Content-Type: application/json" \
  -d '{"job":"TEST","pcb_type":"Bare","quantity":10,"location":"A1"}'
```

### Test API Inventory
```bash
curl http://localhost:5002/api/inventory
```

### Test PCN Lookup
```bash
curl http://localhost:5002/api/pcn/details/00045
```

### View Recent Activity
```bash
docker logs stockandpick_webapp --tail 50
```

## Key Classes & Functions

### Backend
- `StockForm` - WTF form class for stock page
- `DatabaseManager.stock_pcb()` - Calls stored procedure
- `api_stock()` - API handler for POST /api/stock
- `inventory()` - Handler for /inventory page

### Frontend (JavaScript)
- `parseAndFillBarcode()` - Main barcode parsing function
- `fetchAndPopulatePCNDetails()` - Fetch PCN data from API
- `loadRecentStockOperations()` - Load recent items for display
- `startScanner()` - Initialize Quagga camera scanner
- `stopScanner()` - Cleanup camera scanner

## Documentation Files

- **STOCK_IMPLEMENTATION_COMPLETE_ANALYSIS.md** - Comprehensive guide
- **STOCK_PAGE_FIXES_AND_TESTS.md** - Testing report
- **BARCODE_FULL_DATA_FIX.md** - Barcode format details
- **WORKING_STATUS.md** - System status

---

**Last Updated:** November 3, 2025
**Project:** KOSH 2.0 - ACI Inventory Management
**Location:** /home/tony/ACI Invertory
