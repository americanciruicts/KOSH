#!/usr/bin/env python3
"""
Python script to run the minimal test and diagnose the issue.
"""

import subprocess
import os
import time
import json

def run_cmd(cmd, description=""):
    """Run command and return result."""
    print(f"\n{'='*50}")
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*50)
    
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            capture_output=True, 
            text=True,
            cwd="/Users/khashsarrafi/Projects/revestData/migration/stockAndPick"
        )
        
        print("STDOUT:")
        print(result.stdout)
        
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
            
        print(f"Return code: {result.returncode}")
        return result.returncode == 0, result.stdout, result.stderr
        
    except Exception as e:
        print(f"Error: {e}")
        return False, "", str(e)

def main():
    print("Starting minimal test diagnosis...")
    
    # Change directory
    os.chdir("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
    
    # Stop current web app
    run_cmd("docker-compose stop web_app", "Stop current web app")
    
    # Remove test container if exists
    run_cmd("docker rm -f stockandpick_test", "Remove existing test container")
    
    # Build test app
    success, stdout, stderr = run_cmd(
        "docker build -f web_app/Dockerfile.test -t stockandpick-test web_app/",
        "Build test app"
    )
    
    if not success:
        print("❌ Failed to build test app")
        return False
    
    # Run test app
    success, stdout, stderr = run_cmd(
        """docker run -d \
          --name stockandpick_test \
          --network stockandpick_stockpick-network \
          -p 5001:5000 \
          -e POSTGRES_HOST=postgres \
          -e POSTGRES_PORT=5432 \
          -e POSTGRES_DB=pcb_inventory \
          -e POSTGRES_USER=stockpick_user \
          -e POSTGRES_PASSWORD=stockpick_pass \
          stockandpick-test""",
        "Run test app"
    )
    
    if not success:
        print("❌ Failed to start test app")
        return False
    
    # Wait for startup
    print("Waiting 10 seconds for app to start...")
    time.sleep(10)
    
    # Test endpoints
    print("\n🧪 Testing endpoints...")
    
    # Basic test
    success, stdout, stderr = run_cmd("curl -s http://localhost:5001/", "Basic endpoint test")
    if success and stdout:
        try:
            data = json.loads(stdout)
            print("✅ Basic endpoint working!")
            print(f"Status: {data.get('status')}")
        except:
            print("⚠️ Response not JSON:", stdout)
    
    # Health check
    success, stdout, stderr = run_cmd("curl -s http://localhost:5001/health", "Health check test")
    if success and stdout:
        try:
            data = json.loads(stdout)
            print("✅ Health check working!")
            print(f"Database status: {data.get('database')}")
            print(f"Inventory count: {data.get('inventory_count')}")
        except:
            print("⚠️ Health response not JSON:", stdout)
    
    # Database test
    success, stdout, stderr = run_cmd("curl -s http://localhost:5001/test-db", "Database test")
    if success and stdout:
        try:
            data = json.loads(stdout)
            print("✅ Database test working!")
            print(f"PostgreSQL: {data.get('postgres_version', 'Unknown')[:50]}...")
        except:
            print("⚠️ DB response not JSON:", stdout)
    
    # Show logs
    print("\n📋 Container logs:")
    run_cmd("docker logs stockandpick_test", "Show test container logs")
    
    print("\n" + "="*60)
    print("DIAGNOSIS COMPLETE")
    print("="*60)
    print("If the test app works, the issue is in the main Flask app.")
    print("If the test app fails, the issue is environmental.")
    print("Try accessing: http://localhost:5001")
    
    return True

if __name__ == "__main__":
    main()