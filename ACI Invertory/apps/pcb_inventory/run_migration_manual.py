#!/usr/bin/env python3
"""
Manual migration runner - simplified version to work around shell issues
"""
import os
import sys
import subprocess
import json
from pathlib import Path

# Change to migration directory
migration_dir = Path("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
os.chdir(migration_dir)

def run_cmd(cmd, description):
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        print(f"Exit code: {result.returncode}")
        if result.stdout:
            print(f"Output: {result.stdout}")
        if result.stderr:
            print(f"Error: {result.stderr}")
        return result.returncode == 0
    except Exception as e:
        print(f"Exception: {e}")
        return False

print("="*60)
print("STOCK AND PICK MIGRATION - MANUAL EXECUTION")
print("="*60)

# Step 1: Check Docker
print("\n1. Checking Docker...")
if not run_cmd("docker --version", "Docker version check"):
    print("ERROR: Docker not available")
    sys.exit(1)

# Step 2: Stop existing containers
print("\n2. Stopping existing containers...")
run_cmd("docker-compose down", "Stop containers")

# Step 3: Start PostgreSQL
print("\n3. Starting PostgreSQL...")
if not run_cmd("docker-compose up -d postgres", "Start PostgreSQL"):
    print("ERROR: Failed to start PostgreSQL")
    sys.exit(1)

# Step 4: Wait for PostgreSQL
print("\n4. Waiting for PostgreSQL...")
import time
time.sleep(10)

# Step 5: Check PostgreSQL readiness
print("\n5. Checking PostgreSQL readiness...")
for i in range(10):
    if run_cmd("docker exec stockandpick_postgres pg_isready -h localhost -p 5432 -U stockpick_user", f"PostgreSQL ready check {i+1}"):
        print("PostgreSQL is ready!")
        break
    time.sleep(2)
else:
    print("WARNING: PostgreSQL may not be ready")

# Step 6: Apply schema
print("\n6. Applying database schema...")
schema_file = migration_dir / "analysis_output" / "postgresql_schema.sql"
if schema_file.exists():
    cmd = f"docker exec -i stockandpick_postgres psql -U stockpick_user -d pcb_inventory < {schema_file}"
    run_cmd(cmd, "Apply schema")
else:
    print(f"WARNING: Schema file not found: {schema_file}")

# Step 7: Start pgAdmin
print("\n7. Starting pgAdmin...")
run_cmd("docker-compose up -d pgadmin", "Start pgAdmin")

# Step 8: Run database analysis
print("\n8. Running database analysis...")
run_cmd("python3 analyze_db.py", "Database analysis")

# Step 9: Test database connection
print("\n9. Testing database connection...")
run_cmd("docker exec stockandpick_postgres psql -U stockpick_user -d pcb_inventory -c \"SELECT COUNT(*) FROM pcb_inventory.tblPCB_Inventory;\"", "Test database")

# Step 10: Start web app
print("\n10. Starting web application...")
web_dir = migration_dir / "web_app"
if web_dir.exists():
    os.chdir(web_dir)
    run_cmd("python3 app.py &", "Start web app")
    os.chdir(migration_dir)

print("\n" + "="*60)
print("MIGRATION COMPLETE!")
print("="*60)
print("PostgreSQL: localhost:5432 (pcb_inventory)")
print("pgAdmin: http://localhost:8080")
print("Web App: http://localhost:5000")
print("="*60)