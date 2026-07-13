#!/usr/bin/env bash
# KOSH ledger cutover — PROD. ~1 min downtime. Legacy tables are untouched (only
# ADDS inventory_txn/inventory_balance + renames the schema), so rollback is trivial.
# A fresh backup already exists: backups/kosh_pcb_inventory_20260713_093832.dump
set -euo pipefail
DB=kosh
PG="docker exec aci-database psql -U aci -d $DB -v ON_ERROR_STOP=1"

echo ">> 1. Stop live app (downtime begins)"
docker stop stockandpick_webapp

echo ">> 2. Rename schema pcb_inventory -> warehouse"
$PG -c "ALTER SCHEMA pcb_inventory RENAME TO warehouse;"

echo ">> 3. Create + seed the canonical ledger"
docker cp scripts/ledger_schema.sql aci-database:/tmp/ledger_schema.sql
docker cp scripts/ledger_migrate.sql aci-database:/tmp/ledger_migrate.sql
$PG -f /tmp/ledger_schema.sql
$PG -f /tmp/ledger_migrate.sql

echo ">> 4. Acceptance gate (A must be 0, C must be 0)"
A=$($PG -tAc "WITH wh AS (SELECT pcn_id,SUM(qty) q FROM warehouse.inventory_balance GROUP BY pcn_id),
 h AS (SELECT pcn_id,SUM((CASE WHEN to_location_id IS NOT NULL THEN qty ELSE 0 END)-(CASE WHEN from_location_id IS NOT NULL THEN qty ELSE 0 END)) q FROM warehouse.inventory_txn WHERE reversed=false GROUP BY pcn_id)
 SELECT COUNT(*) FILTER (WHERE COALESCE(wh.q,0)<>COALESCE(h.q,0)) FROM wh FULL JOIN h USING(pcn_id);")
C=$($PG -tAc "SELECT count(*) FROM warehouse.inventory_balance WHERE qty<0;")
echo "   A_mismatches=$A  C_negatives=$C"
if [[ "$A" != "0" || "$C" != "0" ]]; then
  echo "!! GATE FAILED — ROLLING BACK (rename schema back; legacy data intact)"
  $PG -c "DROP TABLE IF EXISTS warehouse.inventory_balance, warehouse.inventory_txn CASCADE;"
  $PG -c "ALTER SCHEMA warehouse RENAME TO pcb_inventory;"
  docker start stockandpick_webapp
  echo "Rolled back. Old app restarted on pcb_inventory."
  exit 1
fi

echo ">> 5. Deploy new app image"
docker compose up -d web_app

echo ">> 6. Wait for health + smoke"
sleep 8
docker ps --filter name=stockandpick_webapp --format '{{.Status}}'
curl -fsS -o /dev/null -w "   GET / -> %{http_code}\n" http://localhost:5002/ || true
echo ">> CUTOVER COMPLETE. Monitor:  $PG -c \"...acceptance A...\"  (must stay 0)"
echo ">> ROLLBACK if needed: git checkout app.py && rm -f ledger.py && \\"
echo "   docker exec aci-database psql -U aci -d kosh -c 'DROP TABLE warehouse.inventory_balance, warehouse.inventory_txn CASCADE; ALTER SCHEMA warehouse RENAME TO pcb_inventory;' && \\"
echo "   docker compose up -d --build web_app"
