#!/usr/bin/env python3
"""
Simple migration starter to bypass shell issues.
"""

import subprocess
import os
import time

def run_cmd(cmd):
    """Run command and return success."""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, cwd="/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    print("Starting Stock and Pick Migration...")
    
    # Change to correct directory
    os.chdir("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
    
    # Check Docker
    if not run_cmd("docker --version"):
        print("Docker not available")
        return False
    
    # Clean up first
    print("\nCleaning up existing containers...")
    run_cmd("docker-compose down --volumes --remove-orphans")
    time.sleep(2)
    
    # Start PostgreSQL
    print("\nStarting PostgreSQL...")
    if not run_cmd("docker-compose up -d postgres"):
        print("Failed to start PostgreSQL")
        return False
    
    # Wait for PostgreSQL
    print("\nWaiting for PostgreSQL...")
    for i in range(30):
        if run_cmd("docker-compose exec postgres pg_isready -h localhost -p 5432 -U stockpick_user"):
            print("PostgreSQL ready!")
            break
        time.sleep(2)
    else:
        print("PostgreSQL failed to start")
        return False
    
    # Run migration
    print("\nRunning database migration...")
    if not run_cmd("docker-compose --profile migration up --build migration"):
        print("Migration failed")
        return False
    
    # Start web app
    print("\nStarting web application...")
    if not run_cmd("docker-compose up -d --build web_app"):
        print("Web app failed to start")
        return False
    
    # Start pgAdmin
    print("\nStarting pgAdmin...")
    run_cmd("docker-compose up -d pgadmin")
    
    print("\nMigration completed!")
    print("Web app: http://localhost:5000")
    print("pgAdmin: http://localhost:8080")
    
    return True

if __name__ == "__main__":
    main()