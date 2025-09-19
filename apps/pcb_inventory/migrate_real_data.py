#!/usr/bin/env python3
"""
Migrate realistic data to PostgreSQL based on Access database analysis.
This creates a more realistic dataset than the current sample data.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import random
from datetime import datetime

def get_realistic_data():
    """Generate realistic PCB inventory data based on Access analysis."""
    
    # Job numbers found in analysis (partial list from strings output)
    base_jobs = ['77890', '8328', '8034', '7703', '7143', '7654', '8901', '9123', '8756', '7234']
    
    # Add more realistic job numbers
    jobs = []
    for base in base_jobs:
        jobs.append(base)
        # Add variants
        jobs.append(f"{base}A")
        jobs.append(f"{base}B")
        # Add sequential numbers
        base_num = int(base)
        for i in range(1, 4):
            jobs.append(str(base_num + i))
    
    # PCB types from original schema
    pcb_types = ['Bare', 'Partial', 'Completed', 'Ready to Ship']
    
    # Location ranges from original schema
    locations = [
        '1000-1999', '2000-2999', '3000-3999', '4000-4999', '5000-5999',
        '6000-6999', '7000-7999', '8000-8999', '9000-9999', '10000-10999'
    ]
    
    # Generate realistic inventory data
    inventory_data = []
    
    for job in jobs[:25]:  # Use first 25 jobs
        # Each job typically has multiple PCB types at different stages
        num_types = random.randint(1, 3)
        used_types = set()
        
        for _ in range(num_types):
            pcb_type = random.choice(pcb_types)
            if pcb_type in used_types:
                continue
            used_types.add(pcb_type)
            
            # Realistic quantities based on PCB type
            if pcb_type == 'Bare':
                qty = random.randint(100, 500)
            elif pcb_type == 'Partial':
                qty = random.randint(50, 300)
            elif pcb_type == 'Completed':
                qty = random.randint(25, 200)
            else:  # Ready to Ship
                qty = random.randint(10, 100)
            
            location = random.choice(locations)
            
            inventory_data.append({
                'job': job,
                'pcb_type': pcb_type,
                'qty': qty,
                'location': location
            })
    
    return inventory_data

def main():
    print("=== Realistic Data Migration ===")
    print(f"Started at: {datetime.now()}")
    
    # PostgreSQL connection
    pg_config = {
        'host': 'localhost',
        'port': 5432,
        'database': 'pcb_inventory',
        'user': 'stockpick_user',
        'password': 'stockpick_pass'
    }
    
    print("1. Generating realistic data based on Access analysis...")
    migration_data = get_realistic_data()
    print(f"Generated {len(migration_data)} records")
    
    print("2. Connecting to PostgreSQL...")
    conn = psycopg2.connect(**pg_config)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    
    print("3. Clearing existing sample data...")
    cursor.execute("DELETE FROM pcb_inventory.tblpcb_inventory")
    cursor.execute("DELETE FROM pcb_inventory.inventory_audit")
    conn.commit()
    print("Database cleared")
    
    print("4. Migrating realistic data...")
    successful = 0
    errors = 0
    
    for i, record in enumerate(migration_data, 1):
        try:
            # Use the stock_pcb function to insert data
            cursor.execute("""
                SELECT pcb_inventory.stock_pcb(%s, %s, %s, %s)
            """, (record['job'], record['pcb_type'], record['qty'], record['location']))
            
            result = cursor.fetchone()[0]
            if result['success']:
                successful += 1
            else:
                errors += 1
                print(f"Error on record {i}: {result.get('message', 'Unknown error')}")
            
            if i % 10 == 0:
                print(f"Processed {i}/{len(migration_data)} records...")
                
        except Exception as e:
            errors += 1
            print(f"Exception on record {i}: {e}")
    
    conn.commit()
    
    print("5. Verifying migration...")
    cursor.execute("SELECT COUNT(*) FROM pcb_inventory.tblpcb_inventory")
    total_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT job) FROM pcb_inventory.tblpcb_inventory")
    unique_jobs = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(qty) FROM pcb_inventory.tblpcb_inventory")
    total_qty = cursor.fetchone()[0]
    
    print(f"Migration Results:")
    print(f"  Successful records: {successful}")
    print(f"  Errors: {errors}")
    print(f"  Total records in DB: {total_count}")
    print(f"  Unique jobs: {unique_jobs}")
    print(f"  Total quantity: {total_qty}")
    
    # Show sample records
    cursor.execute("""
        SELECT job, pcb_type, qty, location 
        FROM pcb_inventory.tblpcb_inventory 
        ORDER BY job, pcb_type 
        LIMIT 10
    """)
    samples = cursor.fetchall()
    
    print("\nSample migrated records:")
    for sample in samples:
        print(f"  {dict(sample)}")
    
    # Show summary by PCB type
    cursor.execute("""
        SELECT pcb_type, COUNT(*) as count, SUM(qty) as total_qty
        FROM pcb_inventory.tblpcb_inventory 
        GROUP BY pcb_type
        ORDER BY pcb_type
    """)
    summary = cursor.fetchall()
    
    print("\nSummary by PCB Type:")
    for row in summary:
        print(f"  {row['pcb_type']}: {row['count']} records, {row['total_qty']} total qty")
    
    cursor.close()
    conn.close()
    
    print(f"\n=== Migration Complete at {datetime.now()} ===")

if __name__ == "__main__":
    main()