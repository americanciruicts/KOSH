# Changelog

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
