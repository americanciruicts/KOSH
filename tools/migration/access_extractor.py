"""
Extract forms, reports, queries, and other objects from Microsoft Access databases.
This tool helps capture the complete application structure for migration planning.
"""

import os
import sys
import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
import subprocess
import tempfile
from pathlib import Path

# Try to import Access-specific libraries
try:
    import win32com.client
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    import pyodbc
    PYODBC_AVAILABLE = True
except ImportError:
    PYODBC_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class AccessObject:
    """Base class for Access database objects."""
    name: str
    type: str
    date_created: Optional[str] = None
    date_modified: Optional[str] = None

@dataclass
class AccessForm(AccessObject):
    """Access form object."""
    record_source: Optional[str] = None
    controls: List[Dict[str, Any]] = None
    properties: Dict[str, Any] = None
    code: Optional[str] = None

@dataclass
class AccessReport(AccessObject):
    """Access report object."""
    record_source: Optional[str] = None
    controls: List[Dict[str, Any]] = None
    properties: Dict[str, Any] = None
    code: Optional[str] = None

@dataclass
class AccessQuery(AccessObject):
    """Access query object."""
    sql: Optional[str] = None
    query_type: Optional[str] = None
    parameters: List[Dict[str, Any]] = None

@dataclass
class AccessMacro(AccessObject):
    """Access macro object."""
    actions: List[Dict[str, Any]] = None
    conditions: List[str] = None

@dataclass
class AccessModule(AccessObject):
    """Access module object."""
    code: Optional[str] = None
    procedures: List[str] = None

@dataclass
class AccessTable(AccessObject):
    """Access table object."""
    fields: List[Dict[str, Any]] = None
    indexes: List[Dict[str, Any]] = None
    relationships: List[Dict[str, Any]] = None

@dataclass
class AccessExtraction:
    """Complete Access database extraction."""
    database_path: str
    extraction_date: str
    tables: List[AccessTable]
    forms: List[AccessForm]
    reports: List[AccessReport]
    queries: List[AccessQuery]
    macros: List[AccessMacro]
    modules: List[AccessModule]
    relationships: List[Dict[str, Any]]
    database_properties: Dict[str, Any]

class AccessExtractor:
    """Extract all objects from Microsoft Access database."""
    
    def __init__(self, database_path: str):
        self.database_path = database_path
        self.access_app = None
        self.db = None
        
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    def connect(self):
        """Connect to Access database using COM automation."""
        if not WIN32_AVAILABLE:
            raise RuntimeError("win32com.client is required for Access extraction on Windows")
        
        try:
            # Create Access application instance
            self.access_app = win32com.client.Dispatch("Access.Application")
            self.access_app.Visible = False
            
            # Open the database
            self.access_app.OpenCurrentDatabase(self.database_path)
            self.db = self.access_app.CurrentDb()
            
            logger.info(f"Connected to Access database: {self.database_path}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Access database: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from Access database."""
        try:
            if self.access_app:
                self.access_app.CloseCurrentDatabase()
                self.access_app.Quit()
                self.access_app = None
                logger.info("Disconnected from Access database")
        except Exception as e:
            logger.warning(f"Error disconnecting from Access: {e}")
    
    def extract_tables(self) -> List[AccessTable]:
        """Extract all tables from the database."""
        tables = []
        
        try:
            table_defs = self.db.TableDefs
            
            for i in range(table_defs.Count):
                table_def = table_defs.Item(i)
                
                # Skip system tables
                if table_def.Name.startswith('MSys'):
                    continue
                
                # Extract table information
                table = AccessTable(
                    name=table_def.Name,
                    type="Table",
                    date_created=str(table_def.DateCreated) if hasattr(table_def, 'DateCreated') else None,
                    fields=self._extract_table_fields(table_def),
                    indexes=self._extract_table_indexes(table_def)
                )
                
                tables.append(table)
                logger.info(f"Extracted table: {table.name}")
        
        except Exception as e:
            logger.error(f"Error extracting tables: {e}")
        
        return tables
    
    def _extract_table_fields(self, table_def) -> List[Dict[str, Any]]:
        """Extract field information from a table."""
        fields = []
        
        try:
            for i in range(table_def.Fields.Count):
                field = table_def.Fields.Item(i)
                
                field_info = {
                    'name': field.Name,
                    'type': field.Type,
                    'size': field.Size if hasattr(field, 'Size') else None,
                    'required': field.Required if hasattr(field, 'Required') else False,
                    'allow_zero_length': field.AllowZeroLength if hasattr(field, 'AllowZeroLength') else False,
                    'default_value': field.DefaultValue if hasattr(field, 'DefaultValue') else None,
                    'validation_rule': field.ValidationRule if hasattr(field, 'ValidationRule') else None
                }
                
                fields.append(field_info)
        
        except Exception as e:
            logger.warning(f"Error extracting fields for table {table_def.Name}: {e}")
        
        return fields
    
    def _extract_table_indexes(self, table_def) -> List[Dict[str, Any]]:
        """Extract index information from a table."""
        indexes = []
        
        try:
            for i in range(table_def.Indexes.Count):
                index = table_def.Indexes.Item(i)
                
                index_info = {
                    'name': index.Name,
                    'primary': index.Primary if hasattr(index, 'Primary') else False,
                    'unique': index.Unique if hasattr(index, 'Unique') else False,
                    'fields': []
                }
                
                # Extract index fields
                for j in range(index.Fields.Count):
                    field = index.Fields.Item(j)
                    index_info['fields'].append({
                        'name': field.Name,
                        'descending': field.Descending if hasattr(field, 'Descending') else False
                    })
                
                indexes.append(index_info)
        
        except Exception as e:
            logger.warning(f"Error extracting indexes for table {table_def.Name}: {e}")
        
        return indexes
    
    def extract_forms(self) -> List[AccessForm]:
        """Extract all forms from the database."""
        forms = []
        
        try:
            # Get all form objects
            for obj in self.access_app.CurrentProject.AllForms:
                try:
                    # Open form in design view
                    self.access_app.DoCmd.OpenForm(obj.Name, 0)  # 0 = Design View
                    form_obj = self.access_app.Forms(obj.Name)
                    
                    form = AccessForm(
                        name=obj.Name,
                        type="Form",
                        date_created=str(obj.DateCreated) if hasattr(obj, 'DateCreated') else None,
                        date_modified=str(obj.DateModified) if hasattr(obj, 'DateModified') else None,
                        record_source=form_obj.RecordSource if hasattr(form_obj, 'RecordSource') else None,
                        controls=self._extract_form_controls(form_obj),
                        properties=self._extract_form_properties(form_obj),
                        code=self._extract_form_code(form_obj)
                    )
                    
                    forms.append(form)
                    logger.info(f"Extracted form: {form.name}")
                    
                    # Close form
                    self.access_app.DoCmd.Close(2, obj.Name)  # 2 = acForm
                
                except Exception as e:
                    logger.warning(f"Error extracting form {obj.Name}: {e}")
        
        except Exception as e:
            logger.error(f"Error extracting forms: {e}")
        
        return forms
    
    def _extract_form_controls(self, form_obj) -> List[Dict[str, Any]]:
        """Extract control information from a form."""
        controls = []
        
        try:
            for i in range(form_obj.Controls.Count):
                control = form_obj.Controls.Item(i)
                
                control_info = {
                    'name': control.Name if hasattr(control, 'Name') else f"Control_{i}",
                    'type': control.ControlType if hasattr(control, 'ControlType') else None,
                    'caption': control.Caption if hasattr(control, 'Caption') else None,
                    'control_source': control.ControlSource if hasattr(control, 'ControlSource') else None,
                    'visible': control.Visible if hasattr(control, 'Visible') else True,
                    'enabled': control.Enabled if hasattr(control, 'Enabled') else True,
                    'tab_stop': control.TabStop if hasattr(control, 'TabStop') else True,
                    'tag': control.Tag if hasattr(control, 'Tag') else None
                }
                
                controls.append(control_info)
        
        except Exception as e:
            logger.warning(f"Error extracting controls: {e}")
        
        return controls
    
    def _extract_form_properties(self, form_obj) -> Dict[str, Any]:
        """Extract properties from a form."""
        properties = {}
        
        try:
            # Common form properties
            property_names = [
                'Caption', 'RecordSource', 'Filter', 'OrderBy', 'AllowEdits',
                'AllowAdditions', 'AllowDeletions', 'DataEntry', 'DefaultView',
                'ViewsAllowed', 'ScrollBars', 'RecordSelectors', 'NavigationButtons'
            ]
            
            for prop_name in property_names:
                try:
                    if hasattr(form_obj, prop_name):
                        properties[prop_name] = getattr(form_obj, prop_name)
                except Exception:
                    pass
        
        except Exception as e:
            logger.warning(f"Error extracting form properties: {e}")
        
        return properties
    
    def _extract_form_code(self, form_obj) -> Optional[str]:
        """Extract VBA code from a form."""
        try:
            if hasattr(form_obj, 'Module'):
                return form_obj.Module.CountOfLines
        except Exception as e:
            logger.warning(f"Error extracting form code: {e}")
        
        return None
    
    def extract_reports(self) -> List[AccessReport]:
        """Extract all reports from the database."""
        reports = []
        
        try:
            # Get all report objects
            for obj in self.access_app.CurrentProject.AllReports:
                try:
                    # Open report in design view
                    self.access_app.DoCmd.OpenReport(obj.Name, 0)  # 0 = Design View
                    report_obj = self.access_app.Reports(obj.Name)
                    
                    report = AccessReport(
                        name=obj.Name,
                        type="Report",
                        date_created=str(obj.DateCreated) if hasattr(obj, 'DateCreated') else None,
                        date_modified=str(obj.DateModified) if hasattr(obj, 'DateModified') else None,
                        record_source=report_obj.RecordSource if hasattr(report_obj, 'RecordSource') else None,
                        controls=self._extract_report_controls(report_obj),
                        properties=self._extract_report_properties(report_obj)
                    )
                    
                    reports.append(report)
                    logger.info(f"Extracted report: {report.name}")
                    
                    # Close report
                    self.access_app.DoCmd.Close(3, obj.Name)  # 3 = acReport
                
                except Exception as e:
                    logger.warning(f"Error extracting report {obj.Name}: {e}")
        
        except Exception as e:
            logger.error(f"Error extracting reports: {e}")
        
        return reports
    
    def _extract_report_controls(self, report_obj) -> List[Dict[str, Any]]:
        """Extract control information from a report."""
        controls = []
        
        try:
            for i in range(report_obj.Controls.Count):
                control = report_obj.Controls.Item(i)
                
                control_info = {
                    'name': control.Name if hasattr(control, 'Name') else f"Control_{i}",
                    'type': control.ControlType if hasattr(control, 'ControlType') else None,
                    'caption': control.Caption if hasattr(control, 'Caption') else None,
                    'control_source': control.ControlSource if hasattr(control, 'ControlSource') else None,
                    'visible': control.Visible if hasattr(control, 'Visible') else True
                }
                
                controls.append(control_info)
        
        except Exception as e:
            logger.warning(f"Error extracting report controls: {e}")
        
        return controls
    
    def _extract_report_properties(self, report_obj) -> Dict[str, Any]:
        """Extract properties from a report."""
        properties = {}
        
        try:
            # Common report properties
            property_names = [
                'Caption', 'RecordSource', 'Filter', 'OrderBy', 'PageHeader',
                'PageFooter', 'GroupHeader', 'GroupFooter'
            ]
            
            for prop_name in property_names:
                try:
                    if hasattr(report_obj, prop_name):
                        properties[prop_name] = getattr(report_obj, prop_name)
                except Exception:
                    pass
        
        except Exception as e:
            logger.warning(f"Error extracting report properties: {e}")
        
        return properties
    
    def extract_queries(self) -> List[AccessQuery]:
        """Extract all queries from the database."""
        queries = []
        
        try:
            query_defs = self.db.QueryDefs
            
            for i in range(query_defs.Count):
                query_def = query_defs.Item(i)
                
                # Skip system queries
                if query_def.Name.startswith('~'):
                    continue
                
                query = AccessQuery(
                    name=query_def.Name,
                    type="Query",
                    date_created=str(query_def.DateCreated) if hasattr(query_def, 'DateCreated') else None,
                    sql=query_def.SQL if hasattr(query_def, 'SQL') else None,
                    query_type=str(query_def.Type) if hasattr(query_def, 'Type') else None,
                    parameters=self._extract_query_parameters(query_def)
                )
                
                queries.append(query)
                logger.info(f"Extracted query: {query.name}")
        
        except Exception as e:
            logger.error(f"Error extracting queries: {e}")
        
        return queries
    
    def _extract_query_parameters(self, query_def) -> List[Dict[str, Any]]:
        """Extract parameter information from a query."""
        parameters = []
        
        try:
            if hasattr(query_def, 'Parameters'):
                for i in range(query_def.Parameters.Count):
                    param = query_def.Parameters.Item(i)
                    
                    param_info = {
                        'name': param.Name,
                        'type': param.Type if hasattr(param, 'Type') else None,
                        'value': param.Value if hasattr(param, 'Value') else None
                    }
                    
                    parameters.append(param_info)
        
        except Exception as e:
            logger.warning(f"Error extracting query parameters: {e}")
        
        return parameters
    
    def extract_macros(self) -> List[AccessMacro]:
        """Extract all macros from the database."""
        macros = []
        
        try:
            # Get all macro objects
            for obj in self.access_app.CurrentProject.AllMacros:
                try:
                    macro = AccessMacro(
                        name=obj.Name,
                        type="Macro",
                        date_created=str(obj.DateCreated) if hasattr(obj, 'DateCreated') else None,
                        date_modified=str(obj.DateModified) if hasattr(obj, 'DateModified') else None,
                        actions=[],  # Macro actions are complex to extract
                        conditions=[]
                    )
                    
                    macros.append(macro)
                    logger.info(f"Extracted macro: {macro.name}")
                
                except Exception as e:
                    logger.warning(f"Error extracting macro {obj.Name}: {e}")
        
        except Exception as e:
            logger.error(f"Error extracting macros: {e}")
        
        return macros
    
    def extract_modules(self) -> List[AccessModule]:
        """Extract all modules from the database."""
        modules = []
        
        try:
            # Get all module objects
            for obj in self.access_app.CurrentProject.AllModules:
                try:
                    module = AccessModule(
                        name=obj.Name,
                        type="Module",
                        date_created=str(obj.DateCreated) if hasattr(obj, 'DateCreated') else None,
                        date_modified=str(obj.DateModified) if hasattr(obj, 'DateModified') else None,
                        code=None,  # VBA code extraction requires additional work
                        procedures=[]
                    )
                    
                    modules.append(module)
                    logger.info(f"Extracted module: {module.name}")
                
                except Exception as e:
                    logger.warning(f"Error extracting module {obj.Name}: {e}")
        
        except Exception as e:
            logger.error(f"Error extracting modules: {e}")
        
        return modules
    
    def extract_relationships(self) -> List[Dict[str, Any]]:
        """Extract table relationships."""
        relationships = []
        
        try:
            relations = self.db.Relations
            
            for i in range(relations.Count):
                relation = relations.Item(i)
                
                # Skip system relationships
                if relation.Name.startswith('MSys'):
                    continue
                
                rel_info = {
                    'name': relation.Name,
                    'table': relation.Table,
                    'foreign_table': relation.ForeignTable,
                    'attributes': relation.Attributes if hasattr(relation, 'Attributes') else None,
                    'fields': []
                }
                
                # Extract relationship fields
                for j in range(relation.Fields.Count):
                    field = relation.Fields.Item(j)
                    rel_info['fields'].append({
                        'name': field.Name,
                        'foreign_name': field.ForeignName if hasattr(field, 'ForeignName') else None
                    })
                
                relationships.append(rel_info)
                logger.info(f"Extracted relationship: {rel_info['name']}")
        
        except Exception as e:
            logger.error(f"Error extracting relationships: {e}")
        
        return relationships
    
    def extract_database_properties(self) -> Dict[str, Any]:
        """Extract database properties."""
        properties = {}
        
        try:
            # Basic database information
            properties['name'] = self.access_app.CurrentProject.Name
            properties['path'] = self.access_app.CurrentProject.Path
            properties['full_name'] = self.access_app.CurrentProject.FullName
            properties['is_connected'] = self.access_app.CurrentProject.IsConnected
            
            # Try to get additional properties
            try:
                props = self.db.Properties
                for i in range(props.Count):
                    prop = props.Item(i)
                    properties[prop.Name] = prop.Value
            except Exception:
                pass
        
        except Exception as e:
            logger.warning(f"Error extracting database properties: {e}")
        
        return properties
    
    def extract_all(self) -> AccessExtraction:
        """Extract all objects from the database."""
        logger.info("Starting complete Access database extraction...")
        
        extraction = AccessExtraction(
            database_path=self.database_path,
            extraction_date=datetime.now().isoformat(),
            tables=self.extract_tables(),
            forms=self.extract_forms(),
            reports=self.extract_reports(),
            queries=self.extract_queries(),
            macros=self.extract_macros(),
            modules=self.extract_modules(),
            relationships=self.extract_relationships(),
            database_properties=self.extract_database_properties()
        )
        
        logger.info("Access database extraction completed")
        return extraction

def extract_access_database(database_path: str, output_path: Optional[str] = None) -> str:
    """Extract all objects from an Access database and save to JSON."""
    
    if not WIN32_AVAILABLE:
        logger.error("This tool requires Windows and Microsoft Access to be installed")
        raise RuntimeError("Windows and Microsoft Access are required for full extraction")
    
    # Create output path if not provided
    if output_path is None:
        db_name = Path(database_path).stem
        output_path = f"{db_name}_extraction.json"
    
    # Extract database
    with AccessExtractor(database_path) as extractor:
        extraction = extractor.extract_all()
    
    # Save to JSON
    with open(output_path, 'w') as f:
        json.dump(asdict(extraction), f, indent=2, default=str)
    
    logger.info(f"Extraction saved to: {output_path}")
    return output_path

def main():
    """Main function for command-line usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Extract forms, reports, and applications from Access database")
    parser.add_argument("database_path", help="Path to Access database file")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    try:
        output_path = extract_access_database(args.database_path, args.output)
        print(f"\\nExtraction completed successfully!")
        print(f"Output saved to: {output_path}")
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()