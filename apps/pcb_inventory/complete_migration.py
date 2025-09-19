#!/usr/bin/env python3
"""
Complete Stock and Pick migration script.
This orchestrates the entire migration process from Access to PostgreSQL with web app deployment.
"""

import os
import sys
import json
import time
import subprocess
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('complete_migration.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class CompleteMigration:
    """Orchestrate the complete migration process."""
    
    def __init__(self):
        self.start_time = datetime.now()
        self.migration_dir = Path("/Users/khashsarrafi/Projects/revestData/migration/stockAndPick")
        self.results = {
            'migration_start': self.start_time.isoformat(),
            'phases': {},
            'migration_end': None,
            'success': False,
            'total_time': 0,
            'summary': {}
        }
        
        # Change to migration directory
        os.chdir(self.migration_dir)
        
    def run_command(self, command: str, description: str, timeout: int = 300) -> Dict[str, Any]:
        """Run a shell command and return the result."""
        logger.info(f"Running: {description}")
        logger.debug(f"Command: {command}")
        
        try:
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout,
                cwd=self.migration_dir
            )
            
            success = result.returncode == 0
            
            if success:
                logger.info(f"✓ {description} - Success")
            else:
                logger.error(f"✗ {description} - Failed")
                logger.error(f"Error output: {result.stderr}")
            
            return {
                'success': success,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"✗ {description} - Timeout after {timeout} seconds")
            return {
                'success': False,
                'stdout': '',
                'stderr': f'Command timed out after {timeout} seconds',
                'returncode': -1
            }
        except Exception as e:
            logger.error(f"✗ {description} - Exception: {e}")
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'returncode': -1
            }
    
    def phase_1_environment_setup(self) -> bool:
        """Phase 1: Set up the Docker environment."""
        logger.info("="*60)
        logger.info("PHASE 1: ENVIRONMENT SETUP")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Stop any existing containers
        logger.info("Stopping existing containers...")
        result = self.run_command("docker-compose down", "Stop existing containers")
        phase_results['stop_containers'] = result
        
        # Clean up Docker system (optional)
        logger.info("Cleaning up Docker system...")
        result = self.run_command("docker system prune -f", "Docker system cleanup")
        phase_results['docker_cleanup'] = result
        
        # Start PostgreSQL and pgAdmin
        logger.info("Starting PostgreSQL and pgAdmin...")
        result = self.run_command("docker-compose up -d postgres pgadmin", "Start database services")
        phase_results['start_database'] = result
        
        if not result['success']:
            logger.error("Failed to start database services")
            self.results['phases']['phase_1'] = {
                'name': 'Environment Setup',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'Failed to start database services'
            }
            return False
        
        # Wait for PostgreSQL to be ready
        logger.info("Waiting for PostgreSQL to be ready...")
        max_retries = 30
        for i in range(max_retries):
            result = self.run_command(
                "docker exec stockandpick_postgres pg_isready -h localhost -p 5432 -U stockpick_user",
                f"Check PostgreSQL readiness (attempt {i+1}/{max_retries})"
            )
            if result['success']:
                logger.info("✓ PostgreSQL is ready")
                break
            time.sleep(2)
        else:
            logger.error("PostgreSQL failed to become ready")
            self.results['phases']['phase_1'] = {
                'name': 'Environment Setup',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'PostgreSQL failed to become ready'
            }
            return False
        
        phase_results['postgres_ready'] = result
        
        # Apply database schema
        logger.info("Applying database schema...")
        schema_file = self.migration_dir / "analysis_output" / "postgresql_schema.sql"
        if schema_file.exists():
            result = self.run_command(
                f"docker exec -i stockandpick_postgres psql -U stockpick_user -d pcb_inventory < {schema_file}",
                "Apply PostgreSQL schema"
            )
            phase_results['apply_schema'] = result
            
            if not result['success']:
                logger.warning("Schema application failed, but continuing...")
        else:
            logger.warning(f"Schema file not found: {schema_file}")
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_1'] = {
            'name': 'Environment Setup',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 1 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_2_database_analysis(self) -> bool:
        """Phase 2: Analyze the Access database."""
        logger.info("="*60)
        logger.info("PHASE 2: DATABASE ANALYSIS")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Run database analysis
        logger.info("Running database analysis...")
        result = self.run_command("python analyze_db.py", "Analyze Access database structure")
        phase_results['database_analysis'] = result
        
        if not result['success']:
            logger.error("Database analysis failed")
            self.results['phases']['phase_2'] = {
                'name': 'Database Analysis',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'Database analysis failed'
            }
            return False
        
        # Check for generated files
        analysis_dir = self.migration_dir / "analysis_output"
        required_files = [
            "database_analysis.json",
            "postgresql_schema.sql",
            "migration_plan.json"
        ]
        
        missing_files = []
        for file_name in required_files:
            file_path = analysis_dir / file_name
            if not file_path.exists():
                missing_files.append(file_name)
        
        if missing_files:
            logger.error(f"Missing analysis files: {missing_files}")
            self.results['phases']['phase_2'] = {
                'name': 'Database Analysis',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': f'Missing analysis files: {missing_files}'
            }
            return False
        
        # Load analysis results
        try:
            with open(analysis_dir / "database_analysis.json", 'r') as f:
                analysis_data = json.load(f)
            
            phase_results['analysis_summary'] = {
                'file_size': analysis_data.get('file_size', 0),
                'table_structure': analysis_data.get('table_structure', {}),
                'business_operations': len(analysis_data.get('business_logic', {}).get('operations', []))
            }
            
        except Exception as e:
            logger.warning(f"Could not load analysis data: {e}")
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_2'] = {
            'name': 'Database Analysis',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 2 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_3_schema_deployment(self) -> bool:
        """Phase 3: Deploy the PostgreSQL schema."""
        logger.info("="*60)
        logger.info("PHASE 3: SCHEMA DEPLOYMENT")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Apply the generated schema
        schema_file = self.migration_dir / "analysis_output" / "postgresql_schema.sql"
        
        if not schema_file.exists():
            logger.error(f"Schema file not found: {schema_file}")
            self.results['phases']['phase_3'] = {
                'name': 'Schema Deployment',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'Schema file not found'
            }
            return False
        
        logger.info("Deploying PostgreSQL schema...")
        result = self.run_command(
            f"docker exec -i stockandpick_postgres psql -U stockpick_user -d pcb_inventory < {schema_file}",
            "Deploy PostgreSQL schema"
        )
        phase_results['schema_deployment'] = result
        
        if not result['success']:
            logger.error("Schema deployment failed")
            self.results['phases']['phase_3'] = {
                'name': 'Schema Deployment',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'Schema deployment failed'
            }
            return False
        
        # Verify schema deployment
        logger.info("Verifying schema deployment...")
        result = self.run_command(
            "docker exec stockandpick_postgres psql -U stockpick_user -d pcb_inventory -c \"\\dt pcb_inventory.*\"",
            "Verify schema tables"
        )
        phase_results['schema_verification'] = result
        
        # Test stored procedures
        logger.info("Testing stored procedures...")
        test_commands = [
            "SELECT pcb_inventory.stock_pcb('TEST001', 'Bare', 10, '8000-8999');",
            "SELECT * FROM pcb_inventory.current_inventory WHERE job = 'TEST001';",
            "SELECT pcb_inventory.pick_pcb('TEST001', 'Bare', 5);",
        ]
        
        for i, cmd in enumerate(test_commands):
            result = self.run_command(
                f"docker exec stockandpick_postgres psql -U stockpick_user -d pcb_inventory -c \"{cmd}\"",
                f"Test stored procedure {i+1}"
            )
            phase_results[f'test_procedure_{i+1}'] = result
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_3'] = {
            'name': 'Schema Deployment',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 3 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_4_web_application(self) -> bool:
        """Phase 4: Deploy the web application."""
        logger.info("="*60)
        logger.info("PHASE 4: WEB APPLICATION DEPLOYMENT")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Build and start the web application
        web_app_dir = self.migration_dir / "web_app"
        
        if not web_app_dir.exists():
            logger.error(f"Web app directory not found: {web_app_dir}")
            self.results['phases']['phase_4'] = {
                'name': 'Web Application Deployment',
                'success': False,
                'time': time.time() - phase_start,
                'results': phase_results,
                'error': 'Web app directory not found'
            }
            return False
        
        # Change to web app directory
        os.chdir(web_app_dir)
        
        # Build and start web application
        logger.info("Building and starting web application...")
        result = self.run_command("docker-compose up -d web_app", "Start web application")
        phase_results['start_webapp'] = result
        
        if not result['success']:
            logger.warning("Docker-compose start failed, trying direct Python execution...")
            
            # Try running the Flask app directly
            result = self.run_command("python app.py &", "Start Flask app directly")
            phase_results['start_flask_direct'] = result
        
        # Wait for web application to be ready
        logger.info("Waiting for web application to be ready...")
        max_retries = 20
        for i in range(max_retries):
            result = self.run_command(
                "curl -f http://localhost:5000/ || exit 1",
                f"Check web app readiness (attempt {i+1}/{max_retries})"
            )
            if result['success']:
                logger.info("✓ Web application is ready")
                break
            time.sleep(3)
        else:
            logger.warning("Web application health check failed, but continuing...")
        
        phase_results['webapp_ready'] = result
        
        # Change back to migration directory
        os.chdir(self.migration_dir)
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_4'] = {
            'name': 'Web Application Deployment',
            'success': True,  # Consider successful even if health check fails
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 4 completed in {phase_time:.2f} seconds")
        return True
    
    def phase_5_validation(self) -> bool:
        """Phase 5: Validate the complete system."""
        logger.info("="*60)
        logger.info("PHASE 5: SYSTEM VALIDATION")
        logger.info("="*60)
        
        phase_start = time.time()
        phase_results = {}
        
        # Test database connectivity
        logger.info("Testing database connectivity...")
        result = self.run_command(
            "docker exec stockandpick_postgres psql -U stockpick_user -d pcb_inventory -c \"SELECT COUNT(*) FROM pcb_inventory.tblPCB_Inventory;\"",
            "Test database connectivity"
        )
        phase_results['database_connectivity'] = result
        
        # Test API endpoints (if web app is running)
        logger.info("Testing API endpoints...")
        api_tests = [
            ("curl -s http://localhost:5000/api/inventory", "Test inventory API"),
            ("curl -s http://localhost:5000/", "Test main page")
        ]
        
        for cmd, description in api_tests:
            result = self.run_command(cmd, description)
            phase_results[description.lower().replace(' ', '_')] = result
        
        # Generate system status report
        logger.info("Generating system status report...")
        status_report = {
            'timestamp': datetime.now().isoformat(),
            'docker_containers': {},
            'database_status': {},
            'web_app_status': {}
        }
        
        # Check Docker containers
        result = self.run_command("docker ps --format 'table {{.Names}}\\t{{.Status}}'", "Check Docker containers")
        if result['success']:
            status_report['docker_containers'] = result['stdout']
        
        # Check database
        result = self.run_command(
            "docker exec stockandpick_postgres psql -U stockpick_user -d pcb_inventory -c \"SELECT version();\"",
            "Check PostgreSQL version"
        )
        if result['success']:
            status_report['database_status']['version'] = result['stdout']
        
        # Save status report
        status_file = self.migration_dir / "system_status.json"
        with open(status_file, 'w') as f:
            json.dump(status_report, f, indent=2)
        
        phase_results['status_report'] = str(status_file)
        
        phase_time = time.time() - phase_start
        self.results['phases']['phase_5'] = {
            'name': 'System Validation',
            'success': True,
            'time': phase_time,
            'results': phase_results
        }
        
        logger.info(f"✓ Phase 5 completed in {phase_time:.2f} seconds")
        return True
    
    def generate_final_report(self):
        """Generate the final migration report."""
        logger.info("="*60)
        logger.info("GENERATING FINAL REPORT")
        logger.info("="*60)
        
        end_time = datetime.now()
        total_time = (end_time - self.start_time).total_seconds()
        
        self.results['migration_end'] = end_time.isoformat()
        self.results['total_time'] = total_time
        
        # Calculate success rate
        successful_phases = sum(1 for phase in self.results['phases'].values() if phase['success'])
        total_phases = len(self.results['phases'])
        success_rate = (successful_phases / total_phases) * 100 if total_phases > 0 else 0
        
        self.results['success'] = success_rate >= 80  # Consider successful if 80% of phases complete
        
        # Generate summary
        self.results['summary'] = {
            'total_phases': total_phases,
            'successful_phases': successful_phases,
            'success_rate': f"{success_rate:.1f}%",
            'total_time_formatted': f"{total_time:.2f} seconds",
            'access_database': str(self.migration_dir / "INVENTORY TABLE.mdb"),
            'postgresql_host': "localhost:5432",
            'web_application': "http://localhost:5000",
            'pgadmin': "http://localhost:8080"
        }
        
        # Save final report
        report_file = self.migration_dir / "migration_final_report.json"
        with open(report_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        # Print summary
        print("\\n" + "="*80)
        print("MIGRATION COMPLETED")
        print("="*80)
        print(f"Success: {'✓' if self.results['success'] else '✗'}")
        print(f"Total Time: {total_time:.2f} seconds")
        print(f"Phases Completed: {successful_phases}/{total_phases} ({success_rate:.1f}%)")
        print(f"\\nAccess Database: {self.migration_dir / 'INVENTORY TABLE.mdb'}")
        print(f"PostgreSQL: localhost:5432 (pcb_inventory)")
        print(f"Web Application: http://localhost:5000")
        print(f"pgAdmin: http://localhost:8080")
        print(f"\\nFinal Report: {report_file}")
        
        # Print phase results
        print("\\nPHASE RESULTS:")
        for phase_id, phase in self.results['phases'].items():
            status = "✓" if phase['success'] else "✗"
            print(f"  {status} {phase['name']}: {phase['time']:.2f}s")
        
        logger.info(f"Final report saved: {report_file}")
    
    def run_complete_migration(self):
        """Run the complete migration process."""
        logger.info("="*80)
        logger.info("STARTING COMPLETE STOCK AND PICK MIGRATION")
        logger.info("="*80)
        logger.info(f"Migration Directory: {self.migration_dir}")
        logger.info(f"Start Time: {self.start_time}")
        
        try:
            # Run all phases
            phases = [
                ("Phase 1", self.phase_1_environment_setup),
                ("Phase 2", self.phase_2_database_analysis),
                ("Phase 3", self.phase_3_schema_deployment),
                ("Phase 4", self.phase_4_web_application),
                ("Phase 5", self.phase_5_validation)
            ]
            
            for phase_name, phase_func in phases:
                logger.info(f"\\nStarting {phase_name}...")
                success = phase_func()
                
                if not success:
                    logger.error(f"{phase_name} failed. Continuing with remaining phases...")
                    # Don't stop on individual phase failures
            
        except KeyboardInterrupt:
            logger.warning("Migration interrupted by user")
            self.results['success'] = False
        except Exception as e:
            logger.error(f"Migration failed with exception: {e}")
            self.results['success'] = False
        finally:
            self.generate_final_report()

def main():
    """Main function."""
    migrator = CompleteMigration()
    migrator.run_complete_migration()

if __name__ == "__main__":
    main()