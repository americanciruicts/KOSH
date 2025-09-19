"""Configuration settings for Access to PostgreSQL migration."""

import os
from typing import Dict, Any
from dataclasses import dataclass

@dataclass
class AccessConfig:
    """Configuration for Access database connection."""
    file_path: str
    driver: str = "Microsoft Access Driver (*.mdb, *.accdb)"
    
    def get_connection_string(self) -> str:
        """Generate ODBC connection string for Access database."""
        return f"DRIVER={{{self.driver}}};DBQ={self.file_path};ExtendedAnsiSQL=1;"

@dataclass
class PostgreSQLConfig:
    """Configuration for PostgreSQL database connection."""
    host: str = "localhost"
    port: int = 5432
    database: str = "migrated_db"
    username: str = "postgres"
    password: str = "password"
    
    def get_connection_string(self) -> str:
        """Generate PostgreSQL connection string."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class MigrationConfig:
    """Main migration configuration."""
    access_config: AccessConfig
    postgresql_config: PostgreSQLConfig
    
    # Migration options
    batch_size: int = 1000
    create_indexes: bool = True
    preserve_relationships: bool = True
    convert_autonumber_to_serial: bool = True
    
    # Data type mappings
    type_mappings: Dict[str, str] = None
    
    def __post_init__(self):
        """Initialize default type mappings."""
        if self.type_mappings is None:
            self.type_mappings = {
                # Access -> PostgreSQL type mappings
                'COUNTER': 'SERIAL',
                'AUTOINCREMENT': 'SERIAL',
                'LONG': 'INTEGER',
                'INTEGER': 'INTEGER',
                'SHORT': 'SMALLINT',
                'BYTE': 'SMALLINT',
                'SINGLE': 'REAL',
                'DOUBLE': 'DOUBLE PRECISION',
                'CURRENCY': 'DECIMAL(19,4)',
                'TEXT': 'VARCHAR',
                'MEMO': 'TEXT',
                'LONGTEXT': 'TEXT',
                'DATETIME': 'TIMESTAMP',
                'DATE': 'DATE',
                'TIME': 'TIME',
                'YESNO': 'BOOLEAN',
                'BOOLEAN': 'BOOLEAN',
                'BINARY': 'BYTEA',
                'VARBINARY': 'BYTEA',
                'OLEOBJECT': 'BYTEA',
                'HYPERLINK': 'TEXT',
                'GUID': 'UUID'
            }

# Default configuration
DEFAULT_CONFIG = MigrationConfig(
    access_config=AccessConfig(
        file_path="database.mdb"
    ),
    postgresql_config=PostgreSQLConfig(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        database=os.getenv("DB_NAME", "migrated_db"),
        username=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "password")
    )
)

# Reserved keywords that need quoting in PostgreSQL
POSTGRESQL_RESERVED_WORDS = {
    'user', 'order', 'group', 'table', 'column', 'index', 'key', 'value',
    'date', 'time', 'year', 'month', 'day', 'hour', 'minute', 'second',
    'primary', 'foreign', 'references', 'constraint', 'check', 'unique',
    'default', 'not', 'null', 'true', 'false', 'select', 'insert', 'update',
    'delete', 'create', 'drop', 'alter', 'grant', 'revoke', 'union', 'join',
    'where', 'having', 'limit', 'offset', 'distinct', 'all', 'and', 'or',
    'in', 'exists', 'between', 'like', 'is', 'as', 'desc', 'asc'
}

def quote_identifier(name: str) -> str:
    """Quote PostgreSQL identifier if it's a reserved word or contains special characters."""
    if (name.lower() in POSTGRESQL_RESERVED_WORDS or 
        not name.isalnum() or 
        name[0].isdigit() or 
        ' ' in name or 
        '-' in name):
        return f'"{name}"'
    return name