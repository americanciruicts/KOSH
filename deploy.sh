#!/usr/bin/env bash
# Safe KOSH deploy: build → verify the NEW image against kosh_test → deploy → push.
#
# Usage:
#   /home/tony/KOSH/deploy.sh                # full safe deploy
#   /home/tony/KOSH/deploy.sh --skip-tests   # only if you absolutely must
#
# ORDER MATTERS, and it is not the obvious one. See the three FLAW notes below — each
# is a real failure this script had until 2026-07-15.

set -e
cd "$(dirname "$0")"

SKIP_TESTS=0
if [[ "${1:-}" == "--skip-tests" ]]; then
    SKIP_TESTS=1
    echo ">> --skip-tests passed; skipping the test gate. NOT recommended."
fi

# --- FLAW #1 (fixed): this script used to `git push origin main`, hardcoded ----------
# Production runs from the `inventory-rebuild-ledger` branch, while `main` sits at a
# commit predating the whole inventory ledger. So `git push origin main` pushed a
# stale, untouched branch, reported "Everything up-to-date", and the final guard then
# compared main to origin/main, saw they matched, and printed "Deploy complete." —
# while none of the actual work had left the machine. Push the branch we are ON.
BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [[ "${BRANCH}" == "HEAD" ]]; then
    echo "!! Detached HEAD — checkout a branch before deploying."
    exit 3
fi
echo ">> Deploying from branch: ${BRANCH}"

# --- Deploy-gap guard ----------------------------------------------------
# The May 4-5 2026 BOM Loader incident was caused by yesterday's fix sitting on the
# local machine while production served the pushed code. Refuse to deploy anything
# uncommitted, and verify at the end that origin actually received it.
git fetch origin "${BRANCH}" --quiet 2>/dev/null || true
if ! git diff-index --quiet HEAD -- ':!*.accdb' ':!*.mdb' ':!*.next' 2>/dev/null; then
    echo "!! You have uncommitted code changes (excluding *.accdb/*.mdb)."
    echo "   Commit them first — every deploy must be a known commit."
    git status --short -- ':!*.accdb' ':!*.mdb' | head -20
    exit 3
fi

# --- FLAW #2 (fixed): the gate used to run BEFORE the rebuild ------------------------
# It ran against the already-running container — i.e. the OLD code — so it could never
# vet what was about to ship. Worse, any deploy that FIXED a bug the suite detects got
# aborted by its own red result (exactly what happened with the restock/FOUND fix on
# 2026-07-15). Build first, verify the new image, then promote.
echo ""
echo ">> docker compose build --no-cache"
docker compose build --no-cache

# --- FLAW #3 (fixed): verify the NEW image, on the TEST database ---------------------
# The gate targets kosh_test_webapp, which `docker compose build` does NOT rebuild —
# left alone it would test a STALE image and green-light new code. So recreate the test
# container from the image just built, then run the gate against it.
# It must be the test DB: the suites COMMIT (db_manager.restock_pcb commits internally,
# so SAVEPOINT can't contain it). Pointing them at prod leaked 70 phantom units into
# the prod ledger on 2026-07-15, and breaks the rule "no generate-and-delete PCN tests
# on prod".
if [[ "${SKIP_TESTS}" -eq 0 ]]; then
    echo ""
    echo ">> Recreating kosh_test_webapp from the freshly-built image…"
    PGPASS=$(grep -oP 'POSTGRES_PASSWORD=\K\S+' docker-compose.yml | head -1)
    docker rm -f kosh_test_webapp >/dev/null 2>&1 || true
    docker run -d --name kosh_test_webapp \
        --network db-consolidation_aci-network \
        -p 5056:5000 \
        -e FLASK_ENV=production \
        -e POSTGRES_HOST=aci-database \
        -e POSTGRES_DB=kosh_test \
        -e POSTGRES_USER=aci \
        -e POSTGRES_PASSWORD="${PGPASS}" \
        -e DATABASE_URL="postgresql://aci:${PGPASS}@aci-database:5432/kosh_test" \
        kosh-web_app >/dev/null

    for i in {1..30}; do
        st=$(docker inspect --format='{{.State.Health.Status}}' kosh_test_webapp 2>/dev/null || echo unknown)
        [[ "${st}" == "healthy" ]] && break
        sleep 2
    done

    echo ""
    echo ">> Running the test gate against the NEW image (kosh_test)…"
    if ! ./tests/run.sh; then
        echo ""
        echo "!! Test gate failed on the new image. NOTHING was promoted."
        echo "   Production is still running the previous image. Fix and re-run,"
        echo "   or --skip-tests if you accept the risk."
        exit 1
    fi
fi

# --- Promote to production ----------------------------------------------
echo ""
echo ">> docker compose up -d"
docker compose up -d

# The static_files named volume overlays /app/static and persists across rebuilds, so
# the IMAGE's static files don't show up in the running container. Sync from the
# freshly-rebuilt image into the volume via a host tmpdir (docker cp can't go
# container-to-container).
echo ">> Syncing /app/static from new image into static_files volume…"
TMP_CID=$(docker create kosh-web_app)
SYNC_DIR=$(mktemp -d)
docker cp "${TMP_CID}:/app/static/." "${SYNC_DIR}/"
docker rm "${TMP_CID}" >/dev/null
docker cp "${SYNC_DIR}/." stockandpick_webapp:/app/static/
rm -rf "${SYNC_DIR}"

echo ">> Waiting for container health…"
status=unknown
for i in {1..30}; do
    status=$(docker inspect --format='{{.State.Health.Status}}' stockandpick_webapp 2>/dev/null || echo "unknown")
    if [[ "${status}" == "healthy" ]]; then
        echo "   container healthy"
        break
    fi
    sleep 2
done
if [[ "${status}" != "healthy" ]]; then
    echo "!! stockandpick_webapp is not healthy (${status}). Investigate before walking away."
    exit 5
fi

# --- Push the branch we actually deployed -------------------------------
echo ""
echo ">> Pushing to origin/${BRANCH}"
git push origin "${BRANCH}"

git fetch origin "${BRANCH}" --quiet
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse "origin/${BRANCH}")
if [[ "${LOCAL}" != "${REMOTE}" ]]; then
    echo "!! origin/${BRANCH} (${REMOTE}) does not match local HEAD (${LOCAL})."
    echo "   The remote does NOT have what you just deployed. Investigate."
    exit 4
fi

# --- Vercel -------------------------------------------------------------
# Standing rule: every KOSH deploy is docker compose AND vercel --prod, no skipping.
# Vercel serves static/** and proxies everything else to the Cloudflare tunnel into the
# container above, so a stale Vercel deploy silently serves stale static assets.
echo ""
echo ">> vercel --prod (from vercel-proxy)"
( cd vercel-proxy && vercel --prod --yes )

echo ""
echo ">> Deploy complete."
echo "   branch:           ${BRANCH}"
echo "   local HEAD:       ${LOCAL}"
echo "   origin/${BRANCH}: ${REMOTE}"
