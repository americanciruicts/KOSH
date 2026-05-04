#!/usr/bin/env bash
# Runs the KOSH regression smoke suite inside the running webapp container.
# Exit code = number of failed tests (0 == all green).
#
# Use before every deploy:
#   /home/tony/KOSH/tests/run.sh && \
#     docker compose build --no-cache && docker compose up -d && \
#     vercel --prod --yes
#
# If any test fails, fix the regression BEFORE shipping.

set -e
cd "$(dirname "$0")/.."

CONTAINER=stockandpick_webapp
if ! docker ps --filter "name=${CONTAINER}" --format '{{.Names}}' | grep -q "${CONTAINER}"; then
    echo "Container ${CONTAINER} is not running. Start it first:"
    echo "  docker compose up -d"
    exit 99
fi

# Copy current test file in case it's newer than the image
docker cp tests/regression_tests.py "${CONTAINER}:/app/tests/regression_tests.py"

docker exec "${CONTAINER}" python /app/tests/regression_tests.py
