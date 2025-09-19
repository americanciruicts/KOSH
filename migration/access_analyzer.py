"""Analyze Microsoft Access database structure and generate schema information."""

import pyodbc
import pandas as pd
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from tabulate import tabulate
import logging

from migration_config import AccessConfig, quote_identifier

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class TableInfo:
    """Information about a database table."""
    name: str
    columns: List[Dict[str, Any]]
    row_count: int
    primary_keys: List[str]
    foreign_keys: List[Dict[str, str]]
    indexes: List[Dict[str, Any]]

@dataclass
class DatabaseInfo:
    """Complete database information."""
    tables: List[TableInfo]
    relationships: List[Dict[str, Any]]
    queries: List[str]
    total_tables: int
    total_rows: int

class AccessAnalyzer:
    """Analyze Microsoft Access database structure."""
    
    def __init__(self, config: AccessConfig):
        self.config = config
        self.connection = None
        
    def connect(self):
        """Connect to Access database."""
        try:
            conn_string = self.config.get_connection_string()
            self.connection = pyodbc.connect(conn_string)
            logger.info(f"Connected to Access database: {self.config.file_path}")
        except Exception as e:
            logger.error(f"Failed to connect to Access database: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from Access database."""
        if self.connection:
            self.connection.close()
            logger.info("Disconnected from Access database")
    
    def get_table_names(self) -> List[str]:
        """Get all table names from the database."""
        cursor = self.connection.cursor()
        
        # Get user tables (exclude system tables)
        tables = []
        for table_info in cursor.tables(tableType='TABLE'):
            table_name = table_info.table_name
            if not table_name.startswith('MSys'):  # Skip system tables
                tables.append(table_name)
        
        logger.info(f"Found {len(tables)} tables: {tables}")
        return tables
    
    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column information for a table."""
        cursor = self.connection.cursor()
        columns = []
        
        for column in cursor.columns(table=table_name):
            column_info = {
                'name': column.column_name,
                'type': column.type_name,
                'size': column.column_size,
                'nullable': column.nullable == 1,
                'default': column.column_def,
                'ordinal_position': column.ordinal_position
            }
            columns.append(column_info)
        
        return sorted(columns, key=lambda x: x['ordinal_position'])
    
    def get_primary_keys(self, table_name: str) -> List[str]:
        """Get primary key columns for a table."""
        cursor = self.connection.cursor()
        primary_keys = []
        
        try:
            for pk in cursor.primaryKeys(table_name):
                primary_keys.append(pk.column_name)
        except Exception as e:
            logger.warning(f"Could not get primary keys for {table_name}: {e}")
        
        return primary_keys
    
    def get_foreign_keys(self, table_name: str) -> List[Dict[str, str]]:
        """Get foreign key relationships for a table."""
        cursor = self.connection.cursor()
        foreign_keys = []
        
        try:
            for fk in cursor.foreignKeys(table_name):
                fk_info = {
                    'column': fk.fkcolumn_name,
                    'referenced_table': fk.pktable_name,
                    'referenced_column': fk.pkcolumn_name,
                    'constraint_name': fk.fk_name
                }
                foreign_keys.append(fk_info)
        except Exception as e:
            logger.warning(f"Could not get foreign keys for {table_name}: {e}")
        
        return foreign_keys
    
    def get_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Get index information for a table."""
        cursor = self.connection.cursor()
        indexes = []
        
        try:
            for index in cursor.statistics(table_name):
                if index.index_name:  # Skip table statistics
                    index_info = {
                        'name': index.index_name,
                        'column': index.column_name,
                        'unique': not index.non_unique,
                        'ordinal_position': index.ordinal_position
                    }
                    indexes.append(index_info)
        except Exception as e:
            logger.warning(f"Could not get indexes for {table_name}: {e}")
        
        return indexes
    
    def get_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        cursor = self.connection.cursor()
        try:
            quoted_table = quote_identifier(table_name)
            cursor.execute(f"SELECT COUNT(*) FROM {quoted_table}")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.warning(f"Could not get row count for {table_name}: {e}")
            return 0
    
    def get_sample_data(self, table_name: str, limit: int = 5) -> pd.DataFrame:
        """Get sample data from a table."""
        try:
            quoted_table = quote_identifier(table_name)
            query = f"SELECT TOP {limit} * FROM {quoted_table}"
            return pd.read_sql(query, self.connection)
        except Exception as e:
            logger.warning(f"Could not get sample data for {table_name}: {e}")
            return pd.DataFrame()
    
    def analyze_table(self, table_name: str) -> TableInfo:
        """Analyze a single table and return comprehensive information."""
        logger.info(f"Analyzing table: {table_name}")
        
        columns = self.get_table_columns(table_name)
        row_count = self.get_row_count(table_name)
        primary_keys = self.get_primary_keys(table_name)
        foreign_keys = self.get_foreign_keys(table_name)
        indexes = self.get_indexes(table_name)
        
        return TableInfo(
            name=table_name,
            columns=columns,
            row_count=row_count,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes
        )
    
    def analyze_database(self) -> DatabaseInfo:
        """Analyze the entire database structure."""
        logger.info("Starting database analysis...")
        
        self.connect()
        
        try:
            table_names = self.get_table_names()
            tables = []
            total_rows = 0
            
            for table_name in table_names:
                table_info = self.analyze_table(table_name)
                tables.append(table_info)
                total_rows += table_info.row_count
            
            # Get relationships (aggregated from foreign keys)
            relationships = []
            for table in tables:
                for fk in table.foreign_keys:
                    relationships.append({
                        'from_table': table.name,
                        'from_column': fk['column'],
                        'to_table': fk['referenced_table'],
                        'to_column': fk['referenced_column'],
                        'constraint_name': fk['constraint_name']
                    })
            
            # Get queries/views (Access stored queries)
            queries = []
            try:
                cursor = self.connection.cursor()
                for table_info in cursor.tables(tableType='VIEW'):
                    queries.append(table_info.table_name)
            except Exception as e:
                logger.warning(f"Could not get queries: {e}")
            
            return DatabaseInfo(
                tables=tables,
                relationships=relationships,
                queries=queries,
                total_tables=len(tables),
                total_rows=total_rows
            )
            
        finally:
            self.disconnect()
    
    def print_analysis_report(self, db_info: DatabaseInfo):
        """Print a detailed analysis report."""
        print("\n" + "="*80)
        print("ACCESS DATABASE ANALYSIS REPORT")
        print("="*80)
        
        print(f"\nDatabase: {self.config.file_path}")
        print(f"Total Tables: {db_info.total_tables}")
        print(f"Total Rows: {db_info.total_rows:,}")
        print(f"Total Relationships: {len(db_info.relationships)}")
        print(f"Total Queries/Views: {len(db_info.queries)}")
        
        # Table summary
        print("\nTABLE SUMMARY:")
        print("-" * 80)
        table_data = []
        for table in db_info.tables:
            table_data.append([
                table.name,
                len(table.columns),
                f"{table.row_count:,}",
                len(table.primary_keys),
                len(table.foreign_keys),
                len(table.indexes)
            ])
        
        print(tabulate(table_data, 
                      headers=['Table Name', 'Columns', 'Rows', 'Primary Keys', 'Foreign Keys', 'Indexes'],
                      tablefmt='grid'))
        
        # Detailed table information
        for table in db_info.tables:
            print(f"\n{'='*60}")
            print(f"TABLE: {table.name}")
            print(f"{'='*60}")
            print(f"Rows: {table.row_count:,}")
            print(f"Primary Keys: {', '.join(table.primary_keys) if table.primary_keys else 'None'}")
            
            # Column details
            print("\nCOLUMNS:")
            column_data = []
            for col in table.columns:
                column_data.append([
                    col['name'],
                    col['type'],
                    col['size'] if col['size'] else '',
                    'Yes' if col['nullable'] else 'No',
                    col['default'] if col['default'] else ''
                ])
            
            print(tabulate(column_data,
                          headers=['Column', 'Type', 'Size', 'Nullable', 'Default'],
                          tablefmt='grid'))
            
            # Foreign keys
            if table.foreign_keys:
                print("\nFOREIGN KEYS:")
                fk_data = []
                for fk in table.foreign_keys:
                    fk_data.append([
                        fk['column'],
                        fk['referenced_table'],
                        fk['referenced_column']
                    ])
                print(tabulate(fk_data,
                              headers=['Column', 'References Table', 'References Column'],
                              tablefmt='grid'))
            
            # Indexes
            if table.indexes:
                print("\nINDEXES:")
                index_data = []
                for idx in table.indexes:
                    index_data.append([
                        idx['name'],
                        idx['column'],
                        'Yes' if idx['unique'] else 'No'
                    ])
                print(tabulate(index_data,
                              headers=['Index Name', 'Column', 'Unique'],
                              tablefmt='grid'))
        
        # Relationships
        if db_info.relationships:
            print(f"\n{'='*60}")
            print("RELATIONSHIPS")
            print(f"{'='*60}")
            rel_data = []
            for rel in db_info.relationships:
                rel_data.append([
                    f"{rel['from_table']}.{rel['from_column']}",
                    f"{rel['to_table']}.{rel['to_column']}"
                ])
            print(tabulate(rel_data,
                          headers=['From', 'To'],
                          tablefmt='grid'))
        
        # Queries/Views
        if db_info.queries:
            print(f"\n{'='*60}")
            print("QUERIES/VIEWS")
            print(f"{'='*60}")
            for query in db_info.queries:
                print(f"- {query}")

def main():
    """Main function to run the analyzer."""
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python access_analyzer.py <access_db_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    
    config = AccessConfig(file_path=db_path)
    analyzer = AccessAnalyzer(config)
    
    try:
        db_info = analyzer.analyze_database()
        analyzer.print_analysis_report(db_info)
        
        # Save analysis to file
        import json
        analysis_file = f"{db_path}_analysis.json"
        with open(analysis_file, 'w') as f:
            # Convert to serializable format
            serializable_data = {
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
            json.dump(serializable_data, f, indent=2)
        
        print(f"\nAnalysis saved to: {analysis_file}")
        
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()