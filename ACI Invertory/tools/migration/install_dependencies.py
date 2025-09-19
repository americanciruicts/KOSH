#!/usr/bin/env python3
"""
Installation script for Access to PostgreSQL migration dependencies.
This script checks and installs required dependencies for the migration tool.
"""

import subprocess
import sys
import os
import platform

def run_command(command, description):
    """Run a command and handle errors."""
    print(f"Running: {description}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed:")
        print(f"  Command: {command}")
        print(f"  Error: {e.stderr}")
        return False

def check_python_version():
    """Check Python version."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("✗ Python 3.8 or higher is required")
        print(f"  Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    
    print(f"✓ Python {version.major}.{version.minor}.{version.micro} is supported")
    return True

def install_python_dependencies():
    """Install Python dependencies."""
    print("Installing Python dependencies...")
    
    # Install from requirements.txt
    success = run_command(
        f"{sys.executable} -m pip install -r requirements.txt",
        "Installing Python packages"
    )
    
    if not success:
        print("Trying to install individual packages...")
        
        # Core packages
        packages = [
            "psycopg2-binary",
            "sqlalchemy",
            "pandas",
            "numpy",
            "click",
            "tqdm",
            "tabulate",
            "python-dotenv",
            "openpyxl",
            "xlsxwriter",
            "alembic"
        ]
        
        all_success = True
        for package in packages:
            if not run_command(f"{sys.executable} -m pip install {package}", f"Installing {package}"):
                all_success = False
        
        return all_success
    
    return success

def install_system_dependencies():
    """Install system dependencies based on platform."""
    system = platform.system().lower()
    
    if system == "linux":
        # Ubuntu/Debian
        if os.path.exists("/etc/debian_version"):
            print("Detected Debian/Ubuntu system")
            commands = [
                "sudo apt-get update",
                "sudo apt-get install -y mdb-tools",
                "sudo apt-get install -y unixodbc-dev",
                "sudo apt-get install -y python3-dev",
                "sudo apt-get install -y build-essential"
            ]
        
        # CentOS/RHEL/Fedora
        elif os.path.exists("/etc/redhat-release"):
            print("Detected RedHat/CentOS/Fedora system")
            commands = [
                "sudo yum install -y mdb-tools",
                "sudo yum install -y unixODBC-devel",
                "sudo yum install -y python3-devel",
                "sudo yum groupinstall -y 'Development Tools'"
            ]
        
        else:
            print("⚠ Unknown Linux distribution. You may need to install mdb-tools manually.")
            return True
        
        for cmd in commands:
            if not run_command(cmd, f"Running: {cmd}"):
                print(f"⚠ Failed to run: {cmd}")
                print("  You may need to install mdb-tools manually")
    
    elif system == "darwin":  # macOS
        print("Detected macOS system")
        
        # Check if Homebrew is installed
        if subprocess.run("which brew", shell=True, capture_output=True).returncode != 0:
            print("⚠ Homebrew not found. Please install Homebrew first:")
            print("  /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
            return False
        
        commands = [
            "brew install mdb-tools",
            "brew install unixodbc"
        ]
        
        for cmd in commands:
            if not run_command(cmd, f"Running: {cmd}"):
                print(f"⚠ Failed to run: {cmd}")
    
    elif system == "windows":
        print("Detected Windows system")
        print("✓ Windows should have built-in ODBC support for Access databases")
        
        # Install pyodbc specifically for Windows
        if not run_command(f"{sys.executable} -m pip install pyodbc", "Installing pyodbc for Windows"):
            print("⚠ Failed to install pyodbc. You may need to install Microsoft Visual C++ Build Tools")
    
    else:
        print(f"⚠ Unknown operating system: {system}")
        print("  You may need to install ODBC drivers manually")
    
    return True

def install_postgresql_client():
    """Install PostgreSQL client tools."""
    system = platform.system().lower()
    
    if system == "linux":
        if os.path.exists("/etc/debian_version"):
            run_command("sudo apt-get install -y postgresql-client", "Installing PostgreSQL client")
        elif os.path.exists("/etc/redhat-release"):
            run_command("sudo yum install -y postgresql", "Installing PostgreSQL client")
    
    elif system == "darwin":
        run_command("brew install postgresql", "Installing PostgreSQL client")
    
    elif system == "windows":
        print("For Windows, please download and install PostgreSQL client from:")
        print("  https://www.postgresql.org/download/windows/")
    
    return True

def create_virtual_environment():
    """Create a virtual environment for the migration tool."""
    venv_path = "venv"
    
    if os.path.exists(venv_path):
        print(f"✓ Virtual environment already exists at {venv_path}")
        return True
    
    print("Creating virtual environment...")
    
    if run_command(f"{sys.executable} -m venv {venv_path}", "Creating virtual environment"):
        print(f"✓ Virtual environment created at {venv_path}")
        print("To activate the virtual environment:")
        
        if platform.system().lower() == "windows":
            print(f"  {venv_path}\\Scripts\\activate.bat")
        else:
            print(f"  source {venv_path}/bin/activate")
        
        return True
    
    return False

def main():
    """Main installation function."""
    print("="*60)
    print("ACCESS TO POSTGRESQL MIGRATION TOOL SETUP")
    print("="*60)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Create virtual environment
    create_virtual_environment()
    
    # Install system dependencies
    print("\\nInstalling system dependencies...")
    install_system_dependencies()
    
    # Install Python dependencies
    print("\\nInstalling Python dependencies...")
    if not install_python_dependencies():
        print("⚠ Some Python packages failed to install. Please check the errors above.")
    
    # Install PostgreSQL client
    print("\\nInstalling PostgreSQL client...")
    install_postgresql_client()
    
    print("\\n" + "="*60)
    print("SETUP COMPLETE")
    print("="*60)
    
    print("Next steps:")
    print("1. Place your Access database file (.mdb or .accdb) in the migration folder")
    print("2. Copy .env.example to .env and configure your database settings")
    print("3. Run the migration tool:")
    print("   python migrate_cli.py --help")
    print("\\nExamples:")
    print("   python migrate_cli.py analyze database.mdb")
    print("   python migrate_cli.py migrate-all database.mdb --pg-database mydb")
    
    print("\\nFor detailed instructions, see README.md")

if __name__ == "__main__":
    main()