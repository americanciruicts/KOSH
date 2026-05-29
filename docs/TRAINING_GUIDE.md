# KOSH Inventory Management System - Training Guide

**Version 2.1.0** | American Circuits Inc.

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Dashboard](#2-dashboard)
3. [Jobs & BOM Management](#3-jobs--bom-management)
4. [Stock Parts](#4-stock-parts)
5. [Pick Parts](#5-pick-parts)
6. [Restock Parts](#6-restock-parts)
7. [Part Number Change](#7-part-number-change)
8. [PCN Generation](#8-pcn-generation)
9. [ACI Number Creator](#9-aci-number-creator)
10. [Shortage Reports](#10-shortage-reports)
11. [Inventory Browsers](#11-inventory-browsers)
12. [Print Labels](#12-print-labels)
13. [PCN History](#13-pcn-history)
14. [PO History](#14-po-history)
15. [Reports](#15-reports)
16. [Locations](#16-locations)
17. [Admin Features](#17-admin-features)
18. [Barcode Scanning](#18-barcode-scanning)
19. [Dark Mode](#19-dark-mode)
20. [Quick Reference](#20-quick-reference)

---

## 1. Getting Started

### Logging In

When you open KOSH, you will see the login screen.

- Enter your **Username** and **Password**
- Click the eye icon next to the password field to show/hide your password
- Click **Sign In**
- If you are already logged into ACI FORGE, you will be signed in automatically through SSO (Single Sign-On)

> If you forget your password, click "Forgot password?" and contact your administrator to reset it.

Once logged in, your name and role appear in the top-right corner of the navbar. Click your name to see your profile or to **Sign Out**.

### Navigation

The top navigation bar gives you access to every section of KOSH:

| Nav Item | What It Contains |
|----------|-----------------|
| **Dashboard** | Home page with inventory stats and quick actions |
| **Jobs** | Jobs list, BOM Loader, Shortage Reports |
| **Numbers** | Generate PCN, ACI Number Creator |
| **Stock / Pick** | Stock Parts, Pick Parts, Restock Parts, Part Number Change |
| **Inventory** | PCB Inventory, Warehouse Inventory |
| **Print Label** | Opens the label printing window |
| **History** | PCN History, PO History |
| **Locations** | Manage warehouse location codes |
| **Reports** | Inventory reports and statistics |

---

## 2. Dashboard

The Dashboard is your home screen. It shows four key metrics at a glance:

| Card | What It Shows |
|------|--------------|
| **Total Jobs** | Number of active jobs loaded into KOSH |
| **Total Quantity** | Sum of all parts currently in inventory |
| **Inventory Items** | Number of unique part entries in the warehouse |
| **Stock Alerts** | Parts that are running low (red if items are below threshold, green if healthy) |

### Quick Actions

Three buttons at the top let you jump directly to:
- **Add Stock** - Go to the Stock Parts page
- **Pick Parts** - Go to the Pick Parts page
- **Restock** - Go to the Restock Parts page

---

## 3. Jobs & BOM Management

### Viewing Jobs

Go to **Jobs** from the navbar. You will see:

- A **search bar** at the top to find jobs by Job #, customer, or description
- A **job list table** showing all loaded jobs with columns:
  - Job #, Customer, Customer P/N, Build QTY, Rev, Status, Created, Actions

**Job Statuses:**
- **New** (blue) - Job just loaded
- **In Prep** (yellow) - Being prepared
- **In Mfg** (green) - Currently in manufacturing

Click the **eye icon** on any job to view its full details.

### Loading a New BOM

To load a new Bill of Materials:

1. In the Jobs page, find the **Create New Job** card
2. Click **Choose File** and select your Excel file (.xlsx or .xls)
3. The file **must** contain a sheet named **"BOM to Load"**
4. Click **Upload and Parse** - KOSH will read the file and show a preview
5. Review the data:
   - **Job Details** at the top: Job #, Customer, Customer P/N, Order Qty, Job Rev, Cust Rev, WO Number
   - **BOM Items Table** below: Line, Description, Manufacturer, MPN, ACI P/N, Qty, POU, Location, Cost
6. If everything looks correct, click **Load to Database**

> **Important:** If a job with the same number already exists, KOSH will warn you. You can choose to view the existing job or reload it (which replaces the old BOM data).

### Job Detail View

When you click into a job, you see:

**Summary Bar:**
- **Order Qty** - Click to edit inline
- **Total BOM Lines** - Number of components in the BOM
- **Shortage Items** - Count of parts that are short

**Job Information:**
- Job Rev, Cust Rev, Last Rev, WO #, Created By, Created Date

**Line Items Table:**
- Every part in the BOM with columns: Line, PCN, ACI PN, Description, MPN, QTY, REQ, On Hand, Location, Cost, Shortage
- Rows with shortages are highlighted in **red**
- Use the search box to filter parts
- Footer shows totals for REQ, On Hand, Cost, and Total Shortage

**Available Actions:**
- **Export Job View** - Download to Excel with customizable columns
- **Generate Shortage Report** - Create a shortage report based on Order Qty
- **Create Revision** - Save a new revision of the BOM
- **Print** - Print the current page
- **Delete Job** - Remove the job and all its BOM data

---

## 4. Stock Parts

Go to **Stock / Pick > Stock Parts** from the navbar.

Use this page to **add new parts into inventory**.

### Fields to Fill In

| Field | Required | Description |
|-------|----------|-------------|
| **PCN Number** | No | 5-digit Part Control Number (if already assigned) |
| **MPN** | Yes | Manufacturer Part Number |
| **Internal Part Number** | No | ACI internal part number |
| **PO Number** | No | Purchase Order number for receiving |
| **Quantity** | Yes | Number of parts being stocked (must be 1 or more) |
| **Date Code** | No | Manufacturing date code (e.g., 2024WK01) |
| **MSD Level** | No | Moisture Sensitivity Device level |
| **Location From** | No | Where the parts came from (e.g., Receiving Area) |
| **Location To** | Yes | Warehouse location to store (7-digit code) |

### How to Stock Parts

1. Enter the **MPN** of the part
2. Enter the **Quantity**
3. Enter the **Location To** (7-digit warehouse location code)
4. Fill in any optional fields (PCN, PO, Date Code, etc.)
5. Click **Submit**
6. A success message will confirm the stock transaction

> **Location Codes:** Must be a 7-digit number (e.g., 1001001) or a standard name like "Receiving Area", "Count Area", "Stock Room", or "MFG Floor".

---

## 5. Pick Parts

Go to **Stock / Pick > Pick Parts** from the navbar.

Use this page to **remove parts from inventory** for manufacturing or other use.

### Quick Inventory Lookup

Enter a **Job Number** at the top to see all available inventory for that job.

### Fields to Fill In

| Field | Required | Description |
|-------|----------|-------------|
| **Work Order #** | No | Work order number (e.g., 6846-028) |
| **PCN Number** | Yes* | Scan or type the PCN barcode |
| **MPN** | Yes* | Manufacturer Part Number (auto-fills from PCN) |
| **Part Number** | No | Internal part number |
| **Date Code** | No | Date code of the parts being picked |
| **MSD Level** | No | Moisture sensitivity level |
| **Quantity** | Yes | Number of parts to pick |

> *At least **PCN** or **MPN** is required.

### How to Pick Parts

1. Scan or type the **PCN** number - KOSH will auto-fill the MPN and show available quantity
2. Enter the **Quantity** to pick
3. KOSH will show the **Available Quantity** - you cannot pick more than what is on hand
4. Click **Pick Parts**
5. A success message confirms the transaction

> **Safety Check:** If you try to pick more than the available quantity, KOSH will block the submission and show a warning.

---

## 6. Restock Parts

Go to **Stock / Pick > Restock Parts** from the navbar.

Use this page to **return unused parts from the manufacturing floor back to inventory**. Parts always move from the **Count Area** to your specified destination.

### Fields to Fill In

| Field | Required | Description |
|-------|----------|-------------|
| **PCN Number** | Yes* | Scan or type the PCN |
| **Item Number** | Yes* | Alternative to PCN lookup |
| **PO Number** | Auto | Auto-filled from part record (read-only) |
| **Quantity** | Yes | Number of parts to restock |
| **Location From** | Auto | Always "Count Area" (read-only) |
| **Location To** | Yes | Destination warehouse location (7-digit code) |

> *Either **PCN** or **Item Number** is required.

### How to Restock

1. Scan or type the **PCN** or **Item Number**
2. KOSH will show the part details: PCN, Item, MPN, Date Code, Current Location, On Hand Qty, and MFG Qty
3. Enter the **Quantity** to return
4. Enter the **Location To** (where you want to store it)
5. Click **Submit** - a confirmation dialog will appear
6. Confirm the restock
7. After success, you will be offered to **Print a Label** for the restocked parts

---

## 7. Part Number Change

Go to **Stock / Pick > Part Number Change** from the navbar.

Use this page to **update or change a part number** in the inventory system. All changes are logged in the audit trail.

---

## 8. PCN Generation

Go to **Numbers > Generate PCN** from the navbar.

Use this page to **create new Part Control Numbers (PCNs)** and assign them to inventory items.

### How It Works

1. Enter the part details
2. Click to generate a new unique PCN
3. The generated PCN will display in a large, scannable format
4. Click **Print Label** to print a barcode label on your thermal printer (4" x 2" labels)

Each PCN is a unique identifier that tracks a specific batch of parts through the warehouse. Once generated, it can be scanned from any page in KOSH.

---

## 9. ACI Number Creator

Go to **Numbers > ACI Numbers** from the navbar.

Use this page to **create new ACI internal part numbers** for parts that are **not part of a BOM**. These numbers are consecutive (ACI-10445, ACI-10446, etc.) and cannot be duplicated.

### How to Create ACI Numbers

1. The page shows the **next available ACI number** in the header badge
2. Each row has an auto-assigned ACI number (shown in the first column)
3. Fill in the fields for each part:

| Field | Description |
|-------|-------------|
| **ACI Number** | Auto-assigned, sequential (read-only) |
| **Manufacturer** | Part manufacturer name |
| **MPN** | Manufacturer Part Number |
| **Description** | Part description |
| **Comment** | Optional notes |
| **Loaded** | Y or N - whether the part has been loaded |

4. Click **Add Row** to add more parts (or press **Enter** on the last field)
5. Review all entries
6. Click **Create ACI Numbers** to save

### Tips
- You can create up to **100 parts** in one batch
- The **Recent History** sidebar on the right shows the last 100 created ACI numbers
- All created ACI numbers are automatically added to the part number list and become available for stock operations
- ACI numbers are **permanent and sequential** - they cannot be reused or deleted

---

## 10. Shortage Reports

### Generating a Shortage Report

Go to **Jobs > Shortage Report** from the navbar.

A shortage report compares what the BOM requires against what is currently in inventory.

1. Enter the **Job Number** (autocomplete will suggest matching jobs)
2. Enter the **Order Qty** (how many units you need to build)
3. Optionally enter a **Report Name** and **Notes**
4. Click **Generate**

**How the calculation works:**
- **REQ** = BOM Qty x Order Qty
- **Shortage** = On Hand - REQ
- Parts where On Hand < REQ are flagged as **shortages**

### Viewing a Shortage Report

After generating, or from the saved reports list, click the **eye icon** to view.

The report shows:

**Summary Cards:**
- Order Qty
- Shortage Items (count of parts that are short)
- Total BOM Cost
- Shortage Cost

**Shortage Table:**
- ACI PN, PCN, MPN, QTY (from BOM), Order Qty, REQ, Item, On Hand QTY, Location
- Rows with shortages are highlighted in **red**
- Green on-hand values mean sufficient stock, red means shortage

**Filters:**
- Toggle **Hide 0 On Hand** to focus on parts with no stock at all
- Use the **search box** to find specific parts

### Exporting a Shortage Report

Click **Export Excel** to download. You can customize:
- Which **columns** to include (checkboxes)
- **Filter** - All items or Shortages only
- **Column order** - Move columns up/down
- **Highlight columns** - Choose columns to highlight in the Excel file

---

## 11. Inventory Browsers

### PCB Inventory

Go to **Inventory > PCB Inventory** from the navbar.

Browse and search all PCB inventory items with filters:
- Job Number(s) (comma-separated for multiple jobs)
- PCB Type (dropdown)
- Location (dropdown)
- PCN Number
- Date range (Updated From / To)
- Quantity range (Min / Max)

Results show: Job, PCB Type, Location, PCN, Description, Item, MPN, Qty, Updated

Click column headers to sort. Use the per-page dropdown (10, 25, 50, 100) to control how many results are displayed.

### Warehouse Inventory

Go to **Inventory > Warehouse Inventory** from the navbar.

This shows inventory data from the legacy warehouse database.

**Search by:**
- PCN
- Item Number
- MPN
- Location

Results display all matching warehouse records with quantities and locations.

---

## 12. Print Labels

Click **Print Label** in the navbar (or from any page that offers label printing).

This opens a print-ready window formatted for **4" x 2" thermal barcode labels**.

The label includes:
- PCN number as a scannable barcode
- Part description
- MPN
- Location information

Click **Print** in the dialog to send to your label printer.

---

## 13. PCN History

Go to **History > PCN History** from the navbar.

Look up the complete transaction history for any PCN.

### How to Use

1. Enter a **PCN number** in the search field
2. Click **Search**
3. KOSH displays:
   - **Part Info:** Description, MPN, Qty, Location
   - **Stats:** Total transactions, Stock count, Pick count
   - **Transaction Timeline:** Every movement of that PCN

### Transaction Types

| Code | Meaning | Color |
|------|---------|-------|
| **STOCK** | Parts added to inventory | Green |
| **PICK** | Parts removed for use | Yellow |
| **RESTOCK** | Parts returned from MFG floor | Cyan |
| **GEN** | PCN label generated | Blue |
| **UPDATE** | Record was updated | Gray |
| **ADJT** | Inventory adjustment | Light Blue |
| **SCRA** | Parts scrapped | Dark |
| **PTWY** | Put away to storage | Gray |

Each transaction shows: Time, Type, Item, MPN, Qty, From Location, To Location, Work Order, PO.

---

## 14. PO History

Go to **History > PO History** from the navbar.

Search purchase order and receipt history.

### Search Filters

- PO Number
- Item Number
- MPN
- PCN
- Date range (From / To)

### Results Table

Columns: Date, PO Number, Vendor, PCN, Type, Item, MPN, Date Code, Quantity, From/To Locations, User ID

The footer shows the **total quantity** across all results. Use pagination controls at the bottom to navigate through large result sets.

---

## 15. Reports

Go to **Reports** from the navbar.

View inventory statistics and analytics including:
- Inventory valuation over time
- Stock level summaries
- Job completion statistics
- Pick/stock activity tracking
- Shortage trends

Reports can be exported to Excel for further analysis.

---

## 16. Locations

Go to **Locations** from the navbar.

Manage warehouse location codes used throughout KOSH.

### Adding a Location

1. Enter the new location code in the form
2. Click **Submit**
3. The location becomes available in all Stock, Pick, and Restock forms

### Location Format

- **7-digit codes** for warehouse shelf locations (e.g., 1001001, 2003045)
- **Standard names** that are always available: Receiving Area, Count Area, Stock Room, MFG Floor

You can also **delete** locations that are no longer in use.

---

## 17. Admin Features

These features are available to users with **Admin** or **Super User** roles.

### User Management

Click your **profile name** in the top-right corner, then **Manage Users**.

- **Create New User** - Set username, full name, password, and role
- **Edit User** - Update user details and role
- **Delete User** - Remove a user account

**User Roles:**

| Role | Access Level |
|------|-------------|
| **Super User** | Full access to all features including user management |
| **Manager** | Full operational access |
| **User** | Standard inventory operations |
| **Operator** | Limited to stock/pick operations |
| **ITAR** | Restricted access for ITAR-controlled items |

### Activity Notifications

Admins see a **bell icon** in the top-right corner showing unread notifications.

Click the bell to view the **Activity Log** - a record of all user actions:
- Login / Logout
- Stock, Pick, and Restock transactions
- PCN generation
- Shortage report creation
- BOM uploads
- Part number changes
- Label printing

Each entry shows: who did it, what they did, and when.

### Sources (Admin Only)

The **Sources** tab in the navbar (visible only to admins) provides direct access to browse tables from the legacy Access database for reference and data verification.

---

## 18. Barcode Scanning

KOSH supports **barcode scanning from any page**.

When you scan a PCN barcode:
- A popup appears showing the part details: Item, QTY, MPN, Location
- Quick action buttons let you:
  - **Print Label** - Reprint the barcode label
  - **Pick** - Go directly to pick that PCN
  - **Stock** - Go directly to stock that PCN
  - **Close** - Dismiss the popup

If the scanned PCN is not found, a "PCN Not Found" message appears.

> **Tip:** Most input fields that accept PCN numbers are designed for fast scanning. Just focus the field and scan - the barcode value will be entered automatically.

---

## 19. Dark Mode

Click the **moon/sun button** in the bottom-right corner of any page to toggle between Light Mode and Dark Mode.

Your preference is saved automatically and remembered the next time you log in.

---

## 20. Quick Reference

### Common Workflows

**Receiving new parts:**
1. Stock Parts > Enter MPN, Qty, Location To > Submit

**Picking parts for a job:**
1. Pick Parts > Scan PCN > Enter Qty > Pick Parts

**Loading a new job:**
1. Jobs > Create New Job > Upload Excel > Review > Load to Database

**Checking if parts are short:**
1. Jobs > Open job > Generate Shortage Report > Enter Order Qty > Generate

**Creating ACI numbers for non-BOM parts:**
1. Numbers > ACI Numbers > Fill in Manufacturer, MPN, Description > Create

**Looking up a PCN history:**
1. History > PCN History > Enter PCN > Search

**Printing a label:**
1. Click Print Label in navbar > Enter PCN > Print

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **Enter** | Submit forms, move to next field in ACI creator |
| **Tab** | Move between form fields |
| **Esc** | Close modals and popups |

### Important Rules

- **PCN numbers** are unique - each one tracks a specific batch of parts
- **ACI numbers** are sequential and permanent - they cannot be reused
- You **cannot pick more** than what is available on hand
- **Location codes** must be 7 digits or a standard location name
- **BOM files** must have a sheet named "BOM to Load"
- All transactions are **logged** and cannot be deleted

---

*KOSH v2.1.0 - American Circuits Inc. - Last updated April 2026*
