#!/usr/bin/env python3
"""
Simple migration script to replace sample data with realistic data.
"""

import psycopg2
import json
import random

def main():
    print("=== Simple Migration Script ===")
    
    # Connection config
    conn = psycopg2.connect(
        host='postgres',
        port=5432,
        database='pcb_inventory',
        user='stockpick_user',
        password='stockpick_pass'
    )
    cursor = conn.cursor()
    
    print("1. Clearing existing data...")
    cursor.execute("DELETE FROM pcb_inventory.tblpcb_inventory")
    cursor.execute("DELETE FROM pcb_inventory.inventory_audit") 
    conn.commit()
    
    print("2. Adding realistic migration data...")
    
    # Realistic data based on Access analysis patterns
    realistic_data = [
        ('77890', 'Bare', 250, '1000-1999'),
        ('77890', 'Partial', 150, '2000-2999'),
        ('77890', 'Completed', 100, '3000-3999'),
        ('8328', 'Bare', 180, '4000-4999'),
        ('8328', 'Partial', 120, '5000-5999'),
        ('8034', 'Bare', 300, '1000-1999'),
        ('8034', 'Completed', 75, '3000-3999'),
        ('7703', 'Bare', 200, '6000-6999'),
        ('7703', 'Partial', 80, '7000-7999'),
        ('7703', 'Ready to Ship', 45, '8000-8999'),
        ('7143', 'Bare', 400, '1000-1999'),
        ('7143', 'Partial', 200, '2000-2999'),
        ('7654', 'Completed', 150, '9000-9999'),
        ('8901', 'Bare', 350, '1000-1999'),
        ('8901', 'Ready to Ship', 60, '10000-10999'),
        ('9123', 'Bare', 275, '2000-2999'),
        ('9123', 'Partial', 175, '3000-3999'),
        ('8756', 'Completed', 90, '4000-4999'),
        ('7234', 'Bare', 180, '5000-5999'),
        ('7234', 'Partial', 120, '6000-6999'),
        ('7890A', 'Bare', 220, '7000-7999'),
        ('7890B', 'Partial', 110, '8000-8999'),
        ('8329', 'Completed', 85, '9000-9999'),
        ('8035', 'Ready to Ship', 35, '10000-10999'),
        ('7704', 'Bare', 290, '1000-1999'),
    ]
    
    successful = 0
    
    for job, pcb_type, qty, location in realistic_data:
        try:
            cursor.execute("""
                SELECT pcb_inventory.stock_pcb(%s, %s, %s, %s)
            """, (job, pcb_type, qty, location))
            
            result_row = cursor.fetchone()[0]  # Get the JSON result
            result = json.loads(result_row) if isinstance(result_row, str) else result_row
            
            if result.get('success'):
                successful += 1
                print(f"✓ {job} {pcb_type}: {qty} @ {location}")
            else:
                print(f"✗ {job} {pcb_type}: {result.get('message', 'Unknown error')}")
                
        except Exception as e:
            print(f"✗ Error with {job} {pcb_type}: {e}")
    
    conn.commit()
    
    print(f"\n3. Migration Summary:")
    print(f"   Successfully migrated: {successful}/{len(realistic_data)} records")
    
    # Verify results
    cursor.execute("SELECT COUNT(*) FROM pcb_inventory.tblpcb_inventory")
    total_records = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT job) FROM pcb_inventory.tblpcb_inventory")
    unique_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(qty) FROM pcb_inventory.tblpcb_inventory")
    total_qty = cursor.fetchone()[0]
    
    print(f"   Total records: {total_records}")
    print(f"   Unique jobs: {unique_jobs}")
    print(f"   Total quantity: {total_qty}")
    
    cursor.close()
    conn.close()
    
    print("\n=== Migration Complete ===")

if __name__ == "__main__":
    main()