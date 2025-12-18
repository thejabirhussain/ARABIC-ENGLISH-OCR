"""
Layout-aware text extraction service.
Extracts text with bounding boxes from both text-based and scanned PDFs.
"""
import pdfplumber
import pytesseract
try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except Exception:
    PYMUPDF_AVAILABLE = False
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
    
    # Preferred: PyMuPDF for digital PDFs (more reliable block grouping)
    if PYMUPDF_AVAILABLE:
        try:
            blocks = _extract_with_pymupdf(pdf_path)
        except Exception as e:
            print(f"PyMuPDF extraction failed: {e}, trying pdfplumber...")
            blocks = []
    
    # Then, try text-based extraction with pdfplumber
    try:
        if not blocks:
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
    
    # Post-process to remove duplicates/overlaps and noisy blocks
    blocks = _postprocess_blocks(blocks)
    return blocks

def _extract_with_pymupdf(pdf_path: str) -> List[TextBlock]:
    """Extract text blocks using PyMuPDF for better structure on digital PDFs."""
    results: List[TextBlock] = []
    try:
        doc = fitz.open(pdf_path)
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            page_num = page_index + 1
            # Use dict to get blocks->lines->spans with bbox
            data = page.get_text("dict")
            height = page.rect.height
            
            for block in data.get("blocks", []):
                if block.get("type", 0) != 0:
                    continue  # skip images
                
                # Process line by line to preserve reading order
                import re
                arabic_re = re.compile(r'[\u0600-\u06FF]')
                
                line_texts = []
                all_spans = []
                
                for line in block.get("lines", []):
                    line_spans = []
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if not text:
                            continue
                        x0, y0, x1, y1 = span["bbox"]
                        # Convert to bottom-up (PyMuPDF uses top-left, we need bottom-left)
                        by0 = height - y1
                        by1 = height - y0
                        
                        span_data = {
                            'text': text,
                            'x0': x0,
                            'y0': by0,
                            'x1': x1,
                            'y1': by1,
                        }
                        line_spans.append(span_data)
                        all_spans.append(span_data)
                    
                    if not line_spans:
                        continue
                    
                    # Check if line has Arabic
                    has_arabic = any(arabic_re.search(s['text']) for s in line_spans)
                    
                    if has_arabic:
                        # Arabic RTL: sort by right edge (x1) descending
                        ordered = sorted(line_spans, key=lambda s: s['x1'], reverse=True)
                    else:
                        # LTR: sort by left edge (x0) ascending
                        ordered = sorted(line_spans, key=lambda s: s['x0'])
                    
                    line_text = ' '.join(s['text'] for s in ordered)
                    line_texts.append(line_text)
                
                text = '\n'.join(line_texts).strip()
                
                if not text:
                    continue
                
                spans = all_spans
                
                # Calculate bounding box from all spans
                x0 = min(s['x0'] for s in spans)
                y0 = min(s['y0'] for s in spans)
                x1 = max(s['x1'] for s in spans)
                y1 = max(s['y1'] for s in spans)
                
                # Only add if we have valid text and dimensions
                if text and (x1 - x0) > 0 and (y1 - y0) > 0:
                    results.append(TextBlock(text, x0, y0, x1, y1, page_num))
        
        doc.close()
        print(f"PyMuPDF extracted {len(results)} text blocks")
    except Exception as e:
        print(f"PyMuPDF extraction failed: {e}")
        import traceback
        traceback.print_exc()
    
    return results

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
    
    # Combine text with RTL awareness for Arabic
    # Group words by line first (similar y positions)
    import re
    arabic_re = re.compile(r'[\u0600-\u06FF]')
    
    # Group words into lines
    lines = []
    current_line = []
    current_y = None
    y_tolerance = 3
    
    for word in words:
        word_y = page_height - word['top']  # Already converted to bottom-up
        if current_y is None or abs(word_y - current_y) <= y_tolerance:
            current_line.append(word)
            if current_y is None:
                current_y = word_y
        else:
            if current_line:
                lines.append(current_line)
            current_line = [word]
            current_y = word_y
    
    if current_line:
        lines.append(current_line)
    
    # Process each line with proper RTL/LTR ordering
    line_texts = []
    for line_words in lines:
        line_has_arabic = any(arabic_re.search(str(w.get('text',''))) for w in line_words)
        if line_has_arabic:
            # Sort words right-to-left (descending x1) for Arabic
            ordered = sorted(line_words, key=lambda w: w['x1'], reverse=True)
        else:
            # Left-to-right default
            ordered = sorted(line_words, key=lambda w: w['x0'])
        line_text = ' '.join(w['text'] for w in ordered)
        line_texts.append(line_text)
    
    text = '\n'.join(line_texts)
    
    return TextBlock(text, x0, y0, x1, y1, page_num)

def _iou(a: TextBlock, b: TextBlock) -> float:
    ax0, ay0, ax1, ay1 = a.x0, a.y0, a.x1, a.y1
    bx0, by0, bx1, by1 = b.x0, b.y0, b.x1, b.y1
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    area_a = (ax1 - ax0) * (ay1 - ay0)
    area_b = (bx1 - bx0) * (by1 - by0)
    union = max(area_a + area_b - inter, 1e-6)
    return inter / union

def _postprocess_blocks(blocks: List[TextBlock]) -> List[TextBlock]:
    """Post-process blocks to remove duplicates while preserving reading order"""
    if not blocks:
        return []
    by_page = {}
    for b in blocks:
        by_page.setdefault(b.page_num, []).append(b)
    cleaned = []
    for page, arr in by_page.items():
        # Sort by reading order: top to bottom, then left to right
        arr_sorted = sorted(arr, key=lambda b: (-b.y1, b.x0))
        kept = []
        for b in arr_sorted:
            if not b.text or len(b.text.strip()) == 0:
                continue
            if b.width <= 2 or b.height <= 2:
                continue
            # Check for duplicates - but be more lenient to avoid removing valid blocks
            dup = False
            for k in kept:
                # Only remove if text is identical AND positions are very similar
                if k.text == b.text and _iou(k, b) > 0.9:
                    dup = True
                    break
                # Don't remove if one text is substring of another - might be valid
            if not dup:
                kept.append(b)
        cleaned.extend(kept)
    return cleaned

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
    """Extract text blocks using OCR with bounding boxes, preserving layout"""
    blocks = []
    
    try:
        # Convert PDF to images with higher DPI for better accuracy
        images = convert_from_path(pdf_path, dpi=400)
        
        for page_num, image in enumerate(images, 1):
            # Try multiple PSM modes for better results
            psm_modes = ['6', '3', '4']  # 6=uniform block, 3=auto, 4=single column
            best_blocks = []
            
            for psm in psm_modes:
                try:
                    # Get OCR data with bounding boxes
                    ocr_data = pytesseract.image_to_data(
                        image,
                        lang='ara',
                        output_type=pytesseract.Output.DICT,
                        config=f'--psm {psm} --oem 1'
                    )
                    
                    # Group words into blocks with better line detection
                    page_blocks = []
                    current_block_words = []
                    current_y = None
                    current_line_height = None
                    y_tolerance = 8  # Tighter tolerance for better line grouping
                    
                    for i in range(len(ocr_data['text'])):
                        text = ocr_data['text'][i].strip()
                        conf = int(ocr_data['conf'][i]) if ocr_data['conf'][i] else 0
                        
                        # Skip low confidence or empty text
                        if not text or conf < 30:
                            continue
                        
                        # Get word position (pytesseract uses top-left origin)
                        x = ocr_data['left'][i]
                        top = ocr_data['top'][i]
                        w = ocr_data['width'][i]
                        h = ocr_data['height'][i]
                        
                        # Convert to bottom-left origin (for consistency with PDF coordinates)
                        y = image.height - top - h
                        
                        # Check if this word is on the same line
                        if current_y is None:
                            current_block_words.append({
                                'text': text,
                                'x0': x,
                                'y0': y,
                                'x1': x + w,
                                'y1': y + h,
                                'conf': conf
                            })
                            current_y = y
                            current_line_height = h
                        elif abs(y - current_y) <= y_tolerance:
                            # Same line - add to current block
                            current_block_words.append({
                                'text': text,
                                'x0': x,
                                'y0': y,
                                'x1': x + w,
                                'y1': y + h,
                                'conf': conf
                            })
                            # Update average y position
                            current_y = sum(w['y0'] for w in current_block_words) / len(current_block_words)
                        else:
                            # New line - create block from current words
                            if current_block_words:
                                block = _create_block_from_ocr_words(
                                    current_block_words, page_num, image.width, image.height
                                )
                                if block:
                                    page_blocks.append(block)
                            
                            # Start new block
                            current_block_words = [{
                                'text': text,
                                'x0': x,
                                'y0': y,
                                'x1': x + w,
                                'y1': y + h,
                                'conf': conf
                            }]
                            current_y = y
                            current_line_height = h
                    
                    # Process last block
                    if current_block_words:
                        block = _create_block_from_ocr_words(
                            current_block_words, page_num, image.width, image.height
                        )
                        if block:
                            page_blocks.append(block)
                    
                    # Use the result with most blocks (likely most complete)
                    if len(page_blocks) > len(best_blocks):
                        best_blocks = page_blocks
                        
                except Exception as e:
                    print(f"OCR extraction with PSM {psm} failed: {e}")
                    continue
            
            blocks.extend(best_blocks)
                    
    except Exception as e:
        print(f"OCR extraction failed: {e}")
        import traceback
        traceback.print_exc()
    
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
    
    # Combine text with RTL awareness for Arabic
    import re
    arabic_re = re.compile(r'[\u0600-\u06FF]')
    has_arabic = any(arabic_re.search(str(w.get('text',''))) for w in words)
    if has_arabic:
        ordered = sorted(words, key=lambda w: w['x1'], reverse=True)
    else:
        ordered = sorted(words, key=lambda w: w['x0'])
    text = ' '.join(w['text'] for w in ordered)
    
    return TextBlock(text, x0, y0, x1, y1, page_num)

def normalize_arabic_numerals(text: str) -> str:
    """Convert Arabic-Indic numerals (٠-٩) to Western numerals (0-9)"""
    arabic_numerals = '٠١٢٣٤٥٦٧٨٩'
    western_numerals = '0123456789'
    
    translation_table = str.maketrans(arabic_numerals, western_numerals)
    return text.translate(translation_table)

