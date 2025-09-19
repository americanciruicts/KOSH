#!/usr/bin/env python3
"""
Migrate data from Access database to PostgreSQL using Docker and mdb-tools.
This script runs inside a Docker container with mdb-tools installed.
"""

import os
import subprocess
import tempfile
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
import json
from datetime import datetime

def run_command(cmd, description=""):
    """Run a shell command and return output."""
    print(f"Running: {description}")
    print(f"Command: {cmd}")
    
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print(f"Stderr: {e.stderr}")
        raise

def main():
    print("=== Access Database Migration ===")
    print(f"Started at: {datetime.now()}")
    
    # Database paths
    access_db_path = "/workspace/INVENTORY TABLE.mdb"
    
    # PostgreSQL connection
    pg_config = {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'database': os.getenv('POSTGRES_DB', 'pcb_inventory'),
        'user': os.getenv('POSTGRES_USER', 'stockpick_user'),
        'password': os.getenv('POSTGRES_PASSWORD', 'stockpick_pass')
    }
    
    print("1. Installing mdb-tools...")
    run_command("apt-get update && apt-get install -y mdb-tools", "Install mdb-tools")
    
    print("2. Analyzing Access database...")
    # List tables in the Access database
    tables_output = run_command(f"mdb-tables -1 '{access_db_path}'", "List tables")
    tables = [t.strip() for t in tables_output.split('\n') if t.strip()]
    print(f"Found tables: {tables}")
    
    # Find the inventory table
    inventory_table = None
    for table in tables:
        if 'inventory' in table.lower() or 'pcb' in table.lower():
            inventory_table = table
            break
    
    if not inventory_table:
        print("Looking for any table with data...")
        inventory_table = tables[0] if tables else None
    
    if not inventory_table:
        raise Exception("No suitable table found in Access database")
        
    print(f"Using table: {inventory_table}")
    
    print("3. Extracting data from Access...")
    # Export to CSV
    csv_file = "/tmp/access_data.csv"
    run_command(f"mdb-export '{access_db_path}' '{inventory_table}' > {csv_file}", "Export to CSV")
    
    # Read the CSV to see structure
    with open(csv_file, 'r') as f:
        first_line = f.readline().strip()
        print(f"CSV headers: {first_line}")
        
        # Count lines
        line_count = sum(1 for line in f) + 1  # +1 for header we already read
        print(f"Total rows (including header): {line_count}")
    
    print("4. Connecting to PostgreSQL...")
    conn = psycopg2.connect(**pg_config)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("5. Clearing existing sample data...")
    cursor.execute("DELETE FROM pcb_inventory.tblpcb_inventory WHERE job LIKE '123%' OR job = 'TEST001'")
    conn.commit()
    print("Sample data cleared")
    
    print("6. Loading Access data into PostgreSQL...")
    
    # Read CSV and insert data
    with open(csv_file, 'r') as f:
        csv_reader = csv.DictReader(f)
        headers = csv_reader.fieldnames
        print(f"CSV columns: {headers}")
        
        inserted_count = 0
        errors = []
        
        for row_num, row in enumerate(csv_reader, 1):
            try:
                # Map CSV columns to PostgreSQL columns
                # Assume the Access table has similar structure
                job = row.get('job') or row.get('Job') or row.get('JOB')
                pcb_type = row.get('pcb_type') or row.get('PCB_Type') or row.get('type')
                qty = row.get('qty') or row.get('Qty') or row.get('quantity')
                location = row.get('location') or row.get('Location') or row.get('loc')
                
                # Clean and validate data
                if not job or not pcb_type or not qty or not location:
                    print(f"Skipping row {row_num}: missing required fields")
                    print(f"Row data: {row}")
                    continue
                
                # Clean data
                job = str(job).strip()
                pcb_type = str(pcb_type).strip()
                location = str(location).strip()
                
                try:
                    qty = int(float(qty))
                except (ValueError, TypeError):
                    print(f"Skipping row {row_num}: invalid quantity '{qty}'")
                    continue
                
                # Validate enum values
                valid_pcb_types = ['Bare', 'Partial', 'Completed', 'Ready to Ship']
                if pcb_type not in valid_pcb_types:
                    print(f"Warning: Unknown PCB type '{pcb_type}' in row {row_num}, trying to map...")
                    # Try to map common variations
                    pcb_type_lower = pcb_type.lower()
                    if 'bare' in pcb_type_lower:
                        pcb_type = 'Bare'
                    elif 'partial' in pcb_type_lower:
                        pcb_type = 'Partial'
                    elif 'complete' in pcb_type_lower:
                        pcb_type = 'Completed'
                    elif 'ship' in pcb_type_lower or 'ready' in pcb_type_lower:
                        pcb_type = 'Ready to Ship'
                    else:
                        print(f"Skipping row {row_num}: unmappable PCB type '{pcb_type}'")
                        continue
                
                # Insert into PostgreSQL using the stock_pcb function
                cursor.execute("""
                    SELECT pcb_inventory.stock_pcb(%s, %s, %s, %s)
                """, (job, pcb_type, qty, location))
                
                result = cursor.fetchone()[0]
                if result['success']:
                    inserted_count += 1
                    if inserted_count % 100 == 0:
                        print(f"Processed {inserted_count} records...")
                else:
                    errors.append(f"Row {row_num}: {result.get('message', 'Unknown error')}")
                
            except Exception as e:
                errors.append(f"Row {row_num}: {str(e)}")
                print(f"Error processing row {row_num}: {e}")
        
        conn.commit()
        print(f"Migration completed!")
        print(f"Successfully inserted: {inserted_count} records")
        print(f"Errors: {len(errors)}")
        
        if errors:
            print("First 10 errors:")
            for error in errors[:10]:
                print(f"  - {error}")
    
    print("7. Verifying migration...")
    cursor.execute("SELECT COUNT(*) FROM pcb_inventory.tblpcb_inventory")
    total_count = cursor.fetchone()[0]
    print(f"Total records in PostgreSQL: {total_count}")
    
    # Get sample records
    cursor.execute("SELECT job, pcb_type, qty, location FROM pcb_inventory.tblpcb_inventory LIMIT 5")
    samples = cursor.fetchall()
    print("Sample migrated records:")
    for sample in samples:
        print(f"  {dict(sample)}")
    
    cursor.close()
    conn.close()
    
    print(f"=== Migration Complete at {datetime.now()} ===")
    print(f"Access database: {access_db_path}")
    print(f"PostgreSQL records: {total_count}")

if __name__ == "__main__":
    main()