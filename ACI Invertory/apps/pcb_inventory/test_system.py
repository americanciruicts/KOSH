#!/usr/bin/env python3

import subprocess
import os
import sys

def test_system():
    print("Testing system access...")
    
    # Test basic commands
    try:
        result = subprocess.run(['ls', '/Users/khashsarrafi/Projects/revestData/migration/stockAndPick'], 
                              capture_output=True, text=True)
        print("Directory listing successful")
        print("Files found:", result.stdout.strip().split('\n'))
    except Exception as e:
        print(f"Directory listing failed: {e}")
        return False
    
    # Test Docker
    try:
        result = subprocess.run(['docker', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Docker available: {result.stdout.strip()}")
        else:
            print("Docker not available")
            return False
    except FileNotFoundError:
        print("Docker command not found")
        return False
    
    # Test Docker Compose
    try:
        result = subprocess.run(['docker-compose', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Docker Compose available: {result.stdout.strip()}")
        else:
            print("Docker Compose not available")
            return False
    except FileNotFoundError:
        print("Docker Compose command not found")
        return False
    
    # Test Docker daemon
    try:
        result = subprocess.run(['docker', 'info'], capture_output=True, text=True)
        if result.returncode == 0:
            print("Docker daemon is running")
        else:
            print("Docker daemon is not running")
            return False
    except Exception as e:
        print(f"Docker daemon check failed: {e}")
        return False
    
    return True

if __name__ == "__main__":
    if test_system():
        print("System tests passed - ready for migration")
        sys.exit(0)
    else:
        print("System tests failed")
        sys.exit(1)