#!/bin/bash
set -e

echo "Starting Stock and Pick Migration..."

cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick

echo "Cleaning up existing containers..."
docker-compose down --volumes --remove-orphans
sleep 2

echo "Starting PostgreSQL..."
docker-compose up -d postgres

echo "Waiting for PostgreSQL..."
sleep 10
docker-compose exec postgres pg_isready -h localhost -p 5432 -U stockpick_user

echo "Running database migration..."
docker-compose --profile migration up --build migration

echo "Starting web application..."
docker-compose up -d --build web_app

echo "Starting pgAdmin..."
docker-compose up -d pgadmin

echo "Migration completed!"
echo "Web app: http://localhost:5000"
echo "pgAdmin: http://localhost:8080"

echo "Checking status..."
docker-compose ps

echo "Testing web app..."
sleep 5
curl -f http://localhost:5000/health || echo "Web app not ready yet"