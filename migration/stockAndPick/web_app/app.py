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
from wtforms.validators import DataRequired, NumberRange, Length, ValidationError, Optional
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import re
from functools import wraps, lru_cache
import hashlib
import secrets
import bcrypt
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
    """Calculate time ago from a datetime object"""
    if not dt:
        return "Unknown"

    # Handle string timestamps from database
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return "Unknown"

    now = datetime.now()
    if dt.tzinfo is not None:
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

@app.template_filter('format_number')
def format_number_filter(value):
    """Format number with thousands separator"""
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return value

# Database configuration from environment variables
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'aci-database'),
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
    pcb_type = StringField('Component Type', validators=[Length(max=50)], default='Bare')
    dc = StringField('Date Code (DC)', validators=[Length(max=50)])
    msd = StringField('Moisture Sensitive Device (MSD)', validators=[Length(max=50)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    location = StringField('Location', validators=[DataRequired(), Length(min=1, max=20)], default='Receiving Area')
    itar_classification = SelectField('ITAR Classification', choices=ITAR_CLASSIFICATIONS, validators=[DataRequired()], default='NONE')
    export_control_notes = StringField('Export Control Notes', validators=[Length(max=500)])
    submit = SubmitField('Stock Parts')

class PickForm(FlaskForm):
    """Form for picking electronic parts."""
    pcn = IntegerField('PCN Number', validators=[Optional(), NumberRange(min=1)])  # Optional - when specified, pick from that specific PCN only
    job = StringField('Job Number (Item)', validators=[Length(max=50)])  # Optional - will use part_number if not provided
    mpn = StringField('MPN (Manufacturing Part Number)', validators=[Length(max=50)])
    part_number = StringField('Part Number', validators=[DataRequired(), Length(min=1, max=50)])  # Now required - serves as job identifier
    po = StringField('Job Number', validators=[Length(max=50)])
    work_order = StringField('Work Order Number', validators=[Length(max=50)])
    pcb_type = StringField('Component Type', validators=[Length(max=50)], default='Bare')
    dc = StringField('Date Code (DC)', validators=[Length(max=50)])
    msd = StringField('Moisture Sensitive Device (MSD)', validators=[Length(max=50)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Pick Parts')

class RestockForm(FlaskForm):
    """Form for restocking parts from MFG floor back to Count Area."""
    pcn = IntegerField('PCN Number', validators=[Optional(), NumberRange(min=1)])
    item = StringField('Item Number', validators=[Optional(), Length(max=50)])
    quantity = IntegerField('Quantity to Restock', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Restock to Count Area')

    def validate(self, extra_validators=None):
        """Custom validation to ensure either PCN or Item is provided."""
        if not super().validate(extra_validators):
            return False

        if not self.pcn.data and not self.item.data:
            self.pcn.errors.append('Either PCN or Item Number is required')
            self.item.errors.append('Either PCN or Item Number is required')
            return False

        return True

# User authentication now handled by ACI Dashboard

class DatabaseManager:
    """Handle database operations using containerized PostgreSQL with connection pooling."""
    
    def __init__(self):
        self.db_config = DB_CONFIG
        # Initialize connection pool with optimized settings
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=5,     # Keep 5 connections ready
                maxconn=25,    # Increased max connections to handle more concurrent requests
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
        conn = None
        try:
            # Call the PostgreSQL function with all 14 parameters
            result = self.execute_function('pcb_inventory.stock_pcb',
                (job, pcb_type, quantity, location, itar_classification, user_role,
                 itar_auth, username, pcn, work_order, dc, msd, mpn, part_number))
            logger.info(f"Stock operation: {result}")

            # Also update warehouse inventory - UPSERT to handle duplicates
            if result.get('success'):
                conn = self.get_connection()
                cursor = conn.cursor()
                try:
                    cursor.execute("""
                        INSERT INTO pcb_inventory."tblWhse_Inventory"
                        (item, pcn, mpn, dc, onhandqty, loc_to, msd, po, loc_from, mfg_qty)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, '-', 0)
                        ON CONFLICT (item, pcn, mpn)
                        DO UPDATE SET
                            onhandqty = "tblWhse_Inventory".onhandqty + EXCLUDED.onhandqty,
                            loc_to = EXCLUDED.loc_to,
                            dc = COALESCE(EXCLUDED.dc, "tblWhse_Inventory".dc),
                            msd = COALESCE(EXCLUDED.msd, "tblWhse_Inventory".msd),
                            po = COALESCE(EXCLUDED.po, "tblWhse_Inventory".po),
                            migrated_at = CURRENT_TIMESTAMP
                    """, (
                        job,
                        pcn,
                        mpn or '',
                        dc,
                        quantity,
                        location,
                        msd,
                        work_order
                    ))
                    conn.commit()
                    logger.info(f"Updated warehouse inventory for item {job}, PCN {pcn} (UPSERT)")
                except Exception as e:

                    if conn:

                        conn.rollback()
                    logger.error(f"Failed to update warehouse inventory: {e}")
                finally:
                    cursor.close()
                    self.return_connection(conn)

            # Clear cache after inventory change
            cache.delete_memoized(self.get_current_inventory)
            cache.delete('stats_summary')
            return result
        except Exception as e:
            error_msg = get_safe_error_message(e, "stock operation")
            return {'success': False, 'error': error_msg}
    
    def pick_pcb(self, job: str, pcb_type: str, quantity: int,
                 user_role: str = 'USER', itar_auth: bool = False, username: str = 'system', work_order: str = None, pcn: int = None) -> Dict[str, Any]:
        """Pick PCB from warehouse inventory.
        If pcn is provided, picks from that specific PCN only.
        Otherwise, picks using FIFO across all PCNs for the item.
        """
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            try:
                # Check if item exists in warehouse inventory with sufficient quantity
                # Use ILIKE for flexible matching (consistent with search_inventory)
                # If PCN specified, check only that PCN
                if pcn:
                    cursor.execute("""
                        SELECT onhandqty as total_qty
                        FROM pcb_inventory."tblWhse_Inventory"
                        WHERE pcn = %s AND item::text ILIKE %s
                        AND onhandqty > 0
                    """, (pcn, job))
                else:
                    cursor.execute("""
                        SELECT SUM(onhandqty) as total_qty
                        FROM pcb_inventory."tblWhse_Inventory"
                        WHERE item::text ILIKE %s
                        AND onhandqty > 0
                    """, (job,))

                result = cursor.fetchone()
                available_qty = int(result[0]) if result and result[0] else 0

                if available_qty < quantity:
                    pcn_msg = f" from PCN {pcn}" if pcn else ""
                    return {
                        'success': False,
                        'error': f'Cannot pick {quantity} units{pcn_msg}. Only {available_qty} available.',
                        'available_qty': available_qty,
                        'requested_qty': quantity,
                        'job': job,
                        'pcb_type': pcb_type
                    }

                # Update warehouse inventory - pick from specific locations using FIFO
                # This ensures we only pick the exact quantity needed from specific rows
                # If PCN is specified, only pick from that PCN
                pcn_filter = "AND pcn = %s" if pcn else ""
                query_params = [job]
                if pcn:
                    query_params.append(pcn)
                query_params.extend([quantity, quantity, quantity, quantity, quantity])

                cursor.execute(f"""
                    WITH inventory_ordered AS (
                        SELECT
                            pcn,
                            item,
                            onhandqty,
                            migrated_at,
                            SUM(onhandqty) OVER (ORDER BY migrated_at, pcn) as running_total
                        FROM pcb_inventory."tblWhse_Inventory"
                        WHERE item::text ILIKE %s
                        {pcn_filter}
                        AND onhandqty > 0
                    ),
                    pick_rows AS (
                        SELECT
                            pcn,
                            item,
                            onhandqty,
                            running_total,
                            LAG(running_total, 1, 0) OVER (ORDER BY migrated_at, pcn) as prev_total
                        FROM inventory_ordered
                        ORDER BY migrated_at, pcn
                    ),
                    rows_to_update AS (
                        SELECT
                            pcn,
                            item,
                            CASE
                                -- If this row completes the pick, take only what's needed
                                WHEN prev_total < %s AND running_total >= %s
                                THEN %s - prev_total
                                -- If this row is fully consumed, take all
                                WHEN running_total <= %s
                                THEN onhandqty
                                ELSE 0
                            END as qty_to_pick
                        FROM pick_rows
                        WHERE prev_total < %s
                    )
                    UPDATE pcb_inventory."tblWhse_Inventory" w
                    SET onhandqty = GREATEST(0, w.onhandqty - r.qty_to_pick),
                        mfg_qty = COALESCE(w.mfg_qty, 0) + r.qty_to_pick,
                        loc_from = COALESCE(w.loc_to, 'Receiving Area'),
                        loc_to = 'MFG Floor'
                    FROM rows_to_update r
                    WHERE w.pcn = r.pcn
                    AND w.item = r.item
                    AND r.qty_to_pick > 0
                """, tuple(query_params))

                updated_rows = cursor.rowcount

                if updated_rows == 0:
                    conn.rollback()
                    return {
                        'success': False,
                        'error': f'Job not found in inventory. Job {job} with component type {pcb_type} not found.',
                        'job': job,
                        'pcb_type': pcb_type
                    }

                # Record the pick transaction (movement from Receiving Area to MFG Floor)
                cursor.execute("""
                    INSERT INTO pcb_inventory."tblTransaction"
                    (trantype, item, pcn, mpn, dc, tranqty, tran_time, loc_from, loc_to, userid)
                    SELECT
                        'PICK',
                        %s,
                        pcn,
                        mpn,
                        dc::integer,
                        %s,
                        CURRENT_TIMESTAMP,
                        'Receiving Area',
                        'MFG Floor',
                        %s
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE item::text ILIKE %s
                    LIMIT 1
                """, (job, quantity, username, job))

                # Get the new remaining quantity
                cursor.execute("""
                    SELECT COALESCE(SUM(onhandqty), 0) as remaining_qty
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE item::text ILIKE %s
                """, (job,))
                remaining_result = cursor.fetchone()
                new_qty = int(remaining_result[0]) if remaining_result and remaining_result[0] else 0

                conn.commit()
                logger.info(f"Pick operation: Updated {updated_rows} warehouse inventory records for item {job}, picked {quantity}, remaining {new_qty}, moved to MFG Floor")

                # Clear cache after inventory change
                cache.delete_memoized(self.get_current_inventory)
                cache.delete('stats_summary')

                return {
                    'success': True,
                    'message': f'Successfully picked {quantity} units of {job}',
                    'picked_qty': quantity,
                    'new_qty': new_qty,
                    'job': job,
                    'pcb_type': pcb_type
                }

            except Exception as e:


                if conn:


                    conn.rollback()
                logger.error(f"Failed to pick from warehouse inventory: {e}")
                raise
            finally:
                cursor.close()
                self.return_connection(conn)

        except Exception as e:
            error_msg = get_safe_error_message(e, "pick operation")
            return {'success': False, 'error': error_msg}

    def restock_pcb(self, pcn: int = None, item: str = None, quantity: int = 0,
                    username: str = 'system') -> Dict[str, Any]:
        """Restock parts from MFG floor back to Count Area."""
        conn = None
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            try:
                # Determine search criteria
                if pcn:
                    where_clause = "pcn = %s"
                    search_param = pcn
                elif item:
                    where_clause = "item = %s"
                    search_param = item
                else:
                    return {
                        'success': False,
                        'error': 'Either PCN or Item number is required'
                    }

                # Check if item exists (no MFG quantity restriction - allows count corrections)
                cursor.execute(f"""
                    SELECT pcn, item, mpn, dc, mfg_qty, onhandqty
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE {where_clause}
                    LIMIT 1
                """, (search_param,))

                result = cursor.fetchone()

                if not result:
                    return {
                        'success': False,
                        'error': f'No parts found for {"PCN " + str(pcn) if pcn else "Item " + item}'
                    }

                pcn_num, item_num, mpn, dc, mfg_qty, current_onhand = result

                # Handle NULL quantities
                if current_onhand is None:
                    current_onhand = 0
                if mfg_qty is None:
                    mfg_qty = 0

                # Allow restocking even if quantity exceeds MFG qty (for count corrections)
                # No validation check - user can adjust quantities based on physical counts

                # Update warehouse inventory - move from MFG to Count Area
                # Use COALESCE to handle NULL onhandqty
                cursor.execute("""
                    UPDATE pcb_inventory."tblWhse_Inventory"
                    SET mfg_qty = GREATEST(0, mfg_qty - %s),
                        onhandqty = COALESCE(onhandqty, 0) + %s,
                        loc_from = 'MFG Floor',
                        loc_to = 'Count Area'
                    WHERE {0}
                """.format(where_clause), (quantity, quantity, search_param))

                updated_rows = cursor.rowcount

                if updated_rows == 0:
                    conn.rollback()
                    return {
                        'success': False,
                        'error': 'Failed to update warehouse inventory'
                    }

                # Record the restock transaction
                cursor.execute("""
                    INSERT INTO pcb_inventory."tblTransaction"
                    (trantype, item, pcn, mpn, dc, tranqty, tran_time, loc_from, loc_to, userid)
                    VALUES ('RESTOCK', %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, 'MFG Floor', 'Count Area', %s)
                """, (item_num, pcn_num, mpn, dc, quantity, username))

                conn.commit()
                logger.info(f"Restock operation: PCN {pcn_num}, Item {item_num}, restocked {quantity} units from MFG Floor to Count Area")

                # Clear cache after inventory change
                cache.delete_memoized(self.get_current_inventory)
                cache.delete('stats_summary')

                return {
                    'success': True,
                    'message': f'Successfully restocked {quantity} units to Count Area',
                    'quantity': quantity,
                    'pcn': pcn_num,
                    'item': item_num,
                    'mpn': mpn,
                    'new_mfg_qty': mfg_qty - quantity,
                    'new_onhand_qty': current_onhand + quantity
                }

            except Exception as e:
                if conn:
                    conn.rollback()
                logger.error(f"Failed to restock: {e}")
                raise
            finally:
                cursor.close()
                self.return_connection(conn)

        except Exception as e:
            error_msg = get_safe_error_message(e, "restock operation")
            return {'success': False, 'error': error_msg}

    def get_current_inventory(self, user_role: str = 'USER', itar_auth: bool = False) -> List[Dict[str, Any]]:
        """Get current warehouse inventory - cached for performance."""
        cache_key = f"warehouse_inventory_{user_role}_{itar_auth}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Read directly from tblWhse_Inventory table (warehouse inventory)
                cur.execute(
                    """
                    SELECT
                        id,
                        pcn,
                        item as job,
                        mpn as pcb_type,
                        onhandqty as qty,
                        loc_to as location,
                        migrated_at as checked_on,
                        migrated_at as updated_at
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE onhandqty > 0
                    ORDER BY item, mpn
                    """
                )
                result = [dict(row) for row in cur.fetchall()]
                cache.set(cache_key, result, timeout=60)  # Cache for 1 minute
                return result
        except Exception as e:
            logger.error(f"Failed to get warehouse inventory: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_inventory_summary(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get warehouse inventory summary grouped by MPN and location with descriptions."""
        cache_key = f"inventory_summary_{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT
                        w.mpn as pcb_type,
                        w.loc_to as location,
                        COUNT(DISTINCT w.item) as job_count,
                        SUM(w.onhandqty) as total_qty,
                        AVG(w.onhandqty) as avg_qty,
                        MAX(p."DESC") as description
                    FROM pcb_inventory."tblWhse_Inventory" w
                    LEFT JOIN pcb_inventory."tblPN_List" p ON w.item = p.item
                    WHERE w.onhandqty > 0
                    GROUP BY w.mpn, w.loc_to
                    ORDER BY total_qty DESC, w.mpn, w.loc_to
                    LIMIT %s
                ''', (limit,))
                result = [dict(row) for row in cur.fetchall()]
                cache.set(cache_key, result, timeout=300)  # Cache for 5 minutes
                return result
        except Exception as e:
            logger.error(f"Failed to get warehouse summary: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_inventory_stats(self) -> Dict[str, int]:
        """Get accurate inventory statistics efficiently - just aggregates, no data loading."""
        cache_key = "inventory_stats_fast"
        cached = cache.get(cache_key)
        if cached:
            return cached

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT
                        COUNT(DISTINCT item) as total_jobs,
                        SUM(onhandqty) as total_quantity,
                        COUNT(*) as total_items,
                        COUNT(DISTINCT mpn) as unique_mpns
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE onhandqty > 0
                ''')
                result = dict(cur.fetchone())
                cache.set(cache_key, result, timeout=300)  # Cache for 5 minutes
                return result
        except Exception as e:
            logger.error(f"Failed to get inventory stats: {e}")
            return {'total_jobs': 0, 'total_quantity': 0, 'total_items': 0, 'unique_mpns': 0}
        finally:
            if conn:
                self.return_connection(conn)

    def get_low_stock_items(self, threshold: int = 10, limit: int = 50) -> List[Dict[str, Any]]:
        """Get low stock items from entire database."""
        cache_key = f"low_stock_{threshold}_{limit}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute('''
                    SELECT
                        item as job,
                        pcn,
                        mpn as pcb_type,
                        onhandqty as qty,
                        loc_to as location,
                        migrated_at as updated_at
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE onhandqty > 0 AND onhandqty < %s
                    ORDER BY onhandqty ASC
                    LIMIT %s
                ''', (threshold, limit))
                result = [dict(row) for row in cur.fetchall()]
                cache.set(cache_key, result, timeout=300)  # Cache for 5 minutes
                return result
        except Exception as e:
            logger.error(f"Failed to get low stock items: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent warehouse transaction entries."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        trantype as operation,
                        item as job,
                        mpn as pcb_type,
                        tranqty as quantity_change,
                        COALESCE(
                            (SELECT onhandqty FROM pcb_inventory."tblWhse_Inventory" w WHERE w.pcn = t.pcn LIMIT 1),
                            tranqty
                        ) as new_quantity,
                        tran_time as timestamp,
                        loc_from,
                        loc_to,
                        userid as user_id
                    FROM pcb_inventory."tblTransaction" t
                    WHERE trantype IN ('GEN', 'STOCK', 'PICK', 'UPDATE')
                    ORDER BY tran_time DESC
                    LIMIT %s
                    """,
                    (limit,)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get audit log from transactions: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def search_inventory(self, job: str = None, pcb_type: str = None, pcn: str = None,
                        user_role: str = 'USER', itar_auth: bool = False) -> List[Dict[str, Any]]:
        """Search warehouse inventory with optional filters.
        If PCN is provided, returns that specific PCN's data.
        Otherwise, returns TOTAL quantity per item (aggregated across all PCNs) for accurate pick validation.
        """
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                params = []

                # If PCN is specified, return that specific PCN's data (not aggregated)
                if pcn:
                    query = """
                        SELECT
                            item as job,
                            'Bare' as pcb_type,
                            onhandqty as qty,
                            loc_to as location,
                            dc as date_code,
                            msd as msd_level,
                            mpn as part_number,
                            pcn
                        FROM pcb_inventory."tblWhse_Inventory"
                        WHERE pcn = %s AND onhandqty > 0
                    """
                    params.append(pcn)

                    if job:
                        query += " AND item::text ILIKE %s"
                        params.append(f'%{job}%')

                    query += " ORDER BY migrated_at, pcn"
                else:
                    # Query warehouse inventory - aggregate by ITEM ONLY to show total available
                    # This ensures pick validation uses the correct total quantity
                    query = """
                        SELECT
                            item as job,
                            'Bare' as pcb_type,
                            SUM(onhandqty) as qty,
                            MAX(loc_to) as location,
                            MAX(dc) as date_code,
                            MAX(msd) as msd_level,
                            MAX(mpn) as part_number,
                            COUNT(DISTINCT pcn) as pcn_count
                        FROM pcb_inventory."tblWhse_Inventory"
                        WHERE onhandqty > 0
                    """

                    if job:
                        query += " AND item::text ILIKE %s"
                        params.append(f'%{job}%')

                    query += " GROUP BY item"
                    query += " ORDER BY item"

                cur.execute(query, params)
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
                        SUM(qty) as total_quantity,
                        COUNT(DISTINCT pcb_type) as pcb_types,
                        MAX(updated_at) as last_updated
                    FROM pcb_inventory.tblpcb_inventory
                """)
                stats = dict(cur.fetchone())

                # Format last_updated
                if stats['last_updated']:
                    stats['last_updated'] = stats['last_updated'].strftime('%B %d, %Y %I:%M %p')
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
                        SUM(qty) as postgres_count,
                        SUM(qty) as source_count  -- Assuming same for now
                    FROM pcb_inventory.tblpcb_inventory
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
                        SUM(qty) as total_qty,
                        ROUND((COUNT(*) * 100.0 / (SELECT COUNT(*) FROM pcb_inventory.tblpcb_inventory)), 1) as usage_percent
                    FROM pcb_inventory.tblpcb_inventory
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
        """Get PCN transaction history with warehouse inventory data."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Query from tblTransaction with warehouse inventory data
                # Get unique PCNs (no duplicates) - show only the most recent transaction per PCN
                # Use subquery to get unique PCNs first, then sort by newest
                query = """
                    SELECT * FROM (
                        SELECT DISTINCT ON (t.pcn)
                            t.record_no,
                            t.trantype as status,
                            t.item as job,
                            t.pcn,
                            t.id as transaction_id,
                            COALESCE(w.mpn, t.mpn) as mpn,
                            COALESCE(w.dc::text, t.dc::text) as dc,
                            COALESCE(w.msd, '0') as msd,
                            COALESCE(w.onhandqty, t.tranqty, 0) as quantity,
                            COALESCE(w.mfg_qty, 0) as mfg_qty,
                            t.tran_time as generated_at,
                            t.loc_from,
                            COALESCE(w.loc_to, t.loc_to) as location,
                            t.wo as work_order,
                            COALESCE(w.po, t.po) as po,
                            t.userid as user_id
                        FROM pcb_inventory."tblTransaction" t
                        LEFT JOIN pcb_inventory."tblWhse_Inventory" w
                            ON t.pcn = w.pcn
                        WHERE t.pcn IS NOT NULL
                """
                params = []

                if filters:
                    if filters.get('pcn'):
                        query += " AND t.pcn::text LIKE %s"
                        params.append(f"%{filters['pcn']}%")
                    if filters.get('job'):
                        query += " AND t.item::text LIKE %s"
                        params.append(f"%{filters['job']}%")
                    if filters.get('status'):
                        query += " AND t.trantype = %s"
                        params.append(filters['status'])

                query += " ORDER BY t.pcn, t.id DESC"
                query += " ) sub ORDER BY transaction_id DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get PCN history: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def search_pcn(self, pcn_number: str = None, job: str = None) -> List[Dict[str, Any]]:
        """Search for PCN records by PCN number or job number - returns unique PCNs only, newest first."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT * FROM (
                        SELECT DISTINCT ON (t.pcn)
                            t.record_no,
                            t.trantype as status,
                            t.item as job,
                            t.pcn,
                            t.id as transaction_id,
                            COALESCE(w.mpn, t.mpn) as mpn,
                            COALESCE(w.dc::text, t.dc::text) as dc,
                            COALESCE(w.msd, '0') as msd,
                            COALESCE(w.onhandqty, t.tranqty, 0) as quantity,
                            COALESCE(w.mfg_qty, 0) as mfg_qty,
                            t.tran_time as generated_at,
                            t.loc_from,
                            COALESCE(w.loc_to, t.loc_to) as location,
                            t.wo as work_order,
                            COALESCE(w.po, t.po) as po,
                            t.userid as user_id
                        FROM pcb_inventory."tblTransaction" t
                        LEFT JOIN pcb_inventory."tblWhse_Inventory" w
                            ON t.pcn = w.pcn
                        WHERE t.pcn IS NOT NULL
                """
                params = []

                if pcn_number:
                    query += " AND t.pcn::text LIKE %s"
                    params.append(f"%{pcn_number}%")

                if job:
                    query += " AND t.item::text LIKE %s"
                    params.append(f"%{job}%")

                query += " ORDER BY t.pcn, t.id DESC"
                query += " ) sub ORDER BY transaction_id DESC"

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"PCN search failed: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)

    def get_po_history(self, limit: int = 100, offset: int = 0, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """Get PO history with optional filters and pagination."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = "SELECT * FROM pcb_inventory.po_history WHERE 1=1"
                params = []

                if filters:
                    if filters.get('po_number'):
                        query += " AND po_number LIKE %s"
                        params.append(f"%{filters['po_number']}%")
                    if filters.get('item'):
                        query += " AND item LIKE %s"
                        params.append(f"%{filters['item']}%")
                    if filters.get('date_from'):
                        query += " AND transaction_date >= %s"
                        params.append(filters['date_from'])
                    if filters.get('date_to'):
                        query += " AND transaction_date <= %s"
                        params.append(filters['date_to'])

                query += " ORDER BY transaction_date DESC LIMIT %s OFFSET %s"
                params.append(limit)
                params.append(offset)

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get PO history: {e}")
            return []

    def get_po_history_count(self, filters: Dict[str, Any] = None) -> int:
        """Get total count of PO history records with optional filters."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor() as cur:
                query = "SELECT COUNT(*) FROM pcb_inventory.po_history WHERE 1=1"
                params = []

                if filters:
                    if filters.get('po_number'):
                        query += " AND po_number LIKE %s"
                        params.append(f"%{filters['po_number']}%")
                    if filters.get('item'):
                        query += " AND item LIKE %s"
                        params.append(f"%{filters['item']}%")
                    if filters.get('date_from'):
                        query += " AND transaction_date >= %s"
                        params.append(filters['date_from'])
                    if filters.get('date_to'):
                        query += " AND transaction_date <= %s"
                        params.append(filters['date_to'])

                cur.execute(query, params)
                return cur.fetchone()[0]
        except Exception as e:
            logger.error(f"Failed to get PO history count: {e}")
            return 0
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
    """Decorator to require user authentication - NO GUEST ACCESS."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is logged in
        if 'user_id' not in session or 'username' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))

        # Check for ACI Dashboard SSO token in headers (optional)
        auth_token = request.headers.get('X-ACI-Auth-Token') or session.get('aci_auth_token')
        if auth_token:
            session['aci_auth_token'] = auth_token

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

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Secure login page with bulletproof authentication."""
    # If already logged in, redirect to dashboard
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        if not username or not password:
            flash('Please provide both username and password.', 'danger')
            return render_template('login.html')

        # Get user from database
        conn = None
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            cursor.execute("""
                SELECT id, username, password_hash, full_name, role, itar_authorized, is_active
                FROM pcb_inventory."tblUsers"
                WHERE username = %s AND is_active = TRUE
            """, (username,))

            user = cursor.fetchone()

            if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
                # Successful login
                session.clear()  # Clear any old session data
                session['user_id'] = user['id']
                session['username'] = user['username']
                session['full_name'] = user['full_name']
                session['role'] = user['role']
                session['itar_authorized'] = user['itar_authorized']
                session.permanent = remember  # Remember me functionality

                # Update last login
                cursor.execute("""
                    UPDATE pcb_inventory."tblUsers"
                    SET last_login = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (user['id'],))
                conn.commit()

                logger.info(f"Successful login: {username}")
                flash(f'Welcome back, {user["full_name"] or username}!', 'success')

                # Redirect to next page or dashboard
                next_page = request.args.get('next')
                if next_page and next_page.startswith('/'):
                    return redirect(next_page)
                return redirect(url_for('index'))
            else:
                # Failed login
                logger.warning(f"Failed login attempt for username: {username}")
                flash('Invalid username or password. Please try again.', 'danger')

        except Exception as e:
            logger.error(f"Login error: {e}")
            flash('An error occurred. Please try again later.', 'danger')
        finally:
            if conn:
                db_manager.return_connection(conn)

    return render_template('login.html')

@app.route('/logout')
def logout():
    """Secure logout - clears all session data."""
    username = session.get('username', 'Unknown')
    session.clear()
    logger.info(f"User logged out: {username}")
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/')
@require_auth
def index():
    """Main dashboard page - optimized for fast loading with accurate stats."""
    try:
        # Get ACCURATE stats efficiently (no data loading, just aggregates)
        stats_data = db_manager.get_inventory_stats()

        # Get top 100 items for display (sorted by quantity)
        summary = db_manager.get_inventory_summary(limit=100)
        recent_activity = db_manager.get_audit_log(10)

        # Use accurate stats from database
        total_jobs = stats_data.get('total_jobs', 0)
        total_quantity = stats_data.get('total_quantity', 0) or 0
        total_items = stats_data.get('total_items', 0)

        # Get low stock items from entire database
        LOW_STOCK_THRESHOLD = 10
        low_stock_items = db_manager.get_low_stock_items(threshold=LOW_STOCK_THRESHOLD, limit=50)

        # Most active jobs from summary (top 5)
        most_active_jobs = sorted(
            [(item.get('pcb_type', 'Unknown'), item.get('total_qty', 0)) for item in summary],
            key=lambda x: x[1],
            reverse=True
        )[:5]

        # PCB type distribution for chart - use summary data
        pcb_type_data = {}
        for item in summary:
            pcb_type = item.get('pcb_type') or 'Unknown'
            qty = item.get('total_qty') or 0
            pcb_type_data[pcb_type] = pcb_type_data.get(pcb_type, 0) + qty

        stats = {
            'total_jobs': total_jobs,
            'total_quantity': total_quantity,
            'total_items': total_items,
            'pcb_types': stats_data.get('unique_mpns', 0),  # Accurate count from database
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
                             pcb_type_data=pcb_type_data)
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
        logger.info(f"Stock form validation passed - Form data: job={form.job.data}, part_number={form.part_number.data}, quantity={form.quantity.data}, location={form.location.data}")

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

            logger.info(f"Calling stock_pcb with: job={job_value}, quantity={form.quantity.data}, location={form.location.data}, pcn={pcn_value}")
            result = db_manager.stock_pcb(
                job=job_value,
                pcb_type='Bare',  # Default value since field was removed
                quantity=form.quantity.data,
                location=form.location.data,
                itar_classification=form.itar_classification.data,
                user_role=user_role,
                itar_auth=itar_auth,
                username=session.get('username', 'system'),
                work_order=form.po.data if hasattr(form, 'po') and form.po.data else None,
                dc=form.dc.data if hasattr(form, 'dc') and form.dc.data else None,
                msd=form.msd.data if hasattr(form, 'msd') and form.msd.data else None,
                pcn=pcn_value,
                mpn=form.mpn.data if hasattr(form, 'mpn') and form.mpn.data else None,
                part_number=form.part_number.data if hasattr(form, 'part_number') and form.part_number.data else None
            )
            logger.info(f"stock_pcb returned: {result}")

            if result.get('success'):
                flash(f"Successfully stocked {result['stocked_qty']} units of {result['job']}. "
                      f"New total: {result['new_qty']}", 'success')
                return redirect(url_for('stock'))
            else:
                flash(f"Stock operation failed: {result.get('error', 'Unknown error')}", 'error')
                
        except Exception as e:
            logger.error(f"Stock operation error: {e}")
            flash(f"Stock operation failed: {e}", 'error')
    else:
        if form.errors:
            logger.error(f"Stock form validation failed - Errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field}: {error}", 'error')

    return render_template('stock.html', form=form)

@app.route('/pick', methods=['GET', 'POST'])
@require_auth
def pick():
    """Pick PCB page."""
    form = PickForm()
    
    if form.validate_on_submit():
        logger.info(f"Pick form validation passed - Form data: job={form.job.data}, part_number={form.part_number.data}, quantity={form.quantity.data}")

        try:
            user_role = session.get('role', 'USER')
            itar_auth = session.get('itar_authorized', False)

            # Use part_number as job identifier if job not provided
            job_value = form.job.data if form.job.data else form.part_number.data
            pcn_value = form.pcn.data if form.pcn.data else None

            logger.info(f"Calling pick_pcb with: job={job_value}, pcn={pcn_value}, quantity={form.quantity.data}")
            result = db_manager.pick_pcb(
                job=job_value,
                pcb_type='Bare',  # Default value since field was removed
                quantity=form.quantity.data,
                user_role=user_role,
                itar_auth=itar_auth,
                username=session.get('username', 'system'),
                work_order=form.work_order.data if form.work_order.data else None,
                pcn=pcn_value  # Pass PCN if specified - picks from that specific PCN only
            )
            logger.info(f"pick_pcb returned: {result}")

            if result.get('success'):
                flash(f"Successfully picked {result['picked_qty']} units of {result['job']}. "
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
    else:
        if form.errors:
            logger.error(f"Pick form validation failed - Errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field}: {error}", 'error')

    return render_template('pick.html', form=form)

@app.route('/restock', methods=['GET', 'POST'])
@require_auth
def restock():
    """Restock parts from MFG floor back to Count Area."""
    form = RestockForm()

    if form.validate_on_submit():
        logger.info(f"Restock form validation passed - PCN={form.pcn.data}, Item={form.item.data}, Quantity={form.quantity.data}")

        try:
            username = session.get('username', 'system')

            result = db_manager.restock_pcb(
                pcn=form.pcn.data if form.pcn.data else None,
                item=form.item.data if form.item.data else None,
                quantity=form.quantity.data,
                username=username
            )
            logger.info(f"restock_pcb returned: {result}")

            if result.get('success'):
                flash(f"Successfully restocked {result['quantity']} units of {result['item']} (PCN: {result['pcn']}) to Count Area. "
                      f"MFG Qty: {result['new_mfg_qty']}, On Hand: {result['new_onhand_qty']}", 'success')
                # Pass PCN to show print label button
                return redirect(url_for('restock', restocked_pcn=result['pcn']))
            else:
                error_msg = result.get('error', 'Unknown error')
                flash(f"Restock operation failed: {error_msg}", 'error')

        except Exception as e:
            logger.error(f"Restock operation error: {e}")
            flash(f"Restock operation failed: {e}", 'error')
    else:
        if form.errors:
            logger.error(f"Restock form validation failed - Errors: {form.errors}")
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f"{field}: {error}", 'error')

    return render_template('restock.html', form=form)

@app.route('/part-number-change', methods=['GET', 'POST'])
@require_auth
def part_number_change():
    """Change part number (item) for a PCN."""
    if request.method == 'POST':
        pcn = request.form.get('pcn', '').strip()
        new_part_number = request.form.get('new_part_number', '').strip()
        username = session.get('username', 'unknown')

        if not pcn or not new_part_number:
            flash('PCN and new part number are required.', 'danger')
            return render_template('part_number_change.html')

        conn = None
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)

            # Check if PCN exists
            cursor.execute('''
                SELECT pcn, item, mpn, onhandqty, loc_to
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn = %s
            ''', (pcn,))

            item = cursor.fetchone()

            if not item:
                flash(f'PCN {pcn} not found in inventory.', 'danger')
                return render_template('part_number_change.html')

            old_part_number = item['item']

            # Check if new part number is the same
            if old_part_number == new_part_number:
                flash(f'New part number is the same as current part number ({old_part_number}).', 'warning')
                return render_template('part_number_change.html', item=item)

            # Update part number in inventory
            cursor.execute('''
                UPDATE pcb_inventory."tblWhse_Inventory"
                SET item = %s
                WHERE pcn = %s
            ''', (new_part_number, pcn))

            # Log the change in transaction table
            cursor.execute('''
                INSERT INTO pcb_inventory."tblTransaction"
                (trantype, item, pcn, mpn, tranqty, tran_time, loc_to, userid, migrated_at)
                VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, CURRENT_TIMESTAMP)
            ''', ('PN_CHANGE', new_part_number, pcn, item['mpn'], 0, item['loc_to'], username))

            conn.commit()

            logger.info(f"Part number changed by {username}: PCN {pcn} from '{old_part_number}' to '{new_part_number}'")
            flash(f'Successfully changed part number for PCN {pcn} from "{old_part_number}" to "{new_part_number}".', 'success')

            # Fetch updated item
            cursor.execute('''
                SELECT pcn, item, mpn, onhandqty, loc_to
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn = %s
            ''', (pcn,))
            updated_item = cursor.fetchone()

            return render_template('part_number_change.html', item=updated_item)

        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Error changing part number: {e}")
            flash(f'Error changing part number: {str(e)}', 'danger')
            return render_template('part_number_change.html')
        finally:
            if conn:
                db_manager.return_connection(conn)

    return render_template('part_number_change.html')

@app.route('/api/search-inventory', methods=['GET'])
@require_auth
def api_search_inventory():
    """API endpoint to search full inventory database with improved MPN matching."""
    description = request.args.get('description', '').strip()
    mpn = request.args.get('mpn', '').strip()
    location = request.args.get('location', '').strip()

    if not description and not mpn and not location:
        return jsonify({'success': False, 'results': []})

    conn = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        logger.info(f"Search request - Description: '{description}', MPN: '{mpn}', Location: '{location}'")

        # Build dynamic query with better matching
        query = '''
            SELECT
                w.mpn as pcb_type,
                w.loc_to as location,
                COUNT(DISTINCT w.item) as job_count,
                SUM(w.onhandqty) as total_qty,
                AVG(w.onhandqty) as avg_qty,
                MAX(p."DESC") as description,
                MAX(w.pcn) as pcn,
                MAX(w.item) as sample_item,
                -- Exact match score for sorting
                CASE
                    WHEN LOWER(w.mpn) = LOWER(%s) THEN 1
                    ELSE 2
                END as match_priority
            FROM pcb_inventory."tblWhse_Inventory" w
            LEFT JOIN pcb_inventory."tblPN_List" p ON w.item = p.item
            WHERE w.onhandqty > 0
        '''
        params = [mpn if mpn else '']

        if description:
            query += ' AND (LOWER(p."DESC") LIKE %s OR LOWER(w.item) LIKE %s)'
            params.extend([f'%{description.lower()}%', f'%{description.lower()}%'])

        if mpn:
            # Search for exact match OR partial match (handles hyphens, spaces, case)
            query += ' AND (LOWER(w.mpn) = %s OR LOWER(w.mpn) LIKE %s OR LOWER(REPLACE(w.mpn, \'-\', \'\')) LIKE %s)'
            mpn_clean = mpn.lower().replace('-', '').replace(' ', '')
            params.extend([mpn.lower(), f'%{mpn.lower()}%', f'%{mpn_clean}%'])

        if location:
            query += ' AND LOWER(w.loc_to) LIKE %s'
            params.append(f'%{location.lower()}%')

        query += ' GROUP BY w.mpn, w.loc_to ORDER BY match_priority, total_qty DESC LIMIT 200'

        cursor.execute(query, params)
        results = [dict(row) for row in cursor.fetchall()]

        # Remove match_priority from results (internal use only)
        for result in results:
            result.pop('match_priority', None)

        logger.info(f"Search results: {len(results)} items found")
        if results and mpn:
            logger.info(f"First result for MPN '{mpn}': {results[0].get('pcb_type')} at {results[0].get('location')}")

        return jsonify({'success': True, 'results': results, 'count': len(results)})

    except Exception as e:
        logger.error(f"Error searching inventory: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if conn:
            db_manager.return_connection(conn)

@app.route('/api/get-part-details', methods=['GET'])
@require_auth
def get_part_details():
    """API endpoint to get part details for autofill in restock form."""
    pcn = request.args.get('pcn', '').strip()
    item = request.args.get('item', '').strip()

    if not pcn and not item:
        return jsonify({'success': False, 'error': 'PCN or Item number is required'})

    conn = None
    try:
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Determine search criteria
        if pcn:
            where_clause = "pcn = %s"
            search_param = int(pcn)
        else:
            where_clause = "item = %s"
            search_param = item

        # Fetch part details from warehouse inventory
        cursor.execute(f"""
            SELECT
                pcn,
                item,
                mpn,
                dc,
                COALESCE(mfg_qty, 0) as mfg_qty,
                COALESCE(onhandqty, 0) as onhandqty,
                loc_from,
                loc_to,
                msd,
                po
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE {where_clause}
            LIMIT 1
        """, (search_param,))

        result = cursor.fetchone()

        if result:
            return jsonify({
                'success': True,
                'data': {
                    'pcn': result['pcn'],
                    'item': result['item'],
                    'mpn': result['mpn'],
                    'dc': result['dc'],
                    'mfg_qty': result['mfg_qty'],
                    'onhandqty': result['onhandqty'],
                    'location_from': result['loc_from'] if result['loc_from'] != 'Stock' else '-',
                    'location_to': result['loc_to'],
                    'msd': result['msd'],
                    'po': result['po'],
                    'has_mfg_qty': result['mfg_qty'] > 0
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Part not found for {"PCN " + pcn if pcn else "Item " + item}'
            })

    except ValueError:
        return jsonify({'success': False, 'error': 'Invalid PCN format. Must be a number.'})
    except Exception as e:
        logger.error(f"Error fetching part details: {e}")
        return jsonify({'success': False, 'error': str(e)})
    finally:
        if conn:
            db_manager.return_connection(conn)

@app.route('/pcb-inventory')
@require_auth
def pcb_inventory():
    """PCB Inventory listing page with pagination and advanced filters."""
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
            inventory_data = [item for item in inventory_data if item.get('pcn') and search_pcn.lower() in item.get('pcn', '').lower()]

        # Date range filter
        if search_date_from:
            from datetime import datetime
            date_from = datetime.strptime(search_date_from, '%Y-%m-%d')
            inventory_data = [item for item in inventory_data
                            if item.get('updated_at') and item.get('updated_at').replace(tzinfo=None) >= date_from]

        if search_date_to:
            from datetime import datetime
            date_to = datetime.strptime(search_date_to, '%Y-%m-%d')
            date_to = date_to.replace(hour=23, minute=59, second=59)
            inventory_data = [item for item in inventory_data
                            if item.get('updated_at') and item.get('updated_at').replace(tzinfo=None) <= date_to]

        # Quantity range filter
        if search_min_qty:
            try:
                min_qty = int(search_min_qty)
                inventory_data = [item for item in inventory_data if (item.get('qty') or 0) >= min_qty]
            except ValueError:
                pass

        if search_max_qty:
            try:
                max_qty = int(search_max_qty)
                inventory_data = [item for item in inventory_data if (item.get('qty') or 0) <= max_qty]
            except ValueError:
                pass

        # Sort the data - handle None values properly
        reverse_sort = sort_order == 'desc'
        if sort_by == 'job':
            inventory_data.sort(key=lambda x: (x.get('job') or ''), reverse=reverse_sort)
        elif sort_by == 'pcb_type':
            inventory_data.sort(key=lambda x: (x.get('pcb_type') or ''), reverse=reverse_sort)
        elif sort_by == 'qty':
            inventory_data.sort(key=lambda x: (x.get('qty') or 0), reverse=reverse_sort)
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

@app.route('/warehouse-inventory')
@require_auth
def warehouse_inventory():
    """Warehouse Inventory listing page - reads from PostgreSQL database."""
    conn = None
    cursor = None
    try:
        # Get search parameters
        search_item = request.args.get('search_item', '').strip()
        search_pcn = request.args.get('search_pcn', '').strip()
        search_mpn = request.args.get('search_mpn', '').strip()
        search_location = request.args.get('search_location', '').strip()

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        per_page = min(max(per_page, 10), 200)

        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Build query with filters
        query = """
            SELECT id, item, pcn, mpn, dc, onhandqty, loc_from, loc_to,
                   mfg_qty, qty_old, msd, po, cost, migrated_at
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE 1=1
        """
        params = []

        if search_item:
            query += " AND LOWER(item::text) LIKE %s"
            params.append(f"%{search_item.lower()}%")

        if search_pcn:
            query += " AND pcn::text LIKE %s"
            params.append(f"%{search_pcn}%")

        if search_mpn:
            query += " AND LOWER(mpn::text) LIKE %s"
            params.append(f"%{search_mpn.lower()}%")

        if search_location:
            query += " AND LOWER(loc_to::text) LIKE %s"
            params.append(f"%{search_location.lower()}%")

        # Get total count for pagination
        count_query = f"SELECT COUNT(*) as total FROM ({query}) AS filtered"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()['total']

        # Add sorting and pagination (newest entries first for efficiency)
        query += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([per_page, (page - 1) * per_page])

        # Execute main query
        cursor.execute(query, params)
        rows = cursor.fetchall()

        # Convert to list of dicts with consistent naming (matching .mdb format)
        inventory = []
        for row in rows:
            inventory.append({
                'PCN': row['pcn'],
                'Item': row['item'],
                'MPN': row['mpn'],
                'DC': row['dc'],
                'OnHandQty': row['onhandqty'],
                'Loc_From': row['loc_from'],
                'Loc_To': row['loc_to'],
                'MFG_Qty': row['mfg_qty'],
                'Qty_Old': row['qty_old'],
                'MSD': row['msd'],
                'PO': row['po'],
                'Cost': row['cost']
            })

        # Calculate pagination
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1

        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_records,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
            'pages': list(range(max(1, page - 2), min(total_pages + 1, page + 3)))
        }

        return render_template('warehouse_inventory.html',
                             inventory=inventory,
                             pagination=pagination,
                             total_records=total_records,
                             search_item=search_item,
                             search_pcn=search_pcn,
                             search_mpn=search_mpn,
                             search_location=search_location)

    except Exception as e:
        logger.error(f"Error loading warehouse inventory: {e}")
        flash(f"Error loading warehouse inventory: {e}", 'error')
        return render_template('warehouse_inventory.html', inventory=[],
                             pagination={'total': 0, 'page': 1, 'total_pages': 1, 'per_page': 10},
                             total_records=0)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                db_manager.return_connection(conn)
            except Exception:
                pass

@app.route('/api/warehouse-inventory/item')
@require_auth
def get_warehouse_item():
    """API endpoint to get a single warehouse inventory item."""
    try:
        item_id = request.args.get('item', '').strip()
        pcn = request.args.get('pcn', '').strip()

        if not item_id or not pcn:
            return jsonify({'success': False, 'message': 'Item and PCN are required'}), 400

        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Query for specific item
            cursor.execute("""
                SELECT id, item, pcn, mpn, dc, onhandqty, loc_from, loc_to,
                       mfg_qty, qty_old, msd, po, cost
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE item::text = %s AND pcn::text = %s
                LIMIT 1
            """, (item_id, pcn))

            row = cursor.fetchone()

            if row:
                # Convert to dict with consistent naming (matching .mdb format)
                item_data = {
                    'PCN': row['pcn'],
                    'Item': row['item'],
                    'MPN': row['mpn'],
                    'DC': row['dc'],
                    'OnHandQty': row['onhandqty'],
                    'Loc_From': row['loc_from'],
                    'Loc_To': row['loc_to'],
                    'MFG_Qty': row['mfg_qty'],
                    'Qty_Old': row['qty_old'],
                    'MSD': row['msd'],
                    'PO': row['po'],
                    'Cost': row['cost']
                }
                return jsonify({'success': True, 'item': item_data})
            else:
                return jsonify({'success': False, 'message': 'Item not found'}), 404

        finally:


            if cursor:


                cursor.close()


            if conn:


                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error fetching warehouse item: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/warehouse-inventory/recent')
@require_auth
def get_recent_warehouse_inventory():
    """API endpoint to get recent warehouse inventory items for stock page."""
    try:
        limit = request.args.get('limit', 10, type=int)

        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Get recent warehouse inventory items with quantity > 0
            cursor.execute("""
                SELECT id, item, pcn, mpn, dc, onhandqty, loc_to as location,
                       msd, po, migrated_at as updated_at
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE onhandqty > 0
                ORDER BY id DESC
                LIMIT %s
            """, (limit,))

            rows = cursor.fetchall()

            data = []
            for row in rows:
                data.append({
                    'id': row['id'],
                    'item': row['item'],
                    'pcn': row['pcn'],
                    'mpn': row['mpn'],
                    'dc': row['dc'],
                    'onhandqty': row['onhandqty'],
                    'location': row['location'],
                    'msd': row['msd'],
                    'po': row['po'],
                    'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None
                })

            return jsonify({'success': True, 'data': data})

        finally:
            if cursor:
                cursor.close()
            if conn:
                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error fetching recent warehouse inventory: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/warehouse-inventory/update', methods=['POST'])
@csrf.exempt
@require_auth
def update_warehouse_item():
    """API endpoint to update warehouse inventory item."""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'success': False, 'message': 'No data provided'}), 400

        # Validate required fields
        required_fields = ['item', 'pcn', 'mpn']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'message': f'{field} is required'}), 400

        conn = db_manager.get_connection()
        cursor = conn.cursor()

        try:
            # Helper function to convert empty strings to None for numeric fields
            def to_int_or_none(value):
                if value == '' or value is None:
                    return None
                try:
                    return int(value)
                except (ValueError, TypeError):
                    return None

            def to_float_or_none(value):
                if value == '' or value is None:
                    return None
                try:
                    return float(value)
                except (ValueError, TypeError):
                    return None

            # Update warehouse inventory record
            cursor.execute("""
                UPDATE pcb_inventory."tblWhse_Inventory"
                SET dc = %s,
                    onhandqty = %s,
                    loc_from = %s,
                    loc_to = %s,
                    mfg_qty = %s,
                    msd = %s,
                    po = %s,
                    cost = %s
                WHERE item::text = %s AND pcn::text = %s AND mpn::text = %s
            """, (
                data.get('dc') or None,
                to_int_or_none(data.get('onhandqty')),
                data.get('loc_from') or None,
                data.get('loc_to') or None,
                to_int_or_none(data.get('mfg_qty')),
                data.get('msd') or None,
                data.get('po') or None,
                to_float_or_none(data.get('cost')),
                data.get('item'),
                data.get('pcn'),
                data.get('mpn')
            ))

            if cursor.rowcount == 0:
                conn.rollback()
                return jsonify({'success': False, 'message': 'Item not found'}), 404

            conn.commit()
            logger.info(f"Updated warehouse inventory item: {data.get('item')}, PCN: {data.get('pcn')}")

            return jsonify({
                'success': True,
                'message': 'Item updated successfully'
            })

        except Exception as e:


            if conn:


                conn.rollback()
            logger.error(f"Database error updating warehouse item: {e}")
            return jsonify({'success': False, 'message': f'Database error: {str(e)}'}), 500
        finally:

            if cursor:

                cursor.close()

            if conn:

                db_manager.return_connection(conn)

    except Exception as e:
        logger.error(f"Error updating warehouse item: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

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

            location_type_summary[key]['total_quantity'] += item.get('qty', 0)
            if item.get('job'):
                location_type_summary[key]['jobs'].add(item.get('job'))

        # Convert to list format expected by template
        total_all_qty = sum(item.get('qty', 0) for item in inventory)
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
            host='aci-database',
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
            host='aci-database',
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

@app.route('/api/search')
@require_auth
def api_search():
    """API endpoint for searching inventory."""
    try:
        job = request.args.get('job')
        pcb_type = request.args.get('pcb_type')
        pcn = request.args.get('pcn')  # Optional PCN filter
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)

        inventory = db_manager.search_inventory(
            job=job,
            pcb_type=pcb_type,
            pcn=pcn,  # Pass PCN to search_inventory
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
@require_auth
def po_history():
    """PO History lookup page"""
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    # Get filter parameters
    search_po = request.args.get('po', '').strip()
    search_item = request.args.get('item', '').strip()
    search_mpn = request.args.get('mpn', '').strip()
    search_pcn = request.args.get('pcn', '').strip()
    search_date_from = request.args.get('date_from', '').strip()
    search_date_to = request.args.get('date_to', '').strip()

    conn = None
    try:
        conn = db_manager.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Build query
            query = """
                SELECT id, po_number, item, pcn, mpn, date_code, quantity,
                       transaction_type, transaction_date, location_from, location_to, user_id
                FROM pcb_inventory.po_history
                WHERE 1=1
            """
            params = []

            if search_po:
                query += " AND po_number ILIKE %s"
                params.append(f'%{search_po}%')

            if search_item:
                query += " AND item ILIKE %s"
                params.append(f'%{search_item}%')

            if search_mpn:
                query += " AND mpn ILIKE %s"
                params.append(f'%{search_mpn}%')

            if search_pcn:
                query += " AND pcn = %s"
                params.append(int(search_pcn))

            if search_date_from:
                query += " AND transaction_date >= %s"
                params.append(search_date_from)

            if search_date_to:
                query += " AND transaction_date <= %s"
                params.append(f'{search_date_to} 23:59:59')

            # Get total count
            count_query = f"SELECT COUNT(*) FROM ({query}) AS count_query"
            cur.execute(count_query, params)
            total_count = cur.fetchone()['count']

            # Add sorting and pagination
            query += " ORDER BY transaction_date DESC NULLS LAST LIMIT %s OFFSET %s"
            params.extend([per_page, (page - 1) * per_page])

            # Execute query
            cur.execute(query, params)
            receipts = [dict(row) for row in cur.fetchall()]

            # Calculate pagination
            total_pages = (total_count + per_page - 1) // per_page
            pagination = {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'total_pages': total_pages,
                'has_prev': page > 1,
                'has_next': page < total_pages,
                'prev_num': page - 1 if page > 1 else None,
                'next_num': page + 1 if page < total_pages else None,
                'pages': list(range(max(1, page - 2), min(total_pages + 1, page + 3)))
            }

            return render_template('po_history.html',
                                 receipts=receipts,
                                 pagination=pagination,
                                 search_po=search_po,
                                 search_item=search_item,
                                 search_mpn=search_mpn,
                                 search_pcn=search_pcn,
                                 search_date_from=search_date_from,
                                 search_date_to=search_date_to)
    except Exception as e:
        logger.error(f"Error loading PO history: {e}")
        flash(f"Error loading PO history: {e}", 'error')
        return render_template('po_history.html', receipts=[], pagination={'total': 0})
    finally:
        if conn:
            conn.close()

@app.route('/pcn-history')
@require_auth
def pcn_history():
    """PCN transaction history page - focused on efficiency"""
    # Get PCN parameter only
    search_pcn = request.args.get('pcn', '').strip()

    conn = None
    transactions = []
    pcn_info = None

    try:
        if search_pcn:
            conn = db_manager.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get all transactions for the PCN (no pagination, show everything)
                # Format tran_time consistently as MM/DD/YYYY HH:MI:SS AM/PM for ALL date formats
                query = """
                    SELECT trantype, item, mpn, tranqty,
                           CASE
                               -- Handle ISO format timestamps (YYYY-MM-DD HH:MM:SS...) - convert from UTC to EST
                               WHEN tran_time ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}' THEN
                                   TO_CHAR(timezone('America/New_York', tran_time::timestamptz), 'MM/DD/YYYY HH12:MI:SS AM')
                               -- Handle old short format (MM/DD/YY HH:MI:SS) - convert to full year
                               WHEN tran_time ~ '^[0-9]{2}/[0-9]{2}/[0-9]{2}\\s+[0-9]{2}:[0-9]{2}' THEN
                                   TO_CHAR(TO_TIMESTAMP(tran_time, 'MM/DD/YY HH24:MI:SS'), 'MM/DD/YYYY HH12:MI:SS AM')
                               -- If empty, NULL or other format, return as-is
                               ELSE
                                   tran_time
                           END as tran_time,
                           loc_from, loc_to, wo, po
                    FROM pcb_inventory."tblTransaction"
                    WHERE pcn = %s
                    ORDER BY tran_time DESC NULLS LAST, id DESC
                """
                cur.execute(query, (int(search_pcn),))
                transactions = [dict(row) for row in cur.fetchall()]

                # Get PCN info from warehouse inventory
                cur.execute("""
                    SELECT item, mpn, dc, onhandqty, mfg_qty, loc_to, msd, po
                    FROM pcb_inventory."tblWhse_Inventory"
                    WHERE pcn = %s
                    LIMIT 1
                """, (int(search_pcn),))
                result = cur.fetchone()
                if result:
                    pcn_info = dict(result)

            return render_template('pcn_history.html',
                                 transactions=transactions,
                                 pcn_info=pcn_info,
                                 search_pcn=search_pcn)
        else:
            # No PCN provided, just show the search form
            return render_template('pcn_history.html',
                                 transactions=[],
                                 pcn_info=None,
                                 search_pcn='')

    except Exception as e:
        logger.error(f"Error loading PCN history: {e}")
        flash(f"Error loading PCN history: {e}", 'error')
        return render_template('pcn_history.html', transactions=[], pcn_info=None, search_pcn=search_pcn)
    finally:
        if conn:
            conn.close()

@app.route('/stock-alerts')
@require_auth
def stock_alerts():
    """Stock Alerts page - shows all items below threshold."""
    conn = None
    cursor = None
    try:
        LOW_STOCK_THRESHOLD = 10

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 25, type=int)
        per_page = min(max(per_page, 10), 100)

        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Get low stock items with pagination
        query = """
            SELECT pcn, item, mpn, dc, onhandqty, loc_to, msd, po
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE onhandqty < %s AND onhandqty >= 0
            ORDER BY onhandqty ASC, item ASC
        """

        # Get total count
        count_query = """
            SELECT COUNT(*) as total
            FROM pcb_inventory."tblWhse_Inventory"
            WHERE onhandqty < %s AND onhandqty >= 0
        """
        cursor.execute(count_query, (LOW_STOCK_THRESHOLD,))
        total_records = cursor.fetchone()['total']

        # Get paginated results
        query += " LIMIT %s OFFSET %s"
        cursor.execute(query, (LOW_STOCK_THRESHOLD, per_page, (page - 1) * per_page))
        low_stock_items = [dict(row) for row in cursor.fetchall()]

        # Calculate pagination
        total_pages = (total_records + per_page - 1) // per_page if total_records > 0 else 1

        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_records,
            'total_pages': total_pages,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'prev_num': page - 1 if page > 1 else None,
            'next_num': page + 1 if page < total_pages else None,
            'pages': list(range(max(1, page - 2), min(total_pages + 1, page + 3)))
        }

        return render_template('stock_alerts.html',
                             low_stock_items=low_stock_items,
                             low_stock_threshold=LOW_STOCK_THRESHOLD,
                             pagination=pagination,
                             total_records=total_records)

    except Exception as e:
        logger.error(f"Error loading stock alerts: {e}")
        flash(f"Error loading stock alerts: {e}", 'error')
        return render_template('stock_alerts.html',
                             low_stock_items=[],
                             low_stock_threshold=10,
                             pagination={'total': 0, 'page': 1, 'total_pages': 1, 'per_page': 25},
                             total_records=0)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                db_manager.return_connection(conn)
            except Exception:
                pass

@app.route('/api/pcn/generate', methods=['POST'])
@csrf.exempt
def api_generate_pcn():
    """API endpoint to generate new PCN"""
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

            # Create barcode data string (pipe-delimited)
            # Format: PCN|Job|MPN|PartNumber|QTY|PO|Location|PCBType|DateCode|MSD
            barcode_data = f"{pcn_number}|{data.get('item', '')}|{data.get('mpn', '')}|{data.get('part_number', '')}|{data.get('quantity', '')}|{data.get('po_number', '')}|{data.get('location', '')}|{data.get('pcb_type', '')}|{data.get('date_code', '')}|{data.get('msd', '')}"

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
                    '-',
                    'Inventory',
                    session.get('username', 'system')
                ))
                logger.info(f"Added PO {data.get('po_number')} to PO history (PCN: {pcn_number})")

            # Also insert into warehouse inventory - simple INSERT, no ON CONFLICT
            cursor.execute("""
                INSERT INTO pcb_inventory."tblWhse_Inventory"
                (item, pcn, mpn, dc, onhandqty, loc_from, loc_to, msd, po)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get('item'),
                pcn_number,
                data.get('mpn') or '',
                data.get('date_code'),
                data.get('quantity', 0),
                '-',
                data.get('location', 'Receiving Area'),
                data.get('msd'),
                data.get('po_number')
            ))
            logger.info(f"Added/Updated PCN {pcn_number} in warehouse inventory")

            # Also insert into tblTransaction for PCN history tracking
            cursor.execute("""
                INSERT INTO pcb_inventory."tblTransaction"
                (trantype, item, pcn, mpn, dc, tranqty, tran_time, loc_from, loc_to, wo, po, userid)
                VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s, %s)
            """, (
                'GEN',  # Transaction type for PCN generation
                data.get('item'),
                pcn_number,
                data.get('mpn'),
                data.get('date_code'),
                data.get('quantity', 0),
                '-',  # location from
                data.get('location', 'Receiving Area'),  # location to - defaults to Receiving Area
                data.get('work_order'),  # work order
                data.get('po_number'),  # PO
                session.get('username', 'system')  # user
            ))
            logger.info(f"Added PCN {pcn_number} to tblTransaction for history tracking")

            conn.commit()

            logger.info(f"Generated PCN: {pcn_number} for item: {data.get('item')}")

            return jsonify({
                'success': True,
                'pcn_number': pcn_record['pcn_number'],
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
    try:
        conn = None
        cursor = None
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
                return jsonify({
                    'success': True,
                    'pcn_number': record['pcn_number'],
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

            # If not in pcn_records, try tblWhse_Inventory (main warehouse table)
            cursor.execute("""
                SELECT pcn, item, mpn, onhandqty, dc, msd, loc_to, po
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn::text = %s
                LIMIT 1
            """, (pcn_number,))

            whse_record = cursor.fetchone()

            if whse_record:
                return jsonify({
                    'success': True,
                    'pcn_number': str(whse_record['pcn']),
                    'part_number': whse_record['item'],
                    'job': whse_record['item'],
                    'mpn': whse_record['mpn'],
                    'quantity': whse_record['onhandqty'],
                    'date_code': whse_record['dc'],
                    'msd': whse_record['msd'],
                    'location': whse_record['loc_to'],
                    'po_number': whse_record['po']
                })

            # If not in tblWhse_Inventory, try pcn_history
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
                # Also try to get MPN from warehouse inventory for this job
                mpn_value = None
                cursor.execute("""
                    SELECT mpn FROM pcb_inventory."tblWhse_Inventory"
                    WHERE item::text = %s AND mpn IS NOT NULL AND mpn != ''
                    LIMIT 1
                """, (history_record['job'],))
                mpn_row = cursor.fetchone()
                if mpn_row:
                    mpn_value = mpn_row['mpn']

                return jsonify({
                    'success': True,
                    'pcn_number': history_record['pcn'],
                    'part_number': history_record['job'],
                    'job': history_record['job'],
                    'mpn': mpn_value,
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
    try:
        conn = None
        cursor = None
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
                    'pcn_number': r['pcn_number'],
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
    try:
        conn = None
        cursor = None
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

                # If not in pcn_history, check tblTransaction
                if not history_record:
                    cursor.execute("""
                        SELECT pcn, item
                        FROM pcb_inventory."tblTransaction"
                        WHERE pcn = %s
                        LIMIT 1
                    """, (pcn_number,))

                    transaction_record = cursor.fetchone()

                    if not transaction_record:
                        return jsonify({'success': False, 'error': 'PCN not found'}), 404

                    # PCN exists in tblTransaction
                    item_name = transaction_record['item']
                else:
                    # PCN exists only in history
                    item_name = history_record['job']
            else:
                item_name = pcn_record['item']

            # Delete from all tables where PCN exists

            # 1. Delete from pcn_history table
            cursor.execute("""
                DELETE FROM pcb_inventory.pcn_history
                WHERE pcn = %s
            """, (pcn_number,))

            # 2. Delete from po_history if exists
            cursor.execute("""
                DELETE FROM pcb_inventory.po_history
                WHERE pcn = %s
            """, (pcn_number,))

            # 3. Delete from pcn_records table if it exists there
            cursor.execute("""
                DELETE FROM pcb_inventory.pcn_records
                WHERE pcn_number = %s
            """, (pcn_number,))

            # 4. Delete from tblWhse_Inventory (warehouse inventory)
            cursor.execute("""
                DELETE FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn = %s
            """, (pcn_number,))

            # 5. Delete from tblTransaction (PCN history tracking)
            cursor.execute("""
                DELETE FROM pcb_inventory."tblTransaction"
                WHERE pcn = %s
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
    """API endpoint to get PCN history - NO AUTH REQUIRED for public access"""
    try:
        limit = request.args.get('limit', 100, type=int)
        pcn = request.args.get('pcn', None)
        job = request.args.get('job', None)
        pcb_type = request.args.get('pcb_type', None)
        status = request.args.get('status', None)

        filters = {}
        if pcn:
            filters['pcn'] = pcn
        if job:
            filters['job'] = job
        if pcb_type:
            filters['pcb_type'] = pcb_type
        if status:
            filters['status'] = status

        history = db_manager.get_pcn_history(limit=limit, filters=filters if filters else None)

        # Format dates for JSON serialization
        for record in history:
            if record.get('generated_at'):
                # Handle both datetime objects and string dates
                if hasattr(record['generated_at'], 'isoformat'):
                    record['generated_at'] = record['generated_at'].isoformat()
                # else: leave as string

        return jsonify({'success': True, 'data': history})
    except Exception as e:
        logger.error(f"Error getting PCN history: {e}")
        return jsonify({'success': False, 'error': 'Failed to get PCN history'}), 500

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
                # Handle both datetime objects and string dates
                if hasattr(record['generated_at'], 'isoformat'):
                    record['generated_at'] = record['generated_at'].isoformat()
                # else: leave as string

        return jsonify({'success': True, 'data': results})
    except Exception as e:
        logger.error(f"Error searching PCN: {e}")
        return jsonify({'success': False, 'error': 'Failed to search PCN'}), 500

@app.route('/api/po/history', methods=['GET'])
def api_po_history():
    """API endpoint to get PO history - NO AUTH REQUIRED for public access"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        limit = request.args.get('limit', per_page, type=int)  # For backwards compatibility
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

        # Calculate offset for pagination
        offset = (page - 1) * per_page

        # Get total count first
        total_count = db_manager.get_po_history_count(filters if filters else None)

        # Get paginated results
        history = db_manager.get_po_history(limit=per_page, offset=offset, filters=filters if filters else None)

        # Format dates for JSON serialization
        for record in history:
            if record.get('transaction_date'):
                record['transaction_date'] = record['transaction_date'].isoformat()
            if record.get('created_at'):
                record['created_at'] = record['created_at'].isoformat()

        return jsonify({
            'success': True,
            'data': history,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page
        })
    except Exception as e:
        logger.error(f"Error getting PO history: {e}")
        return jsonify({'success': False, 'error': 'Failed to get PO history'}), 500

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
    try:
        conn = None
        cursor = None
        conn = db_manager.get_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # First check tblWhse_Inventory for most current data (updated by restock/stock/pick)
            cursor.execute("""
                SELECT pcn::varchar as pcn_number,
                       item,
                       po as po_number,
                       item as part_number,
                       mpn,
                       onhandqty as quantity,
                       dc as date_code,
                       msd,
                       NULL as barcode_data,
                       loc_to as location,
                       NULL as pcb_type
                FROM pcb_inventory."tblWhse_Inventory"
                WHERE pcn = %s
            """, (int(pcn_number),))

            pcn_data = cursor.fetchone()

            # If not found in warehouse inventory, try pcn_records (legacy)
            if not pcn_data:
                cursor.execute("""
                    SELECT pcn_number, item, po_number, part_number, mpn,
                           quantity, date_code, msd, barcode_data,
                           NULL as location, NULL as pcb_type
                    FROM pcb_inventory.pcn_records
                    WHERE pcn_number = %s
                """, (pcn_number,))
                pcn_data = cursor.fetchone()

            # If still not found, try pcn_history
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

            response = make_response(render_template('print_label.html', data=dict(pcn_data)))
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
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
    try:
        conn = None
        cursor = None
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

            # Generate ZPL code for 3x1 inch label (Zebra ZP450)
            # Label dimensions: 3 inches wide (288 dots @ 203dpi), 1 inch tall (96 dots @ 203dpi)
            zpl = f"""^XA
^FO0,0^GB576,0,2^FS
^FO0,0^GB0,192,2^FS
^FO576,0^GB0,192,2^FS
^FO0,192^GB576,0,2^FS

^FO10,10^A0N,28,28^FDPCN: {data['pcn_number']}^FS

^FO200,8^BY2,2,40^BCN,40,N,N,N^FD{data['pcn_number']}^FS

^FO480,10^A0N,16,16^FDQTY^FS
^FO480,30^A0N,32,32^FD{data.get('quantity', 0)}^FS

^FO0,80^GB576,0,1^FS

^FO10,85^A0N,16,16^FDJob: {data.get('item', 'N/A')}^FS
^FO10,105^A0N,16,16^FDMPN: {data.get('mpn', 'N/A')}^FS
^FO10,125^A0N,16,16^FDPO: {data.get('po_number', 'N/A')}^FS

^FO350,85^A0N,16,16^FDDC: {data.get('date_code', 'N/A')}^FS
^FO350,105^A0N,16,16^FDMSD: {data.get('msd', 'N/A')}^FS

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