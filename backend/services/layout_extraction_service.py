"""
Layout-aware text extraction service.
Extracts text with bounding boxes from both text-based and scanned PDFs.
"""
import pdfplumber
import pytesseract
import tempfile
import os
from pdf2image import convert_from_path
from typing import List, Dict, Tuple
import re

class TextBlock:
    """Represents a text block with its position and content"""
    def __init__(self, text: str, x0: float, y0: float, x1: float, y1: float, 
                 page_num: int, is_table: bool = False):
        self.text = text.strip()
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.width = x1 - x0
        self.height = y1 - y0
        self.page_num = page_num
        self.is_table = is_table
        self.font_size = None
        self.font_name = None

def extract_text_blocks_with_layout(pdf_path: str) -> List[TextBlock]:
    """
    Extract text blocks with bounding boxes from PDF.
    Handles both text-based and scanned PDFs.
    Returns list of TextBlock objects.
    """
    blocks = []
    
    # First, try text-based extraction with pdfplumber
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text with bounding boxes
                words = page.extract_words(
                    x_tolerance=3,
                    y_tolerance=3,
                    keep_blank_chars=False
                )
                
                if words:
                    # Group words into lines and blocks
                    text_blocks = _group_words_into_blocks(words, page_num, page.height)
                    blocks.extend(text_blocks)
                    
                    # Extract tables separately
                    tables = page.extract_tables()
                    if tables:
                        for table in tables:
                            table_blocks = _extract_table_blocks(table, page_num, page.height)
                            blocks.extend(table_blocks)
    except Exception as e:
        print(f"Text-based extraction failed: {e}, trying OCR...")
        # Fallback to OCR-based extraction
        blocks = _extract_with_ocr(pdf_path)
    
    return blocks

def _group_words_into_blocks(words: List[Dict], page_num: int, page_height: float) -> List[TextBlock]:
    """Group words into text blocks based on proximity"""
    if not words:
        return []
    
    blocks = []
    current_line = []
    current_y = None
    line_tolerance = 5  # pixels
    
    for word in words:
        word_y = page_height - word['top']  # Convert to bottom-up coordinates
        
        if current_y is None or abs(word_y - current_y) <= line_tolerance:
            # Same line
            current_line.append(word)
            if current_y is None:
                current_y = word_y
        else:
            # New line - process current line
            if current_line:
                block = _create_block_from_words(current_line, page_num, page_height)
                if block:
                    blocks.append(block)
            current_line = [word]
            current_y = word_y
    
    # Process last line
    if current_line:
        block = _create_block_from_words(current_line, page_num, page_height)
        if block:
            blocks.append(block)
    
    return blocks

def _create_block_from_words(words: List[Dict], page_num: int, page_height: float) -> TextBlock:
    """Create a TextBlock from a list of words"""
    if not words:
        return None
    
    # Calculate bounding box
    x0 = min(w['x0'] for w in words)
    y0 = page_height - max(w['top'] for w in words)  # Convert to bottom-up
    x1 = max(w['x1'] for w in words)
    y1 = page_height - min(w['top'] for w in words)
    
    # Combine text
    text = ' '.join(w['text'] for w in words)
    
    return TextBlock(text, x0, y0, x1, y1, page_num)

def _extract_table_blocks(table: List[List], page_num: int, page_height: float) -> List[TextBlock]:
    """Extract table cells as text blocks"""
    blocks = []
    # Note: This is a simplified version. For accurate table extraction,
    # we'll use Camelot in the table service
    for row_idx, row in enumerate(table):
        for col_idx, cell in enumerate(row):
            if cell and str(cell).strip():
                # Approximate cell position (will be refined by table service)
                text_block = TextBlock(
                    str(cell).strip(),
                    0, 0, 0, 0,  # Placeholder coordinates
                    page_num,
                    is_table=True
                )
                blocks.append(text_block)
    return blocks

def _extract_with_ocr(pdf_path: str) -> List[TextBlock]:
    """Extract text blocks using OCR with bounding boxes"""
    blocks = []
    
    try:
        # Convert PDF to images
        images = convert_from_path(pdf_path, dpi=300)
        
        for page_num, image in enumerate(images, 1):
            # Get OCR data with bounding boxes using TSV format
            ocr_data = pytesseract.image_to_data(
                image,
                lang='ara',
                output_type=pytesseract.Output.DICT,
                config='--psm 6'
            )
            
            # Group words into blocks
            current_block_words = []
            current_y = None
            y_tolerance = 10
            
            for i in range(len(ocr_data['text'])):
                text = ocr_data['text'][i].strip()
                if not text or int(ocr_data['conf'][i]) < 30:  # Skip low confidence
                    continue
                
                x = ocr_data['left'][i]
                y = image.height - ocr_data['top'][i] - ocr_data['height'][i]  # Bottom-up
                w = ocr_data['width'][i]
                h = ocr_data['height'][i]
                
                if current_y is None or abs(y - current_y) <= y_tolerance:
                    current_block_words.append({
                        'text': text,
                        'x0': x,
                        'y0': y,
                        'x1': x + w,
                        'y1': y + h
                    })
                    if current_y is None:
                        current_y = y
                else:
                    # New line - create block
                    if current_block_words:
                        block = _create_block_from_ocr_words(
                            current_block_words, page_num, image.width, image.height
                        )
                        if block:
                            blocks.append(block)
                    current_block_words = [{
                        'text': text,
                        'x0': x,
                        'y0': y,
                        'x1': x + w,
                        'y1': y + h
                    }]
                    current_y = y
            
            # Process last block
            if current_block_words:
                block = _create_block_from_ocr_words(
                    current_block_words, page_num, image.width, image.height
                )
                if block:
                    blocks.append(block)
                    
    except Exception as e:
        print(f"OCR extraction failed: {e}")
    
    return blocks

def _create_block_from_ocr_words(words: List[Dict], page_num: int, 
                                 page_width: float, page_height: float) -> TextBlock:
    """Create TextBlock from OCR words"""
    if not words:
        return None
    
    x0 = min(w['x0'] for w in words)
    y0 = min(w['y0'] for w in words)
    x1 = max(w['x1'] for w in words)
    y1 = max(w['y1'] for w in words)
    
    text = ' '.join(w['text'] for w in words)
    
    return TextBlock(text, x0, y0, x1, y1, page_num)

def normalize_arabic_numerals(text: str) -> str:
    """Convert Arabic-Indic numerals (٠-٩) to Western numerals (0-9)"""
    arabic_numerals = '٠١٢٣٤٥٦٧٨٩'
    western_numerals = '0123456789'
    
    translation_table = str.maketrans(arabic_numerals, western_numerals)
    return text.translate(translation_table)

