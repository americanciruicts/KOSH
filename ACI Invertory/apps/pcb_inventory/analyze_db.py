#!/usr/bin/env python3
"""Analyze the Stock and Pick Access database without requiring Docker."""

import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def analyze_database_structure():
    """Analyze the database structure based on the Python application."""
    
    print("="*60)
    print("STOCK AND PICK DATABASE ANALYSIS")
    print("="*60)
    
    # Database path
    db_path = "/Users/khashsarrafi/Projects/revestData/migration/stockAndPick/INVENTORY TABLE.mdb"
    
    # Check if database exists
    if not os.path.exists(db_path):
        print(f"✗ Database not found: {db_path}")
        return False
    
    print(f"✓ Database found: {db_path}")
    
    # Get file size
    file_size = os.path.getsize(db_path)
    print(f"✓ Database size: {file_size:,} bytes ({file_size/1024:.1f} KB)")
    
    # Analyze based on Python application
    print("\\nAnalyzing database structure from Python application...")
    
    # Main table structure
    table_structure = {
        "name": "tblPCB_Inventory",
        "description": "Main PCB inventory table",
        "columns": [
            {
                "name": "job",
                "type": "TEXT",
                "size": 50,
                "nullable": False,
                "description": "Job number identifier"
            },
            {
                "name": "pcb_type", 
                "type": "TEXT",
                "size": 20,
                "nullable": False,
                "description": "PCB assembly type",
                "values": ["Bare", "Partial", "Completed", "Ready to Ship"]
            },
            {
                "name": "qty",
                "type": "LONG",
                "nullable": False,
                "description": "Quantity in inventory"
            },
            {
                "name": "location",
                "type": "TEXT", 
                "size": 20,
                "nullable": False,
                "description": "Storage location",
                "values": ["1000-1999", "2000-2999", "3000-3999", "4000-4999", 
                          "5000-5999", "6000-6999", "7000-7999", "8000-8999", 
                          "9000-9999", "10000-10999"]
            }
        ],
        "primary_key": ["job", "pcb_type"],
        "constraints": [
            "qty >= 0",
            "pcb_type IN ('Bare', 'Partial', 'Completed', 'Ready to Ship')"
        ]
    }
    
    # Business logic analysis
    business_logic = {
        "operations": [
            {
                "name": "stockPCB",
                "description": "Add inventory (create new or update existing)",
                "validation": "All fields required",
                "sql": "INSERT or UPDATE based on job + pcb_type existence"
            },
            {
                "name": "pickPCB", 
                "description": "Remove inventory with validation",
                "validation": "Check sufficient quantity, job exists",
                "sql": "UPDATE qty = qty - pick_qty WHERE job + pcb_type"
            },
            {
                "name": "findOldQty",
                "description": "Query current inventory level",
                "sql": "SELECT qty FROM tblPCB_Inventory WHERE job + pcb_type"
            }
        ],
        "safety_checks": [
            "Prevent negative inventory",
            "Check job exists before picking",
            "Validate all required fields",
            "Confirmation dialogs for all operations"
        ]
    }
    
    # Create analysis report
    analysis_report = {
        "database_path": db_path,
        "analysis_date": datetime.now().isoformat(),
        "file_size": file_size,
        "database_type": "Microsoft Access (.mdb)",
        "table_structure": table_structure,
        "business_logic": business_logic,
        "migration_notes": [
            "Simple single-table structure",
            "Compound primary key (job + pcb_type)",
            "Enum-like values for pcb_type and location",
            "Business logic enforced in application layer",
            "No foreign key relationships",
            "No complex queries or stored procedures"
        ],
        "postgresql_mapping": {
            "table_name": "tblPCB_Inventory",
            "enums": [
                "pcb_type_enum: ('Bare', 'Partial', 'Completed', 'Ready to Ship')",
                "location_range_enum: ('1000-1999', '2000-2999', ..., '10000-10999')"
            ],
            "constraints": [
                "UNIQUE(job, pcb_type)",
                "CHECK(qty >= 0)"
            ],
            "indexes": [
                "idx_job ON (job)",
                "idx_pcb_type ON (pcb_type)", 
                "idx_location ON (location)",
                "idx_job_pcb_type ON (job, pcb_type)"
            ]
        }
    }
    
    # Save analysis
    output_dir = Path("analysis_output")
    output_dir.mkdir(exist_ok=True)
    
    analysis_file = output_dir / "database_analysis.json"
    with open(analysis_file, 'w') as f:
        json.dump(analysis_report, f, indent=2)
    
    print(f"✓ Analysis saved to: {analysis_file}")
    
    # Print summary
    print("\\nDATABASE SUMMARY:")
    print(f"  Tables: 1 (tblPCB_Inventory)")
    print(f"  Columns: {len(table_structure['columns'])}")
    print(f"  Primary Key: {', '.join(table_structure['primary_key'])}")
    print(f"  Business Operations: {len(business_logic['operations'])}")
    
    print("\\nPCB TYPES:")
    for pcb_type in table_structure['columns'][1]['values']:
        print(f"  - {pcb_type}")
    
    print("\\nLOCATION RANGES:")
    for location in table_structure['columns'][3]['values']:
        print(f"  - {location}")
    
    print("\\nBUSINESS OPERATIONS:")
    for op in business_logic['operations']:
        print(f"  - {op['name']}: {op['description']}")
    
    return True

def generate_postgresql_schema():
    """Generate PostgreSQL schema for the database."""
    
    print("\\n" + "="*60)
    print("GENERATING POSTGRESQL SCHEMA")
    print("="*60)
    
    schema_sql = """-- Stock and Pick PCB Inventory Database Schema
-- Generated from Access database analysis
-- Date: {date}

-- Create schema
CREATE SCHEMA IF NOT EXISTS pcb_inventory;
SET search_path TO pcb_inventory, public;

-- Create enums for controlled values
CREATE TYPE pcb_type_enum AS ENUM (
    'Bare',
    'Partial', 
    'Completed',
    'Ready to Ship'
);

CREATE TYPE location_range_enum AS ENUM (
    '1000-1999',
    '2000-2999',
    '3000-3999',
    '4000-4999',
    '5000-5999',
    '6000-6999',
    '7000-7999',
    '8000-8999',
    '9000-9999',
    '10000-10999'
);

-- Create main inventory table
CREATE TABLE tblPCB_Inventory (
    id SERIAL PRIMARY KEY,
    job VARCHAR(50) NOT NULL,
    pcb_type pcb_type_enum NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0,
    location location_range_enum NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT qty_non_negative CHECK (qty >= 0),
    CONSTRAINT unique_job_pcb_type UNIQUE (job, pcb_type)
);

-- Create indexes for performance
CREATE INDEX idx_job ON tblPCB_Inventory(job);
CREATE INDEX idx_pcb_type ON tblPCB_Inventory(pcb_type);
CREATE INDEX idx_location ON tblPCB_Inventory(location);
CREATE INDEX idx_job_pcb_type ON tblPCB_Inventory(job, pcb_type);

-- Create audit table for tracking changes
CREATE TABLE inventory_audit (
    audit_id SERIAL PRIMARY KEY,
    job VARCHAR(50) NOT NULL,
    pcb_type pcb_type_enum NOT NULL,
    operation VARCHAR(10) NOT NULL, -- 'STOCK' or 'PICK'
    quantity_change INTEGER NOT NULL,
    old_quantity INTEGER,
    new_quantity INTEGER,
    location location_range_enum,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(50) DEFAULT 'system'
);

-- Create function for automatic updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for updated_at
CREATE TRIGGER update_tblPCB_Inventory_updated_at
    BEFORE UPDATE ON tblPCB_Inventory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create function for audit logging
CREATE OR REPLACE FUNCTION log_inventory_change()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO inventory_audit (
        job, pcb_type, operation, quantity_change, 
        old_quantity, new_quantity, location
    )
    VALUES (
        COALESCE(NEW.job, OLD.job),
        COALESCE(NEW.pcb_type, OLD.pcb_type),
        CASE 
            WHEN TG_OP = 'INSERT' THEN 'STOCK'
            WHEN TG_OP = 'UPDATE' AND NEW.qty > OLD.qty THEN 'STOCK'
            WHEN TG_OP = 'UPDATE' AND NEW.qty < OLD.qty THEN 'PICK'
            ELSE 'UPDATE'
        END,
        CASE 
            WHEN TG_OP = 'INSERT' THEN NEW.qty
            WHEN TG_OP = 'UPDATE' THEN NEW.qty - OLD.qty
            WHEN TG_OP = 'DELETE' THEN -OLD.qty
            ELSE 0
        END,
        CASE WHEN TG_OP = 'DELETE' THEN OLD.qty ELSE COALESCE(OLD.qty, 0) END,
        CASE WHEN TG_OP = 'DELETE' THEN 0 ELSE NEW.qty END,
        COALESCE(NEW.location, OLD.location)
    );
    
    RETURN COALESCE(NEW, OLD);
END;
$$ language 'plpgsql';

-- Create trigger for audit logging
CREATE TRIGGER inventory_audit_trigger
    AFTER INSERT OR UPDATE OR DELETE ON tblPCB_Inventory
    FOR EACH ROW
    EXECUTE FUNCTION log_inventory_change();

-- Create business logic functions
CREATE OR REPLACE FUNCTION stock_pcb(
    p_job VARCHAR(50),
    p_pcb_type pcb_type_enum,
    p_qty INTEGER,
    p_location location_range_enum
) RETURNS JSON AS $$
DECLARE
    v_old_qty INTEGER := 0;
    v_new_qty INTEGER;
    v_result JSON;
BEGIN
    -- Check if record exists
    SELECT qty INTO v_old_qty 
    FROM tblPCB_Inventory 
    WHERE job = p_job AND pcb_type = p_pcb_type;
    
    IF v_old_qty IS NULL THEN
        -- Create new record
        INSERT INTO tblPCB_Inventory (job, pcb_type, qty, location)
        VALUES (p_job, p_pcb_type, p_qty, p_location);
        v_new_qty := p_qty;
    ELSE
        -- Update existing record
        v_new_qty := v_old_qty + p_qty;
        UPDATE tblPCB_Inventory 
        SET qty = v_new_qty, location = p_location
        WHERE job = p_job AND pcb_type = p_pcb_type;
    END IF;
    
    -- Return result
    v_result := json_build_object(
        'success', true,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'old_qty', COALESCE(v_old_qty, 0),
        'new_qty', v_new_qty,
        'stocked_qty', p_qty,
        'location', p_location
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pick_pcb(
    p_job VARCHAR(50),
    p_pcb_type pcb_type_enum,
    p_qty INTEGER
) RETURNS JSON AS $$
DECLARE
    v_old_qty INTEGER := 0;
    v_new_qty INTEGER;
    v_result JSON;
BEGIN
    -- Check if record exists and get current quantity
    SELECT qty INTO v_old_qty 
    FROM tblPCB_Inventory 
    WHERE job = p_job AND pcb_type = p_pcb_type;
    
    IF v_old_qty IS NULL THEN
        -- Job not found
        v_result := json_build_object(
            'success', false,
            'error', 'Job not found',
            'job', p_job,
            'pcb_type', p_pcb_type
        );
        RETURN v_result;
    END IF;
    
    -- Check if enough quantity available
    IF v_old_qty < p_qty THEN
        v_result := json_build_object(
            'success', false,
            'error', 'Insufficient quantity',
            'job', p_job,
            'pcb_type', p_pcb_type,
            'available_qty', v_old_qty,
            'requested_qty', p_qty
        );
        RETURN v_result;
    END IF;
    
    -- Update quantity
    v_new_qty := v_old_qty - p_qty;
    UPDATE tblPCB_Inventory 
    SET qty = v_new_qty
    WHERE job = p_job AND pcb_type = p_pcb_type;
    
    -- Return success result
    v_result := json_build_object(
        'success', true,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'old_qty', v_old_qty,
        'new_qty', v_new_qty,
        'picked_qty', p_qty
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Create useful views
CREATE VIEW current_inventory AS
SELECT 
    job,
    pcb_type,
    qty,
    location,
    created_at,
    updated_at
FROM tblPCB_Inventory
WHERE qty > 0
ORDER BY job, pcb_type;

CREATE VIEW inventory_summary AS
SELECT 
    pcb_type,
    COUNT(*) as job_count,
    SUM(qty) as total_quantity,
    AVG(qty) as average_quantity,
    location
FROM tblPCB_Inventory
WHERE qty > 0
GROUP BY pcb_type, location
ORDER BY pcb_type, location;

-- Insert sample data for testing
INSERT INTO tblPCB_Inventory (job, pcb_type, qty, location) VALUES
    ('12345', 'Bare', 100, '8000-8999'),
    ('12345', 'Partial', 50, '8000-8999'),
    ('12346', 'Bare', 200, '7000-7999'),
    ('12347', 'Completed', 25, '9000-9999'),
    ('12348', 'Ready to Ship', 10, '10000-10999')
ON CONFLICT (job, pcb_type) DO NOTHING;

-- Comments for documentation
COMMENT ON TABLE tblPCB_Inventory IS 'Main PCB inventory tracking table';
COMMENT ON COLUMN tblPCB_Inventory.job IS 'Job number identifier';
COMMENT ON COLUMN tblPCB_Inventory.pcb_type IS 'PCB assembly stage';
COMMENT ON COLUMN tblPCB_Inventory.qty IS 'Current quantity in inventory';
COMMENT ON COLUMN tblPCB_Inventory.location IS 'Storage location range';

COMMENT ON FUNCTION stock_pcb(VARCHAR, pcb_type_enum, INTEGER, location_range_enum) IS 'Add inventory with business logic validation';
COMMENT ON FUNCTION pick_pcb(VARCHAR, pcb_type_enum, INTEGER) IS 'Remove inventory with safety checks';
""".format(date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    # Save schema
    output_dir = Path("analysis_output")
    output_dir.mkdir(exist_ok=True)
    
    schema_file = output_dir / "postgresql_schema.sql"
    with open(schema_file, 'w') as f:
        f.write(schema_sql)
    
    print(f"✓ PostgreSQL schema generated: {schema_file}")
    
    return True

def generate_migration_plan():
    """Generate a detailed migration plan."""
    
    print("\\n" + "="*60)
    print("MIGRATION PLAN")
    print("="*60)
    
    migration_plan = {
        "phase_1": {
            "name": "Environment Setup",
            "steps": [
                "Start Docker PostgreSQL container",
                "Create pcb_inventory database",
                "Initialize schema with enums and tables",
                "Set up audit logging and triggers"
            ]
        },
        "phase_2": {
            "name": "Data Migration",
            "steps": [
                "Connect to Access database",
                "Extract data from tblPCB_Inventory",
                "Transform data types and validate",
                "Load data into PostgreSQL",
                "Verify row counts and data integrity"
            ]
        },
        "phase_3": {
            "name": "Business Logic Migration",
            "steps": [
                "Test stock_pcb() function",
                "Test pick_pcb() function",  
                "Validate business rules",
                "Test audit logging",
                "Performance testing"
            ]
        },
        "phase_4": {
            "name": "Application Migration",
            "steps": [
                "Extract Access forms (if possible)",
                "Document current tkinter UI",
                "Design modern web interface",
                "Implement REST API",
                "Build React/Vue frontend"
            ]
        }
    }
    
    # Save migration plan
    output_dir = Path("analysis_output")
    output_dir.mkdir(exist_ok=True)
    
    plan_file = output_dir / "migration_plan.json"
    with open(plan_file, 'w') as f:
        json.dump(migration_plan, f, indent=2)
    
    print(f"✓ Migration plan saved: {plan_file}")
    
    for phase, details in migration_plan.items():
        print(f"\\n{phase.upper()}: {details['name']}")
        for i, step in enumerate(details['steps'], 1):
            print(f"  {i}. {step}")
    
    return True

def main():
    """Main analysis function."""
    
    # Change to the stockAndPick directory
    os.chdir("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
    
    # Run analysis
    success = analyze_database_structure()
    if not success:
        return False
    
    # Generate PostgreSQL schema
    success = generate_postgresql_schema()
    if not success:
        return False
    
    # Generate migration plan
    success = generate_migration_plan()
    if not success:
        return False
    
    print("\\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)
    print("Next steps:")
    print("1. Review the generated files in analysis_output/")
    print("2. Start Docker PostgreSQL with: docker-compose up -d")
    print("3. Run the migration script")
    print("4. Test the migrated database")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)