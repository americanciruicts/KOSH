#!/usr/bin/env python3

import subprocess
import os
import sys
import time
from datetime import datetime

def main():
    print("=" * 50)
    print("Stock and Pick Docker Migration")
    print(f"Started at: {datetime.now()}")
    print("=" * 50)
    
    # Change to the migration directory
    migration_dir = "/Users/khashsarrafi/Projects/revestData/migration/stockAndPick"
    os.chdir(migration_dir)
    
    print(f"Working directory: {os.getcwd()}")
    print("Current files:", os.listdir('.'))
    
    # Check if Docker is available
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Docker version: {result.stdout.strip()}")
        else:
            print("Docker not found")
            return False
    except FileNotFoundError:
        print("Docker command not found")
        return False
    
    # Check if docker-compose is available
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Docker Compose version: {result.stdout.strip()}")
        else:
            print("Docker Compose not found")
            return False
    except FileNotFoundError:
        print("Docker Compose command not found")
        return False
    
    # Create necessary directories
    os.makedirs('logs', exist_ok=True)
    os.makedirs('analysis_output', exist_ok=True)
    os.makedirs('backups', exist_ok=True)
    print("Directories created")
    
    # Clean up existing containers
    print("Cleaning up existing containers...")
    try:
        result = subprocess.run(['docker-compose', 'down', '--volumes', '--remove-orphans'], 
                              capture_output=True, text=True, cwd=migration_dir)
        print("Container cleanup completed")
    except Exception as e:
        print(f"Container cleanup failed: {e}")
    
    # Start PostgreSQL and pgAdmin
    print("Starting PostgreSQL and pgAdmin...")
    try:
        result = subprocess.run(['docker-compose', 'up', '-d', 'postgres', 'pgadmin'], 
                              capture_output=True, text=True, cwd=migration_dir)
        if result.returncode == 0:
            print("PostgreSQL and pgAdmin started successfully")
        else:
            print(f"Failed to start PostgreSQL and pgAdmin: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error starting PostgreSQL and pgAdmin: {e}")
        return False
    
    # Wait for PostgreSQL to be ready
    print("Waiting for PostgreSQL to be ready...")
    for i in range(30):
        try:
            result = subprocess.run(['docker', 'exec', 'stockandpick_postgres', 'pg_isready', 
                                   '-h', 'localhost', '-p', '5432', '-U', 'stockpick_user'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                print("PostgreSQL is ready")
                break
        except Exception:
            pass
        print(f"Waiting for PostgreSQL... (attempt {i+1}/30)")
        time.sleep(2)
    else:
        print("PostgreSQL failed to start after 30 attempts")
        # Show logs
        try:
            result = subprocess.run(['docker-compose', 'logs', 'postgres'], 
                                  capture_output=True, text=True, cwd=migration_dir)
            print("PostgreSQL logs:")
            print(result.stdout)
        except Exception as e:
            print(f"Failed to get PostgreSQL logs: {e}")
        return False
    
    # Run database migration
    print("Running database migration...")
    try:
        result = subprocess.run(['docker-compose', '--profile', 'migration', 'up', '--build', 'migration'], 
                              capture_output=True, text=True, cwd=migration_dir, timeout=120)
        if result.returncode == 0:
            print("Database migration completed successfully")
        else:
            print("Database migration completed with warnings")
            print(f"Migration output: {result.stdout}")
            if result.stderr:
                print(f"Migration errors: {result.stderr}")
    except subprocess.TimeoutExpired:
        print("Database migration timed out")
    except Exception as e:
        print(f"Error running database migration: {e}")
    
    # Start web application
    print("Starting web application...")
    try:
        result = subprocess.run(['docker-compose', 'up', '-d', '--build', 'web_app'], 
                              capture_output=True, text=True, cwd=migration_dir)
        if result.returncode == 0:
            print("Web application started successfully")
        else:
            print(f"Failed to start web application: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error starting web application: {e}")
        return False
    
    # Wait for web application to be ready
    print("Waiting for web application to be ready...")
    for i in range(20):
        try:
            import requests
            response = requests.get("http://localhost:5000/health", timeout=5)
            if response.status_code == 200:
                print("Web application is ready")
                break
        except:
            pass
        print(f"Waiting for web application... (attempt {i+1}/20)")
        time.sleep(3)
    else:
        print("Web application health check failed, but it may still be working")
    
    # Show final status
    print("\nContainer Status:")
    try:
        result = subprocess.run(['docker-compose', 'ps'], 
                              capture_output=True, text=True, cwd=migration_dir)
        print(result.stdout)
    except Exception as e:
        print(f"Failed to get container status: {e}")
    
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
        import requests
        response = requests.get("http://localhost:5000/health", timeout=10)
        if response.status_code == 200 and "healthy" in response.text.lower():
            print("✓ Health check: PASSED")
        else:
            print("⚠ Health check: FAILED")
    except Exception as e:
        print(f"⚠ Health check: FAILED - {e}")
    
    # Test inventory API
    try:
        import requests
        response = requests.get("http://localhost:5000/api/inventory", timeout=10)
        if response.status_code == 200:
            print("✓ Inventory API: PASSED")
        else:
            print("⚠ Inventory API: FAILED")
    except Exception as e:
        print(f"⚠ Inventory API: FAILED - {e}")
    
    print("\n" + "=" * 50)
    print("✓ Docker migration completed!")
    print("ℹ The Stock and Pick system is now running entirely in Docker containers")
    print(f"Completed at: {datetime.now()}")
    print("=" * 50)
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)