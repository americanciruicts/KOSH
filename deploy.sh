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
echo ">> vercel --prod --yes"
vercel --prod --yes

echo ""
echo ">> Deploy complete."
