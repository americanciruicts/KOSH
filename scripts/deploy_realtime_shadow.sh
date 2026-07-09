#!/usr/bin/env bash
# KOSH — deploy the validated real-time shadow events (Phase 4c) to prod,
# ZERO-DOWNTIME, with self-verification and AUTOMATIC ROLLBACK on failure.
# Safe to run unattended. Validated on kosh_test 2026-07-09.
#
# Deploys: app.py (5 fail-safe write-path hooks) + inv_shadow.py (realtime_sync).
# Method: docker cp into the running container + graceful gunicorn HUP reload.
set -uo pipefail

REPO=/home/tony/KOSH
C=stockandpick_webapp
DB=aci-database
: "${PGPASSWORD:?Set PGPASSWORD (prod DB password for role 'aci') before running}"; export PGPASSWORD
TS=$(date +%Y%m%d_%H%M%S)
LOG=$REPO/logs/deploy_realtime_${TS}.log
BK=/tmp/kosh_deploy_backup_${TS}
mkdir -p "$BK" "$REPO/logs"
say(){ echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

psql(){ docker exec -e PGPASSWORD "$DB" psql -U aci -d kosh -qAt -c "$1" 2>&1; }
health(){ docker exec "$C" sh -c 'curl -sf -o /dev/null -w "%{http_code}" http://localhost:5000/' 2>/dev/null; }
differ(){ psql "WITH n AS (SELECT pcn,SUM(onhand_qty) o FROM pcb_inventory.inv_onhand GROUP BY pcn),
  o AS (SELECT pcn::text pcn,SUM(GREATEST(onhandqty,0)+CASE WHEN mfg_qty ~ '^[1-9][0-9]*\$' THEN mfg_qty::int ELSE 0 END) o FROM pcb_inventory.\"tblWhse_Inventory\" GROUP BY pcn::text)
  SELECT count(*) FILTER (WHERE COALESCE(n.o,0)<>COALESCE(o.o,0)) FROM o FULL JOIN n USING(pcn)"; }

say "=== KOSH real-time shadow deploy start ==="
say "pre-check: app health=$(health)  reconcile_differ=$(differ)"

# 1. Backup the currently-running files (for rollback)
docker cp "$C:/app/app.py"        "$BK/app.py"        && say "backed up app.py"
docker cp "$C:/app/inv_shadow.py" "$BK/inv_shadow.py" 2>/dev/null || say "no existing inv_shadow.py in container (new file)"

# 2. Deploy the new files
if ! docker cp "$REPO/app.py" "$C:/app/app.py"; then say "FAIL: cp app.py"; exit 1; fi
if ! docker cp "$REPO/inv_shadow.py" "$C:/app/inv_shadow.py"; then say "FAIL: cp inv_shadow.py"; exit 1; fi
say "copied new app.py + inv_shadow.py"

# 3. Graceful zero-downtime reload
docker kill --signal=HUP "$C" >/dev/null && say "HUP sent (graceful reload)"
sleep 30

# 4. Verify
H=$(health); D=$(differ)
TSTART=$(psql "SELECT COALESCE(MAX(id),0) FROM pcb_inventory.\"tblTransaction\"")
ERR=$(docker logs "$C" --since 40s 2>&1 | grep -icE "traceback|CRITICAL|Booting worker" )
THREAD=$(docker logs "$C" --since 40s 2>&1 | grep -c "inv shadow sync thread started")
say "post-check: app health=$H  reconcile_differ=$D  thread_started=$THREAD  txn_max=$TSTART"

OK=1
[ "$H" = "200" ] || [ "$H" = "302" ] || { say "VERIFY FAIL: app health=$H"; OK=0; }
[ "$D" = "0" ] || { say "VERIFY WARN: reconcile_differ=$D (expected 0)"; OK=0; }
[ "$THREAD" -ge 1 ] || { say "VERIFY FAIL: shadow thread did not start"; OK=0; }

if [ "$OK" = "1" ]; then
  say "=== DEPLOY SUCCESS — real-time shadow events live, app healthy, reconcile 0 ==="
  say "NOTE: image NOT rebuilt; change is live in the running container. Bake with:"
  say "  cd $REPO && docker compose build --no-cache web_app && docker compose up -d web_app"
  exit 0
else
  say "=== VERIFY FAILED — ROLLING BACK ==="
  docker cp "$BK/app.py" "$C:/app/app.py"
  [ -f "$BK/inv_shadow.py" ] && docker cp "$BK/inv_shadow.py" "$C:/app/inv_shadow.py"
  docker kill --signal=HUP "$C" >/dev/null && say "rollback HUP sent"
  sleep 20
  say "post-rollback: app health=$(health)  reconcile_differ=$(differ)"
  say "=== ROLLED BACK — prod restored to pre-deploy code ==="
  exit 2
fi
