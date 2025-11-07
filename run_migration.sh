#!/bin/bash

# ACI Inventory Migration Script
# This script migrates all data from the Access database to PostgreSQL

set -e  # Exit on error

echo "=============================================="
echo "    ACI INVENTORY DATABASE MIGRATION"
echo "=============================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if MDB file exists
if [ ! -f "INVENTORY TABLE.mdb" ]; then
    echo -e "${RED}ERROR: INVENTORY TABLE.mdb not found in current directory${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Found INVENTORY TABLE.mdb${NC}"
echo ""

# Step 1: Start PostgreSQL if not already running
echo "Step 1: Starting PostgreSQL database..."
docker-compose up -d postgres

echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Wait for PostgreSQL to be healthy
for i in {1..30}; do
    if docker-compose exec -T postgres pg_isready -U stockpick_user -d pcb_inventory > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PostgreSQL is ready${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}ERROR: PostgreSQL failed to start${NC}"
        exit 1
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

echo ""

# Step 2: Build migration container
echo "Step 2: Building migration container..."
docker build -f Dockerfile.migration -t aci-migration:latest .
echo -e "${GREEN}✓ Migration container built${NC}"
echo ""

# Step 3: Run migration
echo "Step 3: Running migration..."
echo "This may take several minutes depending on database size..."
echo ""

docker run --rm \
    --name aci-migration \
    --network aciinvertory_stockpick-network \
    -v "$(pwd)/INVENTORY TABLE.mdb:/app/INVENTORY TABLE.mdb:ro" \
    -e DB_HOST=postgres \
    -e DB_PORT=5432 \
    -e DB_NAME=pcb_inventory \
    -e DB_USER=stockpick_user \
    -e DB_PASSWORD=stockpick_pass \
    aci-migration:latest

MIGRATION_EXIT_CODE=$?

echo ""
echo "=============================================="

if [ $MIGRATION_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ MIGRATION COMPLETED SUCCESSFULLY!${NC}"
    echo ""
    echo "You can now:"
    echo "  1. Start the web application: docker-compose up -d web_app"
    echo "  2. Access pgAdmin at http://localhost:8080"
    echo "     Email: admin@stockandpick.com"
    echo "     Password: admin123"
    echo "  3. View the data in your application at http://localhost:5000"
else
    echo -e "${RED}❌ MIGRATION FAILED${NC}"
    echo "Please check the error messages above"
    exit 1
fi

echo "=============================================="
