"""Convert Access database schema to PostgreSQL schema."""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import sqlalchemy as sa
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, Text, Boolean, DateTime, Date, Time, Numeric, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, BYTEA
from sqlalchemy.sql import text

from migration_config import MigrationConfig, quote_identifier, POSTGRESQL_RESERVED_WORDS
from access_analyzer import AccessAnalyzer, DatabaseInfo, TableInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class ConversionResult:
    """Result of schema conversion."""
    success: bool
    postgresql_schema: str
    tables_created: List[str]
    errors: List[str]
    warnings: List[str]

class SchemaConverter:
    """Convert Access database schema to PostgreSQL."""
    
    def __init__(self, config: MigrationConfig):
        self.config = config
        self.pg_engine = None
        self.metadata = MetaData()
        
    def connect_postgresql(self):
        """Connect to PostgreSQL database."""
        try:
            conn_string = self.config.postgresql_config.get_connection_string()
            self.pg_engine = create_engine(conn_string)
            logger.info("Connected to PostgreSQL database")
        except Exception as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            raise
    
    def map_access_type_to_postgresql(self, access_type: str, size: Optional[int] = None) -> sa.types.TypeEngine:
        """Map Access data type to PostgreSQL data type."""
        access_type_upper = access_type.upper()
        
        # Handle specific type mappings
        if access_type_upper in ['COUNTER', 'AUTOINCREMENT']:
            return sa.INTEGER  # Will be handled as SERIAL in CREATE TABLE
        elif access_type_upper in ['LONG', 'INTEGER']:
            return sa.INTEGER
        elif access_type_upper in ['SHORT', 'BYTE']:
            return sa.SMALLINT
        elif access_type_upper == 'SINGLE':
            return sa.REAL
        elif access_type_upper == 'DOUBLE':
            return sa.DOUBLE_PRECISION
        elif access_type_upper == 'CURRENCY':
            return sa.NUMERIC(19, 4)
        elif access_type_upper == 'TEXT':
            if size and size > 0:
                return sa.VARCHAR(size)
            else:
                return sa.VARCHAR(255)  # Default varchar size
        elif access_type_upper in ['MEMO', 'LONGTEXT']:
            return sa.TEXT
        elif access_type_upper == 'DATETIME':
            return sa.TIMESTAMP
        elif access_type_upper == 'DATE':
            return sa.DATE
        elif access_type_upper == 'TIME':
            return sa.TIME
        elif access_type_upper in ['YESNO', 'BOOLEAN']:
            return sa.BOOLEAN
        elif access_type_upper in ['BINARY', 'VARBINARY', 'OLEOBJECT']:
            return BYTEA
        elif access_type_upper in ['HYPERLINK']:
            return sa.TEXT
        elif access_type_upper == 'GUID':
            return UUID
        else:
            # Default to TEXT for unknown types
            logger.warning(f"Unknown Access type '{access_type}', defaulting to TEXT")
            return sa.TEXT
    
    def convert_table_schema(self, table_info: TableInfo) -> Table:
        """Convert a single table schema from Access to PostgreSQL."""
        # Clean table name
        table_name = quote_identifier(table_info.name)
        
        # Create columns
        columns = []
        for col_info in table_info.columns:
            col_name = quote_identifier(col_info['name'])
            col_type = self.map_access_type_to_postgresql(col_info['type'], col_info['size'])
            
            # Handle auto-increment columns
            if col_info['type'].upper() in ['COUNTER', 'AUTOINCREMENT']:
                if col_info['name'] in table_info.primary_keys:
                    # Use SERIAL for primary key auto-increment
                    columns.append(Column(col_name, sa.INTEGER, primary_key=True, autoincrement=True))
                    continue
            
            # Create column
            column_kwargs = {
                'nullable': col_info['nullable'],
            }
            
            # Handle default values
            if col_info['default']:
                column_kwargs['default'] = col_info['default']
            
            # Handle primary keys
            if col_info['name'] in table_info.primary_keys:
                column_kwargs['primary_key'] = True
            
            columns.append(Column(col_name, col_type, **column_kwargs))
        
        # Create table
        table = Table(table_name, self.metadata, *columns)
        
        return table
    
    def generate_foreign_keys(self, db_info: DatabaseInfo) -> List[str]:
        """Generate foreign key constraint SQL statements."""
        fk_statements = []\n        \n        for table in db_info.tables:\n            for fk in table.foreign_keys:\n                fk_sql = f\"\"\"ALTER TABLE {quote_identifier(table.name)} \n                ADD CONSTRAINT {quote_identifier(fk['constraint_name'] or f'fk_{table.name}_{fk['column']}')} \n                FOREIGN KEY ({quote_identifier(fk['column'])}) \n                REFERENCES {quote_identifier(fk['referenced_table'])}({quote_identifier(fk['referenced_column'])});\"\"\"\n                fk_statements.append(fk_sql)\n        \n        return fk_statements\n    \n    def generate_indexes(self, db_info: DatabaseInfo) -> List[str]:\n        \"\"\"Generate index creation SQL statements.\"\"\"\n        index_statements = []\n        \n        for table in db_info.tables:\n            # Group indexes by name (composite indexes)\n            indexes_by_name = {}\n            for idx in table.indexes:\n                idx_name = idx['name']\n                if idx_name not in indexes_by_name:\n                    indexes_by_name[idx_name] = []\n                indexes_by_name[idx_name].append(idx)\n            \n            for idx_name, idx_columns in indexes_by_name.items():\n                # Skip primary key indexes (already handled)\n                if any(col['column'] in table.primary_keys for col in idx_columns):\n                    continue\n                \n                # Sort by ordinal position\n                idx_columns.sort(key=lambda x: x['ordinal_position'])\n                \n                # Generate column list\n                column_list = ', '.join(quote_identifier(col['column']) for col in idx_columns)\n                \n                # Check if unique\n                is_unique = all(col['unique'] for col in idx_columns)\n                unique_clause = 'UNIQUE ' if is_unique else ''\n                \n                # Generate index SQL\n                index_sql = f\"\"\"CREATE {unique_clause}INDEX {quote_identifier(idx_name)} \n                ON {quote_identifier(table.name)} ({column_list});\"\"\"\n                index_statements.append(index_sql)\n        \n        return index_statements\n    \n    def convert_database_schema(self, db_info: DatabaseInfo) -> ConversionResult:\n        \"\"\"Convert entire database schema from Access to PostgreSQL.\"\"\"\n        logger.info(\"Starting schema conversion...\")\n        \n        errors = []\n        warnings = []\n        tables_created = []\n        \n        try:\n            self.connect_postgresql()\n            \n            # Convert tables\n            for table_info in db_info.tables:\n                try:\n                    table = self.convert_table_schema(table_info)\n                    tables_created.append(table_info.name)\n                    logger.info(f\"Converted table: {table_info.name}\")\n                except Exception as e:\n                    error_msg = f\"Failed to convert table {table_info.name}: {e}\"\n                    errors.append(error_msg)\n                    logger.error(error_msg)\n            \n            # Create all tables\n            if not errors:\n                try:\n                    self.metadata.create_all(self.pg_engine)\n                    logger.info(\"Created all tables in PostgreSQL\")\n                except Exception as e:\n                    error_msg = f\"Failed to create tables in PostgreSQL: {e}\"\n                    errors.append(error_msg)\n                    logger.error(error_msg)\n            \n            # Generate foreign keys\n            fk_statements = self.generate_foreign_keys(db_info)\n            \n            # Generate indexes\n            index_statements = self.generate_indexes(db_info)\n            \n            # Generate complete schema SQL\n            schema_sql = self.generate_schema_sql(db_info, fk_statements, index_statements)\n            \n            # Apply foreign keys and indexes if requested\n            if self.config.preserve_relationships and not errors:\n                try:\n                    with self.pg_engine.connect() as conn:\n                        for fk_sql in fk_statements:\n                            conn.execute(text(fk_sql))\n                        conn.commit()\n                    logger.info(\"Applied foreign key constraints\")\n                except Exception as e:\n                    warning_msg = f\"Failed to apply foreign keys: {e}\"\n                    warnings.append(warning_msg)\n                    logger.warning(warning_msg)\n            \n            if self.config.create_indexes and not errors:\n                try:\n                    with self.pg_engine.connect() as conn:\n                        for idx_sql in index_statements:\n                            conn.execute(text(idx_sql))\n                        conn.commit()\n                    logger.info(\"Created indexes\")\n                except Exception as e:\n                    warning_msg = f\"Failed to create indexes: {e}\"\n                    warnings.append(warning_msg)\n                    logger.warning(warning_msg)\n            \n            return ConversionResult(\n                success=len(errors) == 0,\n                postgresql_schema=schema_sql,\n                tables_created=tables_created,\n                errors=errors,\n                warnings=warnings\n            )\n            \n        except Exception as e:\n            error_msg = f\"Schema conversion failed: {e}\"\n            errors.append(error_msg)\n            logger.error(error_msg)\n            \n            return ConversionResult(\n                success=False,\n                postgresql_schema=\"\",\n                tables_created=[],\n                errors=errors,\n                warnings=warnings\n            )\n    \n    def generate_schema_sql(self, db_info: DatabaseInfo, fk_statements: List[str], index_statements: List[str]) -> str:\n        \"\"\"Generate complete PostgreSQL schema SQL.\"\"\"\n        sql_parts = []\n        \n        # Header\n        sql_parts.append(\"-- PostgreSQL Schema Generated from Access Database\")\n        sql_parts.append(f\"-- Source: {self.config.access_config.file_path}\")\n        sql_parts.append(f\"-- Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\")\n        sql_parts.append(\"\")\n        \n        # Create tables\n        sql_parts.append(\"-- Create Tables\")\n        for table in self.metadata.tables.values():\n            sql_parts.append(str(sa.schema.CreateTable(table).compile(self.pg_engine)))\n            sql_parts.append(\"\")\n        \n        # Foreign keys\n        if fk_statements:\n            sql_parts.append(\"-- Foreign Key Constraints\")\n            sql_parts.extend(fk_statements)\n            sql_parts.append(\"\")\n        \n        # Indexes\n        if index_statements:\n            sql_parts.append(\"-- Indexes\")\n            sql_parts.extend(index_statements)\n            sql_parts.append(\"\")\n        \n        return \"\\n\".join(sql_parts)\n\ndef main():\n    \"\"\"Main function to run the schema converter.\"\"\"\n    import sys\n    from datetime import datetime\n    \n    if len(sys.argv) < 2:\n        print(\"Usage: python schema_converter.py <access_db_path> [postgresql_db_name]\")\n        sys.exit(1)\n    \n    db_path = sys.argv[1]\n    pg_db_name = sys.argv[2] if len(sys.argv) > 2 else \"migrated_db\"\n    \n    # Create configuration\n    from migration_config import AccessConfig, PostgreSQLConfig, MigrationConfig\n    \n    config = MigrationConfig(\n        access_config=AccessConfig(file_path=db_path),\n        postgresql_config=PostgreSQLConfig(database=pg_db_name)\n    )\n    \n    # Analyze Access database\n    analyzer = AccessAnalyzer(config.access_config)\n    db_info = analyzer.analyze_database()\n    \n    # Convert schema\n    converter = SchemaConverter(config)\n    result = converter.convert_database_schema(db_info)\n    \n    # Print results\n    print(\"\\n\" + \"=\"*80)\n    print(\"SCHEMA CONVERSION RESULTS\")\n    print(\"=\"*80)\n    \n    print(f\"Success: {result.success}\")\n    print(f\"Tables Created: {len(result.tables_created)}\")\n    print(f\"Errors: {len(result.errors)}\")\n    print(f\"Warnings: {len(result.warnings)}\")\n    \n    if result.tables_created:\n        print(f\"\\nCreated Tables: {', '.join(result.tables_created)}\")\n    \n    if result.errors:\n        print(\"\\nErrors:\")\n        for error in result.errors:\n            print(f\"  - {error}\")\n    \n    if result.warnings:\n        print(\"\\nWarnings:\")\n        for warning in result.warnings:\n            print(f\"  - {warning}\")\n    \n    # Save schema SQL\n    schema_file = f\"{db_path}_postgresql_schema.sql\"\n    with open(schema_file, 'w') as f:\n        f.write(result.postgresql_schema)\n    \n    print(f\"\\nPostgreSQL schema saved to: {schema_file}\")\n\nif __name__ == \"__main__\":\n    main()