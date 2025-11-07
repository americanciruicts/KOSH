#!/usr/bin/env python3
"""
Minimal test Flask app to diagnose issues.
"""

import os
import logging
from flask import Flask, jsonify
import psycopg2

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-key'

# Database config
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'postgres'),
    'port': int(os.getenv('POSTGRES_PORT', 5432)),
    'database': os.getenv('POSTGRES_DB', 'pcb_inventory'),
    'user': os.getenv('POSTGRES_USER', 'stockpick_user'),
    'password': os.getenv('POSTGRES_PASSWORD', 'stockpick_pass')
}

@app.route('/')
def index():
    return jsonify({
        'status': 'ok',
        'message': 'Stock and Pick Test App',
        'config': {
            'host': DB_CONFIG['host'],
            'port': DB_CONFIG['port'],
            'database': DB_CONFIG['database'],
            'user': DB_CONFIG['user']
        }
    })

@app.route('/health')
def health():
    try:
        # Test database connection
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM pcb_inventory.tblPCB_Inventory;")
            count = cur.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'healthy',
            'database': 'connected',
            'inventory_count': count
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 500

@app.route('/test-db')
def test_db():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            cur.execute("SELECT version();")
            version = cur.fetchone()[0]
        conn.close()
        
        return jsonify({
            'status': 'success',
            'postgres_version': version
        })
    except Exception as e:
        logger.error(f"Database test failed: {e}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

if __name__ == '__main__':
    logger.info("Starting test Flask app...")
    app.run(debug=True, host='0.0.0.0', port=5000)