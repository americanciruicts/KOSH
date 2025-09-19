#!/usr/bin/env python3
"""
Command-line interface for Access to PostgreSQL database migration.
"""

import click
import os
import sys
from pathlib import Path
from typing import Optional
import logging

# Add the current directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from migration_config import AccessConfig, PostgreSQLConfig, MigrationConfig
from access_analyzer import AccessAnalyzer
from schema_converter import SchemaConverter
from data_migrator import DataMigrator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@click.group()
@click.version_option(version='1.0.0')
def cli():
    """Access to PostgreSQL Database Migration Tool.
    
    This tool helps you migrate Microsoft Access databases to PostgreSQL.
    It supports schema analysis, conversion, and data migration.
    """
    pass

@cli.command()
@click.argument('access_db_path', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='Output file for analysis report')
@click.option('--json', 'output_json', is_flag=True, help='Output analysis as JSON')
def analyze(access_db_path: str, output: Optional[str], output_json: bool):
    """Analyze Access database structure and generate a report.
    
    This command will connect to your Access database and analyze its structure,
    including tables, columns, relationships, and data types.
    """
    try:
        # Create configuration
        config = AccessConfig(file_path=access_db_path)
        
        # Analyze database
        analyzer = AccessAnalyzer(config)
        db_info = analyzer.analyze_database()
        
        # Generate report
        if output_json:
            import json
            from datetime import datetime
            
            # Convert to serializable format
            analysis_data = {
                'database_path': access_db_path,
                'analysis_date': datetime.now().isoformat(),
                'total_tables': db_info.total_tables,
                'total_rows': db_info.total_rows,
                'tables': [
                    {
                        'name': table.name,
                        'columns': table.columns,
                        'row_count': table.row_count,
                        'primary_keys': table.primary_keys,
                        'foreign_keys': table.foreign_keys,
                        'indexes': table.indexes
                    }
                    for table in db_info.tables
                ],
                'relationships': db_info.relationships,
                'queries': db_info.queries
            }
            
            output_file = output or f"{access_db_path}_analysis.json"
            with open(output_file, 'w') as f:
                json.dump(analysis_data, f, indent=2)
            
            click.echo(f"Analysis saved to: {output_file}")
        else:
            # Print detailed report
            analyzer.print_analysis_report(db_info)
            
            if output:
                # Save text report
                with open(output, 'w') as f:
                    # Redirect stdout to file temporarily
                    import io
                    import contextlib
                    
                    f_stdout = io.StringIO()
                    with contextlib.redirect_stdout(f_stdout):
                        analyzer.print_analysis_report(db_info)
                    
                    f.write(f_stdout.getvalue())
                
                click.echo(f"Analysis report saved to: {output}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)

@cli.command()
@click.argument('access_db_path', type=click.Path(exists=True))
@click.option('--pg-host', default='localhost', help='PostgreSQL host')
@click.option('--pg-port', default=5432, type=int, help='PostgreSQL port')
@click.option('--pg-database', required=True, help='PostgreSQL database name')
@click.option('--pg-user', default='postgres', help='PostgreSQL username')
@click.option('--pg-password', prompt=True, hide_input=True, help='PostgreSQL password')
@click.option('--output', '-o', type=click.Path(), help='Output file for SQL schema')
@click.option('--create-indexes/--no-create-indexes', default=True, help='Create indexes')
@click.option('--preserve-relationships/--no-preserve-relationships', default=True, help='Preserve foreign key relationships')
def convert_schema(access_db_path: str, pg_host: str, pg_port: int, pg_database: str, 
                  pg_user: str, pg_password: str, output: Optional[str], 
                  create_indexes: bool, preserve_relationships: bool):
    """Convert Access database schema to PostgreSQL.
    
    This command will analyze your Access database structure and create
    equivalent PostgreSQL tables, indexes, and foreign key constraints.
    """
    try:
        # Create configuration
        config = MigrationConfig(
            access_config=AccessConfig(file_path=access_db_path),
            postgresql_config=PostgreSQLConfig(
                host=pg_host,
                port=pg_port,
                database=pg_database,
                username=pg_user,
                password=pg_password
            ),
            create_indexes=create_indexes,
            preserve_relationships=preserve_relationships
        )
        
        # Analyze Access database
        click.echo("Analyzing Access database...")\n        analyzer = AccessAnalyzer(config.access_config)\n        db_info = analyzer.analyze_database()\n        \n        # Convert schema\n        click.echo("Converting schema to PostgreSQL...")\n        converter = SchemaConverter(config)\n        result = converter.convert_database_schema(db_info)\n        \n        # Print results\n        click.echo("\\n" + "="*60)\n        click.echo("SCHEMA CONVERSION RESULTS")\n        click.echo("="*60)\n        \n        click.echo(f"Success: {result.success}")\n        click.echo(f"Tables Created: {len(result.tables_created)}")\n        click.echo(f"Errors: {len(result.errors)}")\n        click.echo(f"Warnings: {len(result.warnings)}")\n        \n        if result.tables_created:\n            click.echo(f"\\nCreated Tables: {', '.join(result.tables_created)}")\n        \n        if result.errors:\n            click.echo("\\nERRORS:", err=True)\n            for error in result.errors:\n                click.echo(f"  - {error}", err=True)\n        \n        if result.warnings:\n            click.echo("\\nWARNINGS:")\n            for warning in result.warnings:\n                click.echo(f"  - {warning}")\n        \n        # Save schema SQL\n        output_file = output or f"{access_db_path}_postgresql_schema.sql"\n        with open(output_file, 'w') as f:\n            f.write(result.postgresql_schema)\n        \n        click.echo(f"\\nPostgreSQL schema saved to: {output_file}")\n        \n        if not result.success:\n            sys.exit(1)\n        \n    except Exception as e:\n        click.echo(f"Error: {e}", err=True)\n        sys.exit(1)\n\n@cli.command()\n@click.argument('access_db_path', type=click.Path(exists=True))\n@click.option('--pg-host', default='localhost', help='PostgreSQL host')\n@click.option('--pg-port', default=5432, type=int, help='PostgreSQL port')\n@click.option('--pg-database', required=True, help='PostgreSQL database name')\n@click.option('--pg-user', default='postgres', help='PostgreSQL username')\n@click.option('--pg-password', prompt=True, hide_input=True, help='PostgreSQL password')\n@click.option('--batch-size', default=1000, type=int, help='Batch size for data migration')\n@click.option('--tables', help='Comma-separated list of tables to migrate (all if not specified)')\ndef migrate_data(access_db_path: str, pg_host: str, pg_port: int, pg_database: str, \n                pg_user: str, pg_password: str, batch_size: int, tables: Optional[str]):\n    \"\"\"Migrate data from Access to PostgreSQL.\n    \n    This command will transfer all data from your Access database to PostgreSQL.\n    Make sure you have already created the PostgreSQL schema using the convert-schema command.\n    \"\"\"\n    try:\n        # Create configuration\n        config = MigrationConfig(\n            access_config=AccessConfig(file_path=access_db_path),\n            postgresql_config=PostgreSQLConfig(\n                host=pg_host,\n                port=pg_port,\n                database=pg_database,\n                username=pg_user,\n                password=pg_password\n            ),\n            batch_size=batch_size\n        )\n        \n        # Analyze Access database\n        click.echo(\"Analyzing Access database...\")\n        analyzer = AccessAnalyzer(config.access_config)\n        db_info = analyzer.analyze_database()\n        \n        # Filter tables if specified\n        if tables:\n            table_names = [t.strip() for t in tables.split(',')]\n            db_info.tables = [t for t in db_info.tables if t.name in table_names]\n            click.echo(f\"Migrating selected tables: {', '.join(table_names)}\")\n        \n        # Migrate data\n        click.echo(\"Starting data migration...\")\n        migrator = DataMigrator(config)\n        result = migrator.migrate_database(db_info)\n        \n        # Print results\n        click.echo(\"\\n\" + \"=\"*60)\n        click.echo(\"DATA MIGRATION RESULTS\")\n        click.echo(\"=\"*60)\n        \n        click.echo(f\"Success: {result.success}\")\n        click.echo(f\"Tables Migrated: {len(result.tables_migrated)}\")\n        click.echo(f\"Total Rows Migrated: {result.total_rows_migrated:,}\")\n        click.echo(f\"Migration Time: {result.migration_time:.2f} seconds\")\n        click.echo(f\"Errors: {len(result.errors)}\")\n        click.echo(f\"Warnings: {len(result.warnings)}\")\n        \n        if result.tables_migrated:\n            click.echo(f\"\\nMigrated Tables: {', '.join(result.tables_migrated)}\")\n        \n        # Detailed table results\n        click.echo(\"\\nTABLE MIGRATION DETAILS:\")\n        click.echo(\"-\" * 60)\n        for table_name, table_result in result.table_results.items():\n            status = \"✓\" if table_result['success'] else \"✗\"\n            verification = table_result.get('verification', {})\n            match_status = \"✓\" if verification.get('match', False) else \"✗\"\n            \n            click.echo(f\"{status} {table_name}: {table_result['rows_migrated']:,} rows, \"\n                      f\"{table_result['migration_time']:.2f}s, verified: {match_status}\")\n        \n        if result.errors:\n            click.echo(\"\\nERRORS:\", err=True)\n            for error in result.errors:\n                click.echo(f\"  - {error}\", err=True)\n        \n        if result.warnings:\n            click.echo(\"\\nWARNINGS:\")\n            for warning in result.warnings:\n                click.echo(f\"  - {warning}\")\n        \n        # Save migration report\n        import json\n        from datetime import datetime\n        \n        report_file = f\"{access_db_path}_migration_report.json\"\n        with open(report_file, 'w') as f:\n            report_data = {\n                'success': result.success,\n                'tables_migrated': result.tables_migrated,\n                'total_rows_migrated': result.total_rows_migrated,\n                'migration_time': result.migration_time,\n                'errors': result.errors,\n                'warnings': result.warnings,\n                'table_results': result.table_results,\n                'migration_date': datetime.now().isoformat()\n            }\n            json.dump(report_data, f, indent=2, default=str)\n        \n        click.echo(f\"\\nMigration report saved to: {report_file}\")\n        \n        if not result.success:\n            sys.exit(1)\n        \n    except Exception as e:\n        click.echo(f\"Error: {e}\", err=True)\n        sys.exit(1)\n\n@cli.command()\n@click.argument('access_db_path', type=click.Path(exists=True))\n@click.option('--pg-host', default='localhost', help='PostgreSQL host')\n@click.option('--pg-port', default=5432, type=int, help='PostgreSQL port')\n@click.option('--pg-database', required=True, help='PostgreSQL database name')\n@click.option('--pg-user', default='postgres', help='PostgreSQL username')\n@click.option('--pg-password', prompt=True, hide_input=True, help='PostgreSQL password')\n@click.option('--batch-size', default=1000, type=int, help='Batch size for data migration')\n@click.option('--create-indexes/--no-create-indexes', default=True, help='Create indexes')\n@click.option('--preserve-relationships/--no-preserve-relationships', default=True, help='Preserve foreign key relationships')\ndef migrate_all(access_db_path: str, pg_host: str, pg_port: int, pg_database: str, \n               pg_user: str, pg_password: str, batch_size: int, \n               create_indexes: bool, preserve_relationships: bool):\n    \"\"\"Complete migration: analyze, convert schema, and migrate data.\n    \n    This command performs a complete migration from Access to PostgreSQL\n    in a single operation.\n    \"\"\"\n    try:\n        # Create configuration\n        config = MigrationConfig(\n            access_config=AccessConfig(file_path=access_db_path),\n            postgresql_config=PostgreSQLConfig(\n                host=pg_host,\n                port=pg_port,\n                database=pg_database,\n                username=pg_user,\n                password=pg_password\n            ),\n            batch_size=batch_size,\n            create_indexes=create_indexes,\n            preserve_relationships=preserve_relationships\n        )\n        \n        click.echo(\"Starting complete migration process...\")\n        click.echo(\"=\"*60)\n        \n        # Step 1: Analyze database\n        click.echo(\"Step 1: Analyzing Access database...\")\n        analyzer = AccessAnalyzer(config.access_config)\n        db_info = analyzer.analyze_database()\n        click.echo(f\"Found {db_info.total_tables} tables with {db_info.total_rows:,} total rows\")\n        \n        # Step 2: Convert schema\n        click.echo(\"\\nStep 2: Converting schema to PostgreSQL...\")\n        converter = SchemaConverter(config)\n        schema_result = converter.convert_database_schema(db_info)\n        \n        if not schema_result.success:\n            click.echo(\"Schema conversion failed!\", err=True)\n            for error in schema_result.errors:\n                click.echo(f\"  - {error}\", err=True)\n            sys.exit(1)\n        \n        click.echo(f\"Schema converted successfully: {len(schema_result.tables_created)} tables created\")\n        \n        # Step 3: Migrate data\n        click.echo(\"\\nStep 3: Migrating data...\")\n        migrator = DataMigrator(config)\n        migration_result = migrator.migrate_database(db_info)\n        \n        # Final results\n        click.echo(\"\\n\" + \"=\"*60)\n        click.echo(\"COMPLETE MIGRATION RESULTS\")\n        click.echo(\"=\"*60)\n        \n        click.echo(f\"Schema Conversion: {'✓' if schema_result.success else '✗'}\")\n        click.echo(f\"Data Migration: {'✓' if migration_result.success else '✗'}\")\n        click.echo(f\"Tables Migrated: {len(migration_result.tables_migrated)}\")\n        click.echo(f\"Total Rows Migrated: {migration_result.total_rows_migrated:,}\")\n        click.echo(f\"Total Time: {migration_result.migration_time:.2f} seconds\")\n        \n        # Save complete report\n        import json\n        from datetime import datetime\n        \n        report_file = f\"{access_db_path}_complete_migration_report.json\"\n        with open(report_file, 'w') as f:\n            report_data = {\n                'migration_type': 'complete',\n                'source_database': access_db_path,\n                'target_database': pg_database,\n                'migration_date': datetime.now().isoformat(),\n                'schema_conversion': {\n                    'success': schema_result.success,\n                    'tables_created': schema_result.tables_created,\n                    'errors': schema_result.errors,\n                    'warnings': schema_result.warnings\n                },\n                'data_migration': {\n                    'success': migration_result.success,\n                    'tables_migrated': migration_result.tables_migrated,\n                    'total_rows_migrated': migration_result.total_rows_migrated,\n                    'migration_time': migration_result.migration_time,\n                    'errors': migration_result.errors,\n                    'warnings': migration_result.warnings,\n                    'table_results': migration_result.table_results\n                }\n            }\n            json.dump(report_data, f, indent=2, default=str)\n        \n        click.echo(f\"\\nComplete migration report saved to: {report_file}\")\n        \n        if not (schema_result.success and migration_result.success):\n            sys.exit(1)\n        \n    except Exception as e:\n        click.echo(f\"Error: {e}\", err=True)\n        sys.exit(1)\n\nif __name__ == '__main__':\n    cli()