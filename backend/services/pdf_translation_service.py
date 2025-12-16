"""
Main service for PDF-to-PDF translation with layout preservation.
Orchestrates extraction, translation, and rendering.
"""
import tempfile
import os
from typing import Tuple
from services.layout_extraction_service import (
    extract_text_blocks_with_layout,
    TextBlock,
    normalize_arabic_numerals
)
from services.table_extraction_service import (
    extract_tables_from_pdf,
    extract_tables_from_ocr,
    Table
)
from services.translate_service import translate_to_english
from services.pdf_renderer_service import render_translated_pdf
import re

def translate_pdf_with_layout(pdf_path: str, output_path: str) -> dict:
    """
    Translate PDF from Arabic to English while preserving layout.
    
    Returns:
        dict with statistics about the translation
    """
    stats = {
        'pages_processed': 0,
        'text_blocks_translated': 0,
        'tables_translated': 0,
        'total_characters': 0
    }
    
    try:
        # Step 1: Extract text blocks with layout
        print("Extracting text blocks with layout...")
        text_blocks = extract_text_blocks_with_layout(pdf_path)
        stats['text_blocks_translated'] = len(text_blocks)
        stats['total_characters'] = sum(len(block.text) for block in text_blocks)
        
        # Step 2: Extract tables
        print("Extracting tables...")
        tables = extract_tables_from_pdf(pdf_path)
        
        # If no tables found with Camelot/pdfplumber, try OCR-based detection
        if not tables:
            print("Trying OCR-based table detection...")
            ocr_tables = extract_tables_from_ocr(text_blocks)
            tables = ocr_tables
        
        stats['tables_translated'] = len(tables)
        
        # Step 3: Translate text blocks
        print("Translating text blocks...")
        translated_blocks = []
        for block in text_blocks:
            if block.is_table:
                # Skip table blocks, they'll be handled separately
                continue
            
            # Normalize Arabic numerals
            normalized_text = normalize_arabic_numerals(block.text)
            
            # Translate
            translated_text = translate_to_english(normalized_text)
            
            # Create translated block
            translated_block = TextBlock(
                translated_text,
                block.x0, block.y0, block.x1, block.y1,
                block.page_num,
                is_table=False
            )
            translated_blocks.append(translated_block)
        
        # Step 4: Translate tables
        print("Translating tables...")
        translated_tables = []
        for table in tables:
            translated_cells = []
            for cell in table.cells:
                # Normalize numerals
                normalized_text = normalize_arabic_numerals(cell.text)
                
                # Translate
                translated_text = translate_to_english(normalized_text)
                
                # Create translated cell
                from services.table_extraction_service import TableCell
                translated_cell = TableCell(
                    translated_text,
                    cell.row, cell.col,
                    cell.x0, cell.y0, cell.x1, cell.y1,
                    cell.page_num
                )
                translated_cells.append(translated_cell)
            
            # Create translated table
            translated_table = Table(translated_cells, table.page_num)
            translated_tables.append(translated_table)
        
        # Step 5: Render translated PDF
        print("Rendering translated PDF...")
        render_translated_pdf(
            translated_blocks,
            translated_tables,
            output_path,
            original_pdf_path=pdf_path
        )
        
        # Calculate pages processed
        all_pages = set(block.page_num for block in translated_blocks)
        all_pages.update(table.page_num for table in translated_tables)
        stats['pages_processed'] = len(all_pages) if all_pages else 1
        
        print(f"Translation complete: {stats['pages_processed']} pages, "
              f"{stats['text_blocks_translated']} blocks, "
              f"{stats['tables_translated']} tables")
        
        return stats
        
    except Exception as e:
        raise Exception(f"PDF translation failed: {str(e)}")

def is_number(text: str) -> bool:
    """Check if text is a number (to avoid translating numbers)"""
    # Remove common number formatting
    cleaned = text.replace(',', '').replace('.', '').replace(' ', '').replace('-', '')
    try:
        float(cleaned)
        return True
    except:
        return False

