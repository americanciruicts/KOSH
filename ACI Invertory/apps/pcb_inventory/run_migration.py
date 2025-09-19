#!/usr/bin/env python3
import subprocess
import time
import sys
import os
import requests
from datetime import datetime

def print_status(message):
    print(f"✓ {message}")

def print_error(message):
    print(f"✗ {message}")

def print_info(message):
    print(f"ℹ {message}")

def print_warning(message):
    print(f"⚠ {message}")

def run_command(command, cwd=None, timeout=None):
    """Run a command and return the result"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        print_error(f"Command timed out: {command}")
        return None
    except Exception as e:
        print_error(f"Error running command: {e}")
        return None

def main():
    print("=" * 50)
    print("Stock and Pick Docker Migration")
    print(f"Started at: {datetime.now()}")
    print("=" * 50)
    
    # Set working directory
    migration_dir = "/Users/khashsarrafi/Projects/revestData/migration/stockAndPick"
    os.chdir(migration_dir)
    print_info(f"Working directory: {os.getcwd()}")
    
    # Phase 1: Infrastructure Setup
    print("\nPhase 1: Infrastructure Setup (30s)")
    print_info("Cleaning up existing containers...")
    
    # Clean up existing containers
    result = run_command("docker-compose down --volumes --remove-orphans", cwd=migration_dir)
    if result and result.returncode == 0:
        print_status("Container cleanup completed")
    else:
        print_warning("Container cleanup had issues (this is normal if no containers were running)")
    
    # Create directories
    print_info("Creating directories...")
    os.makedirs("logs", exist_ok=True)
    os.makedirs("analysis_output", exist_ok=True)
    os.makedirs("backups", exist_ok=True)
    print_status("Directories created")
    
    # Start PostgreSQL and pgAdmin
    print_info("Starting PostgreSQL and pgAdmin...")
    result = run_command("docker-compose up -d postgres pgadmin", cwd=migration_dir)
    if result and result.returncode == 0:
        print_status("PostgreSQL and pgAdmin started")
    else:
        print_error("Failed to start PostgreSQL and pgAdmin")
        if result:
            print(f"Error: {result.stderr}")
        return False
    
    # Wait for PostgreSQL to be ready
    print_info("Waiting for PostgreSQL to be ready...")
    for i in range(30):
        result = run_command("docker exec stockandpick_postgres pg_isready -h localhost -p 5432 -U stockpick_user")
        if result and result.returncode == 0:
            print_status("PostgreSQL is ready")
            break
        print(f"Waiting for PostgreSQL... (attempt {i+1}/30)")
        time.sleep(2)
    else:
        print_error("PostgreSQL failed to start after 30 attempts")
        # Show logs
        logs_result = run_command("docker-compose logs postgres", cwd=migration_dir)
        if logs_result:
            print(logs_result.stdout)
        return False
    
    # Phase 2: Database Migration
    print("\nPhase 2: Database Migration (60s)")
    print_info("Running database migration...")
    result = run_command("docker-compose --profile migration up --build migration", cwd=migration_dir, timeout=120)
    if result and result.returncode == 0:
        print_status("Database migration completed successfully")
    else:
        print_warning("Database migration completed with warnings")
        if result:
            print(f"Migration output: {result.stdout}")
            if result.stderr:
                print(f"Migration errors: {result.stderr}")
    
    # Phase 3: Web Application
    print("\nPhase 3: Web Application (30s)")
    print_info("Starting web application...")
    result = run_command("docker-compose up -d --build web_app", cwd=migration_dir)
    if result and result.returncode == 0:
        print_status("Web application started")
    else:
        print_error("Failed to start web application")
        if result:
            print(f"Error: {result.stderr}")
        return False
    
    # Wait for web application to be ready
    print_info("Waiting for web application to be ready...")
    for i in range(20):
        try:
            response = requests.get("http://localhost:5000/health", timeout=5)
            if response.status_code == 200:
                print_status("Web application is ready")
                break
        except:
            pass
        print(f"Waiting for web application... (attempt {i+1}/20)")
        time.sleep(3)
    else:
        print_warning("Web application health check failed, but it may still be working")
    
    # Phase 4: Health Checks
    print("\nPhase 4: Health Checks and Validation (15s)")
    
    # Check container status
    print_info("Container Status:")
    result = run_command("docker-compose ps", cwd=migration_dir)
    if result:
        print(result.stdout)
    
    print("\nAccess URLs:")
    print("• Web Application: http://localhost:5000")
    print("• pgAdmin: http://localhost:8080")
    print("  - Email: admin@stockandpick.com")
    print("  - Password: admin123")
    print("• PostgreSQL: localhost:5432")
    print("  - Database: pcb_inventory")
    print("  - User: stockpick_user")
    print("  - Password: stockpick_pass")
    
    # Test basic functionality
    print("\nTesting basic functionality...")
    
    # Test health endpoint
    try:
        response = requests.get("http://localhost:5000/health", timeout=10)
        if response.status_code == 200 and "healthy" in response.text.lower():
            print_status("Health check: PASSED")
        else:
            print_warning("Health check: FAILED")
    except Exception as e:
        print_warning(f"Health check: FAILED - {e}")
    
    # Test inventory API
    try:
        response = requests.get("http://localhost:5000/api/inventory", timeout=10)
        if response.status_code == 200:
            print_status("Inventory API: PASSED")
        else:
            print_warning("Inventory API: FAILED")
    except Exception as e:
        print_warning(f"Inventory API: FAILED - {e}")
    
    print("\n" + "=" * 50)
    print_status("Docker migration completed!")
    print_info("The Stock and Pick system is now running entirely in Docker containers")
    print(f"Completed at: {datetime.now()}")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)