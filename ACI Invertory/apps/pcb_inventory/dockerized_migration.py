#!/usr/bin/env python3
"""
Dockerized migration script for Stock and Pick system.
Runs entirely within Docker containers with no local dependencies.
"""

import os
import sys
import json
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
import psycopg2
from psycopg2.extras import RealDictCursor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DockerizedMigration:
    """Handle migration entirely within Docker containers."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'pcb_inventory'),
            'user': os.getenv('POSTGRES_USER', 'stockpick_user'),
            'password': os.getenv('POSTGRES_PASSWORD', 'stockpick_pass')
        }
        
        self.results = {
            'migration_start': self.start_time.isoformat(),
            'phases': {},
            'migration_end': None,
            'success': False,
            'total_time': 0
        }
        
        # Ensure directories exist
        Path('/app/logs').mkdir(exist_ok=True)
        Path('/app/analysis_output').mkdir(exist_ok=True)
        
    def wait_for_postgres(self, max_retries=30):
        """Wait for PostgreSQL to be ready."""
        logger.info("Waiting for PostgreSQL to be ready...")
        
        for i in range(max_retries):
            try:
                conn = psycopg2.connect(**self.db_config)
                conn.close()
                logger.info("✓ PostgreSQL is ready")
                return True
            except Exception as e:
                logger.info(f"PostgreSQL not ready (attempt {i+1}/{max_retries}): {e}")
                time.sleep(2)
        
        logger.error("PostgreSQL failed to become ready")
        return False
    
    def run_sql_command(self, sql: str, description: str) -> Dict[str, Any]:
        """Execute SQL command and return result."""
        logger.info(f"Running: {description}")
        
        try:
            with psycopg2.connect(**self.db_config) as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(sql)
                    
                    # Handle different SQL command types
                    if sql.strip().upper().startswith('SELECT'):
                        results = cur.fetchall()
                        return {
                            'success': True,
                            'results': [dict(row) for row in results],
                            'row_count': len(results)
                        }
                    else:
                        conn.commit()
                        return {
                            'success': True,
                            'message': f"{description} completed successfully"
                        }
                        
        except Exception as e:
            logger.error(f"SQL command failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def phase_1_database_setup(self) -> bool:
        """Phase 1: Set up database schema and structure."""
        logger.info("="*60)
        logger.info("PHASE 1: DATABASE SETUP")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Wait for PostgreSQL
        if not self.wait_for_postgres():
            self.results['phases']['phase_1'] = {
                'name': 'Database Setup',
                'success': False,
                'time': time.time() - phase_start,
                'error': 'PostgreSQL not ready'
            }
            return False
        
        # Create schema
        logger.info("Creating database schema...")
        schema_sql = """
        -- Create schema
        CREATE SCHEMA IF NOT EXISTS pcb_inventory;
        SET search_path TO pcb_inventory, public;
        
        -- Create enums
        DO $$ BEGIN
            CREATE TYPE pcb_type_enum AS ENUM ('Bare', 'Partial', 'Completed', 'Ready to Ship');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        
        DO $$ BEGIN
            CREATE TYPE location_range_enum AS ENUM (
                '1000-1999', '2000-2999', '3000-3999', '4000-4999', '5000-5999',
                '6000-6999', '7000-7999', '8000-8999', '9000-9999', '10000-10999'
            );
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
        """
        
        result = self.run_sql_command(schema_sql, "Create schema and enums")
        phase_results['create_schema'] = result
        
        if not result['success']:
            logger.error("Failed to create schema")
            self.results['phases']['phase_1'] = {
                'name': 'Database Setup',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'Schema creation failed'
            }
            return False
        
        # Create main table
        logger.info("Creating main inventory table...")
        table_sql = """
        CREATE TABLE IF NOT EXISTS pcb_inventory.tblPCB_Inventory (
            id SERIAL PRIMARY KEY,
            job VARCHAR(50) NOT NULL,
            pcb_type pcb_inventory.pcb_type_enum NOT NULL,
            qty INTEGER NOT NULL DEFAULT 0,
            location pcb_inventory.location_range_enum NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            
            -- Constraints
            CONSTRAINT qty_non_negative CHECK (qty >= 0),
            CONSTRAINT unique_job_pcb_type UNIQUE (job, pcb_type)
        );
        
        -- Create indexes
        CREATE INDEX IF NOT EXISTS idx_job ON pcb_inventory.tblPCB_Inventory(job);
        CREATE INDEX IF NOT EXISTS idx_pcb_type ON pcb_inventory.tblPCB_Inventory(pcb_type);
        CREATE INDEX IF NOT EXISTS idx_location ON pcb_inventory.tblPCB_Inventory(location);
        CREATE INDEX IF NOT EXISTS idx_job_pcb_type ON pcb_inventory.tblPCB_Inventory(job, pcb_type);
        """
        
        result = self.run_sql_command(table_sql, "Create main inventory table")
        phase_results['create_table'] = result
        
        # Create audit table
        logger.info("Creating audit table...")
        audit_sql = """
        CREATE TABLE IF NOT EXISTS pcb_inventory.inventory_audit (
            audit_id SERIAL PRIMARY KEY,
            job VARCHAR(50) NOT NULL,
            pcb_type pcb_inventory.pcb_type_enum NOT NULL,
            operation VARCHAR(10) NOT NULL,
            quantity_change INTEGER NOT NULL,
            old_quantity INTEGER,
            new_quantity INTEGER,
            location pcb_inventory.location_range_enum,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            user_id VARCHAR(50) DEFAULT 'system'
        );
        """
        
        result = self.run_sql_command(audit_sql, "Create audit table")
        phase_results['create_audit'] = result
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_1'] = {
            'name': 'Database Setup',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 1 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_2_business_logic(self) -> bool:
        """Phase 2: Create business logic functions and triggers."""
        logger.info("="*60)
        logger.info("PHASE 2: BUSINESS LOGIC")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Create update trigger function
        logger.info("Creating update trigger function...")
        trigger_sql = """
        CREATE OR REPLACE FUNCTION pcb_inventory.update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = CURRENT_TIMESTAMP;
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS update_tblPCB_Inventory_updated_at ON pcb_inventory.tblPCB_Inventory;
        CREATE TRIGGER update_tblPCB_Inventory_updated_at
            BEFORE UPDATE ON pcb_inventory.tblPCB_Inventory
            FOR EACH ROW
            EXECUTE FUNCTION pcb_inventory.update_updated_at_column();
        """
        
        result = self.run_sql_command(trigger_sql, "Create update trigger")
        phase_results['update_trigger'] = result
        
        # Create audit trigger function
        logger.info("Creating audit trigger function...")
        audit_trigger_sql = """
        CREATE OR REPLACE FUNCTION pcb_inventory.log_inventory_change()
        RETURNS TRIGGER AS $$
        BEGIN
            INSERT INTO pcb_inventory.inventory_audit (
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
        
        DROP TRIGGER IF EXISTS inventory_audit_trigger ON pcb_inventory.tblPCB_Inventory;
        CREATE TRIGGER inventory_audit_trigger
            AFTER INSERT OR UPDATE OR DELETE ON pcb_inventory.tblPCB_Inventory
            FOR EACH ROW
            EXECUTE FUNCTION pcb_inventory.log_inventory_change();
        """
        
        result = self.run_sql_command(audit_trigger_sql, "Create audit trigger")
        phase_results['audit_trigger'] = result
        
        # Create stock function
        logger.info("Creating stock_pcb function...")
        stock_function_sql = """
        CREATE OR REPLACE FUNCTION pcb_inventory.stock_pcb(
            p_job VARCHAR(50),
            p_pcb_type pcb_inventory.pcb_type_enum,
            p_qty INTEGER,
            p_location pcb_inventory.location_range_enum
        ) RETURNS JSON AS $$
        DECLARE
            v_old_qty INTEGER := 0;
            v_new_qty INTEGER;
            v_result JSON;
        BEGIN
            -- Check if record exists
            SELECT qty INTO v_old_qty 
            FROM pcb_inventory.tblPCB_Inventory 
            WHERE job = p_job AND pcb_type = p_pcb_type;
            
            IF v_old_qty IS NULL THEN
                -- Create new record
                INSERT INTO pcb_inventory.tblPCB_Inventory (job, pcb_type, qty, location)
                VALUES (p_job, p_pcb_type, p_qty, p_location);
                v_new_qty := p_qty;
            ELSE
                -- Update existing record
                v_new_qty := v_old_qty + p_qty;
                UPDATE pcb_inventory.tblPCB_Inventory 
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
        """
        
        result = self.run_sql_command(stock_function_sql, "Create stock_pcb function")
        phase_results['stock_function'] = result
        
        # Create pick function
        logger.info("Creating pick_pcb function...")
        pick_function_sql = """
        CREATE OR REPLACE FUNCTION pcb_inventory.pick_pcb(
            p_job VARCHAR(50),
            p_pcb_type pcb_inventory.pcb_type_enum,
            p_qty INTEGER
        ) RETURNS JSON AS $$
        DECLARE
            v_old_qty INTEGER := 0;
            v_new_qty INTEGER;
            v_result JSON;
        BEGIN
            -- Check if record exists and get current quantity
            SELECT qty INTO v_old_qty 
            FROM pcb_inventory.tblPCB_Inventory 
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
            UPDATE pcb_inventory.tblPCB_Inventory 
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
        """
        
        result = self.run_sql_command(pick_function_sql, "Create pick_pcb function")
        phase_results['pick_function'] = result
        
        # Create views
        logger.info("Creating views...")
        views_sql = """
        CREATE OR REPLACE VIEW pcb_inventory.current_inventory AS
        SELECT 
            job,
            pcb_type,
            qty,
            location,
            created_at,
            updated_at
        FROM pcb_inventory.tblPCB_Inventory
        WHERE qty > 0
        ORDER BY job, pcb_type;
        
        CREATE OR REPLACE VIEW pcb_inventory.inventory_summary AS
        SELECT 
            pcb_type,
            COUNT(*) as job_count,
            SUM(qty) as total_quantity,
            AVG(qty) as average_quantity,
            location
        FROM pcb_inventory.tblPCB_Inventory
        WHERE qty > 0
        GROUP BY pcb_type, location
        ORDER BY pcb_type, location;
        """
        
        result = self.run_sql_command(views_sql, "Create views")
        phase_results['create_views'] = result
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_2'] = {
            'name': 'Business Logic',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 2 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_3_sample_data(self) -> bool:
        """Phase 3: Insert sample data and test functions."""
        logger.info("="*60)
        logger.info("PHASE 3: SAMPLE DATA & TESTING")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Insert sample data
        logger.info("Inserting sample data...")
        sample_data_sql = """
        INSERT INTO pcb_inventory.tblPCB_Inventory (job, pcb_type, qty, location) VALUES
            ('12345', 'Bare', 100, '8000-8999'),
            ('12345', 'Partial', 50, '8000-8999'),
            ('12346', 'Bare', 200, '7000-7999'),
            ('12347', 'Completed', 25, '9000-9999'),
            ('12348', 'Ready to Ship', 10, '10000-10999')
        ON CONFLICT (job, pcb_type) DO NOTHING;
        """
        
        result = self.run_sql_command(sample_data_sql, "Insert sample data")
        phase_results['sample_data'] = result
        
        # Test stock function
        logger.info("Testing stock_pcb function...")
        result = self.run_sql_command(
            "SELECT pcb_inventory.stock_pcb('TEST001', 'Bare', 50, '8000-8999');",
            "Test stock_pcb function"
        )
        phase_results['test_stock'] = result
        
        # Test pick function
        logger.info("Testing pick_pcb function...")
        result = self.run_sql_command(
            "SELECT pcb_inventory.pick_pcb('TEST001', 'Bare', 25);",
            "Test pick_pcb function"
        )
        phase_results['test_pick'] = result
        
        # Test views
        logger.info("Testing views...")
        result = self.run_sql_command(
            "SELECT COUNT(*) as inventory_count FROM pcb_inventory.current_inventory;",
            "Test current_inventory view"
        )
        phase_results['test_views'] = result
        
        # Test audit log
        logger.info("Testing audit log...")
        result = self.run_sql_command(
            "SELECT COUNT(*) as audit_count FROM pcb_inventory.inventory_audit;",
            "Test audit log"
        )
        phase_results['test_audit'] = result
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_3'] = {
            'name': 'Sample Data & Testing',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 3 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_4_validation(self) -> bool:
        """Phase 4: Final validation and reporting."""
        logger.info("="*60)
        logger.info("PHASE 4: VALIDATION & REPORTING")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Validate schema
        logger.info("Validating database schema...")
        result = self.run_sql_command(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'pcb_inventory';",
            "Validate schema tables"
        )
        phase_results['schema_validation'] = result
        
        if result['success']:
            tables = [row['table_name'] for row in result['results']]
            logger.info(f"Found tables: {tables}")
        
        # Check data integrity
        logger.info("Checking data integrity...")
        integrity_checks = [
            ("SELECT COUNT(*) as total_records FROM pcb_inventory.tblPCB_Inventory;", "Total records"),
            ("SELECT COUNT(*) as audit_records FROM pcb_inventory.inventory_audit;", "Audit records"),
            ("SELECT COUNT(DISTINCT pcb_type) as pcb_types FROM pcb_inventory.tblPCB_Inventory;", "PCB types"),
            ("SELECT COUNT(DISTINCT location) as locations FROM pcb_inventory.tblPCB_Inventory;", "Locations")
        ]
        
        for sql, description in integrity_checks:
            result = self.run_sql_command(sql, description)
            phase_results[description.lower().replace(' ', '_')] = result
        
        # Generate final report
        logger.info("Generating migration report...")
        
        # Get summary statistics
        stats_result = self.run_sql_command("""
            SELECT 
                COUNT(*) as total_items,
                SUM(qty) as total_quantity,
                COUNT(DISTINCT job) as unique_jobs,
                COUNT(DISTINCT pcb_type) as pcb_types,
                COUNT(DISTINCT location) as locations
            FROM pcb_inventory.tblPCB_Inventory;
        """, "Get summary statistics")
        
        if stats_result['success'] and stats_result['results']:
            stats = stats_result['results'][0]
            phase_results['summary_stats'] = stats
            
            logger.info("Database Summary:")
            logger.info(f"  Total Items: {stats['total_items']}")
            logger.info(f"  Total Quantity: {stats['total_quantity']}")
            logger.info(f"  Unique Jobs: {stats['unique_jobs']}")
            logger.info(f"  PCB Types: {stats['pcb_types']}")
            logger.info(f"  Locations: {stats['locations']}")
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_4'] = {
            'name': 'Validation & Reporting',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 4 completed in {phase_time:.2f} seconds")
        return True
    
    def generate_final_report(self):
        """Generate final migration report."""
        end_time = datetime.now()
        total_time = (end_time - self.start_time).total_seconds()
        
        self.results['migration_end'] = end_time.isoformat()
        self.results['total_time'] = total_time
        
        # Calculate success
        successful_phases = sum(1 for phase in self.results['phases'].values() if phase['success'])
        total_phases = len(self.results['phases'])
        self.results['success'] = successful_phases == total_phases
        
        # Save report
        report_file = '/app/analysis_output/dockerized_migration_report.json'
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        # Print summary
        print("\\n" + "="*80)
        print("DOCKERIZED MIGRATION COMPLETED")
        print("="*80)
        print(f"Success: {'✓' if self.results['success'] else '✗'}")
        print(f"Total Time: {total_time:.2f} seconds")
        print(f"Phases: {successful_phases}/{total_phases}")
        print(f"\\nDatabase: postgres:5432 (pcb_inventory)")
        print(f"Schema: pcb_inventory")
        print(f"Report: {report_file}")
        
        logger.info(f"Migration report saved: {report_file}")
    
    def run_migration(self):
        """Run the complete dockerized migration."""
        logger.info("="*80)
        logger.info("STARTING DOCKERIZED STOCK AND PICK MIGRATION")
        logger.info("="*80)
        
        try:
            phases = [
                self.phase_1_database_setup,
                self.phase_2_business_logic,
                self.phase_3_sample_data,
                self.phase_4_validation
            ]
            
            for phase_func in phases:
                success = phase_func()
                if not success:
                    logger.error(f"Phase failed, stopping migration")
                    break
            
        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.results['success'] = False
        finally:
            self.generate_final_report()

def main():
    """Main function."""
    logger.info("Starting dockerized migration...")
    migrator = DockerizedMigration()
    migrator.run_migration()

if __name__ == "__main__":
    main()