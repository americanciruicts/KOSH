#!/usr/bin/env bash
# Safe KOSH deploy: regression tests → Docker --no-cache rebuild → Vercel.
# Aborts before any deploy step if any regression test fails.
#
# Usage:
#   /home/tony/KOSH/deploy.sh          # full safe deploy
#   /home/tony/KOSH/deploy.sh --skip-tests   # only if you absolutely must
#
# Tests must run against the live container BEFORE the rebuild so we catch
# regressions in the code about to be shipped, not the code already running.

set -e
cd "$(dirname "$0")"

SKIP_TESTS=0
if [[ "${1:-}" == "--skip-tests" ]]; then
    SKIP_TESTS=1
    echo ">> --skip-tests passed; skipping regression suite. NOT recommended."
fi

# --- Deploy-gap guard ----------------------------------------------------
# The May 4-5 2026 BOM Loader incident was caused by yesterday's fix sitting
# on local main while production (Vercel) was still on origin/main. Refuse
# to deploy if anything is uncommitted, and verify at the end that local
# matches origin so Vercel actually got the changes.
git fetch origin main --quiet 2>/dev/null || true
if ! git diff-index --quiet HEAD -- ':!*.accdb' ':!*.mdb' ':!*.next' 2>/dev/null; then
    echo "!! You have uncommitted code changes (excluding *.accdb/*.mdb)."
    echo "   Commit them first — every deploy must be a known commit."
    git status --short -- ':!*.accdb' ':!*.mdb' | head -20
    exit 3
fi

if [[ "${SKIP_TESTS}" -eq 0 ]]; then
    echo ">> Running KOSH regression smoke tests against the running container…"
    if ! ./tests/run.sh; then
        echo ""
        echo "!! Regression tests failed. Deploy aborted."
        echo "   Fix the failing test(s) and re-run, OR run with --skip-tests"
        echo "   if you accept the risk."
        exit 1
    fi
fi

echo ""
echo ">> docker compose build --no-cache"
docker compose build --no-cache

echo ""
echo ">> docker compose up -d"
docker compose up -d

# The static_files named volume overlays /app/static and persists across
# rebuilds, so the IMAGE's static files don't show up in the running
# container. Sync from the freshly-rebuilt image into the volume by
# routing through a host tmpdir (docker cp can't go container-to-container).
echo ">> Syncing /app/static from new image into static_files volume…"
TMP_CID=$(docker create kosh-web_app)
SYNC_DIR=$(mktemp -d)
docker cp "${TMP_CID}:/app/static/." "${SYNC_DIR}/"
docker rm "${TMP_CID}" >/dev/null
docker cp "${SYNC_DIR}/." stockandpick_webapp:/app/static/
rm -rf "${SYNC_DIR}"

# Wait for the new container to come up healthy before pushing Vercel
echo ">> Waiting for container health…"
for i in {1..30}; do
    status=$(docker inspect --format='{{.State.Health.Status}}' stockandpick_webapp 2>/dev/null || echo "unknown")
    if [[ "${status}" == "healthy" ]]; then
        echo "   container healthy"
        break
    fi
    sleep 2
done

# Re-run the suite against the freshly-built container too, so we catch
# anything the no-cache rebuild itself might have re-introduced.
if [[ "${SKIP_TESTS}" -eq 0 ]]; then
    echo ""
    echo ">> Re-running regression suite against rebuilt container…"
    if ! ./tests/run.sh; then
        echo ""
        echo "!! Post-rebuild regression failure. Vercel push aborted."
        echo "   The new image is running locally but DON'T promote to prod."
        exit 2
    fi
fi

echo ""
echo ">> Pushing to origin/main (this is what triggers Vercel — vercel CLI is unreliable for KOSH)"
git push origin main

# Final guard: confirm origin actually received what we have locally.
git fetch origin main --quiet
LOCAL=$(git rev-parse main)
REMOTE=$(git rev-parse origin/main)
if [[ "${LOCAL}" != "${REMOTE}" ]]; then
    echo "!! origin/main (${REMOTE}) does not match local main (${LOCAL})."
    echo "   Vercel will deploy stale code. Investigate before walking away."
    exit 4
fi

echo ""
echo ">> Deploy complete."
echo "   local main:  ${LOCAL}"
echo "   origin/main: ${REMOTE}"
echo "   Vercel build will pick this up automatically (~2 min)."
