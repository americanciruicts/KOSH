# KOSH - Inventory Management System

**Version 2.1.0** | American Circuits Inc.

KOSH is a full-featured warehouse and PCB inventory management system built for American Circuits. It handles the complete lifecycle of electronic components — from BOM loading and job tracking to stock operations, shortage reporting, and barcode-based PCN management.

## Features

### Inventory Operations
- **Stock Parts** - Add inventory to warehouse with location, date code, and MSD tracking
- **Pick Parts** - Remove inventory with PCN scanning and transaction logging
- **Restock Parts** - Move parts from Count Area back to warehouse
- **Part Number Change** - Track and manage part number changes across inventory

### Job & BOM Management
- **BOM Loader** - Upload Excel BOMs with automatic column mapping and validation
- **Job Management** - Create, view, and manage jobs with BOM detail, revisions, and build quantities
- **Shortage Reports** - Generate, view, and export shortage reports comparing BOM requirements vs. on-hand inventory

### PCN & ACI Numbers
- **Generate PCN** - Create unique PCN barcodes for inventory items with assignment tracking
- **ACI Number Creator** - Create consecutive ACI part numbers (ACI-10XXX) for non-BOM parts to place in stock
- **PCN History** - Full history of PCN generation and assignments
- **PO History** - Purchase order history tracking

### Inventory Browsers
- **PCB Inventory** - Browse and search PCB inventory with filtering
- **Warehouse Inventory** - View warehouse stock with item details, locations, and expiration status

### Reporting & Admin
- **Reports** - Statistics dashboard with inventory valuation and trends
- **Admin Notifications** - Activity log for all user actions (stock, pick, restock, PCN, login/logout)
- **User Management** - Role-based access control (Super User, Manager, User, Operator, ITAR)
- **Location Management** - Manage warehouse location codes
- **Print Labels** - Generate and print labels with ZPL barcode support
- **Sources** - Legacy Access database table browser (admin only)

### Platform
- **SSO** - Single sign-on integration with ACI FORGE
- **Dark Mode** - Toggle between light and dark themes
- **Responsive Design** - Optimized for desktop, tablet, and mobile devices
- **Barcode Scanning** - Scan PCN barcodes from any page to view item details

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11, Flask 2.3 |
| Database | PostgreSQL 15 |
| Frontend | Jinja2, Bootstrap 5, JavaScript |
| Excel Parsing | SheetJS (client-side), openpyxl (server-side) |
| Auth | Session-based + SSO (JWT) with bcrypt |
| Deployment | Docker Compose, Nginx, Gunicorn |
| Remote Access | Vercel serverless + Cloudflare tunnel |

## Project Structure

```
KOSH/
├── migration/stockAndPick/web_app/   # Docker build context
│   ├── app.py                        # Main Flask application (~8000 lines)
│   ├── expiration_manager.py         # DC/MSD expiration logic
│   ├── templates/                    # Jinja2 HTML templates (38 files)
│   ├── static/                       # CSS, JS, images
│   ├── Dockerfile.webapp             # Docker image definition
│   └── requirements.txt              # Python dependencies
├── docker-compose.yml                # Docker Compose services
├── nginx.conf                        # Nginx reverse proxy config
├── VERSION                           # Current version
├── CHANGELOG.md                      # Version history
└── README.md
```

## Deployment

### Docker (Production)

```bash
# Build and start
docker compose build --no-cache web_app
docker compose up -d

# Services:
#   stockandpick_webapp  - Flask app on port 5000 (internal)
#   stockandpick_nginx   - Nginx proxy on port 5002 (external)
#   aci-database         - PostgreSQL (shared, external)
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `POSTGRES_HOST` | Database host (default: `aci-database`) |
| `POSTGRES_DB` | Database name (default: `kosh`) |
| `POSTGRES_USER` | Database user |
| `POSTGRES_PASSWORD` | Database password |
| `SECRET_KEY` | Flask session secret key |
| `SSO_SECRET_KEY` | JWT secret for ACI FORGE SSO |

### Database

KOSH uses the `kosh` database on the shared `aci-database` PostgreSQL container. Tables are in the `pcb_inventory` schema:

- `tblBOM` - Bill of Materials records
- `tblJob` - Job master records
- `tblWhse_Inventory` - Warehouse inventory
- `tblPN_List` - Part number list
- `tblTransaction` - Audit trail for stock/pick operations
- `tblACI_PartNumbers` - Manually created ACI numbers
- `tblActivityLog` - User activity notifications
- `tblLoc` - Warehouse locations
- `tblUser` - User accounts and roles
- `tblShortageReport` / `tblShortageReportItems` - Shortage reports
- `tblReceipt` - Receipt records
- `tblPCB_Inventory` - PCB inventory
- `tblBOM_Archive` - Historical BOM records

## Development Notes

- The Docker build context is `./migration/stockAndPick/web_app/`, not the repo root. When editing files in the repo root, copy them to the build context before rebuilding.
- The `static_files` Docker volume persists `/app/static`. To deploy CSS/JS changes, remove the volume: `docker volume rm kosh_static_files` then recreate containers.
- Flask runs in production mode (debug=False) behind Gunicorn and Nginx.
- All database operations use connection pooling with automatic failover.

## Owner

**American Circuits Inc.**

Developed by **Kanav Sharma**

## License

Proprietary — American Circuits Inc. Internal use only.
