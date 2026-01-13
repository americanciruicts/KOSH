# ACI Inventory Database Migration Guide

This guide will help you migrate all data from your Microsoft Access database (`INVENTORY TABLE.mdb`) to PostgreSQL.

## Overview

The migration will:
- ✅ Extract ALL tables from the Access database
- ✅ Automatically detect column data types
- ✅ Create properly structured PostgreSQL tables
- ✅ Migrate all data with data type conversion
- ✅ Verify the migration was successful
- ✅ Preserve original table and column names (with PostgreSQL-safe naming)

## Prerequisites

- Docker and Docker Compose installed
- The `INVENTORY TABLE.mdb` file in this directory

## Quick Start (Recommended)

### Option 1: Using the Migration Script (Easiest)

```bash
cd "/home/tony/ACI Invertory"
./run_migration.sh
```

This script will:
1. Start PostgreSQL
2. Build the migration container
3. Run the complete migration
4. Verify all data was transferred

### Option 2: Manual Docker Migration

1. **Start PostgreSQL:**
   ```bash
   docker-compose up -d postgres
   ```

2. **Wait for PostgreSQL to be ready:**
   ```bash
   # Check status
   docker-compose exec postgres pg_isready -U stockpick_user -d pcb_inventory
   ```

3. **Build migration container:**
   ```bash
   docker build -f Dockerfile.migration -t aci-migration:latest .
   ```

4. **Run migration:**
   ```bash
   docker run --rm \
     --name aci-migration \
     --network aci-invertory_stockpick-network \
     -v "$(pwd)/INVENTORY TABLE.mdb:/app/INVENTORY TABLE.mdb:ro" \
     -e DB_HOST=postgres \
     aci-migration:latest
   ```

### Option 3: Local Python Migration (If mdb-tools is installed locally)

```bash
# Install Python dependencies
pip install psycopg2-binary

# Make sure PostgreSQL is running
docker-compose up -d postgres

# Run migration
python3 migrate_all_tables.py
```

## Migration Process Details

### Step 1: Data Extraction
- Connects to the Access database using `mdb-tools`
- Lists all user tables (filters out system tables)
- Exports each table as CSV
- Analyzes column types from sample data

### Step 2: Schema Creation
- Creates `pcb_inventory` schema in PostgreSQL
- Infers appropriate PostgreSQL data types:
  - INTEGER for whole numbers
  - NUMERIC for decimals
  - TIMESTAMP for dates
  - VARCHAR/TEXT for strings

### Step 3: Table Creation
- Creates tables with proper column types
- Adds `id` (auto-increment primary key)
- Adds `migrated_at` timestamp

### Step 4: Data Migration
- Converts and cleans data
- Handles special characters
- Truncates overly long text
- Converts data types appropriately

### Step 5: Verification
- Counts records in each table
- Compares with source data
- Reports any discrepancies

## Expected Tables

Based on the Access database structure, the following tables will be migrated:

- `tblPCB_Inventory` - Main PCB inventory (851 records)
- `TranCode` - Transaction codes (5 records)
- `tblWhse_Inventory` - Warehouse inventory
- `tblTransaction` - Transaction history
- `tblUser` - User information
- `tblReceipt` - Receipt records
- `tblPICK_Entry` - Pick entries
- `tblPTWY_Entry` - Pathway entries
- `tblRNDT` - RNDT data
- `tblBOM` - Bill of materials
- `tblPN_List` - Part number list
- `tblLoc` - Location data
- `tblCustomerSupply` - Customer supply information
- `tblDateCode` - Date codes
- `tblAVII` - AVII data
- And others...

## Accessing Your Data After Migration

### 1. Using pgAdmin (Web Interface)

```bash
# Start pgAdmin
docker-compose up -d pgadmin

# Access at: http://localhost:8080
# Email: admin@stockandpick.com
# Password: admin123
```

Add Server in pgAdmin:
- Host: postgres
- Port: 5432
- Database: pcb_inventory
- Username: stockpick_user
- Password: stockpick_pass

### 2. Using PostgreSQL Command Line

```bash
# Connect to database
docker-compose exec postgres psql -U stockpick_user -d pcb_inventory

# List all tables
\dt pcb_inventory.*

# View data from a table
SELECT * FROM pcb_inventory."tblPCB_Inventory" LIMIT 10;

# Count records
SELECT COUNT(*) FROM pcb_inventory."tblPCB_Inventory";
```

### 3. Start the Web Application

```bash
# Start all services
docker-compose up -d

# Access at: http://localhost:5000
```

## Troubleshooting

### Migration Script Fails

**Issue:** `mdb-tools not found`
- **Solution:** Use the Docker-based migration (recommended)

**Issue:** `Connection refused` to PostgreSQL
- **Solution:** Make sure PostgreSQL is running: `docker-compose up -d postgres`
- Wait 10-15 seconds for it to fully start

**Issue:** `Permission denied` on MDB file
- **Solution:** Check file permissions: `ls -l "INVENTORY TABLE.mdb"`
- Make it readable: `chmod 644 "INVENTORY TABLE.mdb"`

### Network Issues

**Issue:** Docker containers can't communicate
- **Solution:** Check network exists:
  ```bash
  docker network ls | grep stockpick
  ```
- Create if missing:
  ```bash
  docker network create aci-invertory_stockpick-network
  ```

### Data Type Issues

**Issue:** Some data didn't migrate correctly
- **Solution:** Check the migration logs for specific errors
- The script will continue even if some records fail
- Check error messages to identify problematic data

## Viewing Migration Logs

The migration script provides detailed output:
- ✓ Green checkmarks indicate success
- ✗ Red X marks indicate errors
- Record counts for each table
- Success rates percentage
- Specific error messages for failed records

## Re-running the Migration

The migration can be safely re-run. It will:
1. Drop existing tables (CASCADE)
2. Recreate with fresh schema
3. Re-import all data

```bash
# Simply run the migration script again
./run_migration.sh
```

## Database Connection Details

**PostgreSQL Connection:**
- Host: localhost (or `postgres` within Docker network)
- Port: 5432
- Database: pcb_inventory
- Username: stockpick_user
- Password: stockpick_pass
- Schema: pcb_inventory

**Connection String:**
```
postgresql://stockpick_user:stockpick_pass@localhost:5432/pcb_inventory
```

## Next Steps After Migration

1. **Verify Data:**
   - Check record counts match
   - Spot-check critical tables
   - Verify data integrity

2. **Start Application:**
   ```bash
   docker-compose up -d
   ```

3. **Backup PostgreSQL Data:**
   ```bash
   docker-compose exec postgres pg_dump -U stockpick_user pcb_inventory > backup_$(date +%Y%m%d).sql
   ```

4. **Create Indexes (Optional):**
   - Add indexes to frequently queried columns
   - Improve query performance

## Support

For issues or questions:
1. Check the migration output logs
2. Verify PostgreSQL is running and accessible
3. Check Docker container logs: `docker-compose logs`
4. Review this guide's troubleshooting section

## Files Created by This Migration

- `migrate_all_tables.py` - Main migration script
- `Dockerfile.migration` - Docker container for migration
- `run_migration.sh` - Automated migration runner
- `MIGRATION_GUIDE.md` - This guide

## Clean Up

To remove migration containers and start fresh:

```bash
# Stop all containers
docker-compose down

# Remove volumes (WARNING: This deletes all data!)
docker-compose down -v

# Remove migration image
docker rmi aci-migration:latest
```

---

**Migration Tool Version:** 1.0
**Last Updated:** 2025-10-27
