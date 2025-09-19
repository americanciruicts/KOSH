#!/usr/bin/env python3
"""Check Docker availability and start services if possible."""

import subprocess
import sys
import time
import os

def run_command(cmd, description):
    """Run a command and return success status."""
    print(f"Running: {description}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print(f"✓ {description} - Success")
            return True, result.stdout
        else:
            print(f"✗ {description} - Failed")
            print(f"Error: {result.stderr}")
            return False, result.stderr
    except subprocess.TimeoutExpired:
        print(f"✗ {description} - Timeout")
        return False, "Command timed out"
    except Exception as e:
        print(f"✗ {description} - Error: {e}")
        return False, str(e)

def check_docker():
    """Check if Docker is available."""
    print("Checking Docker availability...")
    
    # Check if Docker is installed
    success, output = run_command("docker --version", "Docker version check")
    if not success:
        print("Docker is not installed or not in PATH")
        return False
    
    print(f"Docker version: {output.strip()}")
    
    # Check if Docker daemon is running
    success, output = run_command("docker ps", "Docker daemon check")
    if not success:
        print("Docker daemon is not running")
        return False
    
    print("Docker is available and running")
    return True

def start_services():
    """Start Docker services for the migration."""
    print("Starting PostgreSQL and pgAdmin services...")
    
    # Change to the stockAndPick directory
    os.chdir("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
    
    # Stop any existing services
    run_command("docker-compose down", "Stopping existing services")
    
    # Start services
    success, output = run_command("docker-compose up -d", "Starting Docker services")
    if not success:
        print("Failed to start Docker services")
        return False
    
    # Wait for services to be ready
    print("Waiting for services to start...")
    time.sleep(10)
    
    # Check if services are running
    success, output = run_command("docker-compose ps", "Checking service status")
    if success:
        print("Service status:")
        print(output)
    
    # Test PostgreSQL connection
    print("Testing PostgreSQL connection...")
    success, output = run_command(
        "docker exec stockandpick_postgres pg_isready -h localhost -p 5432 -U stockpick_user",
        "PostgreSQL connection test"
    )
    
    if success:
        print("✓ PostgreSQL is ready")
        return True
    else:
        print("✗ PostgreSQL is not ready")
        return False

def main():
    """Main function."""
    print("="*60)
    print("DOCKER ENVIRONMENT SETUP")
    print("="*60)
    
    if not check_docker():
        print("\\nDocker is not available. Please install Docker and try again.")
        print("Download Docker from: https://www.docker.com/products/docker-desktop")
        return False
    
    if not start_services():
        print("\\nFailed to start Docker services.")
        return False
    
    print("\\n" + "="*60)
    print("DOCKER SERVICES STARTED SUCCESSFULLY")
    print("="*60)
    print("PostgreSQL: localhost:5432")
    print("  Database: pcb_inventory")
    print("  User: stockpick_user")
    print("  Password: stockpick_pass")
    print("\\npgAdmin: http://localhost:8080")
    print("  Email: admin@stockandpick.com")
    print("  Password: admin123")
    print("\\nReady for migration!")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)