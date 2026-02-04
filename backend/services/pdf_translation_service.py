"""
Main service for PDF-to-PDF translation with layout preservation.
Orchestrates extraction, translation, and rendering.
"""
import tempfile
import os
import re
import shutil
import time
import gc
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

# Try to import PyMuPDF
try:
    import fitz
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    print("Warning: PyMuPDF not available.")

# Try to import ocrmypdf
try:
    import ocrmypdf
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

def _ensure_searchable_pdf(pdf_path: str) -> str:
    if not PYMUPDF_AVAILABLE: return pdf_path
    try:
        doc = fitz.open(pdf_path)
        text_len = 0
        for i in range(min(3, len(doc))):
            text = doc[i].get_text()
            if text.strip(): text_len += len(text.strip())
        doc.close()
        if text_len > 50: return pdf_path
        if not OCR_AVAILABLE: return pdf_path
        print("Scanned PDF detected. Running OCR...")
        temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf'); os.close(temp_fd)
        try:
            ocrmypdf.ocr(pdf_path, temp_path, language='ara', force_ocr=True, progress_bar=False, deskew=True)
            return temp_path
        except:
            if os.path.exists(temp_path): os.unlink(temp_path)
            return pdf_path
    except: return pdf_path

def translate_pdf_inplace(pdf_path: str, output_path: str) -> dict:
    if not PYMUPDF_AVAILABLE: raise Exception("PyMuPDF required.")
    
    start_time = time.time()
    working_pdf_path = _ensure_searchable_pdf(pdf_path)
    is_temp_file = working_pdf_path != pdf_path

    print("=" * 60)
    print("Exact Replica PDF Translation (Fidelity Optimized)")
    print("=" * 60)

    doc = fitz.open(working_pdf_path)
    total_pages = len(doc)
    arabic_pattern = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    numeric_pattern = re.compile(r'^[\d\s\.,\-\+\*/%$€£¥₹\(\)\[\]]+$')
    
    stats = {
        'pages_processed': total_pages, 
        'text_blocks_translated': 0, 
        'tables_translated': 0,
        'full_translated_text': [], 
        'full_original_text': [], 
        'segments': []  # Structured data for Excel/JSON
    }

    font_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
    font_path = os.path.join(font_dir, "NotoSans-Regular.ttf")
    font_path_bold = os.path.join(font_dir, "NotoSans-Bold.ttf")
    has_custom_font = os.path.exists(font_path)
    has_custom_font_bold = os.path.exists(font_path_bold)

    maryum_available = False
    if MARYUM_AVAILABLE:
        try:
            from services.tables_service import TableDetectionService, PDFExtractionService
            maryum_detector = TableDetectionService()
            maryum_extractor = PDFExtractionService()
            maryum_available = True
        except: pass

    # --- PHASE 1: UNIVERSAL COLLECTION ---
    print(f"\n[Phase 1] Collecting ALL text segments from {total_pages} pages...")
    global_queue = []
    pages_ops = {}
    
    for page_num in range(total_pages):
        page = doc[page_num]
        print(f"  Scanning page {page_num + 1}/{total_pages}...", end='\r')
        ops = {'tables': [], 'text_blocks': []}
        table_exclusion = []
        
        if maryum_available:
            try:
                m_configs = maryum_detector.detect_tables_on_page(working_pdf_path, page_num)
                if m_configs:
                    extracted = maryum_extractor.extract_tables(working_pdf_path, m_configs, None, f"p{page_num}")
                    if extracted:
                        for orig_csv, layout in extracted:
                            try:
                                df = pd.read_csv(orig_csv, header=None).fillna("")
                                if df.empty or not layout: continue
                                bbox = (min(c.x0 for r in layout for c in r), min(c.y0 for r in layout for c in r),
                                        max(c.x1 for r in layout for c in r), max(c.y1 for r in layout for c in r))
                                table_exclusion.append(bbox)
                                t_item = {"type": "maryum_table", "df_json": df.to_json(), "layout": layout, "rect": bbox, "indices": {}}
                                for r_idx, row in df.iterrows():
                                    for c_idx, val in enumerate(row):
                                        val_s = str(val).strip()
                                        if val_s:
                                            # Always collect for table cells to ensure full Excel
                                            t_item['indices'][f"{r_idx},{c_idx}"] = len(global_queue)
                                            global_queue.append(normalize_arabic_numerals(val_s))
                                ops['tables'].append(t_item)
                            except: pass
            except: pass
        
        if not ops['tables']:
            try:
                for table in page.find_tables():
                    table_exclusion.append(tuple(table.bbox))
                    lt = {"type": "legacy", "bbox": tuple(table.bbox), "cells": []}
                    for row in table.rows:
                        for cell in row.cells:
                            txt = page.get_text("text", clip=cell).strip()
                            c_data = {"rect": tuple(cell), "text": txt, "idx": None}
                            if txt:
                                c_data["idx"] = len(global_queue)
                                global_queue.append(normalize_arabic_numerals(txt))
                            lt["cells"].append(c_data)
                    ops['tables'].append(lt)
            except: pass

        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block: continue
            if any(fitz.Rect(tr).intersects(fitz.Rect(block["bbox"])) for tr in table_exclusion): continue
            
            for line in block["lines"]:
                line_text = " ".join(s["text"].strip() for s in line["spans"] if s["text"].strip())
                if not line_text: continue
                
                is_bold = any(s.get("flags", 0) & 16 for s in line["spans"])
                max_size = max(s.get("size", 10) for s in line["spans"])
                
                l_item = {
                    'text': line_text, 
                    'bbox': line["bbox"], 
                    'size': max_size, 
                    'is_bold': is_bold,
                    'idx': len(global_queue),
                    'type': 'heading' if is_bold or max_size > 14 else 'body'
                }
                global_queue.append(normalize_arabic_numerals(line_text))
                ops['text_blocks'].append(l_item)
        pages_ops[page_num] = ops

    # --- PHASE 2: BATCH TRANSLATION ---
    unique = sorted(list(set(global_queue)))
    t_map = dict(zip(unique, translate_batch(unique, batch_size=32))) if unique else {}
    results = [t_map.get(t, t) for t in global_queue]

    # --- PHASE 3: RENDERING ---
    print(f"\n[Phase 3] Applying Precision Redactions and Standard Font Rendering...")
    try:
        for page_num in range(total_pages):
            page = doc[page_num]
            ops = pages_ops.get(page_num, {'tables': [], 'text_blocks': []})
            
            # 1. Redact all segments
            redact_count = 0
            for b in ops['text_blocks']:
                page.add_redact_annot(fitz.Rect(b['bbox']), fill=(1,1,1))
                redact_count += 1
            for t in ops['tables']:
                t_bbox = t.get('rect') or t.get('bbox')
                if t_bbox:
                    page.add_redact_annot(fitz.Rect(t_bbox), fill=(1,1,1))
                    redact_count += 1
            
            # Security sweep for any remaining Arabic artifacts
            for b in page.get_text("dict")["blocks"]:
                if b.get("type") != 0: continue
                for l in b.get("lines", []):
                    for s in l.get("spans", []):
                        if arabic_pattern.search(s["text"]):
                            page.add_redact_annot(fitz.Rect(s["bbox"]), fill=(1,1,1))
                            redact_count += 1
            
            page.apply_redactions()
            
            # 2. Render with Standard Fonts (guarantees visibility)
            f_regular = "helv"
            f_bold = "hebo" # Helvetica-Bold in PyMuPDF

            # Tables
            for t in ops['tables']:
                if t['type'] == 'maryum_table':
                    df = pd.read_json(t['df_json'])
                    for r_idx, row in df.iterrows():
                        for c_idx, val in enumerate(row):
                            q_idx = t['indices'].get(f"{r_idx},{c_idx}")
                            if q_idx is None: continue
                            txt = results[q_idx]
                            if not txt or arabic_pattern.search(txt):
                                txt = re.sub(arabic_pattern, '', txt or "").strip() or normalize_arabic_numerals(str(val))
                            layout = t['layout'][r_idx][c_idx]
                            page.insert_textbox(fitz.Rect(layout.x0, layout.y0, layout.x1, layout.y1), txt, fontsize=8, fontname=f_regular)
                            stats['segments'].append({'page': page_num+1, 'type': 'table_cell', 'original': str(val), 'translated': txt})
                            stats['full_translated_text'].append(txt)
                            stats['full_original_text'].append(str(val))
                else:
                    for c in t['cells']:
                        if c['idx'] is None: continue
                        txt = results[c['idx']]
                        if not txt or arabic_pattern.search(txt):
                            txt = re.sub(arabic_pattern, '', txt or "").strip() or normalize_arabic_numerals(c['text'])
                        page.insert_textbox(fitz.Rect(c['rect']), txt, fontsize=8, fontname=f_regular)
                        stats['segments'].append({'page': page_num+1, 'type': 'legacy_table_cell', 'original': c['text'], 'translated': txt})
                        stats['full_translated_text'].append(txt)
                        stats['full_original_text'].append(c['text'])

            # Blocks
            for b in ops['text_blocks']:
                txt = results[b['idx']]
                orig_txt = b['text']
                if not txt or arabic_pattern.search(txt):
                    txt = re.sub(arabic_pattern, '', txt or "").strip() or normalize_arabic_numerals(orig_txt)
                
                # Fidelity Fix: Slightly smaller font + larger box to ensure visibility
                f_size = b['size'] * 0.8
                rect = fitz.Rect(b['bbox'])
                rect.y1 += (rect.y1 - rect.y0) * 0.3 # Allow more height for wrapping
                rect.x1 += 5 # Slight width buffer
                
                font = f_bold if b['is_bold'] or b['type'] == 'heading' else f_regular
                page.insert_textbox(rect, txt, fontsize=f_size, fontname=font, align=fitz.TEXT_ALIGN_LEFT)
                
                stats['full_translated_text'].append(txt)
                stats['full_original_text'].append(orig_txt)
                stats['text_blocks_translated'] += 1
                stats['segments'].append({'page': page_num+1, 'type': b['type'], 'original': orig_txt, 'translated': txt})

            if page_num % 20 == 0: gc.collect()

        doc.save(output_path, garbage=3, deflate=True)
        doc.close()
        if is_temp_file and os.path.exists(working_pdf_path): os.unlink(working_pdf_path)
        stats['full_text_content'] = "\n\n".join(stats['full_translated_text'])
        stats['full_original_content'] = "\n\n".join(stats['full_original_text'])
        del stats['full_translated_text'], stats['full_original_text']
        return stats
    except Exception as e:
        if 'doc' in locals(): doc.close()
        raise Exception(f"Failed: {e}")

def translate_pdf_with_layout(pdf_path, output_path): return translate_pdf_inplace(pdf_path, output_path)
