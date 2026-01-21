"""
Main service for PDF-to-PDF translation with layout preservation.
Orchestrates extraction, translation, and rendering.
"""
import tempfile
import os
import re
import shutil
from typing import Tuple, List, Optional
import pandas as pd
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

# Maryum Services Integration (Renamed to Tables Service)
try:
    from services.tables_service import (
        TableDetectionService, 
        PDFExtractionService, 
        TranslationService, 
        TranslatorModel,
        TableConfig
    )
    MARYUM_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Tables services not available: {e}")
    MARYUM_AVAILABLE = False
    TableDetectionService = None
    PDFExtractionService = None
    TranslationService = None
    TranslatorModel = None

import shutil
import os


# Try to import PyMuPDF for in-place editing
try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("Warning: PyMuPDF not available. In-place PDF editing will not work.")

# Try to import ocrmypdf for scanned PDF support
try:
    import ocrmypdf
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Warning: ocrmypdf not available. Scanned PDFs will not be processed correctly.")

def _ensure_searchable_pdf(pdf_path: str) -> str:
    """
    Check if PDF has text layer. If not (scanned), use OCR to add one.
    Returns path to searchable PDF (original or new temp file).
    """
    if not PYMUPDF_AVAILABLE:
        return pdf_path

    try:
        doc = fitz.open(pdf_path)
        has_text = False
        text_len = 0
        
        # Check first few pages
        for i in range(min(3, len(doc))):
            text = doc[i].get_text()
            if text.strip():
                text_len += len(text.strip())
        
        doc.close()
        
        # If substantial text found, verify if it's Arabic
        if text_len > 50:
             return pdf_path
             
        # If we are here, PDF is likely scanned or empty of text
        if not OCR_AVAILABLE:
            print("Warning: PDF seems scanned but ocrmypdf is not available.")
            return pdf_path
            
        print("PDF appears to be scanned/image-based. Running OCR...")
        
        # Create temp file for OCR'd PDF
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(temp_fd)
        
        try:
            ocrmypdf.ocr(
                pdf_path,
                temp_path,
                language='ara',
                force_ocr=True,
                progress_bar=False,
                deskew=True
            )
            print("OCR complete. Using searchable PDF version.")
            return temp_path
        except Exception as e:
            print(f"OCR failed: {e}")
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            return pdf_path

    except Exception as e:
        print(f"Error checking/OCRing PDF: {e}")
        return pdf_path

def translate_pdf_inplace(pdf_path: str, output_path: str) -> dict:
    """
    Translate PDF by replacing Arabic text in-place with English translations.
    Preserves exact layout, fonts, and formatting by working at block level.
    Now optimized with batch translation.
    """
    if not PYMUPDF_AVAILABLE:
        raise Exception("PyMuPDF is required for in-place PDF editing but is not available.")
    
    # Import the batch translation function locally to ensure it picks up the latest version
    from services.translate_service import translate_batch

    # Ensure we have a text layer to work with
    working_pdf_path = _ensure_searchable_pdf(pdf_path)
    is_temp_file = working_pdf_path != pdf_path

    print("=" * 60)
    print("Starting in-place PDF translation (Optimized Batch Processing)")
    print("=" * 60)

    # Open the PDF
    doc = fitz.open(working_pdf_path)
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    # Regex for pure numbers/symbols (dates, currency, percentages, simple integers)
    # Matches: 123, 1,234.56, $100, 50%, 12/12/2024, etc.
    numeric_pattern = re.compile(r'^[\d\s\.,\-%$€£/]+$') 
    
    stats = {
        'pages_processed': len(doc),
        'text_blocks_translated': 0,
        'tables_translated': 0,
        'full_translated_text': [],  # Accumulate English text here
        'full_original_text': [],    # Accumulate Arabic text here
        'segments': []               # Structured segments for JSON/Excel
    }

    # Path to our custom font
    font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "NotoSans-Regular.ttf")
    font_path_bold = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "NotoSans-Bold.ttf")
    
    has_custom_font = os.path.exists(font_path)
    has_custom_font_bold = os.path.exists(font_path_bold)
    
    if has_custom_font:
        print(f"Using custom font: {font_path}")
    if has_custom_font_bold:
        print(f"Using custom bold font: {font_path_bold}")

    # Initialize Maryum Services
    maryum_detector = None
    maryum_extractor = None
    maryum_translator = None
    
    if MARYUM_AVAILABLE:
        try:
            print("Initializing Maryum Table Services...")
            translator_model = TranslatorModel() # Singleton
            maryum_detector = TableDetectionService()
            maryum_extractor = PDFExtractionService()
            maryum_translator = TranslationService(translator_model)
            print("Maryum Services initialized successfully.")
        except Exception as e:
            print(f"Failed to init Maryum services: {e}")
            maryum_detector = None

    try:
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Register custom font for this page if available
            if has_custom_font:
                try:
                    page.insert_font(fontname="noto", fontfile=font_path)
                except Exception as fe:
                    print(f"Font registration warning: {fe}")
                    has_custom_font = False
            
            if has_custom_font_bold:
                try:
                    page.insert_font(fontname="noto-bold", fontfile=font_path_bold)
                except Exception as fe:
                    print(f"Bold Font registration warning: {fe}")
                    has_custom_font_bold = False
            print(f"\nProcessing page {page_num + 1}/{len(doc)}...")

            # --- COLLECTION PHASE ---
            # Collect all items needing translation
            
            translation_queue = [] # List of strings to translate
            # Map index of translation_queue back to the object
            # queue_map = [ { 'type': 'table_cell', 'obj': cell_ref }, ... ]
            queue_map = []
            
            # --- Table Detection Phase ---
            # Used to identify grids and process them cell-by-cell for alignment
            # Also creates an exclusion zone for standard text blocks
            table_exclusion_rects = []
            
            # Store table processing data to apply later
            # List of items:
            # { "type": "maryum_table", "df": orig_df, "layout": layout, "csv_path": path, "translated_df": placeholder_df }
            # { "type": "legacy_table", "cells": [ { "rect": rect, "text": text, "trans": "" } ] }
            pending_tables = []
            
            if maryum_detector and maryum_extractor and maryum_translator:
                # === MARYUM INTEGRATION PATH ===
                try:
                    # 1. Detect Tables
                    m_configs = maryum_detector.detect_tables_on_page(working_pdf_path, page_num)
                    
                    if m_configs:
                        # FILTER: Remove configs that are likely text paragraphs (high word density)
                        final_configs = []
                        for cfg in m_configs:
                            # 1. Check for single column
                            num_cols = len(cfg.columns) - 1
                            if num_cols < 2:
                                print(f"  Skipping Table candidate (cols={num_cols}): likely single column text.")
                                continue
                            
                            # 2. Check Text Density
                            cfg_rect = fitz.Rect(cfg.bbox.x0, cfg.bbox.y0, cfg.bbox.x1, cfg.bbox.y1)
                            region_text = page.get_text("text", clip=cfg_rect)
                            total_words = len(region_text.split())
                            approx_rows = max(1, cfg_rect.height / 20)
                            approx_cells = approx_rows * num_cols
                            density = total_words / approx_cells if approx_cells > 0 else 0
                            
                            if density > 12:
                                print(f"  Skipping Table candidate (density={density:.1f}): likely multi-column text.")
                                continue
                                
                            final_configs.append(cfg)

                        m_configs = final_configs
                        print(f"  Maryum found {len(m_configs)} tables on page {page_num+1}.")
                        
                        # 2. Extract & Translate
                        debug_dir = os.path.join(os.path.dirname(output_path), "debug_tables")
                        os.makedirs(debug_dir, exist_ok=True)
                        
                        # Use debug_dir
                        temp_dir = debug_dir
                            
                        # Extract returns list of (csv_path, layout)
                        extracted_data = maryum_extractor.extract_tables(
                            working_pdf_path, m_configs, temp_dir, f"p{page_num}"
                        )
                        
                        if extracted_data:
                            # Iterate extracted tables
                            for idx, (orig_csv, layout) in enumerate(extracted_data):
                                try:
                                    orig_df = pd.read_csv(orig_csv, header=None).fillna("")
                                    if orig_df.empty:
                                        continue

                                    if not layout or not layout[0]:
                                        continue
                                        
                                    # Calculate exclusion bbox
                                    min_x = min(cell.x0 for row in layout for cell in row)
                                    min_y = min(cell.y0 for row in layout for cell in row)
                                    max_x = max(cell.x1 for row in layout for cell in row)
                                    max_y = max(cell.y1 for row in layout for cell in row)
                                    table_exclusion_rects.append((min_x, min_y, max_x, max_y))
                                    
                                    # Prepare table structure for translation
                                    # We flatten the table into the queue
                                    table_item = {
                                        "type": "maryum_table",
                                        "orig_df": orig_df,
                                        "layout": layout,
                                        "rect": (min_x, min_y, max_x, max_y),
                                        "cells": [] # store (r, c) -> queue_idx
                                    }
                                    
                                    for r_idx, row in orig_df.iterrows():
                                        for c_idx, val in enumerate(row):
                                            val_str = str(val).strip()
                                            if not val_str:
                                                continue
                                            
                                            # Add to queue if not numeric
                                            normalized_text = normalize_arabic_numerals(val_str)
                                            if not numeric_pattern.match(normalized_text) and arabic_pattern.search(normalized_text):
                                                translation_queue.append(normalized_text)
                                                queue_map.append({
                                                    'type': 'maryum_cell',
                                                    'table_idx': len(pending_tables),
                                                    'r': r_idx,
                                                    'c': c_idx
                                                })
                                    
                                    pending_tables.append(table_item)

                                except Exception as e:
                                    print(f"Error preparing Maryum Table {idx}: {e}")
                            
                    else:
                        print(f"  No tables found by Maryum on page {page_num+1}")

                except Exception as e:
                    print(f"Maryum detection failed on page {page_num+1}: {e}")
                    pass

            else:
                # === FALLBACK / LEGACY PATH ===
                try:
                    tables = page.find_tables()
                    if tables:
                        print(f"  Found {len(tables)} tables (Legacy).")
                        for table in tables:
                            table_exclusion_rects.append(table.bbox)
                            
                            legacy_table_item = {
                                "type": "legacy_table",
                                "bbox": table.bbox,
                                "cells": [] # list of { rect, text, queue_idx }
                            }
                            
                            # Process cells
                            for row in table.rows:
                                for cell in row.cells:
                                    cell_text = page.get_text("text", clip=cell).strip()
                                    if not cell_text: continue
                                        
                                    normalized_text = normalize_arabic_numerals(cell_text)
                                    
                                    if arabic_pattern.search(normalized_text):
                                        if numeric_pattern.match(normalized_text):
                                            # Numeric, keep as is (no translation needed, but we might want to rewrite it?)
                                            # Currently we only rewrite if translating.
                                            pass
                                        else:
                                            # Add to queue
                                            translation_queue.append(normalized_text)
                                            queue_map.append({
                                                'type': 'legacy_cell',
                                                'table_idx': len(pending_tables),
                                                'cell_idx': len(legacy_table_item['cells'])
                                            })
                                            
                                            legacy_table_item['cells'].append({
                                                "rect": fitz.Rect(cell),
                                                "text": cell_text,
                                                "translated": None # Will be filled
                                            })
                            
                            pending_tables.append(legacy_table_item)

                except Exception as e:
                    print(f"  Table processing warning: {e}")

            # --- Text Block Phase ---
            text_dict = page.get_text("dict")
            text_blocks = []
            
            for block in text_dict["blocks"]:
                if "lines" not in block: continue
                
                # Check intersection with detected tables
                block_rect = fitz.Rect(block["bbox"])
                in_table = False
                for t_rect in table_exclusion_rects:
                    if fitz.Rect(t_rect).intersects(block_rect):
                        in_table = True
                        break
                
                if in_table: continue

                # Collect text parts
                block_text_parts = []
                block_spans = []
                min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
                
                for line in block["lines"]:
                    spans = line["spans"]
                    if not spans: continue
                    
                    line_text = " ".join([s.get("text", "") for s in spans])
                    is_arabic_line = bool(arabic_pattern.search(line_text))
                    
                    if is_arabic_line:
                        spans.sort(key=lambda s: s["bbox"][0], reverse=True)
                    else:
                        spans.sort(key=lambda s: s["bbox"][0])

                    for span in spans:
                        span_text = span.get("text", "").strip()
                        if span_text:
                            block_text_parts.append(span_text)
                            block_spans.append(span)
                        bbox = span["bbox"]
                        min_x = min(min_x, bbox[0])
                        min_y = min(min_y, bbox[1])
                        max_x = max(max_x, bbox[2])
                        max_y = max(max_y, bbox[3])
                
                if block_text_parts:
                    combined_text = " ".join(block_text_parts)
                    if arabic_pattern.search(combined_text):
                        font_sizes = [s.get("size", 12) for s in block_spans]
                        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12
                        
                        # Add to queue
                        translation_queue.append(normalize_arabic_numerals(combined_text))
                        queue_map.append({
                            'type': 'text_block',
                            'block_idx': len(text_blocks)
                        })
                        
                        text_blocks.append({
                            'text': combined_text,
                            'bbox': [min_x, min_y, max_x, max_y],
                            'font_size': avg_font_size,
                            'spans': block_spans,
                            'translated': None # Will be filled
                        })

            print(f"Found {len(text_blocks)} Arabic text blocks on page {page_num + 1}")
            
            # --- STRUCTURE ANALYSIS (Optional, for headings) ---
            if text_blocks:
                all_sizes = [b['font_size'] for b in text_blocks]
                if all_sizes:
                    page_avg_size = sum(all_sizes) / len(all_sizes)
                    for block in text_blocks:
                        size = block['font_size']
                        if size > page_avg_size * 1.15:
                            block['type'] = 'heading'
                        elif size < page_avg_size * 0.85:
                            block['type'] = 'small'
                        else:
                            block['type'] = 'body'

            # --- BATCH TRANSLATION ---
            print(f"  Translating {len(translation_queue)} items in batch...")
            translated_results = []
            if translation_queue:
                try:
                    translated_results = translate_batch(translation_queue, batch_size=8)
                except Exception as e:
                    print(f"  Batch translation failed: {e}")
                    # Fallback?
                    translated_results = [""] * len(translation_queue)

            # --- APPLICATION PHASE ---
            print(f"  Applying translations to page...")
            
            # 1. Distribute translations back to objects
            for idx, item in enumerate(queue_map):
                trans_text = translated_results[idx] if idx < len(translated_results) else ""
                
                if item['type'] == 'maryum_cell':
                    table = pending_tables[item['table_idx']]
                    # We store translations in a dict for easy lookup or just create a new DF later
                    if 'trans_map' not in table: table['trans_map'] = {}
                    table['trans_map'][(item['r'], item['c'])] = trans_text
                    
                elif item['type'] == 'legacy_cell':
                    table = pending_tables[item['table_idx']]
                    cell = table['cells'][item['cell_idx']]
                    cell['translated'] = trans_text
                    
                elif item['type'] == 'text_block':
                    block = text_blocks[item['block_idx']]
                    block['translated'] = trans_text

            # 2. Apply Tables (Maryum)
            for table in pending_tables:
                if table['type'] == 'maryum_table':
                    try:
                        orig_df = table['orig_df']
                        layout = table['layout']
                        trans_map = table.get('trans_map', {})
                        rect = table['rect']
                        
                        # Cover table area
                        mega_cover_rect = fitz.Rect(rect[0]-2, rect[1]-2, rect[2]+2, rect[3]+2)
                        shape = page.new_shape()
                        shape.draw_rect(mega_cover_rect)
                        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                        shape.commit()
                        
                        # Apply cells
                        for r_idx, row_layout in enumerate(layout):
                            for c_idx, cell_layout in enumerate(row_layout):
                                # Get translated text if available, else original (or skip if empty)
                                trans_text = trans_map.get((r_idx, c_idx), "")
                                orig_val = str(orig_df.iloc[r_idx, c_idx]).strip() if (r_idx < len(orig_df) and c_idx < len(orig_df.columns)) else ""
                                
                                if not trans_text and orig_val:
                                    # If original was numeric, use it
                                    norm = normalize_arabic_numerals(orig_val)
                                    if numeric_pattern.match(norm):
                                        trans_text = norm
                                
                                if not trans_text: continue

                                # Stats
                                stats['full_translated_text'].append(trans_text)
                                stats['full_original_text'].append(orig_val)
                                stats['segments'].append({
                                    "page": page_num + 1,
                                    "type": "table_cell",
                                    "original": orig_val,
                                    "translated": trans_text
                                })

                                # Insert
                                cell_rect = fitz.Rect(cell_layout.x0, cell_layout.y0, cell_layout.x1, cell_layout.y1)
                                current_fontsize = 8
                                font_to_use = "helv"
                                
                                # Simple LTR check
                                if numeric_pattern.match(trans_text) or re.match(r'^[A-Za-z0-9\s\.,\-%]+$', trans_text):
                                    tw = fitz.TextWriter(page.rect)
                                    text_start = fitz.Point(cell_rect.x0 + 2, cell_rect.y1 - 3) 
                                    tw.append(text_start, trans_text, fontsize=current_fontsize, font=fitz.Font(font_to_use))
                                    tw.write_text(page)
                                else:
                                    page.insert_textbox(cell_rect, trans_text, fontsize=current_fontsize, fontname=font_to_use, align=0)
                                    
                        stats['tables_translated'] += 1
                        
                    except Exception as e:
                        print(f"    Error applying Maryum table: {e}")

                elif table['type'] == 'legacy_table':
                    try:
                        for cell in table['cells']:
                            trans_text = cell.get('translated')
                            orig_text = cell.get('text')
                            
                            if not trans_text and orig_text:
                                norm = normalize_arabic_numerals(orig_text)
                                if numeric_pattern.match(norm):
                                    trans_text = norm
                            
                            if not trans_text: continue
                            
                            stats['full_translated_text'].append(trans_text)
                            stats['full_original_text'].append(orig_text)
                            
                            # Cover and Insert
                            cell_rect = cell['rect']
                            cover_rect = fitz.Rect(cell_rect[0]-1, cell_rect[1]-1, cell_rect[2]+1, cell_rect[3]+1)
                            shape = page.new_shape()
                            shape.draw_rect(cover_rect)
                            shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                            shape.commit()
                            
                            current_fontsize = 8
                            page.insert_textbox(cell_rect, trans_text, fontsize=current_fontsize, fontname="helv", align=0)
                            
                        stats['tables_translated'] += 1
                    except Exception as e:
                        print(f"    Error applying legacy table: {e}")

            # 3. Apply Text Blocks
            for text_block in text_blocks:
                trans_text = text_block.get('translated')
                orig_text = text_block['text']
                bbox = text_block['bbox']
                
                if not trans_text: continue
                
                # Check for Arabic in result
                if arabic_pattern.search(trans_text):
                    continue # Skip failed translation
                    
                stats['full_translated_text'].append(trans_text)
                stats['full_original_text'].append(orig_text)
                stats['segments'].append({
                    "page": page_num + 1,
                    "type": text_block.get('type', 'body'),
                    "original": orig_text,
                    "translated": trans_text
                })
                
                # Cover
                rect = fitz.Rect(bbox)
                cover_rect = fitz.Rect(bbox[0]-1, bbox[1]-1, bbox[2]+1, bbox[3]+1)
                shape = page.new_shape()
                shape.draw_rect(cover_rect)
                shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                shape.commit()
                
                # Insert
                try:
                    font_to_use = "helv"
                    if has_custom_font:
                         if text_block.get('type') == 'heading' and has_custom_font_bold:
                             font_to_use = "noto-bold"
                         else:
                             font_to_use = "noto"
                             
                    current_fontsize = text_block['font_size'] * 0.85
                    padding_x = 2
                    padding_y = 1
                    text_rect = fitz.Rect(rect.x0 + padding_x, rect.y0 + padding_y, rect.x1 - padding_x, rect.y1 - padding_y)
                    
                    remaining = page.insert_textbox(
                        text_rect,
                        trans_text,
                        fontsize=current_fontsize,
                        fontname=font_to_use,
                        align=0,
                        encoding=0
                    )
                    
                    if remaining < 0:
                         # Resize loop
                         min_fontsize = 5
                         while remaining < 0 and current_fontsize > min_fontsize:
                             current_fontsize -= 1.0
                             shape = page.new_shape()
                             shape.draw_rect(cover_rect)
                             shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                             shape.commit()
                             
                             remaining = page.insert_textbox(
                                text_rect,
                                trans_text,
                                fontsize=current_fontsize,
                                fontname=font_to_use,
                                align=0
                             )
                             
                    stats['text_blocks_translated'] += 1
                except Exception as e:
                    print(f"    Error inserting text block: {e}")

        # Save the modified PDF
        doc.save(output_path)
        doc.close()
        
        # Cleanup temp file if created
        if is_temp_file and os.path.exists(working_pdf_path):
            try:
                os.unlink(working_pdf_path)
            except:
                pass

        print("\n" + "=" * 60)
        print(f"In-place translation complete!")
        print(f"Output saved to: {output_path}")
        print("=" * 60)
        
        stats['full_text_content'] = "\n\n".join(stats['full_translated_text'])
        stats['full_original_content'] = "\n\n".join(stats['full_original_text'])
        
        del stats['full_translated_text']
        del stats['full_original_text']

        return stats
    except Exception as e:
        print(f"Refactored Translation Process Failed: {e}")
        raise

    except Exception as e:
        if 'doc' in locals():
            doc.close()
        raise Exception(f"In-place PDF translation failed: {str(e)}")


def translate_pdf_with_layout(pdf_path: str, output_path: str) -> dict:
    """
    Translate PDF from Arabic to English using in-place editing to preserve exact layout.
    
    This function replaces the old logic. It strictly enforces the in-place method.
    The old extraction/reconstruction method is REMOVED to prevent layout corruption.
    """
    print("=" * 60)
    print("STRICT MODE: Using In-Place Translation Only")
    print("Reconstruction/Re-rendering is disabled to preserve specific layout.")
    print("=" * 60)
    
    # Delegate solely to in-place translation
    return translate_pdf_inplace(pdf_path, output_path)

# Helper functions that might be unused now but kept if imported elsewhere
def normalize_arabic_numerals(text: str) -> str:
    # See layout_extraction_service for implementation
    from services.layout_extraction_service import normalize_arabic_numerals as norm
    return norm(text)

