# Barcode Full Data Encoding - Generate PCN
**Date:** October 30, 2025
**Status:** FIXED - Barcode now contains ALL label information

---

## Problem Description

The barcode on the PCN label was only encoding the PCN number. When users scanned the barcode, they only got the PCN number, not all the other information visible on the label (Item, MPN, Quantity, PO, Date Code, MSD, etc.).

### What Users Expected
The small barcode should contain **ALL the information shown on the label**, so when scanned, it provides:
- PCN Number
- Item/Job Number
- Manufacturer Part Number (MPN)
- Part Number
- Quantity
- Purchase Order (PO) Number
- Location
- PCB Type
- Date Code (DC)
- Moisture Sensitive Device (MSD) Level

This is standard practice in manufacturing - one scan gives you complete part information.

---

## Solution Implemented

### Barcode Data Format
The barcode now encodes ALL label information in a **pipe-delimited** format:

```
PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
```

### Example Barcode Data
```
00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001||Completed|2025W42|Level 3
```

When scanned, this barcode can be parsed to extract all 10 fields.

---

## Code Changes

### 1. Backend API - Generate PCN (Lines 2023-2033)

**Before:**
```python
# Generate new PCN number
cursor.execute("SELECT pcb_inventory.generate_pcn_number() as pcn_number")
result = cursor.fetchone()
pcn_number = result['pcn_number']

# Create barcode data string
barcode_data = f"{pcn_number}|{data.get('item', '')}|..."  # Used raw integer PCN
```

**After:**
```python
# Generate new PCN number
cursor.execute("SELECT pcb_inventory.generate_pcn_number() as pcn_number")
result = cursor.fetchone()
pcn_number = result['pcn_number']

# Format PCN number as 5-digit string with leading zeros
pcn_number_str = str(pcn_number).zfill(5)

# Create barcode data string (pipe-delimited) - contains ALL label information
# Format: PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
barcode_data = f"{pcn_number_str}|{data.get('item', '')}|{data.get('mpn', '')}|{data.get('part_number', '')}|{data.get('quantity', '')}|{data.get('po_number', '')}|{data.get('location', '')}|{data.get('pcb_type', '')}|{data.get('date_code', '')}|{data.get('msd', '')}"
```

**Key Changes:**
- Format PCN as 5-digit string BEFORE creating barcode_data
- Barcode data now uses formatted PCN (e.g., "00045" instead of "45")
- All 10 fields are included in the barcode string

### 2. Frontend JavaScript - Generate Label Preview (Lines 601-610)

**Before:**
```javascript
// Ensure PCN number is a string and valid for CODE128
const barcodeData = String(data.pcn_number || '').trim();  // Only PCN number
```

**After:**
```javascript
// Use barcode_data if available (contains all label info), otherwise fall back to PCN number
// barcode_data format: PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
const barcodeData = String(data.barcode_data || data.pcn_number || '').trim();

console.log('Barcode data:', barcodeData); // Debug: show what's being encoded
```

**Key Changes:**
- Uses `data.barcode_data` instead of just `data.pcn_number`
- Falls back to PCN number if barcode_data not available (for backwards compatibility)
- Adds console logging for debugging

---

## Barcode Field Mapping

| Field # | Field Name | Description | Example |
|---------|-----------|-------------|---------|
| 1 | PCN | Part Control Number (5 digits) | 00045 |
| 2 | Item | Job number or item identifier | TEST-PART-001 |
| 3 | MPN | Manufacturer Part Number | TEST-MPN-123 |
| 4 | PartNumber | Part number / customer part number | PART-001 |
| 5 | QTY | Quantity | 100 |
| 6 | PO | Purchase Order number | PO-2025-001 |
| 7 | Location | Warehouse location | 8000-8999 |
| 8 | PCBType | Component type (Bare/Partial/Completed/Ready to Ship) | Completed |
| 9 | DateCode | Date code (week/year format) | 2025W42 |
| 10 | MSD | Moisture Sensitive Device level | Level 3 |

### Parsing Example

When scanned, the barcode data can be parsed:

```python
# Scanner returns this string:
barcode_string = "00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001||Completed|2025W42|Level 3"

# Split by pipe delimiter:
fields = barcode_string.split('|')

# Extract fields:
pcn = fields[0]           # "00045"
item = fields[1]          # "TEST-PART-001"
mpn = fields[2]           # "TEST-MPN-123"
part_number = fields[3]   # "PART-001"
quantity = fields[4]      # "100"
po_number = fields[5]     # "PO-2025-001"
location = fields[6]      # "" (empty)
pcb_type = fields[7]      # "Completed"
date_code = fields[8]     # "2025W42"
msd_level = fields[9]     # "Level 3"
```

### Handling Empty Fields

If a field is empty (like Location in the example above), it will appear as an empty string between pipes:
```
00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001||Completed|2025W42|Level 3
                                                            ^^
                                                            Empty location
```

When parsing, check for empty strings:
```python
location = fields[6] if fields[6] else None  # None if empty
```

---

## Benefits

### 1. Complete Data in One Scan
Users only need to scan once to get all part information. No need to:
- Look up additional data in the system
- Manually enter multiple fields
- Cross-reference with other documents

### 2. Reduced Data Entry Errors
All information comes directly from the barcode - no manual typing means fewer mistakes.

### 3. Faster Receiving Process
When parts arrive:
1. Scan barcode
2. System auto-populates all fields
3. Verify and accept

Instead of:
1. Type PCN number
2. Look up part details
3. Manually enter all fields
4. Verify and accept

### 4. Warehouse Efficiency
Workers can:
- Quickly identify parts by scanning
- Verify part details on mobile devices
- Track inventory movements with full context

### 5. Quality Assurance
The barcode captures the exact state at generation time:
- What MSD level was specified
- What date code was recorded
- What quantity was labeled
- Provides audit trail

---

## Label Layout

### Top Section (Small Barcode)
```
┌──────────────────────────────────────┐
│ PCN: 00045    [BARCODE]    QTY: 100 │
└──────────────────────────────────────┘
```

### Middle Section (Text Information)
```
┌──────────────────────────────────────┐
│ Item: TEST-PART-001                  │
│ MPN: TEST-MPN-123          DCC 2025W42│
│ PO: PO-2025-001           MSD Level 3│
└──────────────────────────────────────┘
```

### Bottom Section (Large Barcode)
```
┌──────────────────────────────────────┐
│         [LARGER BARCODE]              │
│         00045|TEST-PART-001|...       │
└──────────────────────────────────────┘
```

**Both barcodes contain the exact same data** - the small one at top for quick scanning, the large one at bottom for reliability.

---

## Barcode Specifications

### Format
- **Type:** CODE128
- **Encoding:** Pipe-delimited string
- **Character Set:** Alphanumeric + pipes (|)
- **Length:** Variable (depends on field content)

### Top Barcode (Small)
- **Width:** 0.8 units per bar
- **Height:** 20 pixels
- **Display Value:** No (cleaner look)
- **Purpose:** Quick identification

### Bottom Barcode (Large)
- **Width:** 1.5 units per bar
- **Height:** 35 pixels
- **Display Value:** Yes (shows full data string)
- **Purpose:** Primary scanning / verification

### Printable Label Barcodes
- **Top:** 1.0 width, 25px height
- **Bottom:** 2.0 width, 45px height
- **Paper Size:** 4" × 2"

---

## Scanner Integration

### Basic Scanner
Most basic barcode scanners will return the raw string:
```
00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001||Completed|2025W42|Level 3
```

Your application needs to parse this string by splitting on `|`.

### Advanced Scanner (with parsing)
Some scanners can be programmed to parse the data:
```
Scanner Configuration:
- Field 1 (PCN): Digits 1-5
- Field 2 (Item): Characters after first |
- etc.
```

### Web-based Scanning
If using JavaScript to handle scanner input:
```javascript
function parseBarcodeData(barcodeString) {
    const fields = barcodeString.split('|');
    return {
        pcn: fields[0],
        item: fields[1],
        mpn: fields[2],
        partNumber: fields[3],
        quantity: parseInt(fields[4]),
        poNumber: fields[5],
        location: fields[6] || null,
        pcbType: fields[7],
        dateCode: fields[8],
        msdLevel: fields[9]
    };
}

// When scanner input detected:
const scannedData = parseBarcodeData(scannerInput);
console.log('Scanned PCN:', scannedData.pcn);
console.log('Part MPN:', scannedData.mpn);
// ... populate form fields automatically
```

---

## Testing

### Test Case 1: Complete Data
**Input Fields:**
- Item: TEST-PART-001
- MPN: TEST-MPN-123
- Part Number: PART-001
- Quantity: 100
- PO: PO-2025-001
- Location: 8000-8999
- PCB Type: Completed
- Date Code: 2025W42
- MSD: Level 3

**Expected Barcode:**
```
00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001|8000-8999|Completed|2025W42|Level 3
```

### Test Case 2: Minimal Data
**Input Fields:**
- Item: SIMPLE-PART
- Quantity: 50
- (All other fields empty)

**Expected Barcode:**
```
00046|SIMPLE-PART|||50||||||
```

### Test Case 3: Special Characters
**Input Fields:**
- Item: PART-WITH-DASH_001
- MPN: MPN#123
- Quantity: 25

**Expected Barcode:**
```
00047|PART-WITH-DASH_001|MPN#123||25||||||
```

**Note:** Avoid using pipe character (|) in field values as it's the delimiter.

---

## Verification Steps

### 1. Generate a PCN
- Fill out form with all fields
- Click "Generate PCN"

### 2. Check Browser Console
- Press F12 to open Developer Tools
- Look for: `Barcode data: 00045|TEST-PART-001|TEST-MPN-123|...`
- Verify all fields are present

### 3. Check Label Preview
- Both top and bottom barcodes should display
- Bottom barcode should show the full data string underneath

### 4. Print and Scan
- Print the label
- Use barcode scanner
- Verify scanner returns the full pipe-delimited string
- Parse the string and verify all fields match

---

## Deployment Status

### Files Modified
1. **app.py** (Lines 2023-2033)
   - Format PCN string earlier
   - Include formatted PCN in barcode_data

2. **generate_pcn.html** (Lines 601-610)
   - Use barcode_data instead of just PCN number
   - Add console logging for debugging

### Deployment Commands
```bash
# Copy files to container
docker cp "/home/tony/ACI Invertory/app.py" stockandpick_webapp:/app/app.py
docker cp "/home/tony/ACI Invertory/templates/generate_pcn.html" stockandpick_webapp:/app/templates/generate_pcn.html

# Restart container
docker restart stockandpick_webapp

# Verify
docker ps | grep stockandpick_webapp  # Should be healthy
curl -I http://acidashboard.aci.local:5002/generate-pcn  # Should return 200
```

### Status
✅ Container: Healthy
✅ Page loads: 200 OK
✅ Barcode encoding: Full data string
✅ API response: Returns barcode_data field
✅ Frontend: Uses barcode_data for generation

---

## Summary

### What Changed
- **Before:** Barcode only contained PCN number (e.g., "00045")
- **After:** Barcode contains all 10 fields (e.g., "00045|TEST-PART-001|TEST-MPN-123|PART-001|100|PO-2025-001||Completed|2025W42|Level 3")

### Impact
- ✅ One scan provides complete part information
- ✅ Faster receiving and inventory processes
- ✅ Reduced data entry errors
- ✅ Better audit trail
- ✅ Scanner-friendly format

### Backwards Compatibility
- Frontend falls back to PCN-only if barcode_data not available
- Existing labels will still scan (though with less data)
- Database stores barcode_data for future reference

---

**Implementation Date:** October 30, 2025
**Status:** PRODUCTION READY
**Verified:** Container healthy, page loads correctly, barcode contains full data

