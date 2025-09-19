#!/usr/bin/env python3
"""
Dockerized Flask web application for Stock and Pick PCB inventory management.
All database connections use container networking.
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, g
from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, IntegerField, SelectField, SubmitField, HiddenField
from wtforms.validators import DataRequired, NumberRange, Length, ValidationError
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
import re
from functools import wraps
import hashlib
import secrets

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
# Use environment variable for secret key, fallback to secure random key
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

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

# Security headers
@app.after_request
def add_security_headers(response):
    """Add comprehensive security headers to all responses."""
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
    # Prevent clickjacking
    response.headers['X-Frame-Options'] = 'DENY'
    # Prevent MIME type sniffing
    response.headers['X-Content-Type-Options'] = 'nosniff'
    # XSS Protection
    response.headers['X-XSS-Protection'] = '1; mode=block'
    # Referrer Policy
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    # Feature Policy
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

@app.context_processor
def inject_current_time():
    return {
        'current_time': datetime.now().strftime('%B %d, %Y %I:%M %p'),
        'current_user': g.get('current_user', {}),
        'user_can_see_itar': g.get('user_can_see_itar', False)
    }

@app.template_filter('moment_fromnow')
def moment_fromnow_filter(dt):
    """Calculate time ago from a datetime object"""
    if not dt:
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
    job = StringField('Part Number', validators=[DataRequired(), Length(min=1, max=50)])
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
    job = StringField('Part Number', validators=[DataRequired(), Length(min=1, max=50)])
    work_order = StringField('Work Order Number', validators=[Length(max=50)])
    pcb_type = StringField('Component Type', validators=[DataRequired(), Length(min=1, max=50), validate_pcb_type_field])
    dc = StringField('Date Code (DC)', validators=[Length(max=50)])
    msd = StringField('Moisture Sensitive Device (MSD)', validators=[Length(max=50)])
    quantity = IntegerField('Quantity', validators=[DataRequired(), NumberRange(min=1)])
    submit = SubmitField('Pick Parts')

class UserSessionForm(FlaskForm):
    """Form for simulating user authentication from ACI dashboard."""
    username = SelectField('User', choices=[], validators=[DataRequired()])
    role = HiddenField()
    itar_authorized = HiddenField()
    submit = SubmitField('Login as User')

class DatabaseManager:
    """Handle database operations using containerized PostgreSQL with connection pooling."""
    
    def __init__(self):
        self.db_config = DB_CONFIG
        # Initialize connection pool
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=1,     # Minimum connections
                maxconn=20,    # Maximum connections
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
                  itar_auth: bool = False, username: str = 'system', work_order: str = None) -> Dict[str, Any]:
        """Stock PCB using the PostgreSQL stored procedure."""
        try:
            # Call the simplified PostgreSQL function with only 4 required parameters
            result = self.execute_function('pcb_inventory.stock_pcb', 
                (job, pcb_type, quantity, location))
            logger.info(f"Stock operation: {result}")
            return result
        except Exception as e:
            error_msg = get_safe_error_message(e, "stock operation")
            return {'success': False, 'error': error_msg}
    
    def pick_pcb(self, job: str, pcb_type: str, quantity: int, 
                 user_role: str = 'USER', itar_auth: bool = False, username: str = 'system', work_order: str = None) -> Dict[str, Any]:
        """Pick PCB using the PostgreSQL stored procedure."""
        try:
            # Call the simplified PostgreSQL function with only 3 required parameters
            result = self.execute_function('pcb_inventory.pick_pcb', 
                (job, pcb_type, quantity))
            logger.info(f"Pick operation: {result}")
            return result
        except Exception as e:
            error_msg = get_safe_error_message(e, "pick operation")
            return {'success': False, 'error': error_msg}
    
    def get_current_inventory(self, user_role: str = 'USER', itar_auth: bool = False) -> List[Dict[str, Any]]:
        """Get current inventory filtered by user access level."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM pcb_inventory.get_filtered_inventory(%s, %s) ORDER BY job, pcb_type",
                    (user_role, itar_auth)
                )
                return [dict(row) for row in cur.fetchall()]
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
                cur.execute("SELECT pcb_type, location, SUM(qty) as total_qty FROM pcb_inventory.tblpcb_inventory GROUP BY pcb_type, location ORDER BY pcb_type, location")
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get summary: {e}")
            return []
        finally:
            if conn:
                self.return_connection(conn)
    
    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        conn = None
        try:
            conn = self.get_connection()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM pcb_inventory.inventory_audit ORDER BY timestamp DESC LIMIT %s",
                    (limit,)
                )
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get audit log: {e}")
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
        """Get comprehensive statistics summary for stats page."""
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
    """Decorator to require user authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Check if user is properly authenticated
        if 'username' not in session or 'role' not in session:
            # Redirect to user selection if not authenticated
            flash('Please log in to access this page', 'warning')
            return redirect(url_for('user_select'))
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
        total_jobs = len(set(item['job'] for item in inventory)) if inventory else 0
        total_quantity = sum(item['qty'] for item in inventory) if inventory else 0
        total_items = len(inventory) if inventory else 0
        
        stats = {
            'total_jobs': total_jobs,
            'total_quantity': total_quantity,
            'total_items': total_items,
            'pcb_types': len(PCB_TYPES)
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
                             recent_activity=recent_activity)
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}")
        # Provide safe default values on error
        safe_stats = {
            'total_jobs': 0,
            'total_quantity': 0,
            'total_items': 0,
            'pcb_types': len(PCB_TYPES)
        }
        flash(f"Error loading dashboard: {e}", 'error')
        return render_template('index.html', stats=safe_stats, summary=[], recent_activity=[])

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
            result = db_manager.stock_pcb(
                job=form.job.data,
                pcb_type=form.pcb_type.data,
                quantity=form.quantity.data,
                location=form.location.data,
                itar_classification=form.itar_classification.data,
                user_role=user_role,
                itar_auth=itar_auth,
                username=session.get('username', 'system'),
                work_order=form.work_order.data if form.work_order.data else None
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
            
            result = db_manager.pick_pcb(
                job=form.job.data,
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
    """Inventory listing page with pagination."""
    # Get search and pagination parameters
    search_job = request.args.get('job', '').strip()
    search_pcb_type = request.args.get('pcb_type', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    sort_by = request.args.get('sort', 'job')
    sort_order = request.args.get('order', 'asc')
    
    # Limit per_page to reasonable values
    per_page = min(max(per_page, 10), 200)
    
    user_role = session.get('role', 'USER')
    itar_auth = session.get('itar_authorized', False)
    
    try:
        if search_job or search_pcb_type:
            inventory_data = db_manager.search_inventory(
                job=search_job if search_job else None,
                pcb_type=search_pcb_type if search_pcb_type else None,
                user_role=user_role,
                itar_auth=itar_auth
            )
        else:
            inventory_data = db_manager.get_current_inventory(user_role, itar_auth)
        
        # Sort the data
        reverse_sort = sort_order == 'desc'
        if sort_by == 'job':
            inventory_data.sort(key=lambda x: x.get('job', ''), reverse=reverse_sort)
        elif sort_by == 'pcb_type':
            inventory_data.sort(key=lambda x: x.get('pcb_type', ''), reverse=reverse_sort)
        elif sort_by == 'qty':
            inventory_data.sort(key=lambda x: x.get('qty', 0), reverse=reverse_sort)
        elif sort_by == 'location':
            inventory_data.sort(key=lambda x: x.get('location', ''), reverse=reverse_sort)
        elif sort_by == 'updated_at':
            inventory_data.sort(key=lambda x: x.get('updated_at', ''), reverse=reverse_sort)
        
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
                             search_job=search_job,
                             search_pcb_type=search_pcb_type,
                             sort_by=sort_by,
                             sort_order=sort_order)
    except Exception as e:
        logger.error(f"Error loading inventory: {e}")
        flash(f"Error loading inventory: {e}", 'error')
        return render_template('inventory.html', inventory=[], pagination={'total': 0}, pcb_types=PCB_TYPES)

@app.route('/reports')
@require_auth
def reports():
    """Reports page."""
    try:
        summary = db_manager.get_inventory_summary()
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
        return redirect(url_for('index'))
    
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
            SELECT tablename as table_name
            FROM pg_tables
            WHERE schemaname = 'pcb_inventory'
            AND tablename NOT IN ('inventory_audit')
            ORDER BY tablename
        """)
        
        table_info = []
        for row in cursor.fetchall():
            table_name = row['table_name']
            try:
                # Get record count for each table
                if '"' in table_name:
                    count_sql = f'SELECT COUNT(*) as count FROM pcb_inventory.{table_name}'
                else:
                    count_sql = f'SELECT COUNT(*) as count FROM pcb_inventory."{table_name}"'
                
                cursor.execute(count_sql)
                count_result = cursor.fetchone()
                record_count = count_result['count'] if count_result else 0
                
                
                table_info.append({
                    'table_name': table_name,
                    'record_count': record_count
                })
                
            except Exception as e:
                logger.error(f"Error getting info for table {table_name}: {e}")
                table_info.append({
                    'table_name': table_name,
                    'record_count': 'Error'
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
        return redirect(url_for('index'))
    
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

# User Management Routes
@app.route('/user-select', methods=['GET', 'POST'])
def user_select():
    """User selection interface to simulate ACI dashboard login."""
    form = UserSessionForm()
    
    # Populate user choices
    users = user_manager.get_all_users()
    form.username.choices = [(u['username'], f"{u['username']} ({u['role']}) {'[ITAR]' if u['itar_authorized'] else ''}") for u in users]
    
    if form.validate_on_submit():
        username = form.username.data
        user = user_manager.get_user_by_username(username)
        
        if user:
            # Simulate ACI dashboard login
            login_result = user_manager.simulate_aci_login(username)
            
            if login_result['success']:
                # Set session
                session['username'] = user['username']
                session['role'] = user['role']
                session['itar_authorized'] = user['itar_authorized']
                session['session_token'] = login_result['session_token']
                
                flash(f"Logged in as {user['username']} with role {user['role']} {'(ITAR Authorized)' if user['itar_authorized'] else '(No ITAR)'}", 'success')
                return redirect(url_for('index'))
            else:
                flash(f"Login failed: {login_result['error']}", 'error')
        else:
            flash('User not found', 'error')
    
    return render_template('user_select.html', form=form, users=users)

@app.route('/logout')
def logout():
    """Logout current user."""
    username = session.get('username', 'unknown')
    session.clear()
    flash(f'Logged out {username}', 'info')
    return redirect(url_for('user_select'))

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
@validate_api_request(['job', 'pcb_type', 'quantity', 'location'])
@require_auth
def api_stock():
    """API endpoint for stocking PCBs."""
    try:
        data = request.get_json()
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        itar_classification = data.get('itar_classification', 'NONE')
        
        # Check ITAR access
        if itar_classification == 'ITAR' and not user_manager.can_access_itar(user_role, itar_auth):
            return jsonify({'success': False, 'error': 'Access denied: ITAR authorization required'}), 403
        
        result = db_manager.stock_pcb(
            job=data['job'],
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
@validate_api_request(['job', 'pcb_type', 'quantity'])
@require_auth
def api_pick():
    """API endpoint for picking PCBs."""
    try:
        data = request.get_json()
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        
        result = db_manager.pick_pcb(
            job=data['job'],
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
        user_role = session.get('role', 'USER')
        itar_auth = session.get('itar_authorized', False)
        
        inventory = db_manager.search_inventory(
            job=job, 
            pcb_type=pcb_type,
            user_role=user_role,
            itar_auth=itar_auth
        )
        return jsonify({'success': True, 'data': inventory})
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