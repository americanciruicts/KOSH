#!/bin/bash
set -e

echo "Testing minimal Stock and Pick application..."

cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick

# Stop current web app
echo "Stopping current web app..."
docker-compose stop web_app

# Build and run test app
echo "Building test app..."
docker build -f web_app/Dockerfile.test -t stockandpick-test web_app/

echo "Running test app..."
docker run -d \
  --name stockandpick_test \
  --network stockandpick_stockpick-network \
  -p 5001:5000 \
  -e POSTGRES_HOST=postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_DB=pcb_inventory \
  -e POSTGRES_USER=stockpick_user \
  -e POSTGRES_PASSWORD=stockpick_pass \
  stockandpick-test

# Wait and test
sleep 5

echo "Testing endpoints..."
echo "Basic test:"
curl -s http://localhost:5001/ | python3 -m json.tool

echo ""
echo "Health check:"
curl -s http://localhost:5001/health | python3 -m json.tool

echo ""
echo "Database test:"
curl -s http://localhost:5001/test-db | python3 -m json.tool

echo ""
echo "Container logs:"
docker logs stockandpick_test

echo ""
echo "If this works, the issue is in the main Flask app."
echo "If this fails, the issue is environmental."