#!/usr/bin/env python3
"""
Check Docker container status for troubleshooting.
"""

import subprocess
import os

def run_cmd(cmd):
    """Run command and show output."""
    print(f"\n{'='*50}")
    print(f"Command: {cmd}")
    print('='*50)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, 
                              cwd="/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
        print("STDOUT:")
        print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        print(f"Return code: {result.returncode}")
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    print("Docker Status Check for Stock and Pick Migration")
    
    os.chdir("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
    
    # Check Docker
    run_cmd("docker --version")
    run_cmd("docker info")
    
    # Check containers
    run_cmd("docker-compose ps")
    
    # Check images
    run_cmd("docker images | grep stockandpick")
    
    # Check networks
    run_cmd("docker network ls | grep stockandpick")
    
    # Check volumes
    run_cmd("docker volume ls | grep stockandpick")
    
    # Check logs
    print("\nContainer Logs:")
    run_cmd("docker-compose logs --tail=20 postgres")
    run_cmd("docker-compose logs --tail=20 web_app")
    run_cmd("docker-compose logs --tail=20 migration")
    
    # Test connections
    print("\nConnection Tests:")
    run_cmd("curl -v http://localhost:5000/health")
    run_cmd("curl -v http://localhost:8080")

if __name__ == "__main__":
    main()