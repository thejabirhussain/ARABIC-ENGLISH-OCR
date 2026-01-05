"""
Main service for PDF-to-PDF translation with layout preservation.
Orchestrates extraction, translation, and rendering.
"""
import tempfile
import os
import re
import shutil
from typing import Tuple, List, Optional
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
    """
    if not PYMUPDF_AVAILABLE:
        raise Exception("PyMuPDF is required for in-place PDF editing but is not available.")

    # Ensure we have a text layer to work with
    working_pdf_path = _ensure_searchable_pdf(pdf_path)
    is_temp_file = working_pdf_path != pdf_path

    print("=" * 60)
    print("Starting in-place PDF translation (block-level processing)")
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
        'full_translated_text': []  # Accumulate text here
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

            # --- Table Detection Phase ---
            # Used to identify grids and process them cell-by-cell for alignment
            # Also creates an exclusion zone for standard text blocks
            table_exclusion_rects = []
            
            if maryum_detector and maryum_extractor and maryum_translator:
                # === MARYUM INTEGRATION PATH ===
                try:

                    # 1. Detect Tables
                    m_configs = maryum_detector.detect_tables_on_page(working_pdf_path, page_num)
                    
                    if m_configs:
                        print(f"  Maryum found {len(m_configs)} tables on page {page_num+1}.")
                        
                        # 2. Extract & Translate
                        # Using temp dir for intermediate processing
                        with tempfile.TemporaryDirectory() as temp_dir:
                            # Extract returns list of (csv_path, layout)
                            extracted_data = maryum_extractor.extract_tables(
                                working_pdf_path, m_configs, temp_dir, f"p{page_num}"
                            )
                            
                            # Start with empty exclusion (only exclude if we actually replace)
                            processed_configs_indices = set()
                            
                            if extracted_data:
                                csv_paths = [x[0] for x in extracted_data]
                                translated_paths = maryum_translator.translate_tables(csv_paths, temp_dir)
                                
                                # 3. Re-insert
                                for idx, ((orig_csv, layout), trans_csv) in enumerate(zip(extracted_data, translated_paths)):
                                    try:
                                        # Load translated CSV
                                        # Use standard pandas read
                                        df = pd.read_csv(trans_csv, header=None)
                                        
                                        # Use simplistic check - if dataframe is empty, likely no translation
                                        if df.empty:
                                            continue

                                        # Mark this table as processed/excluded from text phase
                                        # We only exclude if we successfully processed it
                                        
                                        # Map back to config? Maryum extract loops configs in order.
                                        # extracted_data corresponds to indices of m_configs (if all extracted)
                                        # PDFExtractionService strictly iterates configs and appends result if successful.
                                        # So this corresponds to m_configs.
                                        # But wait, PDFExtractionService logic:
                                        # for idx, config in enumerate(table_configs): ... if table_rows: results.append(...)
                                        # So extracted_data size <= m_configs size.
                                        # This index 'idx' in extracted_data does NOT match m_configs index directly if some failed.
                                        # This is tricky. We need the bbox to exclude.
                                        
                                        # Let's fix PDFExtractionService to return bbox or config index?
                                        # Or we can deduce bbox from layout? 
                                        # Layout is List[List[CellLayout]]. Each CellLayout has bbox.
                                        # We can compute the union bbox of all cells in layout.
                                        
                                        if not layout or not layout[0]:
                                            continue
                                            
                                        # Calculate bounding box of the processed table from layout
                                        min_x = min(cell.x0 for row in layout for cell in row)
                                        min_y = min(cell.y0 for row in layout for cell in row)
                                        max_x = max(cell.x1 for row in layout for cell in row)
                                        max_y = max(cell.y1 for row in layout for cell in row)
                                        
                                        # Add to exclusion
                                        table_exclusion_rects.append((min_x, min_y, max_x, max_y))

                                        # Clean up any NaN
                                        df = df.fillna("")
                                        
                                        # Iterate Layout
                                        for r_idx, row_layout in enumerate(layout):
                                            for c_idx, cell_layout in enumerate(row_layout):
                                                # Get translated text
                                                trans_text = ""
                                                if r_idx < len(df) and c_idx < len(df.columns):
                                                    val = df.iloc[r_idx, c_idx]
                                                    if str(val).strip():
                                                        trans_text = str(val).strip()
                                                
                                                if not trans_text:
                                                    continue
                                                
                                                # Add to stats
                                                stats['full_translated_text'].append(trans_text)
                                                
                                                # Re-insertion Box
                                                # Ensure valid rect
                                                cell_rect = fitz.Rect(cell_layout.x0, cell_layout.y0, cell_layout.x1, cell_layout.y1)
                                                
                                                # Cover old content with white rect
                                                # Add 1px padding to ensure full coverage
                                                cover_rect = fitz.Rect(cell_rect[0]-1, cell_rect[1]-1, cell_rect[2]+1, cell_rect[3]+1)
                                                
                                                shape = page.new_shape()
                                                shape.draw_rect(cover_rect)
                                                shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                                                shape.commit()
                                                
                                                # Font settings
                                                # English tables usually small font
                                                current_fontsize = 8 
                                                # Force standard font for English tables to avoid numeral reversal issues with Noto
                                                font_to_use = "helv"
                                                
                                                # INSERT TEXT (LTR by default with align=0)
                                                # Use TextWriter for numeric/short LTR text to avoid PyMuPDF Bidi auto-reversal on Arabic pages
                                                if numeric_pattern.match(trans_text) or re.match(r'^[A-Za-z0-9\s\.,\-%]+$', trans_text):
                                                    # simple LTR text
                                                    tw = fitz.TextWriter(page.rect)
                                                    
                                                    # Calculate approx position (vertically centered?)
                                                    # insert_text uses baseline. 
                                                    # A simple heuristic: y = rect.y1 - (rect.height - fontsize)/2 - warning: approximate
                                                    text_start = fitz.Point(cell_rect.x0 + 2, cell_rect.y1 - 3) 
                                                    
                                                    tw.append(
                                                        text_start,
                                                        trans_text,
                                                        fontsize=current_fontsize,
                                                        font=fitz.Font(font_to_use)
                                                    )
                                                    tw.write_text(page)
                                                    remaining = 0 # Assume success
                                                else:
                                                    # Fallback to textbox for complex wrapping
                                                    remaining = page.insert_textbox(
                                                        cell_rect,
                                                        trans_text,
                                                        fontsize=current_fontsize,
                                                        fontname=font_to_use,
                                                        align=0  # Left Align (LTR)
                                                    )
                                                
                                                # Resize if needed
                                                while remaining < 0 and current_fontsize > 4:
                                                    current_fontsize -= 0.5
                                                    # Re-cover to clear partial draw
                                                    shape = page.new_shape()
                                                    shape.draw_rect(cover_rect)
                                                    shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                                                    shape.commit()
                                                    
                                                    remaining = page.insert_textbox(
                                                        cell_rect,
                                                        trans_text,
                                                        fontsize=current_fontsize,
                                                        fontname=font_to_use,
                                                        align=0
                                                    )
                                        
                                        stats['tables_translated'] += 1
                                        
                                    except Exception as e:
                                        print(f"Error applying Table {trans_csv}: {e}")
                                
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
                            
                            # Process cells
                            for row in table.rows:
                                for cell in row.cells:
                                    # Get text from cell area
                                    cell_text = page.get_text("text", clip=cell).strip()
                                    
                                    if not cell_text:
                                        continue
                                        
                                    # Check if cell is largely Arabic
                                    if arabic_pattern.search(cell_text):
                                        # Normalize
                                        normalized_text = normalize_arabic_numerals(cell_text)
                                        
                                        # Numeric Guard: If it looks like a number/date, DON'T translate
                                        if numeric_pattern.match(normalized_text):
                                            translated_text = normalized_text # Keep as is
                                            # print(f"    Skipping translation for numeric: {normalized_text}")
                                        else:
                                            # Translate
                                            try:
                                                translated_text = translate_to_english(normalized_text)
                                            except Exception as te:
                                                print(f"    Table cell translation error: {te}")
                                                translated_text = normalized_text
                                        
                                        if translated_text:
                                            # Accumulate for RAG
                                            stats['full_translated_text'].append(translated_text)
                                            # Cover and Insert
                                            # Use padding for cover
                                            cell_rect = fitz.Rect(cell)
                                            cover_rect = fitz.Rect(cell_rect[0]-1, cell_rect[1]-1, cell_rect[2]+1, cell_rect[3]+1)
                                            
                                            shape = page.new_shape()
                                            shape.draw_rect(cover_rect)
                                            shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                                            shape.commit()
                                            
                                            # Insert with auto-scaling
                                            # For tables, we might want smaller default font
                                            current_fontsize = 8 # Default for tables often smaller
                                            
                                            # Try to determine custom font
                                            font_to_use = "noto" if has_custom_font else "helv"
                                            
                                            remaining = page.insert_textbox(
                                                cell_rect,
                                                translated_text,
                                                fontsize=current_fontsize,
                                                fontname=font_to_use,
                                                align=0
                                            )
                                            
                                            # Simple resizing for cells
                                            while remaining < 0 and current_fontsize > 4:
                                                current_fontsize -= 0.5
                                                # Re-cover
                                                shape = page.new_shape()
                                                shape.draw_rect(cover_rect)
                                                shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                                                shape.commit()
                                                
                                                remaining = page.insert_textbox(
                                                    cell_rect,
                                                    translated_text,
                                                    fontsize=current_fontsize,
                                                    fontname=font_to_use,
                                                    align=0
                                                )
                                                
                        stats['tables_translated'] += len(tables)

                except Exception as e:
                    print(f"  Table processing warning: {e}")

            # --- Text Block Phase ---
            # Get text blocks (grouped by layout structure)
            # using "dict" to get structural info including bounding boxes
            text_dict = page.get_text("dict")
            
            # Collect all text blocks with their bounding boxes
            text_blocks = []
            
            for block in text_dict["blocks"]:
                if "lines" not in block:
                    continue
                
                # Check intersection with detected tables
                block_rect = fitz.Rect(block["bbox"])
                in_table = False
                for t_rect in table_exclusion_rects:
                    if fitz.Rect(t_rect).intersects(block_rect):
                        in_table = True
                        break
                
                if in_table:
                    # Skip this block as it was likely processed in Table Phase
                    continue

                # Group spans in this block into a single text block
                block_text_parts = []
                block_spans = []
                min_x, min_y = float('inf'), float('inf')
                max_x, max_y = float('-inf'), float('-inf')
                
                for line in block["lines"]:
                    # Sort spans by x-coordinate using bbox[0]
                    # For Arabic (RTL), we usually want reading order right-to-left if spans are stored visually
                    # But often PyMuPDF extracts physically.
                    # We will detect if line has Arabic, and if so, sort spans descending (Right-to-Left)
                    
                    spans = line["spans"]
                    if not spans:
                        continue
                        
                    # Check for Arabic in this line
                    line_text = " ".join([s.get("text", "") for s in spans])
                    is_arabic_line = bool(arabic_pattern.search(line_text))
                    
                    # Sort spans appropriately
                    if is_arabic_line:
                        # Sort Right-to-Left (descending X)
                        spans.sort(key=lambda s: s["bbox"][0], reverse=True)
                    else:
                        # Sort Left-to-Right (ascending X) - default
                        spans.sort(key=lambda s: s["bbox"][0])

                    for span in spans:
                        span_text = span.get("text", "").strip()
                        if span_text:
                            block_text_parts.append(span_text)
                            block_spans.append(span)
                        # Update bounding box
                        bbox = span["bbox"]
                        min_x = min(min_x, bbox[0])
                        min_y = min(min_y, bbox[1])
                        max_x = max(max_x, bbox[2])
                        max_y = max(max_y, bbox[3])
                
                if block_text_parts:
                    # Combine text parts
                    # Note: Original order often works for PyMuPDF extraction even for RTL 
                    # because it extracts in reading order usually.
                    combined_text = " ".join(block_text_parts)
                    
                    # Check if block contains Arabic
                    if arabic_pattern.search(combined_text):
                        # Get average font properties from spans
                        font_sizes = [s.get("size", 12) for s in block_spans]
                        avg_font_size = sum(font_sizes) / len(font_sizes) if font_sizes else 12
                        
                        text_blocks.append({
                            'text': combined_text,
                            'bbox': [min_x, min_y, max_x, max_y],
                            'font_size': avg_font_size,
                            'spans': block_spans
                        })

            print(f"Found {len(text_blocks)} Arabic text blocks on page {page_num + 1}")

            # --- Layout Analysis Phase ---
            # Determine structural types (Heading vs Body) based on relative font sizes
            if text_blocks:
                all_sizes = [b['font_size'] for b in text_blocks]
                if all_sizes:
                    page_avg_size = sum(all_sizes) / len(all_sizes)
                    print(f"Page {page_num+1} stats: Avg Font Size={page_avg_size:.2f}")
                    
                    for block in text_blocks:
                        size = block['font_size']
                        # Simple heuristics for structure
                        if size > page_avg_size * 1.15:
                            block['type'] = 'heading'
                            block['md_prefix'] = '## ' if size < page_avg_size * 1.5 else '# '
                        elif size < page_avg_size * 0.85:
                            block['type'] = 'small'
                            block['md_prefix'] = ''
                        else:
                            block['type'] = 'body'
                            block['md_prefix'] = ''
                            
                        # Debug structure
                        # print(f"  Block type: {block['type']} (Size: {size:.1f})")

            # --- Text Replacement Phase ---
            # Process each text block
            for block_idx, text_block in enumerate(text_blocks):
                original_text = text_block['text']
                bbox = text_block['bbox']
                
                # Filter out very small blocks or noise
                if (bbox[2] - bbox[0]) < 5 or (bbox[3] - bbox[1]) < 5:
                    continue

                # Normalize numerals
                normalized_text = normalize_arabic_numerals(original_text)

                # Translate the complete block
                try:
                    # Skip numeric-heavy blocks if needed, but "in-place" usually implies 
                    # replacing everything that was selected as Arabic block.
                    # We'll check if it's translatable.
                    
                    translated_text = translate_to_english(normalized_text)

                    # Only replace if translation returned something and isn't just Arabic again
                    if translated_text and not arabic_pattern.search(translated_text):
                        # Accumulate for RAG
                        stats['full_translated_text'].append(translated_text)
                        
                        # Create rectangle for the text area
                        rect = fitz.Rect(bbox)
                        
                        # Apply padding to ensure we cover the old text fully
                        # Expand slightly (1-2 points) to cover anti-aliasing artifacts
                        cover_rect = fitz.Rect(bbox[0]-1, bbox[1]-1, bbox[2]+1, bbox[3]+1)

                        # Draw white rectangle to cover original text
                        # We use shape to ensure it's drawn over existing content
                        shape = page.new_shape()
                        shape.draw_rect(cover_rect)
                        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                        shape.commit()

                        # Insert new text
                        try:
                            # 1. Calculate optimal font size
                            box_width = rect.width
                            box_height = rect.height
                            
                            # Start with original font size but cap it reasonable for English
                            # Arabic often compact; English might need adjustment.
                            # Usually English takes more horizontal space but less vertical per line height sometimes.
                            current_fontsize = text_block['font_size']
                            
                            # Insert textbox allows auto-wrapping
                            # We might need to scale down if it returns a negative result (overflow)
                            
                            # Determine correct font
                            block_type = text_block.get('type', 'body')
                            
                            font_to_use = "helv"
                            if has_custom_font:
                                if block_type == 'heading' and has_custom_font_bold:
                                    font_to_use = "noto-bold"
                                else:
                                    font_to_use = "noto"
                            
                            remaining_text = page.insert_textbox(
                                rect,
                                translated_text,
                                fontsize=current_fontsize,
                                fontname=font_to_use,
                                align=0,  # Left align
                                encoding=0 # PDF standard encoding? 0 is usually fine for Latin
                            )
                            
                            if remaining_text < 0:
                                # Start resizing loop
                                # Minimum legible size
                                min_fontsize = 6
                                while remaining_text < 0 and current_fontsize > min_fontsize:
                                    current_fontsize -= 0.5
                                    # Clear previous attempt (conceptually, we just overwrite on top or we assumed we haven't committed? 
                                    # insert_textbox commits immediately. 
                                    # So we should validte size *before* committing or overwrite with white again.
                                    # PyMuPDF insert_textbox draws immediately.
                                    # So we need to cover again.
                                    
                                    shape = page.new_shape()
                                    shape.draw_rect(cover_rect)
                                    shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                                    shape.commit()
                                    
                                    remaining_text = page.insert_textbox(
                                        rect,
                                        translated_text,
                                        fontsize=current_fontsize,
                                        fontname=font_to_use,
                                        align=0
                                    )
                            
                            stats['text_blocks_translated'] += 1

                        except Exception as insert_error:
                            print(f"    Text insertion error: {insert_error}")
                            # Fallback: simple text insertion if textbox fails completely
                            # (Unlikely if rect is valid, but good safety)
                            pass
                    else:
                        print(f"    Skipping: Translation failed or empty")

                except Exception as e:
                    print(f"    Block processing error: {e}")

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
        # Join all text for the final return
        stats['full_text_content'] = "\n\n".join(stats['full_translated_text'])
        del stats['full_translated_text'] # Remove list to keep dict clean

        return stats

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

