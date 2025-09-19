#!/bin/bash
set -e

echo "Fixing Stock and Pick Web Application..."

cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick

# Stop everything
echo "Stopping all containers..."
docker-compose down

# Wait a moment
sleep 3

# Start PostgreSQL first and wait
echo "Starting PostgreSQL..."
docker-compose up -d postgres

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
sleep 10

# Test database connection
echo "Testing database connection..."
docker-compose exec postgres pg_isready -h localhost -p 5432 -U stockpick_user

# Rebuild web app completely
echo "Rebuilding web application..."
docker-compose build --no-cache web_app

# Start web app
echo "Starting web application..."
docker-compose up -d web_app

# Start pgAdmin
echo "Starting pgAdmin..."
docker-compose up -d pgadmin

# Wait and check
sleep 5

echo "Final status check..."
docker-compose ps

echo "Web app logs:"
docker-compose logs --tail=30 web_app

echo ""
echo "Try accessing: http://localhost:5001"