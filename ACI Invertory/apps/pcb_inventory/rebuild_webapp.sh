#!/bin/bash
set -e

echo "Rebuilding Stock and Pick Web Application..."

cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick

echo "Stopping web app container..."
docker-compose stop web_app

echo "Removing web app container..."
docker-compose rm -f web_app

echo "Rebuilding and starting web app with port 5001..."
docker-compose up -d --build web_app

echo "Starting pgAdmin..."
docker-compose up -d pgadmin

echo "Checking container status..."
docker-compose ps

echo "Checking web app logs..."
docker-compose logs --tail=20 web_app

echo ""
echo "Web Application should now be available at:"
echo "http://localhost:5001"
echo ""
echo "pgAdmin available at:"
echo "http://localhost:8080"