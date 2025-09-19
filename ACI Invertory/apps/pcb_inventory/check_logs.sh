#!/bin/bash

echo "Checking Stock and Pick Application Logs..."

cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick

echo "=== Container Status ==="
docker-compose ps

echo ""
echo "=== Web App Logs ==="
docker-compose logs web_app

echo ""
echo "=== PostgreSQL Logs ==="
docker-compose logs postgres

echo ""
echo "=== Testing Database Connection ==="
docker-compose exec postgres psql -U stockpick_user -d pcb_inventory -c "SELECT COUNT(*) FROM pcb_inventory.tblPCB_Inventory;"

echo ""
echo "=== Testing Health Endpoint ==="
curl -v http://localhost:5001/health

echo ""
echo "=== Container Inspect ==="
docker-compose exec web_app ps aux