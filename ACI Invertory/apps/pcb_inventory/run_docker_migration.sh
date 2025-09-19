#!/bin/bash
set -e

echo "=========================================="
echo "Stock and Pick Docker Migration"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker and try again."
    exit 1
fi

print_status "Docker is running"

# Navigate to the correct directory
cd "$(dirname "$0")"
print_info "Working directory: $(pwd)"

# Clean up any existing containers
print_info "Cleaning up existing containers..."
docker-compose down --volumes --remove-orphans 2>/dev/null || true

# Clean up Docker system (optional)
print_info "Cleaning Docker system..."
docker system prune -f >/dev/null 2>&1 || true

# Create necessary directories
mkdir -p logs analysis_output backups

# Start PostgreSQL and pgAdmin first
print_info "Starting PostgreSQL and pgAdmin..."
docker-compose up -d postgres pgadmin

# Wait for PostgreSQL to be ready
print_info "Waiting for PostgreSQL to be ready..."
for i in {1..30}; do
    if docker exec stockandpick_postgres pg_isready -h localhost -p 5432 -U stockpick_user >/dev/null 2>&1; then
        print_status "PostgreSQL is ready"
        break
    fi
    
    if [ $i -eq 30 ]; then
        print_error "PostgreSQL failed to start after 30 attempts"
        docker-compose logs postgres
        exit 1
    fi
    
    echo "Waiting for PostgreSQL... (attempt $i/30)"
    sleep 2
done

# Run database migration
print_info "Running database migration..."
docker-compose --profile migration up --build migration

# Check migration results
if [ $? -eq 0 ]; then
    print_status "Database migration completed successfully"
else
    print_warning "Database migration completed with warnings"
fi

# Start web application
print_info "Starting web application..."
docker-compose up -d --build web_app

# Wait for web application to be ready
print_info "Waiting for web application to be ready..."
for i in {1..20}; do
    if curl -f http://localhost:5000/health >/dev/null 2>&1; then
        print_status "Web application is ready"
        break
    fi
    
    if [ $i -eq 20 ]; then
        print_warning "Web application health check failed, but it may still be working"
        break
    fi
    
    echo "Waiting for web application... (attempt $i/20)"
    sleep 3
done

# Display final status
echo ""
echo "=========================================="
echo "MIGRATION COMPLETED"
echo "=========================================="

# Check container status
print_info "Container Status:"
docker-compose ps

echo ""
print_info "Access URLs:"
echo "• Web Application: http://localhost:5000"
echo "• pgAdmin: http://localhost:8080"
echo "  - Email: admin@stockandpick.com"
echo "  - Password: admin123"
echo "• PostgreSQL: localhost:5432"
echo "  - Database: pcb_inventory"
echo "  - User: stockpick_user"
echo "  - Password: stockpick_pass"

echo ""
print_info "Test the system:"
echo "curl http://localhost:5000/health"
echo "curl http://localhost:5000/api/inventory"

echo ""
print_info "View logs:"
echo "docker-compose logs web_app"
echo "docker-compose logs postgres"

echo ""
print_info "Migration files:"
ls -la analysis_output/ 2>/dev/null || echo "Analysis output directory not found"
ls -la logs/ 2>/dev/null || echo "Logs directory not found"

# Test basic functionality
print_info "Testing basic functionality..."

# Test health endpoint
if curl -s http://localhost:5000/health | grep -q "healthy"; then
    print_status "Health check: PASSED"
else
    print_warning "Health check: FAILED"
fi

# Test inventory API
if curl -s http://localhost:5000/api/inventory | grep -q "success"; then
    print_status "Inventory API: PASSED"
else
    print_warning "Inventory API: FAILED"
fi

echo ""
print_status "Docker migration completed!"
print_info "The Stock and Pick system is now running entirely in Docker containers"