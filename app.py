#!/usr/bin/env python3
"""
Dockerized Flask web application for Stock and Pick PCB inventory management.
All database connections use container networking.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, g, make_response
from expiration_manager import ExpirationManager, ExpirationStatus
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, IntegerField, SelectField, SubmitField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Length, ValidationError
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import re
from functools import wraps, lru_cache
import hashlib
import secrets
from flask_caching import Cache
from flask_compress import Compress

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
# Use environment variable for secret key, fallback to a consistent key
# IMPORTANT: In production, always set SECRET_KEY environment variable
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'kosh-pcb-inventory-secret-key-2025-production-v1')

# Enable Flask-Caching for performance
app.config['CACHE_TYPE'] = 'simple'  # In-memory cache
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  # 5 minutes default
cache = Cache(app)

# Enable gzip compression for all responses
app.config['COMPRESS_MIMETYPES'] = [
    'text/html', 'text/css', 'text/xml', 'application/json',
    'application/javascript', 'text/javascript'
]
app.config['COMPRESS_LEVEL'] = 6  # Balance between compression and speed
app.config['COMPRESS_MIN_SIZE'] = 500  # Only compress responses > 500 bytes
compress = Compress(app)

# CSRF Configuration
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # No time limit on CSRF tokens
app.config['WTF_CSRF_SSL_STRICT'] = False  # Allow non-HTTPS in development
app.config['WTF_CSRF_CHECK_DEFAULT'] = True

# Enable CSRF protection
csrf = CSRFProtect(app)

# Input validation functions
def validate_job_number(job: str) -> bool:
    """Validate job number format."""
    if not job or len(job) > 50:
        return False
    # Allow alphanumeric characters, dashes, underscores
    return re.match(r'^[a-zA-Z0-9_-]+$', job) is not None

def validate_pcb_type(pcb_type: str) -> bool:
    """Validate PCB type against allowed values."""
    allowed_types = ['Bare', 'Partial', 'Completed', 'Ready to Ship']
    return pcb_type in allowed_types

def validate_quantity(quantity: Any) -> tuple[bool, int]:
    """Validate quantity is a positive integer."""
    try:
        qty = int(quantity)
        return (1 <= qty <= 10000, qty)
    except (ValueError, TypeError):
        return (False, 0)

def validate_location(location: str) -> bool:
    """Validate location format."""
    if not location:
        return False
    # Allow location ranges like "1000-1999" or simple locations like "A1", "Shelf-1", etc.
    return re.match(r'^[A-Za-z0-9_-]+$', location.strip()) is not None

def validate_api_request(required_fields: list):
    """Decorator to validate API request data."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            try:
                data = request.get_json()
                if not data:
                    return jsonify({'success': False, 'error': 'No JSON data provided'}), 400
                
                # Check required fields
                for field in required_fields:
                    if field not in data:
                        return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
                
                # Validate specific fields
                if 'job' in data and not validate_job_number(data['job']):
                    return jsonify({'success': False, 'error': 'Invalid job number format'}), 400
                
                if 'pcb_type' in data and not validate_pcb_type(data['pcb_type']):
                    return jsonify({'success': False, 'error': 'Invalid PCB type'}), 400
                
                if 'quantity' in data:
                    is_valid, qty = validate_quantity(data['quantity'])
                    if not is_valid:
                        return jsonify({'success': False, 'error': 'Invalid quantity (must be 1-10000)'}), 400
                    data['quantity'] = qty
                
                if 'location' in data and not validate_location(data['location']):
                    return jsonify({'success': False, 'error': 'Invalid location format'}), 400
                
                return f(*args, **kwargs)
            except Exception as e:
                logger.error(f"API validation error: {e}")
                return jsonify({'success': False, 'error': 'Request validation failed'}), 400
        return decorated_function
    return decorator

# Secure error handling
def get_safe_error_message(error: Exception, operation: str = "operation") -> str:
    """Return a safe error message that doesn't expose sensitive information."""
    # Log the full error for debugging
    logger.error(f"Error in {operation}: {str(error)}", exc_info=True)
    
    # Return generic error messages to users
    if isinstance(error, psycopg2.Error):
        return f"Database {operation} failed. Please try again."
    elif isinstance(error, ValueError):
        return f"Invalid data provided for {operation}."
    elif isinstance(error, KeyError):
        return f"Missing required information for {operation}."
    else:
        return f"An error occurred during {operation}. Please try again."

# Security headers and performance optimization
@app.after_request
def add_security_headers(response):
    """Add comprehensive security headers and caching to all responses."""
    # Content Security Policy
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' cdn.jsdelivr.net cdnjs.cloudflare.com 'unsafe-inline'; "
        "style-src 'self' cdn.jsdelivr.net 'unsafe-inline'; "
        "font-src 'self' cdn.jsdelivr.net; "
        "img-src 'self' data:; "
        "connect-src 'self'"
    )
    # HTTP Strict Transport Security (force HTTPS in production)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # Prevent clickjacking - allow same origin for print preview iframes
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # XSS Protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Feature Policy
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

    # Performance optimizations
    # Enable browser caching for static assets (1 hour)
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=3600'
    else:
        # For dynamic pages, use short cache (1 minute)
        response.headers['Cache-Control'] = 'public, max-age=60'

    return response

@app.context_processor
def inject_current_time():
    return {
        'current_time': datetime.now().strftime('%B %d, %Y %I:%M %p'),
        'current_year': datetime.now().year,
        'current_user': g.get('current_user', {}),
        'user_can_see_itar': g.get('user_can_see_itar', False)
    }

@app.template_filter('moment_fromnow')
def moment_fromnow_filter(dt):
    """Calculate time ago from a datetime object or string"""
    if not dt:
        return "Unknown"

    # Handle string timestamps
    if isinstance(dt, str):
        try:
            # Try common datetime formats
            for fmt in ['%m/%d/%y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(dt, fmt)
                    break
                except:
                    continue
            else:
                # If no format matches, return the string
                return dt
        except:
            return str(dt)

    now = datetime.now()
    if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
        # Convert to naive datetime for comparison
        dt = dt.replace(tzinfo=None)

    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    else:
        days = int(seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''} ago"

@app.template_filter('expiration_status')
def expiration_status_filter(item):
    """Calculate expiration status for an inventory item"""
    dc = item.get('dc')
    pcb_type = item.get('pcb_type', 'Bare')
    msd = item.get('msd')
    return expiration_manager.calculate_expiration_status(dc, pcb_type, msd)

@app.template_filter('expiration_badge_class')
def expiration_badge_class_filter(status_text):
    """Get Bootstrap badge class for expiration status"""
    try:
        status = ExpirationStatus(status_text)
        return expiration_manager.get_expiration_badge_class(status)
    except ValueError:
        return 'bg-secondary'

@app.template_filter('expiration_icon')
def expiration_icon_filter(status_text):
    """Get Bootstrap icon for expiration status"""
    try:
        status = ExpirationStatus(status_text)
        return expiration_manager.get_expiration_icon(status)
    except ValueError:
        return 'bi-question-circle'

@app.template_filter('expiration_display')
def expiration_display_filter(expiration_info):
    """Format expiration information for display"""
    return expiration_manager.format_expiration_display(expiration_info)

# Database configuration from environment variables
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'pcb_inventory'),
    'user': os.getenv('POSTGRES_USER', 'stockpick_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'stockpick_pass')
}

# PCB Types and Locations (matching the original application)
PCB_TYPES = [
    ('Bare', 'Bare PCB'),
    ('Partial', 'Partial Assembly'),
    ('Completed', 'Completed Assembly'),
    ('Ready to Ship', 'Ready to Ship')
]

# ITAR Classifications
ITAR_CLASSIFICATIONS = [
    ('NONE', 'Non-ITAR (Public)'),
    ('EAR99', 'Export Administration Regulations'),
    ('SENSITIVE', 'Company Sensitive'),
    ('ITAR', 'ITAR Controlled')
]

# User Roles
USER_ROLES = [
    ('Super User', 'Super User'),
    ('User', 'User'),
    ('Manager', 'Manager'),
    ('Operator', 'Operator'),
    ('ITAR', 'ITAR')
]

LOCATION_RANGES = [
    ('1000-1999', '1000-1999'),
    ('2000-2999', '2000-2999'),
    ('3000-3999', '3000-3999'),
    ('4000-4999', '4000-4999'),
    ('5000-5999', '5000-5999'),
    ('6000-6999', '6000-6999'),
    ('7000-7999', '7000-7999'),
    ('8000-8999', '8000-8999'),  # Default in original app
    ('9000-9999', '9000-9999'),
    ('10000-10999', '10000-10999')
]

def validate_pcb_type_field(form, field):
    """Custom validator for PCB type field."""
    allowed_types = ['Bare', 'Partial', 'Completed', 'Ready to Ship']
    if field.data not in allowed_types:
        raise ValidationError(f'Component type must be one of: {", ".join(allowed_types)}')

class StockForm(FlaskForm):
    """Form for stocking electronic parts."""
    pcn_number = StringField('PCN Number', validators=[Length(max=10)])
    job = StringField('Job Number (Item)', validators=[Length(max=50)])  # Optional - will use part_number if not provided
    mpn = StringField('MPN (Manufacturing Part Number)', validators=[Length(max=50)])
    part_number = StringField('Part Number', validators=[DataRequired(), Length(min=1, max=50)])  # Now required - serves as job identifier
    po = StringField('PO (Purchase Order)', validators=[Length(max=50)])
    work_order = StringField('Work Order Number', validators=[Length(max=50)])
    pcb_type = StringField('Component Type', validators=[DataRequired(), Length(min=1, max=50), validate_pcb_type_field])
    dc = StringField('Date Code (DC)', validators=[Length(max=50)])
    msd = StringField('Moisture Sensitive Device (MSD)', validators=[Length(max=50)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    location = StringField('Location', validators=[DataRequired(), Length(min=1, max=20)], default='8000-8999')
    itar_classification = SelectField('ITAR Classification', choices=ITAR_CLASSIFICATIONS, validators=[DataRequired()], default='NONE')
    export_control_notes = StringField('Export Control Notes', validators=[Length(max=500)])
    submit = SubmitField('Stock Parts')

class PickForm(FlaskForm):
    """Form for picking electronic parts."""
    job = StringField('Job Number (Item)', validators=[Length(max=50)])  # Optional - will use part_number if not provided
    mpn = StringField('MPN (Manufacturing Part Number)', validators=[Length(max=50)])
    part_number = StringField('Part Number', validators=[DataRequired(), Length(min=1, max=50)])  # Now required - serves as job identifier
    po = StringField('Job Number', validators=[Length(max=50)])
    work_order = StringField('Work Order Number', validators=[Length(max=50)])
    pcb_type = StringField('Component Type', validators=[DataRequired(), Length(min=1, max=50), validate_pcb_type_field])
    dc = StringField('Date Code (DC)', validators=[Length(max=50)])
    msd = StringField('Moisture Sensitive Device (MSD)', validators=[Length(max=50)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Pick Parts')

# User authentication now handled by ACI Dashboard

class DatabaseManager:
    """Handle database operations using containerized PostgreSQL with connection pooling."""
    
    def __init__(self):
        self.db_config = DB_CONFIG
        # Initialize connection pool with optimized settings
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,     # Keep 2 connections ready
                maxconn=10,    # Reduced max connections for better performance
                **self.db_config
            )
            logger.info("Database connection pool initialized")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise
    
    def get_connection(self):
        """Get a database connection from the pool."""
        try:
            return self.pool.getconn()
        except Exception as e:
            logger.error(f"Failed to get connection from pool: {e}")
            raise
    
    def return_connection(self, conn):
        """Return a connection to the pool."""
        try:
            self.pool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to return connection to pool: {e}")
    
    def execute_function(self, function_name: str, params: tuple) -> Dict[str, Any]:
        """Execute a PostgreSQL function and return the result."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Build function call with proper parameter count
                param_placeholders = ', '.join(['%s'] * len(params))
                sql = f"SELECT {function_name}({param_placeholders})"
                cur.execute(sql, params)
                result = cur.fetchone()
                conn.commit()
                return dict(result[function_name.split('.')[-1]])
        except Exception as e:
            if conn:
                conn.rollback()
            error_msg = get_safe_error_message(e, "database function")
            return {'success': False, 'error': error_msg}
        finally:
            if conn:
                self.return_connection(conn)
    
    def stock_pcb(self, job: str, pcb_type: str, quantity: int, location: str,
                  itar_classification: str = 'NONE', user_role: str = 'USER',
                  itar_auth: bool = False, username: str = 'system', work_order: str = None,
                  dc: str = None, msd: str = None, pcn: int = None, mpn: str = None,
                  part_number: str = None) -> Dict[str, Any]:
        """Stock PCB using the PostgreSQL stored procedure with all fields."""
        try:
            # Call the PostgreSQL function with all 14 parameters
            result = self.execute_function('pcb_inventory.stock_pcb',
                (job, pcb_type, quantity, location, itar_classification, user_role,
                 itar_auth, username, pcn, work_order, dc, msd, mpn, part_number))
            logger.info(f"Stock operation: {result}")
            # Clear cache after inventory change
            cache.delete_memoized(self.get_current_inventory)
            cache.delete('stats_summary')
            return result
        except Exception as e:
            error_msg = get_safe_error_message(e, "stock operation")
            return {'success': False, 'error': error_msg}
    
    def pick_pcb(self, job: str, pcb_type: str, quantity: int,
                 user_role: str = 'USER', itar_auth: bool = False, username: str = 'system', work_order: str = None) -> Dict[str, Any]:
        """Pick PCB using the PostgreSQL stored procedure."""
        try:
            # Call the PostgreSQL function with all 6 parameters
            result = self.execute_function('pcb_inventory.pick_pcb',
                (job, pcb_type, quantity, user_role, itar_auth, username))
            logger.info(f"Pick operation: {result}")
            # Clear cache after inventory change
            cache.delete_memoized(self.get_current_inventory)
            cache.delete('stats_summary')
            return result
        except Exception as e:
            error_msg = get_safe_error_message(e, "pick operation")
            return {'success': False, 'error': error_msg}

    def update_inventory(self, inventory_id: int, job: str, pcb_type: str, quantity: int,
                        location: str, pcn: int = None, username: str = 'system') -> Dict[str, Any]:
        """Update inventory item using the PostgreSQL stored procedure."""
        try:
            # Call the PostgreSQL function with all 7 parameters
            result = self.execute_function('pcb_inventory.update_inventory',
                (inventory_id, job, pcb_type, quantity, location, pcn, username))
            logger.info(f"Update operation: {result}")
            # Clear cache after inventory change
            cache.delete_memoized(self.get_current_inventory)
            cache.delete('stats_summary')
            return result
        except Exception as e:
            error_msg = get_safe_error_message(e, "update operation")
            return {'success': False, 'error': error_msg}


    def get_current_inventory(self, user_role: str = 'USER', itar_auth: bool = False) -> List[Dict[str, Any]]:
        """Get current inventory from tblPCB_Inventory table."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        id,
                        pcn,
                        job,
                        pcb_type,
                        qty,
                        location,
                        migrated_at as updated_at
                    FROM pcb_inventory."tblPCB_Inventory"
                    ORDER BY migrated_at DESC NULLS LAST, job, pcb_type
                """)
                result = [dict(row) for row in cur.fetchall()]
                return result
        except Exception as e:
            logger.error(f"Failed to get inventory: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_inventory_summary(self) -> List[Dict[str, Any]]:
        """Get inventory summary from the view."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        pcb_type,
                        location,
                        COUNT(DISTINCT job) as job_count,
                        SUM(COALESCE(qty, 0)) as total_qty,
                        AVG(COALESCE(qty, 0)) as avg_qty
                    FROM pcb_inventory."tblPCB_Inventory"
                    WHERE pcb_type IS NOT NULL AND location IS NOT NULL
                    GROUP BY pcb_type, location
                    ORDER BY total_qty DESC, pcb_type, location
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get summary: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent activity from transaction log."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Use tblTransaction as audit log since inventory_audit doesn't exist
                cur.execute("""
                    SELECT
                        t.tran_time as timestamp,
                        t.userid as user_id,
                        t.trantype as operation,
                        t.item as job,
                        t.pcn,
                        t.tranqty as quantity_change,
                        t.tranqty as new_quantity,
                        COALESCE(pcb.pcb_type, 'Unknown') as pcb_type
                    FROM pcb_inventory."tblTransaction" t
                    LEFT JOIN pcb_inventory."tblPCB_Inventory" pcb ON t.item = pcb.job OR t.item LIKE pcb.job || '%%'
                    ORDER BY t.id DESC
                    LIMIT %s
                """, (limit,))
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.debug(f"Audit log not available: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def search_inventory(self, job: str = None, pcb_type: str = None, 
                        user_role: str = 'USER', itar_auth: bool = False) -> List[Dict[str, Any]]:
        """Search inventory with optional filters and ITAR access control."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM pcb_inventory.get_filtered_inventory(%s, %s, %s, %s) ORDER BY job, pcb_type",
                    (user_role, itar_auth, job, pcb_type)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """Get comprehensive statistics summary for stats page - cached for performance."""
        cached = cache.get('stats_summary')
        if cached:
            return cached

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get basic counts
                cur.execute("""
                    SELECT
                        COUNT(*) as total_records,
                        COUNT(DISTINCT job) as unique_jobs,
                        SUM(COALESCE(qty, 0)) as total_quantity,
                        COUNT(DISTINCT pcb_type) as pcb_types,
                        MAX(checked_on_8_14_25) as last_updated
                    FROM pcb_inventory."tblPCB_Inventory"
                """)
                stats = dict(cur.fetchone())

                # Format last_updated
                if stats['last_updated']:
                    # checked_on_8_14_25 is a string, not a datetime
                    stats['last_updated'] = str(stats['last_updated'])
                else:
                    stats['last_updated'] = 'Never'

                cache.set('stats_summary', stats, timeout=120)  # Cache for 2 minutes
                return stats
        except Exception as e:
            logger.error(f"Failed to get stats summary: {e}")
            return {
                'total_records': 0, 'unique_jobs': 0, 'total_quantity': 0,
                'pcb_types': 0, 'last_updated': 'Unknown'
            }
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_pcb_type_breakdown(self) -> List[Dict[str, Any]]:
        """Get PCB type breakdown for stats comparison."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        pcb_type as name,
                        SUM(COALESCE(qty, 0)) as postgres_count,
                        SUM(COALESCE(qty, 0)) as source_count  -- Assuming same for now
                    FROM pcb_inventory."tblPCB_Inventory"
                    WHERE pcb_type IS NOT NULL
                    GROUP BY pcb_type
                    ORDER BY pcb_type
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get PCB type breakdown: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_location_breakdown(self) -> List[Dict[str, Any]]:
        """Get location distribution for stats page."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        location as range,
                        COUNT(*) as item_count,
                        SUM(COALESCE(qty, 0)) as total_qty,
                        ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM pcb_inventory."tblPCB_Inventory")), 1) as usage_percent
                    FROM pcb_inventory."tblPCB_Inventory"
                    WHERE location IS NOT NULL
                    GROUP BY location
                    ORDER BY location
                """)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get location breakdown: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def assign_pcn_to_item(self, job: str, pcb_type: str, username: str = 'system') -> Dict[str, Any]:
        """Assign a PCN to an inventory item using the database function."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Call the assign_pcn database function
                cur.execute(
                    "SELECT pcb_inventory.assign_pcn(%s, %s, %s) as result",
                    (job, pcb_type, username)
                )
                result = cur.fetchone()
                conn.commit()

                if result and result['result']:
                    return result['result']
                else:
                    return {'success': False, 'error': 'PCN assignment failed'}
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Failed to assign PCN: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if conn:
                self.return_connection(conn)

    def get_pcn_history(self, limit: int = 100, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Get PCN transaction history - prioritize new PCNs from pcn_records, backfill from tblTransaction if needed."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Strategy: Query pcn_records first (fast, small table), then query tblTransaction for remaining
                results = []

                # Step 1: Get new PCNs from pcn_records (fast!)
                records_where = "1=1"
                records_params = []

                if filters:
                    if filters.get('pcn'):
                        records_where += " AND pr.pcn_number = %s"
                        records_params.append(filters['pcn'])
                    if filters.get('item'):
                        records_where += " AND pr.item LIKE %s"
                        records_params.append(f"%{filters['item']}%")

                records_params.append(limit)

                cur.execute(f"""
                    SELECT
                        pr.pcn_id::bigint as id,
                        pr.pcn_number as pcn,
                        pr.item as job_number,
                        pr.mpn,
                        pr.date_code::varchar as date_code,
                        'PCN Generated' as transaction_type,
                        pr.quantity,
                        pr.created_at::text as transaction_time,
                        NULL as location_from,
                        NULL as location_to,
                        NULL as work_order,
                        pr.po_number as purchase_order,
                        pr.created_by as user_id,
                        pr.created_at as migrated_at,
                        NULL as pcb_type,
                        COALESCE(pr.msd, '') as msd_level
                    FROM pcb_inventory.pcn_records pr
                    WHERE {records_where}
                    ORDER BY pr.pcn_number DESC
                    LIMIT %s
                """, records_params)

                results = [dict(row) for row in cur.fetchall()]

                # Step 2: If we need more results, get from tblTransaction
                remaining = limit - len(results)
                if remaining > 0:
                    trans_where = "t.pcn IS NOT NULL"
                    trans_params = []

                    if filters:
                        if filters.get('pcn'):
                            trans_where += " AND t.pcn = %s"
                            trans_params.append(filters['pcn'])
                        if filters.get('item'):
                            trans_where += " AND t.item LIKE %s"
                            trans_params.append(f"%{filters['item']}%")

                    trans_params.append(remaining)

                    cur.execute(f"""
                        SELECT
                            t.id, t.pcn, t.item as job_number, t.mpn, t.dc::varchar as date_code,
                            t.trantype as transaction_type,
                            t.tranqty as quantity,
                            t.tran_time as transaction_time,
                            t.loc_from as location_from,
                            t.loc_to as location_to,
                            t.wo as work_order,
                            t.po as purchase_order,
                            t.userid as user_id,
                            t.migrated_at,
                            NULL as pcb_type,
                            '' as msd_level
                        FROM pcb_inventory."tblTransaction" t
                        WHERE {trans_where}
                        ORDER BY t.pcn DESC
                        LIMIT %s
                    """, trans_params)

                    results.extend([dict(row) for row in cur.fetchall()])

                # Step 3: Sort combined results by PCN DESC and limit
                results.sort(key=lambda x: x['pcn'], reverse=True)
                return results[:limit]
        except Exception as e:
            logger.error(f"Failed to get PCN history: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def search_pcn(self, pcn_number: str = None, job: str = None) -> List[Dict[str, Any]]:
        """Search for PCN records by PCN number or job number."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM pcb_inventory.v_pcn_history WHERE 1=1"
                params = []

                if pcn_number:
                    query += " AND pcn = %s"
                    params.append(pcn_number)

                if job:
                    query += " AND item = %s"
                    params.append(job)

                query += " ORDER BY id DESC"

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"PCN search failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def get_po_history(self, limit: int = 100, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Get PO history from tblReceipt table."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """SELECT
                    id, pcn, item, mpn, dc,
                    trantype as transaction_type,
                    qty_rec as quantity_received,
                    date_rec as date_received,
                    loc_from as location_from,
                    loc_to as location_to,
                    po as purchase_order,
                    comments, msd,
                    userid as user_id,
                    migrated_at
                FROM pcb_inventory."tblReceipt" WHERE 1=1"""
                params = []

                if filters:
                    if filters.get('po_number'):
                        query += " AND po LIKE %s"
                        params.append(f"%{filters['po_number']}%")
                    if filters.get('item'):
                        query += " AND item LIKE %s"
                        params.append(f"%{filters['item']}%")
                    if filters.get('date_from'):
                        query += " AND date_rec >= %s"
                        params.append(filters['date_from'])
                    if filters.get('date_to'):
                        query += " AND date_rec <= %s"
                        params.append(filters['date_to'])

                query += " ORDER BY id DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get PO history: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def search_po(self, po_number: str = None, item: str = None) -> List[Dict[str, Any]]:
        """Search for PO records by PO number or item."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM pcb_inventory.po_history WHERE 1=1"
                params = []

                if po_number:
                    query += " AND po_number LIKE %s"
                    params.append(f"%{po_number}%")

                if item:
                    query += " AND item LIKE %s"
                    params.append(f"%{item}%")

                query += " ORDER BY transaction_date DESC"

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"PO search failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

# User Authentication and Authorization Functions
class UserManager:
    """Handle user authentication and authorization."""
    
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def get_user_by_username(self, username: str) -> Dict[str, Any]:
        """Get user information by username."""
        conn = None
        try:
            conn = self.db_manager.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM pcb_inventory.users WHERE username = %s AND active = TRUE",
                    (username,)
                )
                user = cur.fetchone()
                return dict(user) if user else None
        except Exception as e:
            logger.error(f"Failed to get user {username}: {e}")
            return None
        finally:
            if conn:
                self.db_manager.return_connection(conn)
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all active users for the demo interface."""
        conn = None
        try:
            conn = self.db_manager.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT username, role, itar_authorized FROM pcb_inventory.users WHERE active = TRUE ORDER BY username"
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get users: {e}")
            return []
        finally:
            if conn:
                self.db_manager.return_connection(conn)
    
    def can_access_itar(self, user_role: str, itar_authorized: bool) -> bool:
        """Check if user can access ITAR items."""
        return user_role == 'Super User' or user_role == 'ITAR'
    
    def simulate_aci_login(self, username: str) -> Dict[str, Any]:
        """Simulate login from ACI dashboard."""
        user = self.get_user_by_username(username)
        if not user:
            return {'success': False, 'error': 'User not found'}
        
        # Create session token
        session_token = secrets.token_urlsafe(32)
        
        # Update user's session info
        conn = None
        try:
            conn = self.db_manager.get_connection()
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pcb_inventory.users SET session_token = %s, token_expires_at = %s, last_login = %s WHERE username = %s",
                    (session_token, datetime.now().replace(hour=23, minute=59, second=59), datetime.now(), username)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to update session for {username}: {e}")
        finally:
            if conn:
                self.db_manager.return_connection(conn)
        
        return {
            'success': True,
            'user': user,
            'session_token': session_token
        }

def require_auth(f):
    """Decorator to require user authentication from ACI Dashboard SSO."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check for ACI Dashboard SSO token in headers or session
        auth_token = request.headers.get('X-ACI-Auth-Token') or session.get('aci_auth_token')
        username = request.headers.get('X-ACI-Username') or session.get('username')
        user_role = request.headers.get('X-ACI-Role') or session.get('role', 'USER')
        itar_auth = request.headers.get('X-ACI-ITAR') or session.get('itar_authorized', False)

        # Convert string values to proper types
        if isinstance(itar_auth, str):
            itar_auth = itar_auth.lower() in ['true', '1', 'yes']

        if username:
            # Set session from ACI Dashboard SSO
            session['username'] = username
            session['role'] = user_role
            session['itar_authorized'] = itar_auth
            session['aci_auth_token'] = auth_token
        else:
            # For direct access without SSO, use guest permissions
            session['username'] = 'guest'
            session['role'] = 'USER'
            session['itar_authorized'] = False

        return f(*args, **kwargs)
    return decorated_function

def require_itar_access(f):
    """Decorator to require ITAR access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        
        if not user_manager.can_access_itar(user_role, itar_auth):
            flash('Access denied: ITAR authorization required', 'error')
            return redirect(url_for('index'))
        
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def load_current_user():
    """Load current user information into g object."""
    g.current_user = {
        'username': session.get('username', 'anonymous'),
        'role': session.get('role', 'USER'),
        'itar_authorized': session.get('itar_authorized', False)
    }
    g.user_can_see_itar = user_manager.can_access_itar(
        g.current_user['role'],
        g.current_user['itar_authorized']
    ) if 'user_manager' in globals() else False

# Initialize database manager
db_manager = DatabaseManager()
user_manager = UserManager(db_manager)
expiration_manager = ExpirationManager()

@app.route('/health')
def health_check():
    """Health check endpoint for Docker."""
    try:
        # Test database connection
        inventory = db_manager.get_current_inventory()
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'inventory_items': len(inventory),
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/')
@require_auth
def index():
    """Main dashboard page."""
    try:
        # Get summary statistics with user access filtering
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)

        inventory = db_manager.get_current_inventory(user_role, itar_auth)
        summary = db_manager.get_inventory_summary()
        recent_activity = db_manager.get_audit_log(10)

        # Calculate totals with safe defaults
        total_jobs = len(set(item['job'] for item in inventory if item.get('job'))) if inventory else 0
        total_quantity = sum(item.get('qty') or 0 for item in inventory) if inventory else 0
        total_items = len(inventory) if inventory else 0

        # Low stock threshold (e.g., less than 10 units)
        LOW_STOCK_THRESHOLD = 10
        low_stock_items_temp = [item for item in inventory if (item.get('qty') or 0) < LOW_STOCK_THRESHOLD and (item.get('qty') or 0) > 0]

        # Most active jobs (top 5 by quantity)
        job_quantities = {}
        for item in inventory:
            job = item.get('job')
            qty = item.get('qty') or 0
            if job:
                job_quantities[job] = job_quantities.get(job, 0) + qty

        most_active_jobs = sorted(job_quantities.items(), key=lambda x: x[1], reverse=True)[:5]

        # PCB type distribution for chart
        pcb_type_data = {}
        for item in inventory:
            pcb_type = item.get('pcb_type', 'Unknown')
            qty = item.get('qty') or 0
            pcb_type_data[pcb_type] = pcb_type_data.get(pcb_type, 0) + qty

        # Calculate trends - simplified for performance (no individual DB queries)
        # Just mark all items as stable for faster load time
        inventory_with_trends = []
        for item in inventory:
            item['trend'] = 'stable'  # Default trend for performance
            inventory_with_trends.append(item)

        # Filter low stock items from the inventory with trends
        low_stock_items = [item for item in inventory_with_trends if (item.get('qty') or 0) < LOW_STOCK_THRESHOLD and (item.get('qty') or 0) > 0]

        stats = {
            'total_jobs': total_jobs,
            'total_quantity': total_quantity,
            'total_items': total_items,
            'pcb_types': len(PCB_TYPES),
            'low_stock_count': len(low_stock_items)
        }

        # Enhanced summary with safe formatting
        enhanced_summary = []
        if summary:
            for item in summary:
                enhanced_item = dict(item)
                # Add safe default values
                enhanced_item['job_count'] = enhanced_item.get('job_count', 1)
                enhanced_item['total_quantity'] = enhanced_item.get('total_qty', 0)
                enhanced_item['average_quantity'] = enhanced_item.get('total_qty', 0) / max(enhanced_item.get('job_count', 1), 1)
                enhanced_summary.append(enhanced_item)

        return render_template('index.html',
                             stats=stats,
                             summary=enhanced_summary,
                             recent_activity=recent_activity,
                             low_stock_items=low_stock_items,
                             low_stock_threshold=LOW_STOCK_THRESHOLD,
                             most_active_jobs=most_active_jobs,
                             pcb_type_data=pcb_type_data,
                             inventory_with_trends=inventory_with_trends)
    except Exception as e:
        import traceback
        logger.error(f"Error loading dashboard: {e}")
        logger.error(traceback.format_exc())
        # Provide safe default values on error
        safe_stats = {
            'total_jobs': 0,
            'total_quantity': 0,
            'total_items': 0,
            'pcb_types': len(PCB_TYPES),
            'low_stock_count': 0
        }
        flash(f"Error loading dashboard: {e}", 'error')
        return render_template('index.html', stats=safe_stats, summary=[], recent_activity=[],
                             low_stock_items=[], low_stock_threshold=10, most_active_jobs=[], pcb_type_data={}, inventory_with_trends=[])

@app.route('/stock', methods=['GET', 'POST'])
@require_auth
def stock():
    """Stock PCB page."""
    form = StockForm()
    
    # Populate form choices based on user access
    user_role = session.get('role', 'USER')
    itar_auth = session.get('itar_authorized', False)
    
    if not user_manager.can_access_itar(user_role, itar_auth):
        # Remove ITAR option for non-authorized users
        form.itar_classification.choices = [choice for choice in ITAR_CLASSIFICATIONS if choice[0] != 'ITAR']
    
    if form.validate_on_submit():
        # Check if user is trying to stock ITAR item without permission
        if form.itar_classification.data == 'ITAR' and not user_manager.can_access_itar(user_role, itar_auth):
            flash('Access denied: ITAR authorization required', 'error')
            return render_template('stock.html', form=form)
        
        try:
            # Convert PCN to integer if provided
            pcn_value = None
            if hasattr(form, 'pcn_number') and form.pcn_number.data:
                try:
                    pcn_value = int(form.pcn_number.data) if form.pcn_number.data else None
                except (ValueError, TypeError):
                    pcn_value = None

            # Use part_number as job identifier if job not provided
            job_value = form.job.data if form.job.data else form.part_number.data

            result = db_manager.stock_pcb(
                job=job_value,
                pcb_type=form.pcb_type.data,
                quantity=form.quantity.data,
                location=form.location.data,
                itar_classification=form.itar_classification.data,
                user_role=user_role,
                itar_auth=itar_auth,
                username=session.get('username', 'system'),
                work_order=form.work_order.data if hasattr(form, 'work_order') and form.work_order.data else None,
                dc=form.dc.data if hasattr(form, 'dc') and form.dc.data else None,
                msd=form.msd.data if hasattr(form, 'msd') and form.msd.data else None,
                pcn=pcn_value,
                mpn=form.mpn.data if hasattr(form, 'mpn') and form.mpn.data else None,
                part_number=form.part_number.data if hasattr(form, 'part_number') and form.part_number.data else None
            )
            
            if result.get('success'):
                flash(f"Successfully stocked {result['stocked_qty']} {result['pcb_type']} PCBs for job {result['job']}. "
                      f"New total: {result['new_qty']}", 'success')
                return redirect(url_for('stock'))
            else:
                flash(f"Stock operation failed: {result.get('error', 'Unknown error')}", 'error')
                
        except Exception as e:
            logger.error(f"Stock operation error: {e}")
            flash(f"Stock operation failed: {e}", 'error')
    
    return render_template('stock.html', form=form)

@app.route('/pick', methods=['GET', 'POST'])
@require_auth
def pick():
    """Pick PCB page."""
    form = PickForm()
    
    if form.validate_on_submit():
        try:
            user_role = session.get('role', 'USER')
            itar_auth = session.get('itar_authorized', False)
            
            # Use part_number as job identifier if job not provided
            job_value = form.job.data if form.job.data else form.part_number.data

            result = db_manager.pick_pcb(
                job=job_value,
                pcb_type=form.pcb_type.data,
                quantity=form.quantity.data,
                user_role=user_role,
                itar_auth=itar_auth,
                username=session.get('username', 'system'),
                work_order=form.work_order.data if form.work_order.data else None
            )
            
            if result.get('success'):
                flash(f"Successfully picked {result['picked_qty']} {result['pcb_type']} PCBs for job {result['job']}. "
                      f"Remaining: {result['new_qty']}", 'success')
                return redirect(url_for('pick'))
            else:
                error_msg = result.get('error', 'Unknown error')
                if 'Insufficient quantity' in error_msg:
                    flash(f"Insufficient quantity! Available: {result.get('available_qty', 0)}, "
                          f"Requested: {result.get('requested_qty', 0)}", 'error')
                elif 'Job not found' in error_msg:
                    flash(f"Job {result['job']} with PCB type {result['pcb_type']} not found in inventory", 'error')
                else:
                    flash(f"Pick operation failed: {error_msg}", 'error')
                
        except Exception as e:
            logger.error(f"Pick operation error: {e}")
            flash(f"Pick operation failed: {e}", 'error')
    
    return render_template('pick.html', form=form)

@app.route('/inventory')
@require_auth
def inventory():
    """Inventory listing page with pagination and advanced filters."""
    # Get search and pagination parameters
    search_job = request.args.get('job', '').strip()
    search_pcb_type = request.args.get('pcb_type', '').strip()
    search_location = request.args.get('location', '').strip()
    search_pcn = request.args.get('pcn', '').strip()
    search_date_from = request.args.get('date_from', '').strip()
    search_date_to = request.args.get('date_to', '').strip()
    search_min_qty = request.args.get('min_qty', '').strip()
    search_max_qty = request.args.get('max_qty', '').strip()

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    sort_by = request.args.get('sort', 'job')
    sort_order = request.args.get('order', 'asc')

    # Limit per_page to reasonable values
    per_page = min(max(per_page, 10), 200)

    user_role = session.get('role', 'USER')
    itar_auth = session.get('itar_authorized', False)

    try:
        # Get all inventory first
        inventory_data = db_manager.get_current_inventory(user_role, itar_auth)

        # Apply filters
        if search_job:
            # Support comma-separated job numbers
            job_list = [j.strip() for j in search_job.split(',') if j.strip()]
            inventory_data = [item for item in inventory_data if item.get('job') in job_list]

        if search_pcb_type:
            inventory_data = [item for item in inventory_data if item.get('pcb_type') == search_pcb_type]

        if search_location:
            inventory_data = [item for item in inventory_data if item.get('location') == search_location]

        if search_pcn:
            inventory_data = [item for item in inventory_data if item.get('pcn') and search_pcn.lower() in str(item.get('pcn', '')).lower()]

        # Date range filter
        if search_date_from:
            from datetime import datetime
            date_from = datetime.strptime(search_date_from, '%Y-%m-%d')
            filtered = []
            for item in inventory_data:
                updated = item.get('updated_at')
                if updated:
                    # Handle both datetime and string types
                    if isinstance(updated, str):
                        try:
                            updated = datetime.strptime(updated, '%Y-%m-%d')
                        except:
                            continue
                    elif hasattr(updated, 'tzinfo') and updated.tzinfo:
                        updated = updated.replace(tzinfo=None)
                    if updated >= date_from:
                        filtered.append(item)
            inventory_data = filtered

        if search_date_to:
            from datetime import datetime
            date_to = datetime.strptime(search_date_to, '%Y-%m-%d')
            date_to = date_to.replace(hour=23, minute=59, second=59)
            filtered = []
            for item in inventory_data:
                updated = item.get('updated_at')
                if updated:
                    # Handle both datetime and string types
                    if isinstance(updated, str):
                        try:
                            updated = datetime.strptime(updated, '%Y-%m-%d')
                        except:
                            continue
                    elif hasattr(updated, 'tzinfo') and updated.tzinfo:
                        updated = updated.replace(tzinfo=None)
                    if updated <= date_to:
                        filtered.append(item)
            inventory_data = filtered

        # Quantity range filter
        if search_min_qty:
            try:
                min_qty = int(search_min_qty)
                inventory_data = [item for item in inventory_data if item.get('qty', 0) >= min_qty]
            except ValueError:
                pass

        if search_max_qty:
            try:
                max_qty = int(search_max_qty)
                inventory_data = [item for item in inventory_data if item.get('qty', 0) <= max_qty]
            except ValueError:
                pass

        # Sort the data
        reverse_sort = sort_order == 'desc'
        if sort_by == 'job':
            inventory_data.sort(key=lambda x: (x.get('job') or ''), reverse=reverse_sort)
        elif sort_by == 'pcb_type':
            inventory_data.sort(key=lambda x: (x.get('pcb_type') or ''), reverse=reverse_sort)
        elif sort_by == 'qty':
            inventory_data.sort(key=lambda x: (x.get('qty') if x.get('qty') is not None else 0), reverse=reverse_sort)
        elif sort_by == 'location':
            inventory_data.sort(key=lambda x: (x.get('location') or ''), reverse=reverse_sort)
        elif sort_by == 'updated_at':
            inventory_data.sort(key=lambda x: (x.get('updated_at') or ''), reverse=reverse_sort)

        # Get unique locations for dropdown
        all_inventory = db_manager.get_current_inventory(user_role, itar_auth)
        locations = sorted(list(set(item.get('location') for item in all_inventory if item.get('location'))))

        # Calculate pagination
        total_items = len(inventory_data)
        total_pages = (total_items + per_page - 1) // per_page
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page

        paginated_inventory = inventory_data[start_idx:end_idx]

        # Calculate pagination info
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_items,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
            'pages': list(range(max(1, page - 2), min(total_pages + 1, page + 3)))
        }

        return render_template('inventory.html',
                             inventory=paginated_inventory,
                             pagination=pagination,
                             pcb_types=PCB_TYPES,
                             locations=locations,
                             search_job=search_job,
                             search_pcb_type=search_pcb_type,
                             search_location=search_location,
                             search_pcn=search_pcn,
                             search_date_from=search_date_from,
                             search_date_to=search_date_to,
                             search_min_qty=search_min_qty,
                             search_max_qty=search_max_qty,
                             sort_by=sort_by,
                             sort_order=sort_order)
    except Exception as e:
        import traceback
        logger.error(f"Error loading inventory: {e}")
        logger.error(traceback.format_exc())
        flash(f"Error loading inventory: {e}", 'error')
        return render_template('inventory.html', inventory=[], pagination={'total': 0},
                             pcb_types=PCB_TYPES, locations=[], search_job='', search_pcb_type='',
                             search_location='', search_pcn='', search_date_from='', search_date_to='',
                             search_min_qty='', search_max_qty='', sort_by='job', sort_order='asc')

@app.route('/reports')
@require_auth
def reports():
    """Reports page."""
    try:
        # Get current inventory data for reports
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        inventory = db_manager.get_current_inventory(user_role, itar_auth)

        # Create summary data matching template expectations
        summary = []
        location_type_summary = {}

        # Group by location and PCB type
        for item in inventory:
            location = item.get('location', 'Unknown')
            pcb_type = item.get('pcb_type', 'Unknown')
            key = f"{location}|{pcb_type}"

            if key not in location_type_summary:
                location_type_summary[key] = {
                    'location': location,
                    'pcb_type': pcb_type,
                    'job_count': 0,
                    'total_quantity': 0,
                    'jobs': set()
                }

            location_type_summary[key]['total_quantity'] += (item.get('qty') or 0)
            if item.get('job'):
                location_type_summary[key]['jobs'].add(item.get('job'))

        # Convert to list format expected by template
        total_all_qty = sum(item.get('qty') or 0 for item in inventory)
        for data in location_type_summary.values():
            data['job_count'] = len(data['jobs'])
            data['average_quantity'] = data['total_quantity'] / max(data['job_count'], 1)
            data['percentage'] = (data['total_quantity'] / max(total_all_qty, 1)) * 100
            del data['jobs']  # Remove set object
            summary.append(data)

        # Sort by total quantity descending
        summary.sort(key=lambda x: x['total_quantity'], reverse=True)

        # Get audit log
        audit_log = db_manager.get_audit_log(100)

        return render_template('reports.html',
                             summary=summary,
                             audit_log=audit_log)
    except Exception as e:
        logger.error(f"Error loading reports: {e}")
        flash(f"Error loading reports: {e}", 'error')
        return render_template('reports.html', summary=[], audit_log=[])

@app.route('/sources')
@require_auth
def sources():
    """Sources page - shows all migrated Access tables (super users only)."""
    user_role = session.get('role', 'USER')
    
    # Only super users can access sources
    if user_role != 'ADMIN':
        flash('Access denied: Super user privileges required', 'error')
        return redirect(url_for('dashboard'))
    
    try:
        # Get list of all migrated tables
        conn = psycopg2.connect(
            host='postgres',
            port=5432,
            database='pcb_inventory',
            user='stockpick_user',
            password='stockpick_pass'
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all tables in the pcb_inventory schema
        cursor.execute("""
            SELECT table_name, 
                   (SELECT COUNT(*) FROM pcb_inventory."" || table_name || "") as record_count
            FROM information_schema.tables 
            WHERE table_schema = 'pcb_inventory' 
            AND table_type = 'BASE TABLE'
            AND table_name NOT IN ('inventory_audit')
            ORDER BY table_name
        """)
        
        # Alternative approach - get tables manually
        cursor.execute("""
            SELECT schemaname, tablename 
            FROM pg_tables 
            WHERE schemaname = 'pcb_inventory'
            AND tablename NOT IN ('inventory_audit')
            ORDER BY tablename
        """)
        
        table_info = []
        for row in cursor.fetchall():
            table_name = row['tablename']
            try:
                # Get record count for each table
                if '"' in table_name:
                    count_sql = f'SELECT COUNT(*) as count FROM pcb_inventory.{table_name}'
                else:
                    count_sql = f'SELECT COUNT(*) as count FROM pcb_inventory."{table_name}"'
                
                cursor.execute(count_sql)
                count_result = cursor.fetchone()
                record_count = count_result['count'] if count_result else 0
                
                # Get column info
                cursor.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'pcb_inventory' 
                    AND table_name = '{table_name}'
                    AND column_name NOT IN ('id', 'created_at')
                    ORDER BY ordinal_position
                """)
                columns = cursor.fetchall()
                
                table_info.append({
                    'name': table_name,
                    'record_count': record_count,
                    'column_count': len(columns),
                    'columns': [col['column_name'] for col in columns[:5]]  # Show first 5 columns
                })
                
            except Exception as e:
                logger.error(f"Error getting info for table {table_name}: {e}")
                table_info.append({
                    'name': table_name,
                    'record_count': 0,
                    'column_count': 0,
                    'columns': []
                })
        
        cursor.close()
        conn.close()
        
        return render_template('sources.html', tables=table_info)
        
    except Exception as e:
        logger.error(f"Error loading sources: {e}")
        flash(f"Error loading sources: {e}", 'error')
        return render_template('sources.html', tables=[])

@app.route('/sources/<table_name>')
@require_auth
def view_source_table(table_name):
    """View data from a specific source table."""
    user_role = session.get('role', 'USER')
    
    # Only super users can access sources
    if user_role != 'ADMIN':
        flash('Access denied: Super user privileges required', 'error')
        return redirect(url_for('dashboard'))
    
    page = request.args.get('page', 1, type=int)
    per_page = 25
    
    try:
        conn = psycopg2.connect(
            host='postgres',
            port=5432,
            database='pcb_inventory',
            user='stockpick_user',
            password='stockpick_pass'
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get total count
        count_sql = f'SELECT COUNT(*) as count FROM pcb_inventory."{table_name}"'
        cursor.execute(count_sql)
        total_records = cursor.fetchone()['count']
        
        # Get paginated data
        offset = (page - 1) * per_page
        data_sql = f'SELECT * FROM pcb_inventory."{table_name}" ORDER BY id LIMIT {per_page} OFFSET {offset}'
        cursor.execute(data_sql)
        records = cursor.fetchall()
        
        # Get column names
        if records:
            columns = [col for col in records[0].keys() if col not in ['id', 'created_at']]
        else:
            columns = []
        
        # Calculate pagination
        total_pages = (total_records + per_page - 1) // per_page
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_records,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
        }
        
        cursor.close()
        conn.close()
        
        return render_template('source_table.html', 
                             table_name=table_name,
                             records=records,
                             columns=columns,
                             pagination=pagination)
        
    except Exception as e:
        logger.error(f"Error viewing table {table_name}: {e}")
        flash(f"Error viewing table: {e}", 'error')
        return redirect(url_for('sources'))

@app.route('/stats')
@require_auth  
def stats():
    """Data migration statistics and comparison page."""
    try:
        # Get current PostgreSQL statistics
        postgres_stats = db_manager.get_stats_summary()
        
        # Source database statistics (actual Access database data)
        source_stats = {
            'total_records': 836,  # Actual records in Access tblPCB_Inventory table  
            'unique_jobs': 750,    # Actual unique jobs from migration
            'total_quantity': 211679,  # Actual total PCBs from migration
            'pcb_types': 3,        # Actual PCB types found (Bare, Partial, Completed)
            'migration_date': 'August 19, 2025'
        }
        
        # Calculate integrity check
        integrity_check = {
            'records_match': abs(postgres_stats['total_records'] - source_stats['total_records']) <= 5,
            'jobs_match': abs(postgres_stats['unique_jobs'] - source_stats['unique_jobs']) <= 2,
            'quantity_match': abs(postgres_stats['total_quantity'] - source_stats['total_quantity']) <= 1000,
            'record_difference': postgres_stats['total_records'] - source_stats['total_records'],
            'job_difference': postgres_stats['unique_jobs'] - source_stats['unique_jobs'],
            'quantity_difference': postgres_stats['total_quantity'] - source_stats['total_quantity']
        }
        
        # Get PCB type breakdown
        pcb_breakdown = db_manager.get_pcb_type_breakdown()
        
        # Get location breakdown  
        location_breakdown = db_manager.get_location_breakdown()
        
        return render_template('stats.html',
                             source_stats=source_stats,
                             postgres_stats=postgres_stats,
                             integrity_check=integrity_check,
                             pcb_breakdown=pcb_breakdown,
                             location_breakdown=location_breakdown)
    except Exception as e:
        logger.error(f"Error loading stats: {e}")
        flash("Error loading statistics page", 'error')
        return redirect(url_for('index'))

# SSO Integration with ACI Dashboard
@app.route('/sso/login', methods=['POST'])
def sso_login():
    """Handle SSO login from ACI Dashboard."""
    try:
        data = request.get_json() or {}

        # Extract user data from ACI Dashboard
        username = data.get('username')
        role = data.get('role', 'USER')
        itar_authorized = data.get('itar_authorized', False)
        auth_token = data.get('token')

        if username:
            session['username'] = username
            session['role'] = role
            session['itar_authorized'] = itar_authorized
            session['aci_auth_token'] = auth_token

            return jsonify({
                'success': True,
                'message': f'User {username} logged in successfully',
                'redirect_url': url_for('index')
            })
        else:
            return jsonify({'success': False, 'error': 'Missing username'}), 400

    except Exception as e:
        logger.error(f"SSO login error: {e}")
        return jsonify({'success': False, 'error': 'SSO login failed'}), 500

# Authentication now handled by ACI Dashboard SSO

# API Endpoints
@app.route('/api/inventory')
@require_auth
def api_inventory():
    """API endpoint for inventory data."""
    try:
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        inventory = db_manager.get_current_inventory(user_role, itar_auth)
        return jsonify({'success': True, 'data': inventory})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stock', methods=['POST'])
@validate_api_request(['pcb_type', 'quantity', 'location'])
@require_auth
def api_stock():
    """API endpoint for stocking PCBs."""
    try:
        data = request.get_json()

        # Use part_number as job identifier (they're the same thing)
        job = data.get('part_number') or data.get('job')
        if not job:
            return jsonify({'success': False, 'error': 'Part number is required'}), 400

        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        itar_classification = data.get('itar_classification', 'NONE')

        # Check ITAR access
        if itar_classification == 'ITAR' and not user_manager.can_access_itar(user_role, itar_auth):
            return jsonify({'success': False, 'error': 'Access denied: ITAR authorization required'}), 403

        result = db_manager.stock_pcb(
            job=job,
            pcb_type=data['pcb_type'],
            quantity=data['quantity'],  # Already validated and converted to int
            location=data['location'],
            itar_classification=itar_classification,
            user_role=user_role,
            itar_auth=itar_auth,
            username=session.get('username', 'system')
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"API stock error: {e}")
        return jsonify({'success': False, 'error': 'Stock operation failed'}), 500

@app.route('/api/pick', methods=['POST'])
@validate_api_request(['pcb_type', 'quantity'])
@require_auth
def api_pick():
    """API endpoint for picking PCBs."""
    try:
        data = request.get_json()

        # Use part_number as job identifier (they're the same thing)
        job = data.get('part_number') or data.get('job')
        if not job:
            return jsonify({'success': False, 'error': 'Part number is required'}), 400

        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)

        result = db_manager.pick_pcb(
            job=job,
            pcb_type=data['pcb_type'],
            quantity=data['quantity'],  # Already validated and converted to int
            user_role=user_role,
            itar_auth=itar_auth,
            username=session.get('username', 'system')
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"API pick error: {e}")
        return jsonify({'success': False, 'error': 'Pick operation failed'}), 500

@app.route('/api/inventory/update', methods=['PUT', 'POST'])
@require_auth
def api_update_inventory():
    """API endpoint for updating inventory items."""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['id', 'job', 'pcb_type', 'quantity', 'location']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing_fields)}"
            }), 400

        # Convert quantity to int
        try:
            quantity = int(data['quantity'])
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid quantity value'}), 400

        # Get PCN if provided
        pcn = None
        if data.get('pcn'):
            try:
                pcn = int(data['pcn'])
            except (ValueError, TypeError):
                pass  # Keep as None if invalid

        result = db_manager.update_inventory(
            inventory_id=int(data['id']),
            job=data['job'],
            pcb_type=data['pcb_type'],
            quantity=quantity,
            location=data['location'],
            pcn=pcn,
            username=session.get('username', 'system')
        )
        return jsonify(result)
    except Exception as e:
        logger.error(f"API update error: {e}")
        return jsonify({'success': False, 'error': 'Update operation failed'}), 500

@app.route('/api/search')
@require_auth
def api_search():
    """API endpoint for searching inventory."""
    try:
        job = request.args.get('job')
        pcb_type = request.args.get('pcb_type')
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)

        inventory = db_manager.search_inventory(
            job=job,
            pcb_type=pcb_type,
            user_role=user_role,
            itar_auth=itar_auth
        )

        # Skip expiration info for search results to avoid serialization issues
        return jsonify({'success': True, 'data': inventory})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/expiration-check')
@require_auth
def api_expiration_check():
    """API endpoint for checking expiration status of specific item."""
    try:
        dc = request.args.get('dc')
        pcb_type = request.args.get('pcb_type', 'Bare')
        msd = request.args.get('msd')

        expiration_info = expiration_manager.calculate_expiration_status(dc, pcb_type, msd)

        return jsonify({
            'success': True,
            'expiration': expiration_info,
            'display_text': expiration_manager.format_expiration_display(expiration_info),
            'badge_class': expiration_manager.get_expiration_badge_class(expiration_info['status']),
            'icon_class': expiration_manager.get_expiration_icon(expiration_info['status'])
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Access Database Routes
@app.route('/source')
def source_access():
    """Source (Access) database browser main page."""
    try:
        from access_db_manager import AccessDBManager
        
        # Path to Access database (mounted in container)
        access_db_path = "/app/INVENTORY TABLE.mdb"
        
        with AccessDBManager(access_db_path) as access_db:
            db_info = access_db.get_database_info()
            
        return render_template('source_access.html', 
                             db_info=db_info,
                             page_title="Source (Access) Database")
    except Exception as e:
        flash(f'Error accessing Access database: {str(e)}', 'error')
        return render_template('source_access.html', 
                             db_info=None,
                             error=str(e),
                             page_title="Source (Access) Database")

@app.route('/source/table/<table_name>')
def source_table_view(table_name):
    """View data from a specific Access database table."""
    try:
        from access_db_manager import AccessDBManager
        
        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 50, type=int)
        offset = (page - 1) * per_page
        
        # Path to Access database (mounted in container)
        access_db_path = "/app/INVENTORY TABLE.mdb"
        
        with AccessDBManager(access_db_path) as access_db:
            # Get table schema
            schema = access_db.get_table_schema(table_name)
            
            # Get table data
            data, total_records = access_db.get_table_data(table_name, limit=per_page, offset=offset)
            
            # Calculate pagination info with safety checks
            total_records = max(0, total_records)  # Ensure non-negative
            total_pages = max(1, (total_records + per_page - 1) // per_page) if total_records > 0 else 1
            has_prev = page > 1
            has_next = page < total_pages
            
            pagination_info = {
                'page': page,
                'per_page': per_page,
                'total_records': total_records,
                'total_pages': total_pages,
                'has_prev': has_prev,
                'has_next': has_next,
                'prev_page': page - 1 if has_prev else None,
                'next_page': page + 1 if has_next else None
            }
            
        return render_template('source_table_view.html',
                             table_name=table_name,
                             schema=schema,
                             data=data,
                             pagination=pagination_info,
                             page_title=f"Table: {table_name}")
    except Exception as e:
        # Log the full exception for debugging
        app.logger.error(f'Error viewing table {table_name}: {str(e)}', exc_info=True)
        flash(f'Error viewing table {table_name}: {str(e)}', 'error')
        return redirect(url_for('source_access'))

@app.route('/source/query', methods=['GET', 'POST'])
def source_query():
    """DISABLED: Raw SQL query interface removed for security reasons."""
    flash("Raw SQL query interface has been disabled for security reasons. Use the table view instead.", "warning")
    return redirect(url_for('source_access'))

@app.route('/api/source/tables')
def api_source_tables():
    """API endpoint to get Access database table list."""
    try:
        from access_db_manager import AccessDBManager
        
        # Path to Access database (mounted in container)
        access_db_path = "/app/INVENTORY TABLE.mdb"
        
        with AccessDBManager(access_db_path) as access_db:
            tables = access_db.get_table_list()
            
        return jsonify({'success': True, 'data': tables})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/source/table-data/<table_name>')
def api_source_table_data(table_name):
    """API endpoint to get actual data from Access database table."""
    try:
        from access_db_manager import AccessDBManager
        
        # Get query parameters
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Path to Access database (mounted in container)
        access_db_path = "/app/INVENTORY TABLE.mdb"
        
        with AccessDBManager(access_db_path) as access_db:
            data, total_records = access_db.get_table_data(table_name, limit=limit, offset=offset)
            
            # Check if we got actual data or fallback message
            if data and len(data) > 0:
                first_row = data[0]
                # Check if this is our fallback data (contains 'Message' key)
                if 'Message' in first_row and 'requires mdb-tools' in str(first_row.get('Message', '')):
                    return jsonify({
                        'success': False, 
                        'message': first_row.get('Message', 'Data access limited'),
                        'note': first_row.get('Note', ''),
                        'alternative': first_row.get('Alternative', '')
                    })
                else:
                    # This is actual data
                    return jsonify({
                        'success': True, 
                        'data': data, 
                        'total_records': total_records,
                        'table_name': table_name
                    })
            else:
                return jsonify({
                    'success': False, 
                    'message': 'No data available',
                    'total_records': 0
                })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/generate-pcn')
def generate_pcn():
    """Generate PCN page"""
    return render_template('generate_pcn.html')

@app.route('/po-history')
def po_history():
    """PO History lookup page"""
    return render_template('po_history.html')

@app.route('/pcn-history')
def pcn_history():
    """PCN History lookup page"""
    return render_template('pcn_history.html')

@app.route('/api/pcn/generate', methods=['POST'])
@csrf.exempt
def api_generate_pcn():
    """API endpoint to generate new PCN"""
    conn = None
    cursor = None
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('item'):
            return jsonify({'error': 'Item (Job Number) is required'}), 400

        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Generate new PCN number
            cursor.execute("SELECT pcb_inventory.generate_pcn_number() as pcn_number")
            result = cursor.fetchone()
            pcn_number = result['pcn_number']

            # Format PCN number as 5-digit string with leading zeros
            pcn_number_str = str(pcn_number).zfill(5)

            # Create barcode data string (pipe-delimited) - contains ALL label information
            # Format: PCN|Item|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
            barcode_data = f"{pcn_number_str}|{data.get('item', '')}|{data.get('mpn', '')}|{data.get('part_number', '')}|{data.get('quantity', '')}|{data.get('po_number', '')}|{data.get('location', '')}|{data.get('pcb_type', '')}|{data.get('date_code', '')}|{data.get('msd', '')}"

            # Insert PCN record
            cursor.execute("""
                INSERT INTO pcb_inventory.pcn_records
                (pcn_number, item, po_number, part_number, mpn, quantity, date_code, msd, barcode_data, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING pcn_id, pcn_number, item, po_number, part_number, mpn, quantity, date_code, msd, created_at
            """, (
                pcn_number,
                data.get('item'),
                data.get('po_number'),
                data.get('part_number'),
                data.get('mpn'),
                data.get('quantity'),
                data.get('date_code'),
                data.get('msd'),
                barcode_data,
                session.get('username', 'system')
            ))

            pcn_record = cursor.fetchone()

            # Insert into pcn_history table for tracking
            cursor.execute("""
                INSERT INTO pcb_inventory.pcn_history
                (pcn, job, qty, date_code, msd, work_order, generated_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                pcn_number,
                data.get('item'),
                data.get('quantity'),
                data.get('date_code'),
                data.get('msd'),
                data.get('po_number'),  # Using PO number as work_order
                session.get('username', 'system')
            ))
            logger.info(f"Added PCN {pcn_number} to pcn_history table")

            # If PO number is provided, also add it to PO history
            if data.get('po_number'):
                cursor.execute("""
                    INSERT INTO pcb_inventory.po_history
                    (po_number, item, pcn, mpn, date_code, quantity, transaction_type,
                     transaction_date, location_from, location_to, user_id)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s)
                """, (
                    data.get('po_number'),
                    data.get('item'),
                    pcn_number,
                    data.get('mpn'),
                    data.get('date_code'),
                    data.get('quantity'),
                    'PCN Generation',
                    'Stock',
                    'Inventory',
                    session.get('username', 'system')
                ))
                logger.info(f"Added PO {data.get('po_number')} to PO history (PCN: {pcn_number})")

            conn.commit()

            logger.info(f"Generated PCN: {pcn_number} for item: {data.get('item')}")

            return jsonify({
                'success': True,
                'pcn_number': pcn_number_str,  # Return as string for barcode compatibility
                'pcn_id': pcn_record['pcn_id'],
                'item': pcn_record['item'],
                'po_number': pcn_record['po_number'],
                'part_number': pcn_record['part_number'],
                'mpn': pcn_record['mpn'],
                'quantity': pcn_record['quantity'],
                'date_code': pcn_record['date_code'],
                'msd': pcn_record['msd'],
                'barcode_data': barcode_data,
                'created_at': pcn_record['created_at'].isoformat() if pcn_record['created_at'] else None
            })

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error generating PCN: {e}")
            return jsonify({'error': str(e)}), 500
        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error in PCN generation endpoint: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/pcn/details/<pcn_number>', methods=['GET'])
def api_get_pcn_details(pcn_number):
    """API endpoint to get PCN details by PCN number - for auto-populating fields on scan"""
    conn = None
    cursor = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # First try pcn_records table
            cursor.execute("""
                SELECT pcn_number, item, po_number, part_number, mpn,
                       quantity, date_code, msd, created_at, created_by
                FROM pcb_inventory.pcn_records
                WHERE pcn_number = %s
            """, (pcn_number,))

            record = cursor.fetchone()

            if record:
                # Format PCN number as 5-digit string with leading zeros for barcode
                pcn_str = str(record['pcn_number']).zfill(5)
                return jsonify({
                    'success': True,
                    'pcn_number': pcn_str,
                    'part_number': record['part_number'] or record['item'],
                    'job': record['item'],
                    'po_number': record['po_number'],
                    'mpn': record['mpn'],
                    'quantity': record['quantity'],
                    'date_code': record['date_code'],
                    'msd': record['msd'],
                    'created_at': record['created_at'].isoformat() if record['created_at'] else None,
                    'created_by': record['created_by']
                })

            # If not in pcn_records, try pcn_history
            cursor.execute("""
                SELECT pcn, job, qty, date_code, msd AS msd_level,
                       work_order, location, pcb_type, generated_at, generated_by
                FROM pcb_inventory.pcn_history
                WHERE pcn = %s
                ORDER BY generated_at DESC
                LIMIT 1
            """, (pcn_number,))

            history_record = cursor.fetchone()

            if history_record:
                # Format PCN number as 5-digit string with leading zeros for barcode
                pcn_str = str(history_record['pcn']).zfill(5) if history_record['pcn'] else None
                return jsonify({
                    'success': True,
                    'pcn_number': pcn_str,
                    'part_number': history_record['job'],
                    'job': history_record['job'],
                    'quantity': history_record['qty'],
                    'date_code': history_record['date_code'],
                    'msd': history_record['msd_level'],
                    'pcb_type': history_record['pcb_type'],
                    'work_order': history_record['work_order'],
                    'location': history_record['location'],
                    'created_at': history_record['generated_at'].isoformat() if history_record['generated_at'] else None,
                    'created_by': history_record['generated_by']
                })

            return jsonify({'success': False, 'error': 'PCN not found'}), 404

        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error fetching PCN details: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/pcn/list', methods=['GET'])
def api_list_pcn():
    """API endpoint to list PCN records"""
    conn = None
    cursor = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            cursor.execute("""
                SELECT pcn_id, pcn_number, item, po_number, part_number, mpn,
                       quantity, date_code, msd, created_at, created_by
                FROM pcb_inventory.pcn_records
                ORDER BY pcn_id DESC
                LIMIT 100
            """)

            records = cursor.fetchall()

            return jsonify({
                'success': True,
                'records': [{
                    'pcn_id': r['pcn_id'],
                    'pcn_number': str(r['pcn_number']).zfill(5),  # Format as string with leading zeros
                    'item': r['item'],
                    'po_number': r['po_number'],
                    'part_number': r['part_number'],
                    'mpn': r['mpn'],
                    'quantity': r['quantity'],
                    'date_code': r['date_code'],
                    'msd': r['msd'],
                    'created_at': r['created_at'].isoformat() if r['created_at'] else None,
                    'created_by': r['created_by']
                } for r in records]
            })

        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error listing PCN records: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/pcn/delete/<pcn_number>', methods=['DELETE'])
@csrf.exempt
def api_delete_pcn(pcn_number):
    """API endpoint to delete a PCN record"""
    conn = None
    cursor = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Check if PCN exists in pcn_records table first
            cursor.execute("""
                SELECT pcn_number, item
                FROM pcb_inventory.pcn_records
                WHERE pcn_number = %s
            """, (pcn_number,))

            pcn_record = cursor.fetchone()

            # If not in pcn_records, check pcn_history
            if not pcn_record:
                cursor.execute("""
                    SELECT pcn, job
                    FROM pcb_inventory.pcn_history
                    WHERE pcn = %s
                """, (pcn_number,))

                history_record = cursor.fetchone()

                if not history_record:
                    return jsonify({'success': False, 'error': 'PCN not found'}), 404

                # PCN exists only in history
                item_name = history_record['job']
            else:
                item_name = pcn_record['item']

            # Delete from pcn_history table
            cursor.execute("""
                DELETE FROM pcb_inventory.pcn_history
                WHERE pcn = %s
            """, (pcn_number,))

            # Delete from po_history if exists
            cursor.execute("""
                DELETE FROM pcb_inventory.po_history
                WHERE pcn = %s
            """, (pcn_number,))

            # Delete from pcn_records table if it exists there
            cursor.execute("""
                DELETE FROM pcb_inventory.pcn_records
                WHERE pcn_number = %s
            """, (pcn_number,))

            conn.commit()

            logger.info(f"Deleted PCN {pcn_number} (Item: {item_name}) by user: {session.get('username', 'system')}")

            return jsonify({
                'success': True,
                'message': f'PCN {pcn_number} deleted successfully',
                'pcn_number': pcn_number
            })

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error deleting PCN {pcn_number}: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500
        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error in PCN delete endpoint: {e}")
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

@app.route('/api/pcn/assign', methods=['POST'])
@require_auth
def api_assign_pcn():
    """API endpoint to assign PCN to inventory item"""
    try:
        data = request.get_json()

        # Validate required fields
        if not data.get('job') or not data.get('pcb_type'):
            return jsonify({'success': False, 'error': 'Job and PCB type are required'}), 400

        username = session.get('username', 'system')
        result = db_manager.assign_pcn_to_item(
            job=data['job'],
            pcb_type=data['pcb_type'],
            username=username
        )

        return jsonify(result)
    except Exception as e:
        logger.error(f"Error assigning PCN: {e}")
        return jsonify({'success': False, 'error': 'Failed to assign PCN'}), 500

@app.route('/api/pcn/history', methods=['GET'])
def api_pcn_history():
    """API endpoint to get PCN transaction history - NO AUTH REQUIRED for public access"""
    try:
        limit = request.args.get('limit', 1000, type=int)
        pcn = request.args.get('pcn', None)
        item = request.args.get('item', None)
        transaction_type = request.args.get('transaction_type', None)

        filters = {}
        if pcn:
            filters['pcn'] = pcn
        if item:
            filters['item'] = item
        if transaction_type:
            filters['transaction_type'] = transaction_type

        history = db_manager.get_pcn_history(limit=limit, filters=filters if filters else None)

        return jsonify({'success': True, 'data': history, 'total': len(history)})
    except Exception as e:
        logger.error(f"Error getting PCN history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pcn/search', methods=['GET'])
@require_auth
def api_pcn_search():
    """API endpoint to search PCN records"""
    try:
        pcn_number = request.args.get('pcn', None)
        job = request.args.get('job', None)

        if not pcn_number and not job:
            return jsonify({'success': False, 'error': 'PCN number or job is required'}), 400

        results = db_manager.search_pcn(pcn_number=pcn_number, job=job)

        # Format dates for JSON serialization
        for record in results:
            if record.get('generated_at'):
                record['generated_at'] = record['generated_at'].isoformat()

        return jsonify({'success': True, 'data': results})
    except Exception as e:
        logger.error(f"Error searching PCN: {e}")
        return jsonify({'success': False, 'error': 'Failed to search PCN'}), 500

@app.route('/api/pcn/transaction/update', methods=['POST'])
@require_auth
def api_update_transaction():
    """API endpoint for updating transaction records"""
    try:
        data = request.get_json()

        # Validate required fields
        required_fields = ['id', 'job', 'quantity', 'transaction_type']
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            return jsonify({
                'success': False,
                'error': f"Missing required fields: {', '.join(missing_fields)}"
            }), 400

        transaction_id = int(data['id'])

        # Build update query
        updates = []
        params = []

        if data.get('pcn'):
            updates.append('pcn = %s')
            params.append(int(data['pcn']))

        if data.get('job'):
            updates.append('item = %s')
            params.append(data['job'])

        if data.get('quantity') is not None:
            updates.append('tranqty = %s')
            params.append(int(data['quantity']))

        if data.get('location_from') is not None:
            updates.append('loc_from = %s')
            params.append(data['location_from'])

        if data.get('location_to') is not None:
            updates.append('loc_to = %s')
            params.append(data['location_to'])

        if data.get('work_order') is not None:
            updates.append('wo = %s')
            params.append(data['work_order'])

        if data.get('transaction_type'):
            updates.append('trantype = %s')
            params.append(data['transaction_type'])

        if not updates:
            return jsonify({'success': False, 'error': 'No fields to update'}), 400

        # Add ID for WHERE clause
        params.append(transaction_id)

        # Execute update
        query = f'''
            UPDATE pcb_inventory."tblTransaction"
            SET {', '.join(updates)}
            WHERE id = %s
            RETURNING id, item, pcn, tranqty, loc_from, loc_to, wo, trantype
        '''

        with db_manager.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(query, params)
                result = cursor.fetchone()
                conn.commit()

        if result:
            logger.info(f"Transaction {transaction_id} updated by {session.get('username', 'system')}")
            return jsonify({
                'success': True,
                'id': result['id'],
                'job': result['item'],
                'pcn': result['pcn'],
                'quantity': result['tranqty'],
                'location_from': result['loc_from'],
                'location_to': result['loc_to'],
                'work_order': result['wo'],
                'transaction_type': result['trantype']
            })
        else:
            return jsonify({'success': False, 'error': 'Transaction not found'}), 404

    except ValueError as e:
        logger.error(f"Validation error updating transaction: {e}")
        return jsonify({'success': False, 'error': 'Invalid data format'}), 400
    except Exception as e:
        logger.error(f"Error updating transaction: {e}")
        return jsonify({'success': False, 'error': 'Update operation failed'}), 500

@app.route('/api/po/history', methods=['GET'])
def api_po_history():
    """API endpoint to get PO history - NO AUTH REQUIRED for public access"""
    try:
        limit = request.args.get('limit', 100, type=int)
        po_number = request.args.get('po_number', None)
        item = request.args.get('item', None)
        date_from = request.args.get('date_from', None)
        date_to = request.args.get('date_to', None)

        filters = {}
        if po_number:
            filters['po_number'] = po_number
        if item:
            filters['item'] = item
        if date_from:
            filters['date_from'] = date_from
        if date_to:
            filters['date_to'] = date_to

        history = db_manager.get_po_history(limit=limit, filters=filters if filters else None)

        # Format the response to match the template expectations
        for record in history:
            # Add po_number as alias for purchase_order (template compatibility)
            record['po_number'] = record.get('purchase_order', '')
            # Add quantity as alias for quantity_received
            if 'quantity_received' in record:
                record['quantity'] = record['quantity_received']
            # Add transaction_date as alias for date_received
            if 'date_received' in record:
                record['transaction_date'] = record['date_received']

        return jsonify({'success': True, 'data': history, 'total': len(history)})
    except Exception as e:
        logger.error(f"Error getting PO history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/po/search', methods=['GET'])
def api_po_search():
    """API endpoint to search PO records - NO AUTH REQUIRED for public access"""
    try:
        po_number = request.args.get('po_number', None)
        item = request.args.get('item', None)

        if not po_number and not item:
            return jsonify({'success': False, 'error': 'PO number or item is required'}), 400

        results = db_manager.search_po(po_number=po_number, item=item)

        # Format dates for JSON serialization
        for record in results:
            if record.get('transaction_date'):
                record['transaction_date'] = record['transaction_date'].isoformat()
            if record.get('created_at'):
                record['created_at'] = record['created_at'].isoformat()

        return jsonify({'success': True, 'data': results, 'total': len(results)})
    except Exception as e:
        logger.error(f"Error searching PO: {e}")
        return jsonify({'success': False, 'error': 'Failed to search PO'}), 500

@app.route('/print-label/<pcn_number>')
def print_label(pcn_number):
    """Dedicated print page for barcode label"""
    conn = None
    cursor = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Try to get from pcn_records first (has full details + barcode_data)
            cursor.execute("""
                SELECT pcn_number, item, po_number, part_number, mpn,
                       quantity, date_code, msd, barcode_data,
                       NULL as location, NULL as pcb_type
                FROM pcb_inventory.pcn_records
                WHERE pcn_number = %s
            """, (pcn_number,))

            pcn_data = cursor.fetchone()

            # If not found in pcn_records, try pcn_history (with new columns)
            if not pcn_data:
                cursor.execute("""
                    SELECT pcn::varchar as pcn_number,
                           job as item,
                           work_order as po_number,
                           NULL as part_number,
                           NULL as mpn,
                           qty as quantity,
                           date_code,
                           msd,
                           location,
                           pcb_type
                    FROM pcb_inventory.pcn_history
                    WHERE pcn::varchar = %s
                """, (pcn_number,))
                pcn_data = cursor.fetchone()

            if not pcn_data:
                return "PCN not found", 404

            import time
            # Add timestamp to force cache invalidation
            data_with_version = dict(pcn_data)
            data_with_version['_cache_bust'] = str(int(time.time()))

            response = make_response(render_template('print_label.html', data=data_with_version))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, post-check=0, pre-check=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '-1'
            response.headers['Last-Modified'] = 'Mon, 01 Jan 2024 00:00:00 GMT'
            return response

        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error loading print label: {e}")
        return "Error loading label", 500

@app.route('/print-label/<pcn_number>/zpl')
def generate_zpl_label(pcn_number):
    """Generate ZPL code for Zebra ZP450 printer (3x1 inch label)"""
    conn = None
    cursor = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get PCN data (same as print_label)
            cursor.execute("""
                SELECT pcn_number, item, po_number, part_number, mpn,
                       quantity, date_code, msd
                FROM pcb_inventory.pcn_records
                WHERE pcn_number = %s
            """, (pcn_number,))

            pcn_data = cursor.fetchone()

            if not pcn_data:
                cursor.execute("""
                    SELECT pcn::varchar as pcn_number,
                           job as item,
                           work_order as po_number,
                           NULL as part_number,
                           NULL as mpn,
                           qty as quantity,
                           date_code,
                           msd
                    FROM pcb_inventory.pcn_history
                    WHERE pcn::varchar = %s
                """, (pcn_number,))
                pcn_data = cursor.fetchone()

            if not pcn_data:
                return "PCN not found", 404

            # Convert to dict
            data = dict(pcn_data)

            # Build barcode data with ALL fields (pipe-separated)
            # Format: PCN|Job|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
            barcode_data = '|'.join([
                str(data.get('pcn_number', '')),
                str(data.get('item', '')),
                str(data.get('mpn', '')),
                str(data.get('part_number', '')),
                str(data.get('quantity', '')),
                str(data.get('po_number', '')),
                str(data.get('location', '')),
                str(data.get('pcb_type', '')),
                str(data.get('date_code', '')),
                str(data.get('msd', ''))
            ])

            # Generate ZPL code for 3x1 inch label (Zebra ZP450)
            # Label dimensions: 3 inches wide (609 dots @ 203dpi), 1 inch tall (203 dots @ 203dpi)
            # CODE128 with ALL data - COMPACT size like barcode.png but all info encoded!
            zpl = f"""^XA
^FO0,0^GB609,0,2^FS
^FO0,0^GB0,203,2^FS
^FO609,0^GB0,203,2^FS
^FO0,203^GB609,0,2^FS

^FO10,15^A0N,22,22^FDPCN: {data['pcn_number']}^FS

^FO120,12^BY0.3,2,22^BCN,22,N,N,N^FD{barcode_data}^FS

^FO520,10^A0N,16,16^FDQTY^FS
^FO520,30^A0N,26,26^FD{data.get('quantity', 0)}^FS

^FO0,75^GB609,0,1^FS

^FO10,85^A0N,16,16^FDJob: {data.get('item', 'N/A')[:20]}^FS
^FO10,107^A0N,16,16^FDMPN: {data.get('mpn', 'N/A')[:20]}^FS
^FO10,129^A0N,16,16^FDPO: {data.get('po_number', 'N/A')[:20]}^FS

^FO340,85^A0N,16,16^FDDC: {data.get('date_code', 'N/A')[:12]}^FS
^FO340,107^A0N,16,16^FDMSD: {data.get('msd', 'N/A')[:12]}^FS

^XZ"""

            # Return ZPL as downloadable file
            response = make_response(zpl)
            response.headers['Content-Type'] = 'application/zpl'
            response.headers['Content-Disposition'] = f'attachment; filename="PCN_{pcn_number}.zpl"'
            return response

        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error generating ZPL: {e}")
        return "Error generating ZPL", 500

@app.route('/api/valuation/snapshots', methods=['GET'])
def api_get_valuation_snapshots():
    """Get list of available pricing snapshots - simplified to return empty list"""
    try:
        # Pricing snapshot feature not available - return empty list
        return jsonify({'success': True, 'snapshots': []})

    except Exception as e:
        logger.error(f"Error fetching valuation snapshots: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/valuation/<snapshot_date>', methods=['GET'])
def api_get_valuation_by_date(snapshot_date):
    """Get inventory valuation - simplified to return current inventory summary"""
    conn = None
    try:
        # Validate date format
        from datetime import datetime, date
        try:
            parsed_date = datetime.strptime(snapshot_date, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({
                'success': False,
                'error': f'Invalid date format. Use YYYY-MM-DD (e.g., 2025-08-31)'
            }), 400

        conn = db_manager.get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Calculate inventory value by joining with BOM cost data
        cur.execute("""
            SELECT
                COUNT(DISTINCT inv.job) as item_count,
                SUM(COALESCE(inv.qty, 0)) as total_quantity,
                SUM(COALESCE(inv.qty, 0) * COALESCE(bom.cost, 0)) as total_value,
                COUNT(CASE WHEN bom.cost IS NOT NULL AND bom.cost > 0 THEN 1 END) as items_with_cost
            FROM pcb_inventory."tblPCB_Inventory" inv
            LEFT JOIN LATERAL (
                SELECT AVG(cost) as cost
                FROM pcb_inventory."tblBOM"
                WHERE job::text = inv.job
                  AND cost IS NOT NULL
                  AND cost > 0
            ) bom ON true
            WHERE inv.qty > 0
        """)
        result_row = cur.fetchone()

        cur.close()

        total_value = float(result_row['total_value']) if result_row and result_row['total_value'] else 0
        item_count = int(result_row['item_count']) if result_row and result_row['item_count'] else 0
        items_with_cost = int(result_row['items_with_cost']) if result_row and result_row['items_with_cost'] else 0

        cost_coverage = (items_with_cost / item_count * 100) if item_count > 0 else 0

        result = {
            'success': True,
            'snapshot': {
                'date': snapshot_date,
                'total_value': round(total_value, 2),
                'total_quantity': int(result_row['total_quantity']) if result_row and result_row['total_quantity'] else 0,
                'item_count': item_count,
                'notes': f'Calculated from BOM cost data ({items_with_cost}/{item_count} jobs have pricing - {cost_coverage:.1f}% coverage)'
            }
        }

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error fetching valuation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            db_manager.return_connection(conn)

@app.route('/api/inventory/history', methods=['GET'])
@require_auth
def api_inventory_history():
    """API endpoint to get inventory change history"""
    conn = None
    try:
        conn = db_manager.get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Get query parameters
        limit = request.args.get('limit', 100, type=int)
        inventory_id = request.args.get('inventory_id', type=int)
        job = request.args.get('job')
        change_type = request.args.get('change_type')
        changed_by = request.args.get('changed_by')

        # Build query
        query = "SELECT * FROM pcb_inventory.v_inventory_full_history WHERE 1=1"
        params = []

        if inventory_id:
            query += " AND inventory_id = %s"
            params.append(inventory_id)

        if job:
            query += " AND job = %s"
            params.append(job)

        if change_type:
            query += " AND change_type = %s"
            params.append(change_type)

        if changed_by:
            query += " AND changed_by = %s"
            params.append(changed_by)

        query += " ORDER BY change_timestamp DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, tuple(params))
        history = cur.fetchall()

        # Format dates for JSON serialization
        for record in history:
            if record.get('change_timestamp'):
                record['change_timestamp'] = record['change_timestamp'].isoformat()
            if record.get('inventory_created_at'):
                record['inventory_created_at'] = record['inventory_created_at'].isoformat()
            if record.get('inventory_updated_at'):
                record['inventory_updated_at'] = record['inventory_updated_at'].isoformat()

        cur.close()
        return jsonify({'success': True, 'data': history, 'total': len(history)})

    except Exception as e:
        logger.error(f"Error fetching inventory history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            db_manager.return_connection(conn)

@app.route('/api/inventory/history/job/<job_number>', methods=['GET'])
@require_auth
def api_job_history(job_number):
    """API endpoint to get complete history for a specific job"""
    conn = None
    try:
        conn = db_manager.get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute(
            "SELECT * FROM pcb_inventory.get_job_history(%s)",
            (job_number,)
        )
        history = cur.fetchall()

        # Format dates for JSON serialization
        for record in history:
            if record.get('change_timestamp'):
                record['change_timestamp'] = record['change_timestamp'].isoformat()

        cur.close()
        return jsonify({'success': True, 'job': job_number, 'history': history})

    except Exception as e:
        logger.error(f"Error fetching job history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            db_manager.return_connection(conn)

@app.route('/api/inventory/history/pcn-assignments', methods=['GET'])
@require_auth
def api_pcn_assignment_history():
    """API endpoint to get all PCN assignments from inventory history"""
    conn = None
    try:
        conn = db_manager.get_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SELECT * FROM pcb_inventory.get_pcn_assignments()")
        assignments = cur.fetchall()

        # Format dates for JSON serialization
        for record in assignments:
            if record.get('assigned_at'):
                record['assigned_at'] = record['assigned_at'].isoformat()

        cur.close()
        return jsonify({'success': True, 'assignments': assignments})

    except Exception as e:
        logger.error(f"Error fetching PCN assignments: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        if conn:
            db_manager.return_connection(conn)

@app.route('/history')
@require_auth
def inventory_history_page():
    """Inventory history page showing all changes"""
    return render_template('history.html')

# ================== BOM ROUTES ==================

@app.route('/bom')
@require_auth
def bom_browser():
    """BOM Browser page"""
    return render_template('bom_browser.html')

@app.route('/api/bom/search', methods=['GET'])
@require_auth
def api_bom_search():
    """API endpoint to search BOM records"""
    try:
        job = request.args.get('job')
        mpn = request.args.get('mpn')
        customer = request.args.get('customer')

        with db_manager.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Build dynamic query
            where_clauses = []
            params = []

            if job:
                where_clauses.append('job::text = %s')
                params.append(job)

            if mpn:
                where_clauses.append('mpn ILIKE %s')
                params.append(f'%{mpn}%')

            if customer:
                where_clauses.append('cust ILIKE %s')
                params.append(f'%{customer}%')

            where_sql = ' AND '.join(where_clauses) if where_clauses else '1=1'

            query = f'''
                SELECT id, line, "DESC", man, mpn, aci_pn, qty, pou, loc, cost,
                       job, job_rev, last_rev, cust, cust_pn, cust_rev, date_loaded
                FROM pcb_inventory."tblBOM"
                WHERE {where_sql}
                ORDER BY job, line
                LIMIT 1000
            '''

            cur.execute(query, params)
            results = cur.fetchall()

            # Convert to list of dicts
            data = [dict(row) for row in results]

            return jsonify({'success': True, 'data': data, 'count': len(data)})

    except Exception as e:
        logger.error(f"Error searching BOM: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/bom/export', methods=['GET'])
@require_auth
def api_bom_export():
    """Export BOM to Excel"""
    try:
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from flask import send_file

        job = request.args.get('job')
        if not job:
            return jsonify({'success': False, 'error': 'Job number required'}), 400

        with db_manager.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute('''
                SELECT line, "DESC", man, mpn, aci_pn, qty, loc, cost,
                       job_rev, cust, cust_pn
                FROM pcb_inventory."tblBOM"
                WHERE job::text = %s
                ORDER BY line
            ''', (job,))

            results = cur.fetchall()

            if not results:
                return jsonify({'success': False, 'error': 'No BOM data found'}), 404

            # Create Excel workbook
            wb = Workbook()
            ws = wb.active
            ws.title = f"BOM {job}"

            # Header row
            headers = ['Line', 'Description', 'Manufacturer', 'MPN', 'ACI PN', 'Qty', 'Locations', 'Unit Cost', 'Ext Cost']
            ws.append(headers)

            # Style header
            header_fill = PatternFill(start_color="4CAF50", end_color="4CAF50", fill_type="solid")
            header_font = Font(bold=True, color="FFFFFF")
            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center')

            # Data rows
            total_cost = 0
            for row in results:
                unit_cost = float(row['cost']) if row['cost'] else 0
                qty = int(row['qty']) if row['qty'] else 0
                ext_cost = unit_cost * qty
                total_cost += ext_cost

                ws.append([
                    row['line'],
                    row['DESC'],
                    row['man'],
                    row['mpn'],
                    row['aci_pn'],
                    qty,
                    row['loc'],
                    unit_cost,
                    ext_cost
                ])

            # Add total row
            ws.append(['', '', '', '', '', '', 'TOTAL:', '', total_cost])
            last_row = ws.max_row
            ws[f'H{last_row}'].font = Font(bold=True)
            ws[f'I{last_row}'].font = Font(bold=True)

            # Adjust column widths
            ws.column_dimensions['A'].width = 6
            ws.column_dimensions['B'].width = 40
            ws.column_dimensions['C'].width = 15
            ws.column_dimensions['D'].width = 20
            ws.column_dimensions['E'].width = 12
            ws.column_dimensions['F'].width = 8
            ws.column_dimensions['G'].width = 30
            ws.column_dimensions['H'].width = 12
            ws.column_dimensions['I'].width = 12

            # Save to BytesIO
            output = io.BytesIO()
            wb.save(output)
            output.seek(0)

            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'BOM_{job}.xlsx'
            )

    except Exception as e:
        logger.error(f"Error exporting BOM: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== SHORTAGE REPORT ROUTES =====

@app.route('/shortage')
@require_auth
def shortage_report():
    """Render shortage report page"""
    return render_template('shortage_report.html')

@app.route('/api/shortage/calculate', methods=['GET'])
@require_auth
def api_calculate_shortage():
    """Calculate shortage by comparing BOM requirements against current inventory"""
    try:
        job = request.args.get('job')
        quantity = request.args.get('quantity', type=int)

        if not job or not quantity or quantity < 1:
            return jsonify({
                'success': False,
                'error': 'Job number and valid quantity required'
            }), 400

        with db_manager.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Get BOM for this job
            cur.execute('''
                SELECT id, line, "DESC" as description, man, mpn, aci_pn, qty, pou, loc, cost
                FROM pcb_inventory."tblBOM"
                WHERE job::text = %s
                ORDER BY line
            ''', (job,))

            bom_items = cur.fetchall()

            if not bom_items:
                return jsonify({
                    'success': False,
                    'error': f'No BOM found for job {job}'
                }), 404

            # Get current component inventory grouped by MPN from warehouse
            cur.execute('''
                SELECT
                    mpn,
                    SUM(onhandqty) as total_qty,
                    MAX(loc_to) as location
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE mpn IS NOT NULL AND mpn != ''
                GROUP BY mpn
            ''')

            inventory_dict = {row['mpn']: row for row in cur.fetchall()}

            # Calculate shortage for each BOM item
            shortage_items = []
            total_parts = len(bom_items)
            parts_in_stock = 0
            parts_short = 0
            total_shortage_cost = 0.0

            for bom_item in bom_items:
                mpn = bom_item['mpn'] or bom_item['aci_pn']
                qty_per_board = float(bom_item['qty'] or 0)
                total_required = qty_per_board * quantity
                unit_cost = float(bom_item['cost'] or 0)

                # Find inventory by MPN
                on_hand = 0
                if mpn and mpn in inventory_dict:
                    on_hand = float(inventory_dict[mpn]['total_qty'] or 0)

                shortage = max(0, total_required - on_hand)
                shortage_cost = shortage * unit_cost

                if shortage > 0:
                    parts_short += 1
                    total_shortage_cost += shortage_cost
                else:
                    parts_in_stock += 1

                shortage_items.append({
                    'line': bom_item['line'],
                    'description': bom_item['description'],
                    'mpn': mpn,
                    'qty_per_board': qty_per_board,
                    'total_required': total_required,
                    'on_hand': on_hand,
                    'shortage': shortage,
                    'unit_cost': unit_cost,
                    'shortage_cost': shortage_cost,
                    'location': bom_item['loc']
                })

            result = {
                'job': job,
                'quantity_needed': quantity,
                'total_parts': total_parts,
                'parts_in_stock': parts_in_stock,
                'parts_short': parts_short,
                'total_shortage_cost': total_shortage_cost,
                'shortage_items': shortage_items
            }

            return jsonify({'success': True, 'data': result})

    except Exception as e:
        logger.error(f"Error calculating shortage: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/shortage/export', methods=['GET'])
@require_auth
def api_export_shortage():
    """Export shortage report to Excel"""
    try:
        job = request.args.get('job')
        quantity = request.args.get('quantity', type=int)

        if not job or not quantity:
            return jsonify({'success': False, 'error': 'Job and quantity required'}), 400

        # Re-calculate shortage (to ensure fresh data)
        with db_manager.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # Get BOM
            cur.execute('''
                SELECT id, line, "DESC" as description, man, mpn, aci_pn, qty, pou, loc, cost
                FROM pcb_inventory."tblBOM"
                WHERE job::text = %s
                ORDER BY line
            ''', (job,))
            bom_items = cur.fetchall()

            if not bom_items:
                return jsonify({'success': False, 'error': 'No BOM found'}), 404

            # Get component inventory from warehouse
            cur.execute('''
                SELECT mpn, SUM(onhandqty) as total_qty
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE mpn IS NOT NULL AND mpn != ''
                GROUP BY mpn
            ''')
            inventory_dict = {row['mpn']: row for row in cur.fetchall()}

            # Calculate shortages
            shortage_items = []
            for bom_item in bom_items:
                mpn = bom_item['mpn'] or bom_item['aci_pn']
                qty_per_board = float(bom_item['qty'] or 0)
                total_required = qty_per_board * quantity
                on_hand = float(inventory_dict.get(mpn, {}).get('total_qty', 0))
                shortage = max(0, total_required - on_hand)
                unit_cost = float(bom_item['cost'] or 0)

                if shortage > 0:  # Only include items with shortage
                    shortage_items.append({
                        'Line': bom_item['line'],
                        'Description': bom_item['description'],
                        'Manufacturer': bom_item['man'],
                        'MPN': mpn,
                        'Location': bom_item['loc'],
                        'Qty Per Board': qty_per_board,
                        'Total Required': total_required,
                        'On Hand': on_hand,
                        'Shortage': shortage,
                        'Unit Cost': unit_cost,
                        'Shortage Cost': shortage * unit_cost
                    })

        # Create Excel workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = f"Shortage {job}"

        # Add title
        ws.merge_cells('A1:K1')
        ws['A1'] = f'SHORTAGE REPORT - Job {job} × {quantity} boards'
        ws['A1'].font = openpyxl.styles.Font(size=16, bold=True)
        ws['A1'].alignment = openpyxl.styles.Alignment(horizontal='center')

        # Add headers
        headers = ['Line', 'Description', 'Manufacturer', 'MPN', 'Location',
                   'Qty/Board', 'Total Req\'d', 'On Hand', 'Shortage', 'Unit Cost', 'Shortage Cost']
        ws.append([])
        ws.append(headers)

        # Style headers
        for cell in ws[3]:
            cell.font = openpyxl.styles.Font(bold=True, color='FFFFFF')
            cell.fill = openpyxl.styles.PatternFill(start_color='DC2626', end_color='DC2626', fill_type='solid')
            cell.alignment = openpyxl.styles.Alignment(horizontal='center')

        # Add data
        for item in shortage_items:
            ws.append([
                item['Line'],
                item['Description'],
                item['Manufacturer'],
                item['MPN'],
                item['Location'],
                item['Qty Per Board'],
                item['Total Required'],
                item['On Hand'],
                item['Shortage'],
                f"${item['Unit Cost']:.4f}",
                f"${item['Shortage Cost']:.2f}"
            ])

        # Auto-size columns
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width

        # Save to BytesIO
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f'Shortage_Job_{job}_Qty_{quantity}.xlsx'
        )

    except Exception as e:
        logger.error(f"Error exporting shortage: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== BOM LOADER ROUTES =====

@app.route('/bom-loader')
@require_auth
def bom_loader():
    """Render BOM loader page"""
    return render_template('bom_loader.html')

@app.route('/api/bom/upload', methods=['POST'])
@require_auth
def api_bom_upload():
    """Upload and process BOM file (Excel or CSV)"""
    try:
        import io
        import openpyxl
        from werkzeug.utils import secure_filename

        # Check if file was uploaded
        if 'bomFile' not in request.files:
            return jsonify({'success': False, 'error': 'No file uploaded'}), 400

        file = request.files['bomFile']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400

        # Get upload mode
        upload_mode = request.form.get('uploadMode', 'replace')  # replace, append, update

        # Read file based on extension
        filename = secure_filename(file.filename)
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''

        if file_ext not in ['xlsx', 'xls', 'csv']:
            return jsonify({'success': False, 'error': 'Invalid file format. Use .xlsx, .xls, or .csv'}), 400

        # Parse file
        bom_records = []
        errors = []

        if file_ext in ['xlsx', 'xls']:
            # Parse Excel file
            try:
                wb = openpyxl.load_workbook(file, data_only=True)
                ws = wb.active

                # Get headers from first row
                headers = []
                for cell in ws[1]:
                    headers.append(str(cell.value).strip().upper() if cell.value else '')

                # Map common column name variations
                col_map = {}
                for idx, header in enumerate(headers):
                    header_clean = header.replace('_', '').replace(' ', '').replace('.', '')
                    if header_clean in ['JOB', 'JOBNO', 'JOBNUMBER']:
                        col_map['job'] = idx
                    elif header_clean in ['LINE', 'LINENO', 'LINENUMBER', 'ITEM']:
                        col_map['line'] = idx
                    elif header_clean in ['DESC', 'DESCRIPTION', 'PARTDESCRIPTION', 'PARTDESC']:
                        col_map['desc'] = idx
                    elif header_clean in ['MAN', 'MANUFACTURER', 'MFR', 'MFG']:
                        col_map['man'] = idx
                    elif header_clean in ['MPN', 'MANUFACTURERPARTNUMBER', 'MFRPN', 'PARTNUMBER', 'PN']:
                        col_map['mpn'] = idx
                    elif header_clean in ['ACIPN', 'ACIPARTNUMBER', 'ACI']:
                        col_map['aci_pn'] = idx
                    elif header_clean in ['QTY', 'QUANTITY', 'QTY/BOARD', 'QTYBOARD']:
                        col_map['qty'] = idx
                    elif header_clean in ['POU', 'UOM', 'UNIT', 'UNITOFMEASURE']:
                        col_map['pou'] = idx
                    elif header_clean in ['LOC', 'LOCATION', 'LOCATIONS', 'REFDES', 'REFERENCEDESIGNATOR']:
                        col_map['loc'] = idx
                    elif header_clean in ['COST', 'UNITCOST', 'PRICE', 'UNITPRICE']:
                        col_map['cost'] = idx
                    elif header_clean in ['JOBREV', 'REVISION', 'REV']:
                        col_map['job_rev'] = idx
                    elif header_clean in ['CUST', 'CUSTOMER']:
                        col_map['cust'] = idx
                    elif header_clean in ['CUSTPN', 'CUSTOMERPARTNUMBER', 'CUSTOMERPN']:
                        col_map['cust_pn'] = idx

                # Validate required columns
                required_cols = ['job', 'line', 'mpn', 'qty']
                missing_cols = [col for col in required_cols if col not in col_map]
                if missing_cols:
                    return jsonify({
                        'success': False,
                        'error': f'Missing required columns: {", ".join(missing_cols).upper()}'
                    }), 400

                # Parse data rows
                for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
                    try:
                        # Skip empty rows
                        if not any(row):
                            continue

                        record = {
                            'job': row[col_map['job']] if 'job' in col_map and row[col_map['job']] else None,
                            'line': row[col_map['line']] if 'line' in col_map and row[col_map['line']] else None,
                            'desc': row[col_map['desc']] if 'desc' in col_map and col_map['desc'] < len(row) else None,
                            'man': row[col_map['man']] if 'man' in col_map and col_map['man'] < len(row) else None,
                            'mpn': row[col_map['mpn']] if 'mpn' in col_map and row[col_map['mpn']] else None,
                            'aci_pn': row[col_map['aci_pn']] if 'aci_pn' in col_map and col_map['aci_pn'] < len(row) else None,
                            'qty': row[col_map['qty']] if 'qty' in col_map and row[col_map['qty']] else 0,
                            'pou': row[col_map['pou']] if 'pou' in col_map and col_map['pou'] < len(row) else None,
                            'loc': row[col_map['loc']] if 'loc' in col_map and col_map['loc'] < len(row) else None,
                            'cost': row[col_map['cost']] if 'cost' in col_map and col_map['cost'] < len(row) else 0,
                            'job_rev': row[col_map['job_rev']] if 'job_rev' in col_map and col_map['job_rev'] < len(row) else None,
                            'cust': row[col_map['cust']] if 'cust' in col_map and col_map['cust'] < len(row) else None,
                            'cust_pn': row[col_map['cust_pn']] if 'cust_pn' in col_map and col_map['cust_pn'] < len(row) else None,
                        }

                        # Validate required fields
                        if not record['job'] or not record['line'] or not record['mpn']:
                            errors.append(f"Row {row_num}: Missing required fields (Job, Line, MPN)")
                            continue

                        bom_records.append(record)

                    except Exception as e:
                        errors.append(f"Row {row_num}: {str(e)}")

            except Exception as e:
                return jsonify({'success': False, 'error': f'Error parsing Excel file: {str(e)}'}), 400

        elif file_ext == 'csv':
            # Parse CSV file
            try:
                import csv
                import codecs

                # Read CSV with UTF-8 encoding
                file.stream.seek(0)
                csv_data = file.stream.read().decode('utf-8-sig')
                csv_reader = csv.DictReader(io.StringIO(csv_data))

                # Map column names
                fieldnames = [str(f).strip().upper().replace('_', '').replace(' ', '') for f in csv_reader.fieldnames]

                for row_num, row in enumerate(csv_reader, start=2):
                    try:
                        # Map fields
                        row_upper = {k.strip().upper().replace('_', '').replace(' ', ''): v for k, v in row.items()}

                        record = {
                            'job': row_upper.get('JOB') or row_upper.get('JOBNO'),
                            'line': row_upper.get('LINE') or row_upper.get('LINENO'),
                            'desc': row_upper.get('DESC') or row_upper.get('DESCRIPTION'),
                            'man': row_upper.get('MAN') or row_upper.get('MANUFACTURER'),
                            'mpn': row_upper.get('MPN') or row_upper.get('PARTNUMBER'),
                            'aci_pn': row_upper.get('ACIPN') or row_upper.get('ACI'),
                            'qty': row_upper.get('QTY') or row_upper.get('QUANTITY') or 0,
                            'pou': row_upper.get('POU') or row_upper.get('UOM'),
                            'loc': row_upper.get('LOC') or row_upper.get('LOCATION'),
                            'cost': row_upper.get('COST') or row_upper.get('UNITCOST') or 0,
                            'job_rev': row_upper.get('JOBREV') or row_upper.get('REV'),
                            'cust': row_upper.get('CUST') or row_upper.get('CUSTOMER'),
                            'cust_pn': row_upper.get('CUSTPN'),
                        }

                        # Validate required fields
                        if not record['job'] or not record['line'] or not record['mpn']:
                            errors.append(f"Row {row_num}: Missing required fields")
                            continue

                        bom_records.append(record)

                    except Exception as e:
                        errors.append(f"Row {row_num}: {str(e)}")

            except Exception as e:
                return jsonify({'success': False, 'error': f'Error parsing CSV file: {str(e)}'}), 400

        # If no records parsed, return error
        if not bom_records:
            return jsonify({
                'success': False,
                'error': 'No valid records found in file',
                'errors': errors
            }), 400

        # Process records based on upload mode
        with db_manager.get_connection() as conn:
            cur = conn.cursor()

            records_success = 0
            jobs_affected = set()

            try:
                if upload_mode == 'replace':
                    # Delete existing records for these jobs
                    job_numbers = list(set([str(r['job']) for r in bom_records]))
                    for job in job_numbers:
                        cur.execute('''
                            DELETE FROM pcb_inventory."tblBOM"
                            WHERE job::text = %s
                        ''', (job,))
                    logger.info(f"Deleted existing BOM records for jobs: {job_numbers}")

                # Insert/update records
                for record in bom_records:
                    try:
                        if upload_mode == 'update':
                            # Check if record exists
                            cur.execute('''
                                SELECT id FROM pcb_inventory."tblBOM"
                                WHERE job::text = %s AND line = %s
                            ''', (str(record['job']), record['line']))

                            existing = cur.fetchone()

                            if existing:
                                # Update existing record
                                cur.execute('''
                                    UPDATE pcb_inventory."tblBOM"
                                    SET "DESC" = %s, man = %s, mpn = %s, aci_pn = %s,
                                        qty = %s, pou = %s, loc = %s, cost = %s,
                                        job_rev = %s, cust = %s, cust_pn = %s,
                                        date_loaded = %s, migrated_at = CURRENT_TIMESTAMP
                                    WHERE job::text = %s AND line = %s
                                ''', (
                                    record['desc'], record['man'], record['mpn'], record['aci_pn'],
                                    record['qty'], record['pou'], record['loc'], record['cost'],
                                    record['job_rev'], record['cust'], record['cust_pn'],
                                    datetime.now().strftime('%Y-%m-%d'),
                                    str(record['job']), record['line']
                                ))
                            else:
                                # Insert new record
                                cur.execute('''
                                    INSERT INTO pcb_inventory."tblBOM"
                                    (job, line, "DESC", man, mpn, aci_pn, qty, pou, loc, cost,
                                     job_rev, cust, cust_pn, date_loaded, migrated_at)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                                ''', (
                                    record['job'], record['line'], record['desc'], record['man'],
                                    record['mpn'], record['aci_pn'], record['qty'], record['pou'],
                                    record['loc'], record['cost'], record['job_rev'],
                                    record['cust'], record['cust_pn'],
                                    datetime.now().strftime('%Y-%m-%d')
                                ))
                        else:
                            # Replace or Append mode - just insert
                            cur.execute('''
                                INSERT INTO pcb_inventory."tblBOM"
                                (job, line, "DESC", man, mpn, aci_pn, qty, pou, loc, cost,
                                 job_rev, cust, cust_pn, date_loaded, migrated_at)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ''', (
                                record['job'], record['line'], record['desc'], record['man'],
                                record['mpn'], record['aci_pn'], record['qty'], record['pou'],
                                record['loc'], record['cost'], record['job_rev'],
                                record['cust'], record['cust_pn'],
                                datetime.now().strftime('%Y-%m-%d')
                            ))

                        records_success += 1
                        jobs_affected.add(str(record['job']))

                    except Exception as e:
                        errors.append(f"Record Job={record['job']}, Line={record['line']}: {str(e)}")

                conn.commit()

                return jsonify({
                    'success': True,
                    'recordsProcessed': len(bom_records),
                    'recordsSuccess': records_success,
                    'jobsUpdated': len(jobs_affected),
                    'errors': errors
                })

            except Exception as e:
                conn.rollback()
                logger.error(f"Database error during BOM upload: {e}")
                return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500

    except Exception as e:
        logger.error(f"Error uploading BOM: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Test database connection on startup
    try:
        test_inventory = db_manager.get_current_inventory()
        logger.info(f"Database connection successful. Found {len(test_inventory)} inventory items.")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        print("Database connection failed. Check if PostgreSQL container is running.")
    
    # Run the application
    app.run(debug=False, host='0.0.0.0', port=5000)