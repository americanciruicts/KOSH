# Access Database to PostgreSQL Migration

This folder contains tools and scripts to migrate Microsoft Access databases to PostgreSQL.

## Migration Options

### Option 1: Using MDB Tools (Linux/Mac)
- Extract data from .mdb/.accdb files
- Convert to CSV/SQL format
- Import into PostgreSQL

### Option 2: Using Python Libraries
- Use `pyodbc` with Access ODBC driver
- Use `pandas` for data manipulation
- Use `sqlalchemy` for PostgreSQL connection

### Option 3: Using Access Export
- Export tables to CSV from Access
- Use migration scripts to import to PostgreSQL

## Files

- `access_analyzer.py` - Analyze Access database structure
- `schema_converter.py` - Convert Access schema to PostgreSQL
- `data_migrator.py` - Migrate data from Access to PostgreSQL
- `migration_config.py` - Configuration settings
- `requirements.txt` - Python dependencies

## Usage

1. Place your Access database (.mdb or .accdb) in this folder
2. Run the analyzer to understand the database structure
3. Use the schema converter to create PostgreSQL tables
4. Run the data migrator to transfer data

## Prerequisites

- Python 3.8+
- PostgreSQL database
- Access database file
- ODBC driver for Access (Windows) or MDB Tools (Linux/Mac)