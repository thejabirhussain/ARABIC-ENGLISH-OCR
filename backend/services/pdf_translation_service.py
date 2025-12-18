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
    print("Starting in-place PDF translation (Unified Layout Mode)")
    print("=" * 60)

    # Open the PDF for writing
    doc = fitz.open(working_pdf_path)
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    stats = {
        'pages_processed': len(doc),
        'text_blocks_translated': 0,
        'tables_translated': 0
    }

    try:
        # Use the robust extraction service to get blocks
        # This handles OCR, line grouping, and filtering better than a simple loop
        all_blocks = extract_text_blocks_with_layout(working_pdf_path)
        
        # Group blocks by page
        blocks_by_page = {}
        for block in all_blocks:
            if block.page_num not in blocks_by_page:
                blocks_by_page[block.page_num] = []
            blocks_by_page[block.page_num].append(block)

        for page_num in range(len(doc)):
            page_index = page_num  # 0-indexed for fitz
            page = doc[page_index]
            page_h = page.rect.height
            
            # Get blocks for this page (1-indexed in extraction service)
            page_blocks = blocks_by_page.get(page_num + 1, [])
            
            print(f"\nProcessing page {page_num + 1}/{len(doc)}... Found {len(page_blocks)} blocks")

            for block_idx, text_block in enumerate(page_blocks):
                original_text = text_block.text
                
                # Verify it contains Arabic before processing
                if not arabic_pattern.search(original_text):
                    continue

                # Convert coordinates: TextBlock is Bottom-Left (PDF standard), Fitz is Top-Left
                # TextBlock: x0, y0 (bottom), x1, y1 (top) - wait, standard PDF is y=0 at bottom.
                # Let's verify layout_extraction_service.py again.
                # It does: `by0 = height - y1` (where y1 was bottom-y in fitz? No, fitz is top-left).
                # Fitz: (x0, top, x1, bottom).
                # Layout Service converts to: (x0, height-bottom, x1, height-top).
                # So stored y0 is bottom-y, y1 is top-y in Math cartesian?
                # Actually usually standard PDF is (0,0) at bottom-left.
                # So if we have (x0, y0, x1, y1) in PDF coordinates:
                # Fitz Rect should be (x0, page_h - y1, x1, page_h - y0).
                
                # TextBlock stores: y0=bottom, y1=top (Cartesian).
                # Fitz needs: top, bottom (Screen/Image).
                # Rect (x0, top, x1, bottom)
                
                x0 = text_block.x0
                y0_cartesian = text_block.y0
                x1 = text_block.x1
                y1_cartesian = text_block.y1
                
                # Convert to Fitz coordinates (Top-Left 0,0)
                # Top y in fitz = Page Height - Max Cartesian Y
                rect_top = page_h - y1_cartesian
                # Bottom y in fitz = Page Height - Min Cartesian Y
                rect_bottom = page_h - y0_cartesian
                
                rect = fitz.Rect(x0, rect_top, x1, rect_bottom)
                
                # Validate rect
                if rect.is_empty or rect.width < 1 or rect.height < 1:
                    continue

                # Normalize numerals
                normalized_text = normalize_arabic_numerals(original_text)

                # Translate
                try:
                    translated_text = translate_to_english(normalized_text)

                    if translated_text and not arabic_pattern.search(translated_text):
                        # Cover original text
                        # Expand slightly to cover anti-aliasing
                        cover_rect = fitz.Rect(rect.x0-2, rect.y0-2, rect.x1+2, rect.y1+2)
                        
                        shape = page.new_shape()
                        shape.draw_rect(cover_rect)
                        shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                        shape.commit()

                        # Insert new text
                        try:
                            # Estimate font size based on height
                            # English text is usually shorter vertically but wider horizontally
                            # than Arabic roughly.
                            # Start with height-based guess.
                            box_height = rect.height
                            initial_font_size = min(box_height * 0.8, 12) # Cap at 12 to avoid massive text
                            if box_height > 20: 
                                initial_font_size = 10 # Reset for large blocks to standard reading size
                            
                            # Adaptive fitting
                            curr_size = initial_font_size
                            min_size = 4
                            
                            remaining = -1
                            while remaining < 0 and curr_size >= min_size:
                                # We need to overwrite the whiteout if we retry, 
                                # because insert_textbox draws immediately.
                                # Actually, we can just draw whiteout once, and then try inserting.
                                # If it fails (overflows), we clear and try smaller.
                                
                                # Re-draw whiteout to clear previous attempt
                                shape = page.new_shape()
                                shape.draw_rect(cover_rect)
                                shape.finish(color=(1, 1, 1), fill=(1, 1, 1), width=0)
                                shape.commit()
                                
                                remaining = page.insert_textbox(
                                    rect,
                                    translated_text,
                                    fontsize=curr_size,
                                    fontname="helv",
                                    align=0, # Left
                                )
                                curr_size -= 0.5
                            
                            stats['text_blocks_translated'] += 1

                        except Exception as insert_error:
                            print(f"    Text insertion error: {insert_error}")
                    else:
                        pass # Translation failed or empty

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

