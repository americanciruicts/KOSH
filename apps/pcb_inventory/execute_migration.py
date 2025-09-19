#!/usr/bin/env python3
"""
Python-based migration executor for Stock and Pick system.
This can be run when shell scripts have issues.
"""

import subprocess
import sys
import time
import os
from datetime import datetime

def run_command(cmd, description, timeout=300):
    """Run a command and return result."""
    print(f"🔄 {description}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True, 
            timeout=timeout
        )
        
        if result.returncode == 0:
            print(f"✅ {description} - SUCCESS")
            if result.stdout.strip():
                print(f"   Output: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ {description} - FAILED")
            if result.stderr.strip():
                print(f"   Error: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"⏰ {description} - TIMEOUT")
        return False
    except Exception as e:
        print(f"💥 {description} - EXCEPTION: {e}")
        return False

def main():
    """Execute the complete migration."""
    print("=" * 60)
    print("STOCK AND PICK DOCKER MIGRATION")
    print("=" * 60)
    print(f"Start Time: {datetime.now()}")
    print()
    
    # Change to correct directory
    migration_dir = "/Users/khashsarrafi/Projects/revestData/migration/stockAndPick"
    os.chdir(migration_dir)
    print(f"📁 Working Directory: {migration_dir}")
    
    # Check Docker
    if not run_command("docker --version", "Check Docker installation"):
        print("❌ Docker is not available. Please install Docker and try again.")
        return False
    
    if not run_command("docker info", "Check Docker daemon"):
        print("❌ Docker daemon is not running. Please start Docker and try again.")
        return False
    
    # Phase 1: Clean up and start infrastructure
    print("\n🚀 PHASE 1: INFRASTRUCTURE SETUP")
    print("-" * 40)
    
    run_command("docker-compose down --volumes --remove-orphans", "Clean up existing containers")
    time.sleep(2)
    
    run_command("mkdir -p logs analysis_output backups", "Create directories")
    
    if not run_command("docker-compose up -d postgres pgadmin", "Start PostgreSQL and pgAdmin"):
        print("❌ Failed to start infrastructure")
        return False
    
    # Wait for PostgreSQL
    print("\n⏳ Waiting for PostgreSQL to be ready...")
    for i in range(30):
        if run_command(
            "docker exec stockandpick_postgres pg_isready -h localhost -p 5432 -U stockpick_user",
            f"PostgreSQL readiness check (attempt {i+1}/30)"
        ):
            print("✅ PostgreSQL is ready!")
            break
        time.sleep(2)
    else:
        print("❌ PostgreSQL failed to start")
        run_command("docker-compose logs postgres", "Show PostgreSQL logs")
        return False
    
    # Phase 2: Database migration
    print("\n🗄️ PHASE 2: DATABASE MIGRATION")
    print("-" * 40)
    
    if not run_command("docker-compose --profile migration up --build migration", "Run database migration"):
        print("❌ Database migration failed")
        run_command("docker-compose logs migration", "Show migration logs")
        return False
    
    # Phase 3: Web application
    print("\n🌐 PHASE 3: WEB APPLICATION")
    print("-" * 40)
    
    if not run_command("docker-compose up -d --build web_app", "Start web application"):
        print("❌ Web application failed to start")
        run_command("docker-compose logs web_app", "Show web app logs")
        return False
    
    # Wait for web app
    print("\n⏳ Waiting for web application to be ready...")
    for i in range(20):
        if run_command("curl -f http://localhost:5000/health", f"Web app health check (attempt {i+1}/20)"):
            print("✅ Web application is ready!")
            break
        time.sleep(3)
    else:
        print("⚠️ Web application health check failed, but it may still be working")
    
    # Phase 4: Validation
    print("\n🔍 PHASE 4: VALIDATION")
    print("-" * 40)
    
    run_command("docker-compose ps", "Show container status")
    
    # Test endpoints
    run_command("curl -s http://localhost:5000/health", "Test health endpoint")
    run_command("curl -s http://localhost:5000/api/inventory", "Test inventory API")
    
    # Final status
    print("\n" + "=" * 60)
    print("🎉 MIGRATION COMPLETED!")
    print("=" * 60)
    print(f"End Time: {datetime.now()}")
    print()
    print("📍 ACCESS URLS:")
    print("• Web Application: http://localhost:5000")
    print("• pgAdmin: http://localhost:8080")
    print("  - Email: admin@stockandpick.com")
    print("  - Password: admin123")
    print("• PostgreSQL: localhost:5432")
    print("  - Database: pcb_inventory")
    print("  - User: stockpick_user")
    print("  - Password: stockpick_pass")
    print()
    print("🧪 TEST COMMANDS:")
    print("curl http://localhost:5000/health")
    print("curl http://localhost:5000/api/inventory")
    print("docker-compose ps")
    print("docker-compose logs web_app")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)