# KOSH — Pages Index

Quick map from each user-facing page to its code. Use this to find the route handler, template, and JS for any page in the app.

All routes live in [app.py](app.py). Templates are grouped by feature under [templates/](templates/). Shared static assets live in [static/](static/).

## Core inventory pages

| Page | URL | Route handler | Template | Notes |
|---|---|---|---|---|
| Home / Dashboard | `/` | [app.py:3405](app.py#L3405) | [templates/index.html](templates/index.html) | Stats + recent activity |
| Stock In | `/stock` | [app.py:3513](app.py#L3513) | [templates/inventory_ops/stock.html](templates/inventory_ops/stock.html) | Receive inventory |
| Pick | `/pick` | [app.py:3577](app.py#L3577) | [templates/inventory_ops/pick.html](templates/inventory_ops/pick.html) | Issue inventory |
| Restock | `/restock` | [app.py:3684](app.py#L3684) | [templates/inventory_ops/restock.html](templates/inventory_ops/restock.html) | MFG Floor → Count Area |
| Part Number Change (PCN) | `/part-number-change` | [app.py:3823](app.py#L3823) | [templates/inventory_ops/part_number_change.html](templates/inventory_ops/part_number_change.html) | Uses `static/js/print-label.js` |
| PCB Inventory | `/pcb-inventory` | [app.py:4070](app.py#L4070) | [templates/inventory/inventory.html](templates/inventory/inventory.html) | |
| Warehouse Inventory | `/warehouse-inventory` | [app.py:4215](app.py#L4215) | [templates/inventory/warehouse_inventory.html](templates/inventory/warehouse_inventory.html) | Edit inventory feature |
| Stock Alerts | `/stock-alerts` | [app.py:6140](app.py#L6140) | [templates/inventory/stock_alerts.html](templates/inventory/stock_alerts.html) | |

## Reporting

| Page | URL | Route handler | Template |
|---|---|---|---|
| Reports | `/reports` | [app.py:4729](app.py#L4729) | [templates/reports/reports.html](templates/reports/reports.html) |
| Shortage Report (list) | `/shortage_report` | [app.py:4787](app.py#L4787) | [templates/reports/shortage_report.html](templates/reports/shortage_report.html) |
| Shortage Report (view) | `/shortage_report/view/<id>` | [app.py:5004](app.py#L5004) | [templates/reports/shortage_report_view.html](templates/reports/shortage_report_view.html) |
| Shortage Report (generate) | `/shortage_report/generate` | [app.py:4830](app.py#L4830) | — (POST) |
| Shortage Report (export) | `/shortage_report/export/<id>` | [app.py:5049](app.py#L5049) | — |
| Stats | `/stats` | [app.py:5408](app.py#L5408) | [templates/reports/stats.html](templates/reports/stats.html) |
| History | `/history` | [app.py:7567](app.py#L7567) | [templates/reports/history.html](templates/reports/history.html) |

## PCN / labels

| Page | URL | Route handler | Template |
|---|---|---|---|
| Generate PCN | `/generate-pcn` | [app.py:5905](app.py#L5905) | [templates/pcn/generate_pcn.html](templates/pcn/generate_pcn.html) |
| PCN History | `/pcn-history` | [app.py:6030](app.py#L6030) | [templates/pcn/pcn_history.html](templates/pcn/pcn_history.html) |
| PO History | `/po-history` | [app.py:5914](app.py#L5914) | [templates/pcn/po_history.html](templates/pcn/po_history.html) |
| Print Label | `/print-label/<pcn>` | [app.py:6849](app.py#L6849) | [templates/pcn/print_label.html](templates/pcn/print_label.html) |
| Print Label (ZPL) | `/print-label/<pcn>/zpl` | [app.py:6911](app.py#L6911) | — |

## Jobs / BOMs

| Page | URL | Route handler | Template | Notes |
|---|---|---|---|---|
| Jobs list | `/jobs` | [app.py:7820](app.py#L7820) | [templates/jobs/jobs.html](templates/jobs/jobs.html) | Uses `static/js/bom_parser.js` |
| Job detail | `/jobs/<job_number>` | [app.py:7861](app.py#L7861) | [templates/jobs/job_detail.html](templates/jobs/job_detail.html) | |
| BOM Loader (legacy) | `/bom-loader` | [app.py:7209](app.py#L7209) | — (301 redirect → `/jobs`) | `bom_browser.html` orphaned |

## Source / query tools

| Page | URL | Route handler | Template |
|---|---|---|---|
| Sources list | `/sources` | [app.py:5247](app.py#L5247) | [templates/source/sources.html](templates/source/sources.html) |
| Source table | `/sources/<table>` | [app.py:5340](app.py#L5340) | [templates/source/source_table.html](templates/source/source_table.html) |
| Source access | `/source` | [app.py:5766](app.py#L5766) | [templates/source/source_access.html](templates/source/source_access.html) |
| Source table view | `/source/table/<table>` | [app.py:5788](app.py#L5788) | [templates/source/source_table_view.html](templates/source/source_table_view.html) |
| Source query | `/source/query` | [app.py:5838](app.py#L5838) | [templates/source/source_query.html](templates/source/source_query.html) |

## Admin

| Page | URL | Route handler | Template |
|---|---|---|---|
| Admin notifications | `/admin/notifications` | [app.py:7574](app.py#L7574) | [templates/admin/admin_notifications.html](templates/admin/admin_notifications.html) |
| User management | `/admin/users` | [app.py:8639](app.py#L8639) | [templates/admin/user_management.html](templates/admin/user_management.html) |
| Location management | `/admin/locations` | [app.py:8857](app.py#L8857) | [templates/admin/location_management.html](templates/admin/location_management.html) |

## Auth & errors

| Page | URL | Route handler | Template |
|---|---|---|---|
| Login | `/login` | [app.py:3261](app.py#L3261) | [templates/auth/login.html](templates/auth/login.html) |
| User select | — | — | [templates/auth/user_select.html](templates/auth/user_select.html) (orphan) |
| 404 | error | [app.py:8847](app.py#L8847) | [templates/errors/404.html](templates/errors/404.html) |
| 500 | error | [app.py:8851](app.py#L8851) | [templates/errors/500.html](templates/errors/500.html) |

## Misc

| Page | URL | Route handler | Template |
|---|---|---|---|
| Reel Change | `/reel-change` | [app.py:8992](app.py#L8992) | [templates/misc/reel_change.html](templates/misc/reel_change.html) |
| ACI Numbers | `/aci-numbers` | [app.py:9326](app.py#L9326) | [templates/misc/aci_numbers.html](templates/misc/aci_numbers.html) |

## Templates folder structure

```
templates/
├── base.html                        ← shared layout (extended by all pages)
├── index.html                       ← home/dashboard
├── admin/                           ← admin pages
├── auth/                            ← login, user select
├── errors/                          ← 404, 500
├── inventory/                       ← PCB inventory, warehouse inventory, alerts
├── inventory_ops/                   ← stock in, pick, restock, PCN
├── jobs/                            ← jobs list, job detail, BOM browser
├── misc/                            ← reel change, ACI numbers
├── pcn/                             ← generate PCN, PCN history, PO history, labels
├── reports/                         ← reports, shortage report, stats, history
└── source/                          ← sources & query tools
```

## Shared frontend assets

- Layout: [templates/base.html](templates/base.html)
- CSS: [static/kosh.css](static/kosh.css)
- JS:
  - [static/js/bom_parser.js](static/js/bom_parser.js) — used by Jobs page
  - [static/js/print-label.js](static/js/print-label.js) — used by base.html (silent print)
- Logos / icons: [static/kosh_logo.svg](static/kosh_logo.svg), [static/kosh_icon.svg](static/kosh_icon.svg), [kosh-logo.svg](kosh-logo.svg)

## Top-level directories

| Folder | Contents |
|---|---|
| [templates/](templates/) | Jinja2 page templates, grouped by feature |
| [static/](static/) | CSS, JS, images served as static assets |
| [docs/](docs/) | Feature docs, audit reports, BRDs, training guide |
| [samples/](samples/) | Sample BOM xlsx files, template xlsx, reports |
| [backups/](backups/) | SQL dumps, MDB/CSV table exports |
| [scripts/](scripts/) | Migration & backfill scripts (one-off utilities) |
| [migration/](migration/) | Older migration tooling (`stockAndPick/` web_app) |
| [reelChange/](reelChange/) | Standalone reel-change subapp |
| [vercel-proxy/](vercel-proxy/) | Vercel deployment proxy |
| [tests/](tests/) | Test suite |
| [api/](api/) | Vercel serverless entry (`index.py`) |

## Top-level files (production essentials)

- [app.py](app.py) — main Flask app (all routes)
- [expiration_manager.py](expiration_manager.py) — imported by app.py (line 14)
- [Dockerfile](Dockerfile), [Dockerfile.webapp](Dockerfile.webapp), [Dockerfile.migration](Dockerfile.migration)
- [docker-compose.yml](docker-compose.yml)
- [nginx.conf](nginx.conf)
- [requirements.txt](requirements.txt)
- [deploy.sh](deploy.sh), [run_migration.sh](run_migration.sh), [verify_and_fix_data.sh](verify_and_fix_data.sh)
- [init_functions.sql](init_functions.sql)
- [vercel.json](vercel.json), [.vercelignore](.vercelignore)
- [README.md](README.md), [CHANGELOG.md](CHANGELOG.md), [VERSION](VERSION)
