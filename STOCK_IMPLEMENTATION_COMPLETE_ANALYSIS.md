# Stock Page Implementation - Complete Understanding

**Project:** ACI Inventory Management System (KOSH 2.0)
**Location:** /home/tony/ACI Invertory
**Tech Stack:** Flask (Python Backend) + Bootstrap 5 (Frontend) + PostgreSQL (Database)
**Date:** November 3, 2025

---

## Table of Contents
1. [Project Structure](#project-structure)
2. [Stock Page Overview](#stock-page-overview)
3. [Barcode Scanning Implementation](#barcode-scanning-implementation)
4. [API Endpoints](#api-endpoints)
5. [Database Layer](#database-layer)
6. [Key Features](#key-features)
7. [File Locations](#file-locations)

---

## Project Structure

### Directory Layout
```
/home/tony/ACI Invertory/
├── app.py                           # Main Flask application (4000+ lines)
├── templates/
│   ├── stock.html                   # Stock page UI
│   ├── pick.html                    # Pick/Remove from inventory page
│   ├── inventory.html               # Inventory listing/browsing page
│   ├── generate_pcn.html            # PCN generation and labeling
│   ├── base.html                    # Base template with navbar
│   └── ... (other templates)
├── migration/                       # Migration-related files
├── init_functions.sql               # PostgreSQL stored procedures
├── expiration_manager.py            # Expiration date calculations
├── STOCK_PAGE_FIXES_AND_TESTS.md    # Testing documentation
├── BARCODE_FULL_DATA_FIX.md         # Barcode implementation details
└── ... (other config files)
```

### Tech Stack
- **Backend:** Flask 2.x (Python 3.9+)
- **Frontend:** HTML5 + Bootstrap 5 + JavaScript
- **Barcode Scanning:** Quagga.js (camera-based) + USB HID Scanner support
- **Database:** PostgreSQL (containerized)
- **Authentication:** Flask-WTF with CSRF protection
- **Caching:** Flask-Caching (in-memory)
- **Compression:** Flask-Compress (gzip)

---

## Stock Page Overview

### Location
- **URL Route:** `/stock` (GET/POST)
- **Template File:** `/home/tony/ACI Invertory/templates/stock.html` (1113 lines)
- **Route Handler:** `/home/tony/ACI Invertory/app.py:1125-1185`

### Page Purpose
The stock page allows users to add electronic components to inventory with the following information:
- **Part Identification:** PCN, MPN, Part Number
- **Quantity & Type:** Quantity, PCB Assembly Stage (Bare/Partial/Completed/Ready to Ship)
- **Storage & Security:** Location, ITAR Classification
- **Optional Details:** Date Code (DC), Moisture Sensitive Device (MSD), Purchase Order (PO)
- **Metadata:** Work Order, Export Control Notes (for ITAR items)

### Form Class
```python
class StockForm(FlaskForm):
    pcn_number = StringField('PCN Number', validators=[Length(max=10)])
    job = StringField('Job Number (Item)', validators=[Length(max=50)])
    mpn = StringField('MPN (Manufacturing Part Number)', validators=[Length(max=50)])
    part_number = StringField('Part Number', validators=[DataRequired(), Length(min=1, max=50)])
    po = StringField('PO (Purchase Order)', validators=[Length(max=50)])
    work_order = StringField('Work Order Number', validators=[Length(max=50)])
    pcb_type = StringField('Component Type', validators=[DataRequired(), validate_pcb_type_field])
    dc = StringField('Date Code (DC)', validators=[Length(max=50)])
    msd = StringField('Moisture Sensitive Device (MSD)', validators=[Length(max=50)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    location = StringField('Location', validators=[DataRequired()], default='8000-8999')
    itar_classification = SelectField('ITAR Classification', choices=ITAR_CLASSIFICATIONS, default='NONE')
    export_control_notes = StringField('Export Control Notes', validators=[Length(max=500)])
    submit = SubmitField('Stock Parts')
```

### Form Validation Rules
- **Part Number:** Required (minimum 1 character, max 50)
- **Quantity:** Required, must be 1-10000
- **PCB Type:** Must be one of: "Bare", "Partial", "Completed", "Ready to Ship"
- **Location:** Required (max 20 characters)
- **ITAR Classification:** Dropdown with security levels (NONE, EAR99, SENSITIVE, ITAR)
- **Quantity Validation:** Shows confirmation dialog for quantities > 1000
- **ITAR Access Control:** Export notes field only shows for ITAR-classified items

---

## Barcode Scanning Implementation

### Barcode Format
The barcode encodes **all label information** in a **pipe-delimited format**:

```
PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
```

**Example:**
```
00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001|8000-8999|Completed|2025W42|Level 3
```

### Field Mapping
| Position | Field | Example | Description |
|----------|-------|---------|-------------|
| 1 | PCN | 00045 | Part Control Number (5-digit, zero-padded) |
| 2 | Item | TEST-PART-001 | Job number or item identifier |
| 3 | MPN | TEST-MPN-123 | Manufacturer Part Number |
| 4 | PartNumber | PART-001 | Part number / customer part number |
| 5 | QTY | 100 | Quantity |
| 6 | PO | PO-2025-001 | Purchase Order number |
| 7 | Location | 8000-8999 | Warehouse location |
| 8 | PCBType | Completed | Component type |
| 9 | DateCode | 2025W42 | Date code (week/year) |
| 10 | MSD | Level 3 | Moisture Sensitive Device level |

### Scanning Methods

#### 1. USB HID Scanner (Hardware Barcode Scanner)
**Implementation Location:** `/home/tony/ACI Invertory/templates/stock.html:454-503`

**How It Works:**
- USB HID scanners simulate keyboard input (typing rapidly followed by Enter/Tab)
- Global event listener buffers keyboard input
- When Enter/Tab is detected, data is parsed and form fields are auto-filled
- Minimum scan length: 3 characters
- Scan timeout: 100ms (faster than human typing)

**Code:**
```javascript
let scanBuffer = '';
let scanTimeout = null;
const SCAN_TIMEOUT_MS = 100;
const MIN_SCAN_LENGTH = 3;

document.addEventListener('keypress', function(e) {
    // If Enter/Tab pressed with buffered data, treat as barcode scan
    if ((e.key === 'Enter' || e.key === 'Tab') && scanBuffer.length >= MIN_SCAN_LENGTH) {
        parseAndFillBarcode(scanBuffer.trim());
        scanBuffer = '';
        return;
    }
    
    // Buffer characters
    if (e.key !== 'Enter' && e.key !== 'Tab') {
        scanBuffer += e.key;
        // Reset buffer after timeout
        scanTimeout = setTimeout(function() {
            if (scanBuffer.length >= MIN_SCAN_LENGTH) {
                parseAndFillBarcode(scanBuffer.trim());
            }
            scanBuffer = '';
        }, SCAN_TIMEOUT_MS);
    }
});
```

#### 2. Camera-Based Scanner (Quagga.js)
**Implementation Location:** `/home/tony/ACI Invertory/templates/stock.html:824-893`

**How It Works:**
- Modal dialog opens with camera video feed
- Quagga.js library detects barcodes in real-time
- Supports multiple barcode formats: CODE128, EAN, UPC, Code39, etc.
- On detection, automatically closes modal and fills form

**Supported Barcode Formats:**
- Code 128
- EAN (13 and 8)
- Code 39
- Code 39 VIN
- Codabar
- UPC (A and E)
- Interleaved 2 of 5
- Code 93

**Usage:**
- Click "Scan" button in UI (if implemented)
- Quagga initializes with camera
- Point camera at barcode
- Modal closes on successful scan
- Form auto-fills with parsed data

### Barcode Parsing Logic
**Location:** `/home/tony/ACI Invertory/templates/stock.html:624-821`

**Parsing Priority:**
1. **JSON Format:** If starts with `{` and ends with `}`, parse as JSON
2. **Delimited Format:** Check for pipe (|), comma, semicolon, space, newline, or tab separators
3. **Standardized Format:** If pipe-delimited with 5+ fields, use direct field mapping
4. **Smart Parsing:** Use regex patterns to identify field types
5. **Single Value:** Treat as PCN, part number, or MPN based on format

**Smart Field Detection Patterns:**
```javascript
- PCN: /^\d{5}$/ or first position 1-4 digits (padded to 5)
- Quantity: 1-4 digits, > 0, <= 10000, not in first position
- MPN: 6+ alphanumeric characters
- Job/Item: 2-8 alphanumeric characters
- Part Number: 4+ alphanumeric characters
- PO: Starts with "PO" or contains dash
- PCB Type: Contains "bare", "partial", "completed", "ready"
- Date Code: YYYY(WK)DD or YY(WK)DD format
- MSD: "level X" or "Xhrs@Y" format
```

### Auto-Population
When barcode is parsed successfully:
1. **All matching fields are filled** with parsed data
2. **PCN triggers auto-fetch** via `/api/pcn/details/<pcn_number>`
3. **Additional data loaded** from database (part_number, mpn, po, quantity, date_code, msd, location, pcb_type)
4. **Visual feedback** shows with success notification

---

## API Endpoints

### Stock Operations

#### 1. POST /api/stock
**Purpose:** API endpoint for stocking PCBs programmatically

**Request:**
```json
{
    "job": "TEST-PART-001",
    "part_number": "PART-001",
    "pcb_type": "Completed",
    "quantity": 100,
    "location": "8000-8999",
    "itar_classification": "NONE",
    "mpn": "MPN-123",
    "po": "PO-2025-001"
}
```

**Response:**
```json
{
    "success": true,
    "job": "TEST-PART-001",
    "pcb_type": "Completed",
    "stocked_qty": 100,
    "new_qty": 100,
    "location": "8000-8999",
    "pcn": 45,
    "message": "Successfully stocked 100 Completed PCBs for job TEST-PART-001"
}
```

**Route Location:** `/home/tony/ACI Invertory/app.py:1700-1734`
**Handler:** `api_stock()`
**Decorators:** `@require_auth`, `@validate_api_request`

---

#### 2. GET /api/inventory
**Purpose:** Retrieve current inventory data (used for displaying Recent Stock Operations)

**Response:**
```json
{
    "success": true,
    "data": [
        {
            "id": 1,
            "pcn": 45,
            "job": "TEST-PART-001",
            "pcb_type": "Completed",
            "qty": 100,
            "location": "8000-8999",
            "updated_at": "2025-10-28T18:24:15.123456+00"
        },
        ...
    ]
}
```

**Route Location:** `/home/tony/ACI Invertory/app.py:1688-1698`
**Handler:** `api_inventory()`
**Query Order:** Sorted by `migrated_at DESC NULLS LAST, job, pcb_type`
**Purpose on Stock Page:** Loads first 5 items for "Recent Stock Operations" table

---

#### 3. GET /api/pcn/details/<pcn_number>
**Purpose:** Fetch PCN details for auto-populating form fields when PCN is scanned

**Response:**
```json
{
    "success": true,
    "pcn_number": "00045",
    "part_number": "PART-001",
    "job": "TEST-PART-001",
    "po_number": "PO-2025-001",
    "mpn": "MPN-123",
    "quantity": 100,
    "date_code": "2025W42",
    "msd": "Level 3",
    "created_at": "2025-10-30T10:15:00",
    "created_by": "testuser"
}
```

**Route Location:** `/home/tony/ACI Invertory/app.py:2124-2197`
**Handler:** `api_get_pcn_details(pcn_number)`
**Data Sources:**
1. First checks `pcn_records` table (generated PCNs)
2. Falls back to `pcn_history` table if not found

---

#### 4. POST /api/pcn/generate
**Purpose:** Generate new PCN with barcode data encoding all fields

**Request:**
```json
{
    "item": "TEST-PART-001",
    "mpn": "MPN-123",
    "part_number": "PART-001",
    "quantity": 100,
    "po_number": "PO-2025-001",
    "location": "8000-8999",
    "pcb_type": "Completed",
    "date_code": "2025W42",
    "msd": "Level 3"
}
```

**Response:**
```json
{
    "success": true,
    "pcn_number": "00045",
    "barcode_data": "00045|TEST-PART-001|MPN-123|PART-001|100|PO-2025-001|8000-8999|Completed|2025W42|Level 3",
    "created_at": "2025-10-30T10:15:00"
}
```

**Route Location:** `/home/tony/ACI Invertory/app.py:2008-2107`
**Handler:** `api_generate_pcn()`
**Key Feature:** Stores complete barcode_data (all 10 fields) in database

---

#### 5. POST /api/pick
**Purpose:** Remove parts from inventory

**Request:**
```json
{
    "job": "TEST-PART-001",
    "part_number": "PART-001",
    "pcb_type": "Completed",
    "quantity": 50
}
```

**Response:**
```json
{
    "success": true,
    "job": "TEST-PART-001",
    "pcb_type": "Completed",
    "picked_qty": 50,
    "new_qty": 50,
    "message": "Successfully picked 50 Completed PCBs"
}
```

**Route Location:** `/home/tony/ACI Invertory/app.py:1736-1763`
**Handler:** `api_pick()`
**Error Handling:** Returns specific errors for insufficient quantity or missing jobs

---

### Inventory Lookup

#### 6. GET /inventory
**Purpose:** Browse and search inventory with advanced filters

**Query Parameters:**
- `job` - Search by job number (comma-separated)
- `pcb_type` - Filter by component type
- `location` - Filter by storage location
- `pcn` - Search by PCN number
- `date_from` - Date range (from)
- `date_to` - Date range (to)
- `min_qty` - Minimum quantity filter
- `max_qty` - Maximum quantity filter
- `page` - Pagination (default 1)
- `per_page` - Items per page (10-200, default 10)
- `sort` - Sort field (default "job")
- `order` - Sort order (asc/desc)

**Route Location:** `/home/tony/ACI Invertory/app.py:1231-1320`
**Handler:** `inventory()`
**Features:**
- Advanced filtering with multiple criteria
- Pagination support
- Sort by job, PCB type, quantity, etc.
- ITAR access control (non-authorized users don't see ITAR items)

---

## Database Layer

### Stored Procedures

#### 1. stock_pcb() Function
**Location:** `/home/tony/ACI Invertory/init_functions.sql:1-150`

**Parameters (14 total):**
```python
def stock_pcb(self, job: str, pcb_type: str, quantity: int, location: str,
              itar_classification: str = 'NONE', user_role: str = 'USER',
              itar_auth: bool = False, username: str = 'system', work_order: str = None,
              dc: str = None, msd: str = None, pcn: int = None, mpn: str = None,
              part_number: str = None) -> Dict[str, Any]:
```

**Functionality:**
- Input validation for job, pcb_type, quantity, location
- Auto-generate PCN if not provided
- Check for existing inventory record
- Create new inventory or update quantity
- Log transaction to `tblTransaction` table
- Update `migrated_at` timestamp to current time
- Return JSON with success/failure details

**Called From:** `/home/tony/ACI Invertory/app.py:1157`

---

#### 2. pick_pcb() Function
**Location:** `/home/tony/ACI Invertory/init_functions.sql:150-250`

**Parameters (7 total):**
```python
def pick_pcb(self, job: str, pcb_type: str, quantity: int,
             user_role: str = 'USER', itar_auth: bool = False, 
             username: str = 'system', work_order: str = None) -> Dict[str, Any]:
```

**Functionality:**
- Check if job/pcb_type combination exists in inventory
- Validate sufficient quantity available
- Deduct quantity from inventory
- Log transaction
- Return availability or error message

---

### Database Tables Referenced

#### tblPCB_Inventory
- **Primary Table:** Stores current inventory
- **Key Fields:** id, pcn, job, pcb_type, qty, location, migrated_at
- **Usage:** Stock operations query/update this table

#### tblTransaction
- **Purpose:** Audit trail for all stock/pick operations
- **Logged By:** Stored procedures
- **Fields:** transaction_id, operation_type, job, quantity, user, timestamp

#### pcn_records
- **Purpose:** Stores generated PCN details
- **Fields:** pcn_id, pcn_number, item, po_number, part_number, mpn, quantity, date_code, msd, barcode_data, created_by, created_at
- **Usage:** Lookup when PCN is scanned

#### pcn_history
- **Purpose:** Historical record of PCN assignments
- **Fields:** pcn, job, qty, date_code, msd, work_order, location, pcb_type, generated_by, generated_at

---

## Key Features

### 1. Smart Barcode Parsing
- Automatically detects barcode format (JSON, delimited, single value)
- Uses intelligent field detection with regex patterns
- Handles multiple delimiter types (|, comma, semicolon, space, tab, newline)
- Falls back gracefully for unknown formats

### 2. USB HID Scanner Support
- Global keyboard event listener for scanner input
- Distinguishes scanner input from human typing using speed/timeout detection
- Auto-fills form fields sequentially on Enter key
- Visual "Scanning..." indicator during data reception

### 3. Camera-Based Scanning (Quagga.js)
- Real-time barcode detection using device camera
- Supports 10+ barcode formats
- Modal dialog with camera stream
- Automatic modal dismissal on successful scan

### 4. PCN Auto-Population
- When PCN is scanned, system looks up details from database
- Auto-fills: part_number, mpn, po, quantity, date_code, msd, location, pcb_type
- Shows success notification with PCN number
- Makes visual feedback with border highlight on PCN field

### 5. Form Validation
- Real-time validation of all required fields
- Quantity range validation (1-10000)
- PCB type validation against allowed values
- ITAR access control with role-based hiding of options
- Conditional visibility of export control notes field

### 6. Recent Stock Operations Display
- Shows top 5 most recently stocked items
- Loads via `/api/inventory` API call
- Displays: Job, PCB Type, Quantity, Location, Time Since Operation
- Sorted by `migrated_at` DESC (newest first)
- Updates on page load automatically

### 7. Multi-role Access Control
- **Super User, Manager, ITAR roles:** Can access ITAR items
- **User, Operator roles:** Cannot see ITAR classifications
- **ITAR-authorized users:** See export control notes field
- Form adjusts available options based on user role

### 8. ITAR Classification System
- Four classification levels: NONE, EAR99, SENSITIVE, ITAR
- ITAR items require special authorization to stock
- Export control notes field appears conditionally for sensitive items
- Database logs which user stocked each item

---

## File Locations - Summary

### Core Implementation Files

| File | Location | Purpose |
|------|----------|---------|
| **Stock Page Template** | `/home/tony/ACI Invertory/templates/stock.html` | UI for stocking parts (1113 lines) |
| **Stock Route Handler** | `/home/tony/ACI Invertory/app.py:1125-1185` | GET/POST logic for /stock |
| **Barcode Parsing JS** | `/home/tony/ACI Invertory/templates/stock.html:624-821` | Parse barcode formats |
| **USB HID Scanner** | `/home/tony/ACI Invertory/templates/stock.html:454-503` | Global keyboard event listener |
| **Quagga Scanner** | `/home/tony/ACI Invertory/templates/stock.html:824-893` | Camera-based scanning |
| **API Stock Endpoint** | `/home/tony/ACI Invertory/app.py:1700-1734` | POST /api/stock handler |
| **API Inventory Endpoint** | `/home/tony/ACI Invertory/app.py:1688-1698` | GET /api/inventory handler |
| **PCN Details API** | `/home/tony/ACI Invertory/app.py:2124-2197` | GET /api/pcn/details/<pcn> |
| **Pick Page** | `/home/tony/ACI Invertory/templates/pick.html` | Remove from inventory UI |
| **Inventory Page** | `/home/tony/ACI Invertory/templates/inventory.html` | Browse/search inventory |
| **Stored Procedures** | `/home/tony/ACI Invertory/init_functions.sql` | PostgreSQL functions |
| **Base Template** | `/home/tony/ACI Invertory/templates/base.html` | Navigation, styling (56kb) |

### Documentation Files

| File | Purpose |
|------|---------|
| `STOCK_PAGE_FIXES_AND_TESTS.md` | Testing report, stored procedure fixes |
| `BARCODE_FULL_DATA_FIX.md` | Barcode format documentation |
| `WORKING_STATUS.md` | System status overview |
| `QUICK_REFERENCE.md` | Quick start guide |

---

## Form Flow Diagram

```
User Enters Data
       ↓
Scan Barcode (USB/Camera)
       ↓
Barcode Parser detects format
       ↓
Smart field detection & extraction
       ↓
If PCN provided: Fetch details from DB
       ↓
Auto-fill all form fields
       ↓
User reviews & submits form
       ↓
Backend validation (ITAR, quantity, etc.)
       ↓
Call PostgreSQL stored procedure (stock_pcb)
       ↓
Database updates tblPCB_Inventory
       ↓
Transaction logged to tblTransaction
       ↓
Flash success message
       ↓
Redirect to /stock
       ↓
Recent Stock Operations loads from API
       ↓
New item appears at top of Recent Operations table
```

---

## Key Code Snippets

### Barcode Detection (USB HID)
```javascript
document.addEventListener('keypress', function(e) {
    const activeElement = document.activeElement;
    const isFormField = activeElement && 
        (activeElement.tagName === 'INPUT' || 
         activeElement.tagName === 'TEXTAREA' || 
         activeElement.tagName === 'SELECT');

    if ((e.key === 'Enter' || e.key === 'Tab') && 
        scanBuffer.length >= MIN_SCAN_LENGTH && !isFormField) {
        parseAndFillBarcode(scanBuffer.trim());
        scanBuffer = '';
        return;
    }

    if (e.key !== 'Enter' && e.key !== 'Tab' && !isFormField) {
        scanBuffer += e.key;
        
        if (scanTimeout) clearTimeout(scanTimeout);
        scanTimeout = setTimeout(() => {
            if (scanBuffer.length >= MIN_SCAN_LENGTH) {
                parseAndFillBarcode(scanBuffer.trim());
            }
            scanBuffer = '';
        }, SCAN_TIMEOUT_MS);
    }
});
```

### Smart Field Detection
```javascript
// Check if it's a PCN (1-5 digits)
if (/^\d{5}$/.test(part) && !pcn) {
    pcn = part;
}
// Check for quantity (1-4 digits, not first position)
else if (/^\d{1,4}$/.test(part) && i > 0 && !quantity) {
    quantity = part;
}
// Check for MPN (6+ alphanumeric)
else if (/^[A-Za-z0-9]{6,}$/.test(part) && !mpn) {
    mpn = part;
}
// ... more patterns
```

### Stock Form Submission
```python
@app.route('/stock', methods=['GET', 'POST'])
@require_auth
def stock():
    form = StockForm()
    
    if form.validate_on_submit():
        # Check ITAR access
        if form.itar_classification.data == 'ITAR' and \
           not user_manager.can_access_itar(user_role, itar_auth):
            flash('Access denied: ITAR authorization required', 'error')
            return render_template('stock.html', form=form)
        
        # Call stored procedure
        result = db_manager.stock_pcb(
            job=form.job.data or form.part_number.data,
            pcb_type=form.pcb_type.data,
            quantity=form.quantity.data,
            location=form.location.data,
            itar_classification=form.itar_classification.data,
            user_role=user_role,
            itar_auth=itar_auth,
            username=session.get('username', 'system'),
            # ... other fields
        )
        
        if result.get('success'):
            flash(f"Successfully stocked {result['stocked_qty']} {result['pcb_type']} PCBs", 'success')
            return redirect(url_for('stock'))
```

---

## Summary

The stock page is a comprehensive inventory management system with:
- **Smart barcode scanning** supporting hardware scanners and camera input
- **Intelligent field detection** automatically extracting data from various formats
- **Real-time database integration** with PostgreSQL stored procedures
- **Multi-role security** with ITAR access control
- **Complete audit trail** of all stock/pick operations
- **User-friendly UI** with form validation and visual feedback

The barcode system is particularly sophisticated, encoding ALL label information (10 fields) in a pipe-delimited format that can be parsed both by hardware scanners and the web-based system.

