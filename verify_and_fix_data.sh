#!/bin/bash
# Data Verification and Fix Script
# Run this after any data migration or transfer to ensure data integrity

echo "=========================================="
echo "ACI Inventory - Data Verification Script"
echo "=========================================="
echo ""

# Database connection info
DB_CONTAINER="aci-database"
DB_USER="stockpick_user"
DB_NAME="pcb_inventory"

echo "1. Fixing 'Stock' to '-' in all tables..."
echo "   - Updating tblWhse_Inventory..."
docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c \
    "UPDATE pcb_inventory.\"tblWhse_Inventory\" SET loc_from = '-' WHERE loc_from = 'Stock';"

echo "   - Updating tblTransaction..."
docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c \
    "UPDATE pcb_inventory.\"tblTransaction\" SET loc_from = '-' WHERE loc_from = 'Stock';"

echo "   - Updating po_history..."
docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c \
    "UPDATE pcb_inventory.po_history SET location_from = '-' WHERE location_from = 'Stock';"

echo ""
echo "2. Verifying fixes..."

echo "   - Checking for any remaining 'Stock' entries in tblWhse_Inventory..."
STOCK_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
    "SELECT COUNT(*) FROM pcb_inventory.\"tblWhse_Inventory\" WHERE loc_from = 'Stock';")
echo "     Found: $STOCK_COUNT (should be 0)"

echo "   - Checking for any remaining 'Stock' entries in tblTransaction..."
STOCK_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
    "SELECT COUNT(*) FROM pcb_inventory.\"tblTransaction\" WHERE loc_from = 'Stock';")
echo "     Found: $STOCK_COUNT (should be 0)"

echo "   - Checking for any remaining 'Stock' entries in po_history..."
STOCK_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
    "SELECT COUNT(*) FROM pcb_inventory.po_history WHERE location_from = 'Stock';")
echo "     Found: $STOCK_COUNT (should be 0)"

echo ""
echo "3. Verifying recent PCN order (newest should be first)..."
docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c \
    "SELECT id, pcn, item, loc_from FROM pcb_inventory.\"tblTransaction\" WHERE pcn IS NOT NULL ORDER BY id DESC LIMIT 5;"

echo ""
echo "4. Data integrity report:"
docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c \
    "SELECT
        'tblWhse_Inventory' as table_name,
        COUNT(*) as total_records,
        COUNT(CASE WHEN loc_from = '-' THEN 1 END) as with_dash,
        COUNT(CASE WHEN loc_from = 'Stock' THEN 1 END) as with_stock
    FROM pcb_inventory.\"tblWhse_Inventory\"
    UNION ALL
    SELECT
        'tblTransaction' as table_name,
        COUNT(*) as total_records,
        COUNT(CASE WHEN loc_from = '-' THEN 1 END) as with_dash,
        COUNT(CASE WHEN loc_from = 'Stock' THEN 1 END) as with_stock
    FROM pcb_inventory.\"tblTransaction\"
    WHERE trantype = 'GEN';"

echo ""
echo "=========================================="
echo "Verification Complete!"
echo "=========================================="
echo ""
echo "If 'with_stock' shows 0 for all tables, everything is correct!"
