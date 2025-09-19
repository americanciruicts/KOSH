#!/usr/bin/env python3
"""Test OCR improvements."""

import sys
import os
import tempfile
from PIL import Image, ImageDraw, ImageFont

# Create a simple test image with text
def create_test_image():
    # Create a white image
    img = Image.new('RGB', (800, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font
    try:
        font = ImageFont.load_default()
    except:
        font = None
    
    # Add some test text similar to employee roster
    text_lines = [
        "EMPLOYEE ROSTER - TECHNICAL DEPARTMENT",
        "",
        "No. | Name                    | Service No | Job Title      | Signature",
        "01  | W.D. Ranjan Puyguolla  | 008249     | Tech. Mgr/OR&M | [signed]",
        "02  | H.C. Jayaweera         | 008301     | T.M./OR&M      | [signed]",
        "03  | H.P.D. Lakmadasa       | 008293     | T.M./SYSOP     | [signed]",
    ]
    
    y_pos = 50
    for line in text_lines:
        draw.text((50, y_pos), line, fill='black', font=font)
        y_pos += 40
    
    # Save to temporary file
    temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
    img.save(temp_file.name)
    return temp_file.name

# Test OCR
def test_ocr():
    sys.path.append('/app')
    from src.doc_parser import DocumentParser
    
    # Create test image
    test_img = create_test_image()
    print(f"Created test image: {test_img}")
    
    try:
        # Test OCR
        parser = DocumentParser()
        text, metadata = parser.parse_file(test_img)
        
        print("OCR Result:")
        print(text)
        
        # Check if key words are detected
        key_words = ['EMPLOYEE', 'ROSTER', 'Ranjan', '008249', 'Tech']
        detected = sum(1 for word in key_words if word in text)
        
        print(f"\nDetected {detected}/{len(key_words)} key words")
        
        if detected > 2:
            print("✅ OCR working well!")
        else:
            print("❌ OCR needs improvement")
            
    finally:
        # Clean up
        os.unlink(test_img)

if __name__ == "__main__":
    test_ocr()