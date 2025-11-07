# Business Requirements Document (BRD)
## KOSH 2.0 - Warehouse Inventory Management Application

**Document Version:** 1.0
**Date:** October 31, 2025
**Status:** Draft

---

## 1. Executive Summary

KOSH 2.0 is a warehouse inventory management application designed to replace the legacy Microsoft Access system. The application manages three distinct inventory types (PCB, Warehouse Goods, and Finished Goods) and streamlines warehouse operations including receiving, put away, picking, counting, and shortage reporting.

### Business Objectives
- Replace legacy Access-based inventory system with modern web application
- Provide real-time inventory visibility across multiple inventory types
- Automate data entry and label generation via API integration
- Improve accuracy in warehouse operations
- Enable efficient shortage reporting for purchasing decisions

---

## 2. Inventory Types

The system supports three independent inventory categories:

1. **PCB Inventory** - Printed Circuit Board management
2. **Warehouse Goods Inventory** - General warehouse materials and components
3. **Finished Goods Inventory** - Completed products ready for shipment

Each inventory type maintains independent tracking and menu options.

---

## 3. Core Functional Modules

### 3.1 Receipt Entry
**Data Entry:**
- Part Number (manual)
- PO Number (manual)
- Quantity (manual)
- Manufacturer Part Number (MFN) - Auto-generated via API
- Date Code (manual)
- MSD designation (manual)

**Requirements:**
- Validate part numbers against master data
- Auto-generate MFN by calling external API
- Support barcode scanning
- Create unique receipt records with timestamps

### 3.2 Put Away
- Display pending put-away items from receipts
- Assign storage locations to received items
- Update inventory locations upon completion
- Support location barcode scanning

### 3.3 Pick Operations
**Data Entry:**
- Work Order number
- PCN (scan or manual)
- PCN Quantity
- Job numbers (e.g., 23806-3, Quarantine, Purge)

**Requirements:**
- Validate work orders before allowing picks
- Scan PCN barcodes for confirmation
- Support partial picks
- Update inventory in real-time
- Track pick history by user, date, and work order
- **Critical:** Pick data entry area must NOT auto-generate data

### 3.4 Count Back
**Data Entry:**
- PCN (scan or manual)
- PCN Quantity
- Part Number
- PO Number

**Requirements:**
- Allow counting back unused materials to inventory
- Validate PCN before accepting
- Update inventory quantities upon completion
- Record transactions with user and timestamp

### 3.5 Cycle Count
**Data Entry:**
- PCN (scan or manual)
- Part Number
- Quantity
- PO Number

**Requirements:**
- Support scheduled and ad-hoc cycle counts
- Compare counted vs. system quantities
- Flag discrepancies for review
- Require supervisor approval for variance adjustments
- Maintain complete audit trail

### 3.6 PCN (Part Change Notice) Management

**Generate PCN:**
- Generate unique PCN identifiers with scannable barcodes
- Support creating PCNs for same part when jobs are created consecutively
- **Critical:** All information must be entered each time for same part

**PCN History:**
- Maintain complete history of each PCN
- Track locations where PCN has been used
- Track part number changes
- Track if PCN has been picked for any jobs
- Refresh capability after every entry

**PCN Status Categories:**
- PCB
- Partial
- Completed
- Shipped
- (Additional categories as needed)

**Delete Function:**
- Users can delete PCNs they created
- **Critical:** System must prevent deletion of next.cfg file
- Display error message when deletion is not allowed

### 3.7 Stock Management
- **Critical:** Must NOT auto-generate data when PCN is scanned or typed
- Provide option to print auto-generated label after data inquiry
- With Access permission, allow printing of new labels

### 3.8 BOM Loader
- View current BOM revision
- Download current revision
- Load ACI-created parts
- Validate BOM data before loading

### 3.9 Shortage Reports

**Report Types:**
- SMT (Surface Mount Technology) Inventory Shortage Report
- PTH (Plated Through Hole) Inventory Shortage Report

**Requirements:**
- Create shortage reports for each job
- Inform Purchasing what to buy and quantity needed
- Generate separate reports for SMT and PTH warehouse locations
- Support on-demand report creation
- Support printing

### 3.10 Part Number Change Functionality
- Support changing part numbers with full audit trail
- Maintain linkage between old and new part numbers
- Update all related inventory records
- Require authorization for changes

---

## 4. User Roles and Permissions

| Role | Key Permissions |
|------|-----------------|
| **Warehouse Operator** | Receive, put away, pick, count back, cycle count, view inventory |
| **Warehouse Supervisor** | All Operator permissions + approve variances, generate shortage reports, access PCN history, print labels |
| **Inventory Manager** | All Supervisor permissions + manage part changes, delete PCNs (restricted), load BOMs, configure system |
| **Administrator** | Full system access, user management, system configuration, audit logs |

---

## 5. Key Reports

1. **Inventory Status Report** - Current quantities by part, location, and inventory type
2. **Transaction History Report** - All inventory movements by date range
3. **Shortage Report (SMT)** - Parts needed for SMT operations
4. **Shortage Report (PTH)** - Parts needed for PTH operations
5. **PCN History Report** - Complete lifecycle of part change notices
6. **Cycle Count Variance Report** - Discrepancies during cycle counts
7. **Pick History Report** - All picks by work order, date, user

**Report Features:**
- All reports printable and exportable (PDF, Excel)
- Support filtering and sorting
- Include timestamp and user identification

---

## 6. Non-Functional Requirements

### Performance
- Barcode scanning response time < 1 second
- Reports generate within 5 seconds
- Support minimum 20 concurrent users
- 99.5% uptime during business hours

### Security
- Role-based access control
- All transactions logged with user identification
- Prevent unauthorized data deletion
- Encrypt sensitive data

### Data Management
- Complete audit trail of all transactions
- Automated daily backups
- Retain transaction history for 7 years
- Prevent deletion of critical configuration files

### Integration
- Integrate with existing API for MFN auto-generation
- Support integration with ERP/Purchasing systems
- Export data in standard formats (CSV, Excel, PDF)

---

## 7. Migration Requirements

- Migrate all active inventory data from Access database
- Migrate historical transaction data (minimum 2 years)
- Migrate complete PCN history
- Validate master data (parts, locations, BOMs) during migration
- Support parallel operation period with legacy system
- Establish data reconciliation process

---

## 8. Critical Issues Addressed from Legacy System

Based on testing of previous PCB system, KOSH 2.0 addresses:

1. ✓ Bar code length and scannability issues
2. ✓ Inability to use previous items in dropdown menus
3. ✓ Need to refresh after every entry
4. ✓ Inventory dropdown limitations when PCNs created for multiple companies
5. ✓ Delete function errors with next.cfg file
6. ✓ Pick data entry unwanted auto-generation
7. ✓ Stock feature unwanted auto-generation
8. ✓ Lack of separation between inventory types

---

## 9. Success Criteria

**Functional Success:**
- All core modules operational (Receipt, Put Away, Pick, Count, Cycle Count)
- All three inventory types independently managed
- API integration for MFN generation working
- Accurate shortage reports for SMT and PTH

**User Acceptance:**
- Warehouse staff trained and proficient
- Operations faster than legacy system
- Error rates reduced by 50%

**Technical Success:**
- All performance requirements met
- Zero data loss during migration
- All security requirements implemented
- Backup and recovery procedures tested

---

## 10. Glossary

- **PCN** - Part Change Notice: Unique identifier for tracking parts
- **MFN** - Manufacturer Part Number
- **SMT** - Surface Mount Technology
- **PTH** - Plated Through Hole
- **BOM** - Bill of Materials
- **MSD** - Moisture Sensitive Device
- **DC** - Date Code
- **ACI** - Company-created parts designation

---

## 11. Approval Signatures

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Business Owner | | | |
| Project Sponsor | | | |
| IT Manager | | | |
| Warehouse Manager | | | |

---

**END OF DOCUMENT**
