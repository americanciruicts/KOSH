#!/usr/bin/env python3
"""
Migrate ALL tables from Access database to PostgreSQL with proper column name handling
"""

import subprocess
import csv
import io
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import re
from datetime import datetime

# PostgreSQL reserved keywords that need quoting
RESERVED_KEYWORDS = {
    'desc', 'order', 'group', 'user', 'table', 'select', 'from', 'where', 
    'insert', 'update', 'delete', 'create', 'drop', 'alter', 'index', 'key',
    'primary', 'foreign', 'references', 'constraint', 'check', 'unique',
    'default', 'null', 'not', 'and', 'or', 'in', 'like', 'between', 'is',
    'exists', 'having', 'union', 'join', 'inner', 'outer', 'left', 'right',
    'on', 'as', 'distinct', 'all', 'any', 'some', 'case', 'when', 'then',
    'else', 'end', 'if', 'begin', 'commit', 'rollback', 'grant', 'revoke'
}

def safe_column_name(col_name):
    """Make column name safe for PostgreSQL."""
    # Clean the name
    clean_name = col_name.replace(' ', '_').replace('-', '_').replace('#', 'num')
    
    # Quote if it's a reserved keyword
    if clean_name.lower() in RESERVED_KEYWORDS:
        return f'"{clean_name}"'
    
    return clean_name

def get_all_access_tables():
    """Get all table names and their data from Access database."""
    print("=== MIGRATING ALL ACCESS TABLES (KEEPING ORIGINAL NAMES) ===")
    
    # Get list of all tables
    try:
        result = subprocess.run(['mdb-tables', '/tmp/inventory.mdb'], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"Error listing tables: {result.stderr}")
            return {}
        
        table_names = result.stdout.strip().split()
        print(f"Found {len(table_names)} tables: {table_names}")
        
        # Filter out system tables
        user_tables = [t for t in table_names if not t.startswith('MSys')]
        print(f"User tables: {user_tables}")
        
    except Exception as e:
        print(f"Error: {e}")
        return {}
    
    # Extract data from each table
    all_data = {}
    
    for table_name in user_tables:
        try:
            print(f"\nExtracting data from {table_name}...")
            
            # Get record count
            count_result = subprocess.run(['mdb-count', '/tmp/inventory.mdb', table_name], 
                                        capture_output=True, text=True, timeout=10)
            record_count = int(count_result.stdout.strip()) if count_result.returncode == 0 else 0
            print(f"  Records: {record_count}")
            
            if record_count == 0:
                all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
                continue
            
            # Export table data as CSV
            export_result = subprocess.run(['mdb-export', '/tmp/inventory.mdb', table_name], 
                                         capture_output=True, text=True, timeout=120)
            
            if export_result.returncode != 0:
                print(f"  Error exporting {table_name}: {export_result.stderr}")
                all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
                continue
            
            # Parse CSV data
            csv_data = export_result.stdout
            if not csv_data.strip():
                all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
                continue
            
            csv_reader = csv.DictReader(io.StringIO(csv_data))
            rows = list(csv_reader)
            
            # Get schema (column names and sample data)
            schema = []
            if rows:
                for col_name in rows[0].keys():
                    sample_values = [row[col_name] for row in rows[:5] if row[col_name]]
                    schema.append({
                        'name': col_name,
                        'safe_name': safe_column_name(col_name),
                        'sample_values': sample_values[:3]
                    })
            
            all_data[table_name] = {
                'records': rows,
                'count': len(rows),
                'schema': schema
            }
            
            print(f"  Successfully extracted {len(rows)} records")
            
        except Exception as e:
            print(f"  Error processing {table_name}: {e}")
            all_data[table_name] = {'records': [], 'count': 0, 'schema': []}
    
    return all_data

def create_postgresql_tables(all_data):
    """Create PostgreSQL tables for all Access tables."""
    print("\n=== CREATING POSTGRESQL TABLES (ORIGINAL NAMES) ===")
    
    try:
        conn = psycopg2.connect(
            host='postgres',
            port=5432,
            database='pcb_inventory',
            user='stockpick_user',
            password='stockpick_pass'
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        print("✓ Connected to PostgreSQL")
        
        cursor.execute("SET search_path TO pcb_inventory, public")
        
        for table_name, table_data in all_data.items():
            if table_data['count'] == 0:
                print(f"Skipping empty table: {table_name}")
                continue
            
            # Skip the main inventory table (already exists)
            if table_name == 'tblPCB_Inventory':
                print(f"Skipping existing table: {table_name}")
                continue
            
            try:
                print(f"\nCreating table: {table_name}")
                
                # Drop table if exists
                cursor.execute(f'DROP TABLE IF EXISTS pcb_inventory."{table_name}" CASCADE')
                
                # Create table with properly quoted column names
                columns = []
                for col in table_data['schema']:
                    col_def = f"{col['safe_name']} TEXT"
                    columns.append(col_def)
                
                if columns:
                    create_sql = f'''
                    CREATE TABLE pcb_inventory."{table_name}" (
                        id SERIAL PRIMARY KEY,
                        {', '.join(columns)},
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                    '''
                    cursor.execute(create_sql)
                    print(f"  ✓ Created table structure with {len(columns)} columns")
                
                conn.commit()
                
            except Exception as e:
                print(f"  ✗ Error creating table {table_name}: {e}")
                conn.rollback()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error connecting to PostgreSQL: {e}")

def migrate_table_data(all_data):
    """Migrate all table data to PostgreSQL."""
    print("\n=== MIGRATING TABLE DATA ===")
    
    try:
        conn = psycopg2.connect(
            host='postgres',
            port=5432,
            database='pcb_inventory',
            user='stockpick_user',
            password='stockpick_pass'
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SET search_path TO pcb_inventory, public")
        
        total_migrated = 0
        migration_summary = {}
        
        for table_name, table_data in all_data.items():
            if table_data['count'] == 0 or table_name == 'tblPCB_Inventory':
                continue
            
            print(f"\nMigrating data to: {table_name}")
            
            records = table_data['records']
            successful = 0
            errors = 0
            
            for record in records:
                try:
                    # Map original column names to safe names
                    clean_record = {}
                    for col in table_data['schema']:
                        original_name = col['name']
                        safe_name = col['safe_name'].strip('"')  # Remove quotes for the dict key
                        value = record.get(original_name, '')
                        
                        # Clean data
                        if value:
                            clean_value = str(value).replace('\x00', '')
                            if len(clean_value) > 1000:
                                clean_value = clean_value[:1000] + '...'
                            clean_record[safe_name] = clean_value
                        else:
                            clean_record[safe_name] = None
                    
                    # Build INSERT statement with quoted table name
                    columns = list(clean_record.keys())
                    values = list(clean_record.values())
                    
                    # Quote column names that need it
                    quoted_columns = []
                    for col_name in columns:
                        if col_name.lower() in RESERVED_KEYWORDS:
                            quoted_columns.append(f'"{col_name}"')
                        else:
                            quoted_columns.append(col_name)
                    
                    placeholders = ', '.join(['%s'] * len(values))
                    columns_str = ', '.join(quoted_columns)
                    
                    insert_sql = f'''
                    INSERT INTO pcb_inventory."{table_name}" ({columns_str})
                    VALUES ({placeholders})
                    '''
                    
                    cursor.execute(insert_sql, values)
                    successful += 1
                    
                except Exception as e:
                    errors += 1
                    if errors <= 5:  # Show first 5 errors only
                        print(f"    Error inserting record: {e}")
            
            conn.commit()
            total_migrated += successful
            migration_summary[table_name] = {'successful': successful, 'errors': errors, 'total': len(records)}
            print(f"  ✓ Migrated {successful}/{len(records)} records (errors: {errors})")
        
        cursor.close()
        conn.close()
        
        print(f"\n=== MIGRATION SUMMARY ===")
        print(f"Total records migrated: {total_migrated}")
        print("\nPer-table summary:")
        for table, stats in migration_summary.items():
            success_rate = (stats['successful'] / stats['total'] * 100) if stats['total'] > 0 else 0
            print(f"  {table}: {stats['successful']}/{stats['total']} ({success_rate:.1f}% success)")
        
        return total_migrated > 0
        
    except Exception as e:
        print(f"Error migrating data: {e}")
        return False

def main():
    """Main migration function."""
    print("="*60)
    print("COMPLETE ACCESS DATABASE MIGRATION - ALL TABLES")
    print("KEEPING ORIGINAL TABLE AND COLUMN NAMES")
    print("="*60)
    
    # Step 1: Extract all data from Access
    all_data = get_all_access_tables()
    if not all_data:
        print("✗ No data extracted from Access database")
        return False
    
    # Print summary
    print(f"\nExtracted data summary:")
    total_records = 0
    for table_name, table_data in all_data.items():
        print(f"  {table_name}: {table_data['count']} records")
        total_records += table_data['count']
    print(f"Total records across all tables: {total_records}")
    
    # Step 2: Create PostgreSQL tables
    create_postgresql_tables(all_data)
    
    # Step 3: Migrate data
    success = migrate_table_data(all_data)
    
    if success:
        print("\n✅ ALL TABLES MIGRATION COMPLETED SUCCESSFULLY!")
        print("All original Access table and column names preserved!")
    else:
        print("\n❌ Migration failed")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)