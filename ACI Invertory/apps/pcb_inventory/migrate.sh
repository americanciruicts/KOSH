#!/bin/bash

echo "=========================================="
echo "Stock and Pick Docker Migration"
echo "Starting at $(date)"
echo "=========================================="

# Set working directory
cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick

# Phase 1: Infrastructure Setup
echo "Phase 1: Infrastructure Setup (PostgreSQL and pgAdmin)"
echo "Cleaning up existing containers..."
docker-compose down --volumes --remove-orphans 2>/dev/null || true

echo "Creating directories..."
mkdir -p logs analysis_output backups

echo "Starting PostgreSQL and pgAdmin..."
docker-compose up -d postgres pgadmin

echo "Waiting for PostgreSQL to be ready..."
sleep 30

# Phase 2: Database Migration
echo "Phase 2: Database Migration"
echo "Running database migration..."
docker-compose --profile migration up --build migration

# Phase 3: Web Application
echo "Phase 3: Web Application"
echo "Starting web application..."
docker-compose up -d --build web_app

sleep 10

# Phase 4: Health Checks
echo "Phase 4: Health Checks"
echo "Container Status:"
docker-compose ps

echo ""
echo "Access URLs:"
echo "• Web Application: http://localhost:5000"
echo "• pgAdmin: http://localhost:8080"
echo "• PostgreSQL: localhost:5432"

echo ""
echo "Testing endpoints..."
curl -s http://localhost:5000/health || echo "Health check failed"
curl -s http://localhost:5000/api/inventory || echo "Inventory API failed"

echo ""
echo "Migration completed at $(date)"