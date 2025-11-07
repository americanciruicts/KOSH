# Business Requirements Document (BRD)
## KOSH 2.0 - Warehouse Inventory Management Application

---

## Document Information
- **Project Name:** KOSH 2.0
- **Document Version:** 1.0
- **Date:** October 31, 2025
- **Status:** Draft

---

## 1. Executive Summary

### 1.1 Purpose
KOSH 2.0 is a comprehensive warehouse inventory management application designed to replace the legacy Microsoft Access system. The application will manage three distinct inventory types: PCB inventory, warehouse goods inventory, and finished goods inventory. It will streamline warehouse operations including receiving, put away, picking, cycle counting, and shortage reporting.

### 1.2 Project Scope
The system will provide a modern, web-based solution for complete warehouse operations management, integrating with existing API services for automated data generation and supporting multiple inventory workflows.

### 1.3 Business Objectives
- Replace legacy Access-based inventory system
- Provide real-time inventory visibility across multiple inventory types
- Automate data entry and label generation
- Improve accuracy in picking, receiving, and counting operations
- Enable efficient shortage reporting for purchasing decisions
- Support Part Change Notice (PCN) workflows and history tracking

---

## 2. System Overview

### 2.1 Inventory Types
The system must support three distinct inventory categories:

1. **PCB Inventory** - Printed Circuit Board inventory management
2. **Warehouse Goods Inventory** - General warehouse materials and components
3. **Finished Goods Inventory** - Completed products ready for shipment

### 2.2 Core Functional Areas
1. Receipt Management
2. Put Away Operations
3. Pick Operations
4. Count Back
5. Cycle Count
6. Inventory Management
7. PCN (Part Change Notice) Management
8. BOM Loader
9. Shortage Reporting
10. Stock Management

---

## 3. Detailed Functional Requirements

### 3.1 Receipt Entry Module

#### 3.1.1 Data Entry Requirements
The receipt entry function shall allow users to enter:
- **Part Number** (Manual entry)
- **PO Number** (Manual entry)
- **Quantity (QTY)** (Manual entry)
- **Manufacturer Part Number (MFN)** - Auto-generated from API
- **Date Code (DC)** (Manual entry)
- **Moisture Sensitive Device (MSD)** designation (Manual entry)

#### 3.1.2 Functional Requirements
- FR-RE-001: System shall validate part numbers against master data
- FR-RE-002: System shall auto-generate MFN by calling external API based on part number
- FR-RE-003: System shall create unique receipt records with timestamps
- FR-RE-004: System shall support barcode scanning for part numbers
- FR-RE-005: System shall validate PO numbers against purchasing system (if integrated)

### 3.2 Put Away Module

#### 3.2.1 Purpose
Manage the movement of received goods to their designated storage locations.

#### 3.2.2 Functional Requirements
- FR-PA-001: System shall display pending put-away items from receipts
- FR-PA-002: Users shall assign storage locations to received items
- FR-PA-003: System shall update inventory locations upon put-away completion
- FR-PA-004: System shall support location barcode scanning

### 3.3 Pick Module

#### 3.3.1 Data Entry Requirements
Users shall enter:
- **Work Order** number
- **PCN** (scan or manual entry)
- **PCN Quantity**

#### 3.3.2 Functional Requirements
- FR-PK-001: System shall validate work orders before allowing picks
- FR-PK-002: System shall scan PCN barcodes for pick confirmation
- FR-PK-003: System shall validate requested quantity against available inventory
- FR-PK-004: System shall support partial picks
- FR-PK-005: System shall update inventory quantities in real-time
- FR-PK-006: System shall track pick history by user, date, and work order
- FR-PK-007: System shall provide data entry point for job numbers (e.g., Ex: 23806-3, Quarantine, Purge, etc.)
- FR-PK-008: Pick data entry area should NOT auto-generate data when scanned or manually typed

### 3.4 Count Back Module

#### 3.4.1 Data Entry Requirements
Users shall enter:
- **PCN** (scan or manual entry)
- **PCN Quantity**
- **Part Number (P/N)**
- **PO Number**

#### 3.4.2 Functional Requirements
- FR-CB-001: System shall allow counting back unused materials to inventory
- FR-CB-002: System shall validate PCN before accepting count back
- FR-CB-003: System shall update inventory quantities upon count back completion
- FR-CB-004: System shall record count back transactions with user and timestamp

### 3.5 Cycle Count Module

#### 3.5.1 Data Entry Requirements
Users shall enter:
- **PCN** (scan or manual entry)
- **Part Number**
- **Quantity**
- **PO Number**

#### 3.5.2 Functional Requirements
- FR-CC-001: System shall support scheduled and ad-hoc cycle counts
- FR-CC-002: System shall compare counted quantities against system quantities
- FR-CC-003: System shall flag discrepancies for review
- FR-CC-004: System shall require supervisor approval for variance adjustments
- FR-CC-005: System shall maintain audit trail of all count adjustments

### 3.6 PCN (Part Change Notice) Management

#### 3.6.1 Generate PCN
- FR-PCN-001: System shall generate unique PCN identifiers
- FR-PCN-002: Bar code must be sufficiently long and scannable
- FR-PCN-003: System shall support creating PCNs for same part when jobs are created consecutively
- FR-PCN-004: All information must be entered each time a PCN is created for same part

#### 3.6.2 PCN History
- FR-PCN-005: System shall maintain complete history of each PCN
- FR-PCN-006: System shall track locations where PCN has been used
- FR-PCN-007: System shall track how many part number changes have occurred
- FR-PCN-008: System shall track if PCN has been picked for any jobs
- FR-PCN-009: Users shall have ability to refresh after every entry

#### 3.6.3 PCN Inventory Status
The system shall support dropdown menu categorization:
- PCB
- Partial
- Completed
- Shipped
- (Other categories as applicable)

- FR-PCN-010: Inventory dropdown shall show PCNs even though PCNs have been created for companies
- FR-PCN-011: Users shall choose from category options provided

#### 3.6.4 PCN Delete Function
- FR-PCN-012: Users shall be able to delete PCNs they created
- FR-PCN-013: System shall prevent deletion of next.cfg file (data integrity protection)
- FR-PCN-014: System shall create error message when deletion is not allowed

### 3.7 Stock Management

#### 3.7.1 Stock Feature Requirements
- FR-ST-001: System shall NOT auto-generate data attached to PCN when scanned or manually typed
- FR-ST-002: System shall provide option to print auto-generated label after data has been inquired
- FR-ST-003: With Access permission, users shall have option to print a new label

### 3.8 BOM Loader Module

#### 3.8.1 Functional Requirements
- FR-BOM-001: System shall provide a way to view the current BOM revision
- FR-BOM-002: System shall provide function for downloading the current revision
- FR-BOM-003: System shall provide function for loading ACI-created parts
- FR-BOM-004: System shall validate BOM data before loading

### 3.9 Warehouse Inventory Management

#### 3.9.1 Separation of Inventory Types
- FR-WI-001: Warehouse inventory shall be separate from PCB inventory
- FR-WI-002: Warehouse inventory shall have its own menu option
- FR-WI-003: Each inventory type shall maintain independent tracking

### 3.10 Shortage Reports

#### 3.10.1 Report Types
System shall support shortage reports for:
- **SMT (Surface Mount Technology) Inventory**
- **PTH (Plated Through Hole) Inventory**

#### 3.10.2 Functional Requirements
- FR-SR-001: Shortage reports shall be created for each job
- FR-SR-002: System shall inform Purchasing what to buy and in what quantity
- FR-SR-003: System shall distinguish between technical warehouse locations (SMT vs PTH)
- FR-SR-004: System shall generate shortage report for SMT inventory separately
- FR-SR-005: System shall generate shortage report for PTH inventory separately
- FR-SR-006: Users shall be able to create a shortage report on demand
- FR-SR-007: Users shall be able to print shortage reports

### 3.11 Part Number Change Functionality

#### 3.11.1 Functional Requirements
- FR-PC-001: System shall support changing part numbers with full audit trail
- FR-PC-002: System shall maintain linkage between old and new part numbers
- FR-PC-003: System shall update all related inventory records
- FR-PC-004: System shall require authorization for part number changes

---

## 4. Non-Functional Requirements

### 4.1 Performance Requirements
- NFR-001: System shall support barcode scanning with < 1 second response time
- NFR-002: Reports shall generate within 5 seconds for standard queries
- NFR-003: System shall support minimum 20 concurrent users
- NFR-004: System shall have 99.5% uptime during business hours

### 4.2 Usability Requirements
- NFR-005: Interface shall be intuitive requiring minimal training
- NFR-006: System shall support both keyboard and barcode scanner input
- NFR-007: System shall provide clear error messages with resolution guidance
- NFR-008: System shall support responsive design for mobile devices/tablets

### 4.3 Security Requirements
- NFR-009: System shall implement role-based access control
- NFR-010: All transactions shall be logged with user identification
- NFR-011: System shall prevent unauthorized data deletion
- NFR-012: System shall encrypt sensitive data in transit and at rest

### 4.4 Data Requirements
- NFR-013: System shall maintain complete audit trail of all inventory transactions
- NFR-014: System shall implement automated daily backups
- NFR-015: System shall retain transaction history for minimum 7 years
- NFR-016: System shall prevent creation or deletion of critical configuration files (e.g., next.cfg)

### 4.5 Integration Requirements
- NFR-017: System shall integrate with existing API for MFN auto-generation
- NFR-018: System shall support integration with ERP/Purchasing systems
- NFR-019: System shall export data in standard formats (CSV, Excel, PDF)

---

## 5. User Roles and Permissions

### 5.1 Warehouse Operator
- Receive materials
- Put away inventory
- Pick materials
- Count back items
- Perform cycle counts
- View inventory

### 5.2 Warehouse Supervisor
- All Warehouse Operator permissions
- Approve variance adjustments
- Generate shortage reports
- Access PCN history
- Print labels with elevated permissions

### 5.3 Inventory Manager
- All Warehouse Supervisor permissions
- Manage part number changes
- Delete PCNs (with restrictions)
- Load BOMs
- Configure system parameters

### 5.4 Administrator
- All system permissions
- User management
- System configuration
- Access audit logs

---

## 6. Reporting Requirements

### 6.1 Standard Reports
1. **Inventory Status Report** - Current quantities by part, location, and inventory type
2. **Transaction History Report** - All inventory movements by date range
3. **Shortage Report (SMT)** - Parts needed for SMT operations
4. **Shortage Report (PTH)** - Parts needed for PTH operations
5. **PCN History Report** - Complete lifecycle of part change notices
6. **Cycle Count Variance Report** - Discrepancies found during cycle counts
7. **Pick History Report** - All picks by work order, date, user

### 6.2 Report Features
- REP-001: All reports shall be printable
- REP-002: All reports shall be exportable to PDF and Excel
- REP-003: Reports shall support filtering and sorting
- REP-004: Reports shall include timestamp and user who generated them

---

## 7. Migration Requirements

### 7.1 Data Migration
- MIG-001: All active inventory data shall be migrated from Access database
- MIG-002: Historical transaction data shall be migrated (minimum 2 years)
- MIG-003: PCN history shall be fully migrated
- MIG-004: Master data (parts, locations, BOMs) shall be validated during migration

### 7.2 Parallel Operations
- MIG-005: System shall support parallel operation period with legacy system
- MIG-006: Data reconciliation process shall be established

---

## 8. Success Criteria

### 8.1 Functional Success
- All core modules operational (Receipt, Put Away, Pick, Count, Cycle Count)
- All three inventory types independently managed
- Integration with API for MFN generation working
- Shortage reports generating accurately for both SMT and PTH

### 8.2 User Acceptance
- Warehouse staff trained and comfortable with new system
- Pick/receive operations faster than legacy system
- Error rates reduced by 50% compared to legacy system

### 8.3 Technical Success
- System meets all performance requirements
- Zero data loss during migration
- All security requirements implemented
- Backup and recovery procedures tested

---

## 9. Constraints and Assumptions

### 9.1 Constraints
- Must integrate with existing API infrastructure
- Must be accessible from warehouse floor (WiFi/network availability)
- Budget constraints (to be defined)
- Timeline constraints (to be defined)

### 9.2 Assumptions
- Barcode scanners will be available for all workstations
- Network infrastructure supports required performance
- Users have basic computer literacy
- Label printers are compatible or will be upgraded

---

## 10. Risks and Mitigation

### 10.1 Technical Risks
- **Risk:** API integration failures
  - **Mitigation:** Implement fallback manual entry; establish API SLA

- **Risk:** Data migration errors
  - **Mitigation:** Multiple validation cycles; parallel operation period

- **Risk:** Performance issues with large datasets
  - **Mitigation:** Database optimization; proper indexing; load testing

### 10.2 Operational Risks
- **Risk:** User resistance to new system
  - **Mitigation:** Early user involvement; comprehensive training; support during transition

- **Risk:** Disruption to warehouse operations during migration
  - **Mitigation:** Phased rollout; parallel operation period; weekend migration activities

---

## 11. Dependencies

### 11.1 External Dependencies
- API availability for MFN generation
- Network infrastructure readiness
- Hardware procurement (scanners, printers, tablets)
- ERP/Purchasing system interfaces (if applicable)

### 11.2 Internal Dependencies
- User availability for requirements validation and testing
- IT resources for infrastructure setup
- Management approval for process changes

---

## 12. Future Enhancements (Out of Scope for v1.0)

- Mobile app for warehouse operations
- RFID tracking integration
- Advanced analytics and forecasting
- Integration with shipping/logistics systems
- Automated reorder point management
- Photo capture of received materials
- Voice-directed picking

---

## 13. Glossary

- **PCN** - Part Change Notice: A unique identifier for tracking parts through the system
- **MFN** - Manufacturer Part Number: The manufacturer's designation for a part
- **SMT** - Surface Mount Technology: Electronic assembly method
- **PTH** - Plated Through Hole: Electronic assembly method
- **BOM** - Bill of Materials: List of parts required for assembly
- **MSD** - Moisture Sensitive Device: Components requiring special handling
- **DC** - Date Code: Manufacturing date code of component
- **ACI** - Company-created parts designation

---

## 14. Approval

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Business Owner | | | |
| Project Sponsor | | | |
| IT Manager | | | |
| Warehouse Manager | | | |
| Quality Manager | | | |

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-31 | System | Initial draft based on requirements analysis |

---

## Appendices

### Appendix A: Current System Issues (From Testing Notes)
Based on testing of previous PCB system, the following issues were identified and shall be addressed in KOSH 2.0:

1. Bar code length and scannability issues
2. Inability to use previous items in dropdown menus
3. Need to refresh after every entry
4. Inventory dropdown limitations when PCNs created for multiple companies
5. Delete function creating errors with next.cfg file
6. Pick data entry auto-generation issues
7. Stock feature auto-generation when not desired
8. Lack of separation between inventory types

### Appendix B: Technical Architecture (To Be Developed)
- System architecture diagrams
- Database schema
- API specifications
- Integration points
- Security architecture

### Appendix C: User Interface Mockups (To Be Developed)
- Receipt entry screen
- Pick operation screen
- Cycle count screen
- Shortage report interface
- PCN management interface

---

**END OF DOCUMENT**
