# Changelog

## [Unreleased]

### Changed
- **Shortage Report — same-MPN/other-PN stock moved from columns to row entries.**
  Removed the two cross-job columns ("ALSO ON HAND (SAME MPN)" and "SAME-MPN
  LOCATIONS") from both the on-screen view and the Excel export. The same
  information — stock of the same MPN sitting under a different job's part number
  — now renders as indented row entries directly under each BOM line (one per
  other PCN). Report users found the columns noisy; they only care about the
  current job's own stock, with the cross-job stock as a glanceable sub-line.
  - This is an **intentional reversal** of the same-MPN two-column display. Do
    NOT reintroduce the columns as a "fix." The underlying same-MPN matching
    logic (tolerant for most customers, **strict exact-MPN for Chemring**) is
    unchanged — only the presentation changed.
  - `tblShortageReportItems.other_mpn_locations` now stores a JSON breakdown
    (item/pcn/qty/location) instead of a display string; `parse_other_mpn_rows()`
    expands it into rows and tolerates the legacy string for old saved reports.

## [2.1.0] - 2026-04-07

### Added
- **ACI Number Creator** - New page to create consecutive ACI part numbers for non-BOM parts, with batch creation, history tracking, and activity logging
- **Responsive Design** - Full responsive layout across all breakpoints (desktop, tablet, phone) with collapsible hamburger navbar, adaptive content padding, and mobile-optimized modals
- Migrated 390 existing ACI numbers from Manual Loader Template spreadsheet into database

### Changed
- Navbar reorganized: Jobs + Shortage Report grouped into dropdown, Generate PCN + ACI Numbers grouped into dropdown
- Reports tab moved to end of navbar
- Reduced navbar padding for better fit on smaller screens
- User menu moved inside navbar (fixes overlap with hamburger on mobile)
- Login page responsive improvements for small screens
- Scan result modal columns stack on small screens

## [2.0.0] - 2026-03-31

### Added
- Full PostgreSQL migration from legacy Access database
- BOM Loader with client-side Excel parsing (SheetJS)
- Job management with BOM detail views and revisions
- Shortage Report generation and export
- PCN barcode generation and assignment
- Stock / Pick / Restock inventory operations with transaction logging
- Warehouse and PCB inventory browsers
- PCN and PO history tracking
- Admin notifications and activity logging
- User management with role-based access (Super User, Manager, User, Operator, ITAR)
- SSO integration with ACI FORGE
- Dark mode toggle
- Print label functionality with ZPL support
- Location management
- Part number change tracking
- Expiration tracking (date codes / MSD)
- Reports and statistics dashboard
- Legacy Access database browser (Sources)
- Docker containerized deployment with Nginx reverse proxy
- Vercel serverless deployment support with Cloudflare tunnel
