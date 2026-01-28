"""
Main service for PDF-to-PDF translation with layout preservation.
Orchestrates extraction, translation, and rendering.
"""
import tempfile
import os
import re
import shutil
from typing import Tuple, List, Optional, Dict, Any
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
from services.translate_service import translate_batch
import time

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
    Now optimized with GLOBAL BATCH PROCESSING and DEDUPLICATION.
    """
    if not PYMUPDF_AVAILABLE:
        raise Exception("PyMuPDF is required for in-place PDF editing but is not available.")
    
    start_time = time.time()
    
    # Ensure we have a text layer to work with
    working_pdf_path = _ensure_searchable_pdf(pdf_path)
    is_temp_file = working_pdf_path != pdf_path

    print("=" * 60)
    print("Starting Global Optimized PDF Translation")
    print("=" * 60)

    # Open the PDF
    doc = fitz.open(working_pdf_path)
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')

    # Regex for pure numbers/symbols (dates, currency, percentages, simple integers)
    # Matches: 123, 1,234.56, $100, 50%, 12/12/2024, (123), etc.
    # Also include Extended Arabic-Indic digits \u06F0-\u06F9
    numeric_pattern = re.compile(r'^[\d\s\.,\-%$€£/\(\)\[\]\u0660-\u0669\u06F0-\u06F9]+$') 
    
    stats = {
        'pages_processed': len(doc),
        'text_blocks_translated': 0,
        'tables_translated': 0,
        'full_translated_text': [], 
        'full_original_text': [],
        'segments': []
    }

    # Font handling
    font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "NotoSans-Regular.ttf")
    font_path_bold = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts", "NotoSans-Bold.ttf")
    has_custom_font = os.path.exists(font_path)
    has_custom_font_bold = os.path.exists(font_path_bold)

    # Initialize Maryum Services
    maryum_detector = None
    maryum_extractor = None
    
    if MARYUM_AVAILABLE:
        try:
            print("Initializing Maryum Table Services...")
            maryum_detector = TableDetectionService()
            maryum_extractor = PDFExtractionService()
            print("Maryum Services initialized.")
        except Exception as e:
            print(f"Failed to init Maryum services: {e}")
            maryum_detector = None

    # =========================================================================
    # PHASE 1: COLLECTION (Global)
    # Iterate all pages and collect text to be translated.
    # =========================================================================
    print(f"\n[Phase 1] Collecting text from {len(doc)} pages...")
    
    global_translation_queue = []  # List of all strings to translate
    
    # Store page-specific operations to apply later
    # pages_ops[page_num] = { 'tables': [], 'text_blocks': [] }
    pages_ops = {} 
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"  Scanning page {page_num + 1}/{len(doc)}...", end='\r')
        
        page_ops = {
            'tables': [],      # List of table objects
            'text_blocks': [], # List of text block objects
            'queue_map': []    # Map index in global_queue to object in this page
        }
        
        # Register fonts once per page (needed for later application)
        # We can do this in phase 3, but fitz might need clean state
        # Actually it's better to do font insertion in Phase 3 when modifying.
        
        # --- Table Detection ---
        table_exclusion_rects = []
        
        if maryum_detector and maryum_extractor:
            try:
                m_configs = maryum_detector.detect_tables_on_page(working_pdf_path, page_num)
                if m_configs:
                    # Filter logic
                    final_configs = []
                    for cfg in m_configs:
                        num_cols = len(cfg.columns) - 1
                        if num_cols < 2: continue
                        
                        cfg_rect = fitz.Rect(cfg.bbox.x0, cfg.bbox.y0, cfg.bbox.x1, cfg.bbox.y1)
                        region_text = page.get_text("text", clip=cfg_rect)
                        total_words = len(region_text.split())
                        approx_rows = max(1, cfg_rect.height / 20)
                        approx_cells = approx_rows * num_cols
                        density = total_words / approx_cells if approx_cells > 0 else 0
                        
                        if density > 12: continue
                        final_configs.append(cfg)

                    m_configs = final_configs
                    
                    if m_configs:
                        debug_dir = os.path.join(os.path.dirname(output_path), "debug_tables")
                        os.makedirs(debug_dir, exist_ok=True)
                        
                        extracted_data = maryum_extractor.extract_tables(
                            working_pdf_path, m_configs, debug_dir, f"p{page_num}"
                        )
                        
                        if extracted_data:
                            for idx, (orig_csv, layout) in enumerate(extracted_data):
                                try:
                                    orig_df = pd.read_csv(orig_csv, header=None).fillna("")
                                    if orig_df.empty or not layout or not layout[0]: continue
                                        
                                    # Exclusion
                                    min_x = min(cell.x0 for row in layout for cell in row)
                                    min_y = min(cell.y0 for row in layout for cell in row)
                                    max_x = max(cell.x1 for row in layout for cell in row)
                                    max_y = max(cell.y1 for row in layout for cell in row)
                                    table_exclusion_rects.append((min_x, min_y, max_x, max_y))
                                    
                                    table_item = {
                                        "type": "maryum_table",
                                        "orig_df": orig_df,
                                        "layout": layout,
                                        "rect": (min_x, min_y, max_x, max_y),
                                        "trans_map_indices": {} # (r,c) -> global_queue_index
                                    }
                                    
                                    for r_idx, row in orig_df.iterrows():
                                        for c_idx, val in enumerate(row):
                                            val_str = str(val).strip()
                                            if not val_str: continue
                                            
                                            normalized_text = normalize_arabic_numerals(val_str)
                                            if not numeric_pattern.match(normalized_text) and arabic_pattern.search(normalized_text):
                                                # Add to global queue
                                                global_queue_idx = len(global_translation_queue)
                                                global_translation_queue.append(normalized_text)
                                                table_item['trans_map_indices'][(r_idx, c_idx)] = global_queue_idx
                                    
                                    page_ops['tables'].append(table_item)

                                except Exception as e:
                                    pass
            except Exception:
                pass
        
        # Legacy Tables Fallback not implemented for simplicity/speed if Maryum works, 
        # checking legacy logic...
        # If no Maryum tables found, we could try legacy. 
        # For optimization, let's assume Maryum is primary. If needed, we can re-add legacy logic here.
        # But to match previous logic, let's add legacy detection only if NO tables found?
        # Previous code: if maryum... else legacy.
        
        if not page_ops['tables']:
            # Fallback legacy
            try:
                tables = page.find_tables()
                if tables:
                    for table in tables:
                        table_exclusion_rects.append(table.bbox)
                        legacy_table_item = {
                            "type": "legacy_table",
                            "bbox": table.bbox,
                            "cells": [] 
                        }
                        for row in table.rows:
                            for cell in row.cells:
                                cell_text = page.get_text("text", clip=cell).strip()
                                if not cell_text: continue
                                normalized_text = normalize_arabic_numerals(cell_text)
                                
                                cell_data = {"rect": fitz.Rect(cell), "text": cell_text, "queue_idx": None}
                                
                                if arabic_pattern.search(normalized_text) and not numeric_pattern.match(normalized_text):
                                    cell_data["queue_idx"] = len(global_translation_queue)
                                    global_translation_queue.append(normalized_text)
                                    
                                legacy_table_item["cells"].append(cell_data)
                        
                        page_ops['tables'].append(legacy_table_item)
            except:
                pass

        # --- Text Blocks ---
        text_dict = page.get_text("dict")
        
        for block in text_dict["blocks"]:
            if "lines" not in block: continue
            
            # Intersection check
            block_rect = fitz.Rect(block["bbox"])
            in_table = False
            for t_rect in table_exclusion_rects:
                if fitz.Rect(t_rect).intersects(block_rect):
                    in_table = True
                    break
            if in_table: continue

            # Extract text
            block_text_parts = []
            block_spans = []
            min_x, min_y, max_x, max_y = float('inf'), float('inf'), float('-inf'), float('-inf')
            
            for line in block["lines"]:
                spans = line["spans"]
                if not spans: continue
                line_text = " ".join([s.get("text", "") for s in spans])
                
                # Sort spans
                if arabic_pattern.search(line_text):
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
                    
                    queue_idx = len(global_translation_queue)
                    global_translation_queue.append(normalize_arabic_numerals(combined_text))
                    
                    page_ops['text_blocks'].append({
                        'text': combined_text,
                        'bbox': [min_x, min_y, max_x, max_y],
                        'font_size': avg_font_size,
                        'queue_idx': queue_idx
                    })
        
        # Font size classification for this page
        if page_ops['text_blocks']:
            all_sizes = [b['font_size'] for b in page_ops['text_blocks']]
            if all_sizes:
                page_avg_size = sum(all_sizes) / len(all_sizes)
                for block in page_ops['text_blocks']:
                    size = block['font_size']
                    if size > page_avg_size * 1.15: block['type'] = 'heading'
                    elif size < page_avg_size * 0.85: block['type'] = 'small'
                    else: block['type'] = 'body'
                        
        pages_ops[page_num] = page_ops

    print(f"\nCollection complete. Found {len(global_translation_queue)} items to translate.")

    # =========================================================================
    # PHASE 2: BATCH TRANSLATION & DEDUPLICATION
    # =========================================================================
    
    # deduplicate
    unique_texts = sorted(list(set(global_translation_queue)))
    print(f"Unique items: {len(unique_texts)} (Reduction: {100 - (len(unique_texts)/len(global_translation_queue)*100 if global_translation_queue else 0):.1f}%)")
    
    # Map text -> translation
    translation_map = {}
    
    if unique_texts:
        print(f"Starting batch translation of {len(unique_texts)} items...")
        
        # Translate in large batches
        batch_results = translate_batch(unique_texts, batch_size=32) 
        
        for orig, trans in zip(unique_texts, batch_results):
            translation_map[orig] = trans
            
    # Resolve global queue to translated strings
    # global_translated_results[i] corresponds to global_translation_queue[i]
    global_translated_results = [translation_map.get(txt, "") for txt in global_translation_queue]

    # =========================================================================
    # PHASE 3: APPLICATION
    # =========================================================================
    print(f"\n[Phase 3] Applying translations to pages...")
    
    try:
        for page_num in sorted(pages_ops.keys()):
            page = doc[page_num]
            ops = pages_ops[page_num]
            
            # Register fonts
            if has_custom_font:
                try: page.insert_font(fontname="noto", fontfile=font_path)
                except: pass
            if has_custom_font_bold:
                try: page.insert_font(fontname="noto-bold", fontfile=font_path_bold)
                except: pass
                
            # Apply Tables
            for table in ops['tables']:
                if table['type'] == 'maryum_table':
                    try:
                        orig_df = table['orig_df']
                        layout = table['layout']
                        trans_map_indices = table['trans_map_indices']
                        rect = table['rect']
                        
                        # Cover
                        mega_cover_rect = fitz.Rect(rect[0]-2, rect[1]-2, rect[2]+2, rect[3]+2)
                        shape = page.new_shape()
                        shape.draw_rect(mega_cover_rect)
                        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                        shape.commit()
                        
                        for r_idx, row_layout in enumerate(layout):
                            for c_idx, cell_layout in enumerate(row_layout):
                                q_idx = trans_map_indices.get((r_idx, c_idx))
                                trans_text = global_translated_results[q_idx] if q_idx is not None else ""
                                
                                orig_val = str(orig_df.iloc[r_idx, c_idx]).strip() if (r_idx < len(orig_df) and c_idx < len(orig_df.columns)) else ""
                                
                                if not trans_text and orig_val:
                                    norm = normalize_arabic_numerals(orig_val)
                                    if numeric_pattern.match(norm): trans_text = norm
                                
                                if not trans_text: continue
                                
                                stats['full_translated_text'].append(trans_text)
                                stats['full_original_text'].append(orig_val)
                                stats['segments'].append({
                                    "page": page_num + 1,
                                    "type": "table_cell",
                                    "original": orig_val,
                                    "translated": trans_text
                                })
                                
                                cell_rect = fitz.Rect(cell_layout.x0, cell_layout.y0, cell_layout.x1, cell_layout.y1)
                                current_fontsize = 8
                                font_to_use = "helv"
                                
                                # LTR check (simple)
                                if numeric_pattern.match(trans_text) or re.match(r'^[A-Za-z0-9\s\.,\-%]+$', trans_text):
                                    tw = fitz.TextWriter(page.rect)
                                    text_start = fitz.Point(cell_rect.x0 + 2, cell_rect.y1 - 3) 
                                    tw.append(text_start, trans_text, fontsize=current_fontsize, font=fitz.Font(font_to_use))
                                    tw.write_text(page)
                                else:
                                    page.insert_textbox(cell_rect, trans_text, fontsize=current_fontsize, fontname=font_to_use, align=0)
                        stats['tables_translated'] += 1
                    except Exception as e:
                        print(f"Error applying table on p{page_num}: {e}")

                elif table['type'] == 'legacy_table':
                    # Similar logic for legacy
                    for cell in table['cells']:
                        q_idx = cell.get('queue_idx')
                        trans_text = global_translated_results[q_idx] if q_idx is not None else ""
                        orig_text = cell['text']
                        
                        if not trans_text and orig_text:
                            norm = normalize_arabic_numerals(orig_text)
                            if numeric_pattern.match(norm): trans_text = norm
                            
                        if not trans_text: continue
                        
                        stats['full_translated_text'].append(trans_text)
                        stats['full_original_text'].append(orig_text)
                        
                        cell_rect = cell['rect']
                        shape = page.new_shape()
                        shape.draw_rect(fitz.Rect(cell_rect[0]-1, cell_rect[1]-1, cell_rect[2]+1, cell_rect[3]+1))
                        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                        shape.commit()
                        
                        page.insert_textbox(cell_rect, trans_text, fontsize=8, fontname="helv", align=0)
                    stats['tables_translated'] += 1

            # Apply Text Blocks
            for block in ops['text_blocks']:
                q_idx = block['queue_idx']
                trans_text = global_translated_results[q_idx] if q_idx is not None else ""
                orig_text = block['text']
                bbox = block['bbox']
                
                if not trans_text: continue
                if arabic_pattern.search(trans_text): continue # Failed translation

                stats['full_translated_text'].append(trans_text)
                stats['full_original_text'].append(orig_text)
                stats['segments'].append({
                    "page": page_num + 1,
                    "type": block.get('type', 'body'),
                    "original": orig_text,
                    "translated": trans_text
                })
                
                # Cover
                rect = fitz.Rect(bbox)
                shape = page.new_shape()
                shape.draw_rect(fitz.Rect(bbox[0]-1, bbox[1]-1, bbox[2]+1, bbox[3]+1))
                shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                shape.commit()
                
                # Insert
                font_to_use = "helv"
                if has_custom_font:
                    if block.get('type') == 'heading' and has_custom_font_bold:
                        font_to_use = "noto-bold"
                    else:
                        font_to_use = "noto"
                
                current_fontsize = block['font_size'] * 0.85
                text_rect = fitz.Rect(rect.x0 + 2, rect.y0 + 1, rect.x1 - 2, rect.y1 - 1)
                
                remaining = page.insert_textbox(
                    text_rect, trans_text, fontsize=current_fontsize, fontname=font_to_use, align=0
                )
                
                if remaining < 0:
                    min_fontsize = 5
                    while remaining < 0 and current_fontsize > min_fontsize:
                        current_fontsize -= 1.0
                        shape = page.new_shape()
                        shape.draw_rect(fitz.Rect(bbox[0]-1, bbox[1]-1, bbox[2]+1, bbox[3]+1))
                        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                        shape.commit()
                        remaining = page.insert_textbox(
                            text_rect, trans_text, fontsize=current_fontsize, fontname=font_to_use, align=0
                        )
                stats['text_blocks_translated'] += 1

        doc.save(output_path)
        doc.close()
        
        if is_temp_file and os.path.exists(working_pdf_path):
             try: os.unlink(working_pdf_path)
             except: pass

        total_time = time.time() - start_time
        print("\n" + "=" * 60)
        print(f"Global Translation Complete in {total_time:.2f}s")
        print(f"Output saved to: {output_path}")
        print("=" * 60)
        
        stats['full_text_content'] = "\n\n".join(stats['full_translated_text'])
        stats['full_original_content'] = "\n\n".join(stats['full_original_text'])
        del stats['full_translated_text']
        del stats['full_original_text']
        
        return stats

    except Exception as e:
        if 'doc' in locals(): doc.close()
        raise Exception(f"In-place PDF translation failed: {str(e)}")

def translate_pdf_with_layout(pdf_path: str, output_path: str) -> dict:
    """
    Translate PDF from Arabic to English using in-place editing.
    """
    return translate_pdf_inplace(pdf_path, output_path)

# Unused helper but kept for compatibility
def normalize_arabic_numerals(text: str) -> str:
    from services.layout_extraction_service import normalize_arabic_numerals as norm
    return norm(text)
