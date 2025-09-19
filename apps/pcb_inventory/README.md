# Stock and Pick Migration to PostgreSQL

This directory contains the complete migration setup for converting the Stock and Pick PCB inventory system from Microsoft Access to PostgreSQL with Docker deployment.

## Overview

The Stock and Pick system is a PCB (Printed Circuit Board) inventory management application that tracks PCBs through different assembly stages:
- **Bare PCB** - Basic circuit board
- **Partial Assembly** - Some components installed  
- **Completed Assembly** - Fully assembled
- **Ready to Ship** - Final stage

## Migration Components

### 1. Docker PostgreSQL Setup
- **`docker-compose.yml`** - PostgreSQL + pgAdmin containers
- **`init/01-create-schema.sql`** - Database schema with enums, triggers, and functions
- **`Dockerfile.migration`** - Migration tools container

### 2. Database Schema
- **`tblPCB_Inventory`** - Main inventory table
- **`inventory_audit`** - Audit trail for all changes
- **Stored procedures** for stock/pick operations
- **Views** for common queries
- **Triggers** for automated logging

### 3. Migration Tools
- **`run_migration.py`** - Complete migration orchestrator
- **`access_extractor.py`** - Extract forms, reports, and applications
- **Parent migration tools** - Schema conversion and data migration

## Quick Start

### 1. Start PostgreSQL
```bash
docker-compose up -d
```

### 2. Run Complete Migration
```bash
python run_migration.py --access-db "INVENTORY TABLE.mdb"
```

### 3. Access Services
- **PostgreSQL**: `localhost:5432`
- **pgAdmin**: `http://localhost:8080`
  - Email: `admin@stockandpick.com`
  - Password: `admin123`

## Database Configuration

### Connection Details
- **Host**: localhost
- **Port**: 5432
- **Database**: pcb_inventory
- **User**: stockpick_user
- **Password**: stockpick_pass

### Schema Features
- **Enums** for PCB types and location ranges
- **Constraints** to prevent negative inventory
- **Audit logging** for all inventory changes
- **Stored procedures** for safe stock/pick operations
- **Indexes** for optimal query performance

## Migration Process

### Step 1: Database Analysis
```bash
python run_migration.py --access-db "INVENTORY TABLE.mdb"
```
This analyzes the Access database structure and generates a comprehensive report.

### Step 2: Schema Conversion
The schema is automatically converted with:
- Data type mappings (Access → PostgreSQL)
- Constraint preservation
- Index creation
- Relationship maintenance

### Step 3: Data Migration
Data is migrated in batches with:
- Progress tracking
- Error handling
- Data validation
- Verification checks

### Step 4: Forms and Reports Extraction
**Windows + Access Required** for automatic extraction:
- Forms structure and controls
- Reports layout and data sources
- Queries and VBA code
- Macros and modules

**Alternative**: Manual extraction guide is generated

### Step 5: Modern Web Application
A modern web application structure is generated to replace the tkinter interface.

## Original System Analysis

### Access Database Structure
- **Table**: `tblPCB_Inventory`
- **Fields**: job, pcb_type, qty, location
- **Key**: Compound key (job + pcb_type)

### Python Application Features
- **Stock Operation**: Add inventory (create or update)
- **Pick Operation**: Remove inventory (with validation)
- **Safety Checks**: Prevent over-picking
- **Location Management**: Range-based storage system

## PostgreSQL Enhancements

### New Features
- **Audit Trail**: Complete history of all changes
- **Stored Procedures**: Safe operations with JSON responses
- **Views**: Pre-built queries for common operations
- **Triggers**: Automatic timestamp and logging
- **Constraints**: Data integrity enforcement

### Sample Operations

#### Stock PCB
```sql
SELECT stock_pcb('12345', 'Bare', 50, '8000-8999');
```

#### Pick PCB
```sql
SELECT pick_pcb('12345', 'Bare', 25);
```

#### View Current Inventory
```sql
SELECT * FROM current_inventory;
```

#### View Audit Trail
```sql
SELECT * FROM inventory_audit ORDER BY timestamp DESC;
```

## Migration Outputs

All migration artifacts are saved in `migration_outputs/`:
- `database_analysis.json` - Complete database structure
- `postgresql_schema.sql` - Generated schema
- `data_migration_report.json` - Migration statistics
- `forms_reports_extraction.json` - UI components (if extracted)
- `manual_extraction_guide.md` - Manual extraction instructions
- `migration_final_report.json` - Complete migration summary

## Troubleshooting

### Common Issues

1. **Docker Port Conflicts**
   ```bash
   # Check if port 5432 is in use
   lsof -i :5432
   ```

2. **Access Database Connection**
   - Ensure Access database is not open in another application
   - Check file permissions
   - Verify database is not corrupted

3. **Migration Failures**
   - Check logs in `migration.log`
   - Review error messages in final report
   - Ensure PostgreSQL is running and accessible

### Logs and Monitoring
- **Application logs**: `migration.log`
- **PostgreSQL logs**: `docker-compose logs postgres`
- **Migration progress**: Real-time console output

## Next Steps

### Modern Web Application
1. **Frontend**: React/Vue.js interface
2. **Backend**: Flask/FastAPI REST API
3. **Authentication**: User management system
4. **Reporting**: Analytics and dashboards
5. **Mobile**: Responsive design for shop floor

### Enhanced Features
- **Multi-user support**
- **Role-based permissions**
- **Advanced reporting**
- **Integration APIs**
- **Mobile app**

## Support

For issues or questions:
1. Check the migration logs
2. Review the final report
3. Consult the manual extraction guide
4. Verify Docker container status

The migration process preserves all data and business logic while modernizing the infrastructure for future enhancements.