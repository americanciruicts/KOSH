#!/usr/bin/env python3
"""
Document Intelligence API
Part of the revestDataPipe project
"""

import os
import sys
from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config import Config
from ai_pipeline import AIPipeline
from doc_parser import DocumentParser

app = Flask(__name__)
app.config.from_object(Config)

# Initialize components
ai_pipeline = AIPipeline()
doc_parser = DocumentParser()

@app.route('/')
def index():
    """Main page for document intelligence"""
    return render_template('index.html')

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'document_intelligence',
        'version': '1.0.0'
    })

@app.route('/api/analyze', methods=['POST'])
def analyze_document():
    """Analyze uploaded document"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Process the document
            result = ai_pipeline.process_document(filepath)
            
            return jsonify({
                'success': True,
                'filename': filename,
                'analysis': result
            })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/extract', methods=['POST'])
def extract_data():
    """Extract data from document"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Extract data from document
            extracted_data = doc_parser.extract_data(filepath)
            
            return jsonify({
                'success': True,
                'filename': filename,
                'extracted_data': extracted_data
            })
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Create upload directory if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
