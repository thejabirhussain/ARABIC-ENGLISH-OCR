"""
PDF rendering service using ReportLab.
Renders translated English text into a new PDF maintaining original layout.
"""
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.colors import black
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle, Spacer
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
import os
import re
from typing import List, Tuple
from services.layout_extraction_service import TextBlock
from services.table_extraction_service import Table, TableCell

def _contains_arabic(text: str) -> bool:
    """Check if text contains Arabic characters"""
    if not text:
        return False
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    return bool(arabic_pattern.search(text))

def _is_valid_english_text(text: str) -> bool:
    """Validate that text is valid (English or Arabic for layout preservation) and not corrupted"""
    if not text or not text.strip():
        return False

    # For layout preservation, accept both English and Arabic text
    # Only reject if it looks like complete garbage/corruption

    # Check if it has at least some recognizable characters (letters, numbers, punctuation)
    if not re.search(r'[a-zA-Z0-9\u0600-\u06FF]', text):
        return False

    # Check for excessive corruption - remove normal characters and check what's left
    # Allow Arabic characters now since we want layout preservation
    cleaned = re.sub(r'[a-zA-Z0-9\u0600-\u06FF\s,.\-:;()%$€£¥/\'"?!؛،]', '', text)
    # If more than 70% is weird characters, likely corrupted
    if len(cleaned) > len(text) * 0.7:
        return False

    return True

def render_translated_pdf(
    text_blocks: List[TextBlock],
    tables: List[Table],
    output_path: str,
    page_size: Tuple[float, float] = None,
    original_pdf_path: str = None,
    preserve_layout: bool = False
):
    """
    Render a new PDF with translated English text.

    Args:
        text_blocks: List of translated text blocks with positions
        tables: List of translated tables
        output_path: Path to save the new PDF
        page_size: (width, height) in points. If None, uses A4
        original_pdf_path: Path to original PDF for page size reference
        preserve_layout: If True, accept Arabic text to maintain layout
    """
    # Filter out invalid blocks - be more permissive in preserve_layout mode
    print(f"Renderer received {len(text_blocks)} text blocks and {len(tables)} tables")
    print(f"preserve_layout mode: {preserve_layout}")

    valid_blocks = []
    for block in text_blocks:
        if preserve_layout or _is_valid_english_text(block.text):
            valid_blocks.append(block)
            print(f"Accepted block: '{block.text[:50]}...'")
        else:
            print(f"Skipping invalid block: {block.text[:50]}...")

    # Filter out invalid table cells - be more permissive in preserve_layout mode
    valid_tables = []
    for table in tables:
        valid_cells = []
        for cell in table.cells:
            if preserve_layout or _is_valid_english_text(cell.text):
                valid_cells.append(cell)
                print(f"Accepted cell: '{cell.text[:30]}...'")
            else:
                print(f"Skipping invalid cell: {cell.text[:30]}...")

        if valid_cells:
            # Create new table with only valid cells
            from services.table_extraction_service import Table as TableClass
            valid_table = TableClass(valid_cells, table.page_num)
            valid_tables.append(valid_table)

    print(f"After filtering: {len(valid_blocks)} blocks and {len(valid_tables)} tables")
    
    # Determine page size
    if page_size is None:
        if original_pdf_path:
            page_size = _get_pdf_page_size(original_pdf_path)
        else:
            page_size = A4  # Default to A4
    
    width, height = page_size
    
    # Create PDF canvas
    c = canvas.Canvas(output_path, pagesize=page_size)
    
    # Register fonts (use default for now, can add custom fonts later)
    try:
        # Try to use a font that supports English well
        c.setFont("Helvetica", 10)
    except:
        c.setFont("Helvetica", 10)
    
    # Group blocks and tables by page
    blocks_by_page = {}
    tables_by_page = {}
    
    for block in valid_blocks:
        if block.page_num not in blocks_by_page:
            blocks_by_page[block.page_num] = []
        blocks_by_page[block.page_num].append(block)
    
    for table in valid_tables:
        if table.page_num not in tables_by_page:
            tables_by_page[table.page_num] = []
        tables_by_page[table.page_num].append(table)
    
    # Get max page number
    all_pages = set(blocks_by_page.keys()) | set(tables_by_page.keys())
    max_page = max(all_pages) if all_pages else 1
    
    # Render each page
    for page_num in range(1, max_page + 1):
        if page_num > 1:
            c.showPage()
        
        # Render text blocks
        if page_num in blocks_by_page:
            for block in blocks_by_page[page_num]:
                if not block.is_table:  # Skip table blocks, handled separately
                    _render_text_block(c, block, height)
        
        # Render tables
        if page_num in tables_by_page:
            for table in tables_by_page[page_num]:
                _render_table(c, table, height)
    
    c.save()

def _render_text_block(c: canvas.Canvas, block: TextBlock, page_height: float):
    """Render a single text block"""
    # Skip if text is invalid (should already be filtered, but double-check)
    if not _is_valid_english_text(block.text):
        return
    
    # Coordinates: our extraction normalizes to bottom-left origin already.
    # Use them directly to avoid double flipping that causes randomness.
    x = block.x0
    y = block.y0
    
    # Calculate font size based on block height
    font_size = max(8, min(block.height * 0.8, 14))  # Reasonable range
    
    # Skip invalid blocks
    if block.width <= 1 or block.height <= 1:
        return

    # Handle text overflow by adjusting font size
    text = block.text.strip()
    if not text:
        return
    text_width = c.stringWidth(text, "Helvetica", font_size)
    block_width = block.width
    
    if text_width > block_width and block_width > 0:
        # Scale font down to fit
        scale_factor = block_width / text_width * 0.95  # 95% to add margin
        font_size = max(6, font_size * scale_factor)
    
    # Word wrap within block rectangle
    if block_width > 0:
        words = text.split()
        lines = []
        current_line = []
        current_width = 0
        
        for word in words:
            word_width = c.stringWidth(word + " ", "Helvetica", font_size)
            if current_width + word_width <= block_width or not current_line:
                current_line.append(word)
                current_width += word_width
            else:
                lines.append(" ".join(current_line))
                current_line = [word]
                current_width = word_width
        
        if current_line:
            lines.append(" ".join(current_line))
        
        # Render each line within block height
        line_height = font_size * 1.2
        max_lines = int(block.height // line_height)
        if max_lines <= 0:
            return
        c.setFont("Helvetica", font_size)
        for i, line in enumerate(lines[:max_lines]):
            line_y = y + block.height - ((i + 1) * line_height)
            if line_y < 0:
                break
            c.drawString(x, line_y, line)
    else:
        # Single line
        c.setFont("Helvetica", font_size)
        c.drawString(x, y + (block.height - font_size * 1.1), text)

def _render_table(c: canvas.Canvas, table: Table, page_height: float):
    """Render a table using canvas with proper cell alignment"""
    if not table.cells:
        return
    
    # Group cells by row and column for better organization
    cells_by_row = {}
    for cell in table.cells:
        if cell.row not in cells_by_row:
            cells_by_row[cell.row] = {}
        cells_by_row[cell.row][cell.col] = cell
    
    # Get column boundaries for proper alignment
    col_x_positions = {}
    for cell in table.cells:
        if cell.col not in col_x_positions:
            col_x_positions[cell.col] = []
        col_x_positions[cell.col].append((cell.x0, cell.x1))
    
    # Calculate average column positions
    col_avg_x0 = {}
    col_avg_x1 = {}
    for col, positions in col_x_positions.items():
        col_avg_x0[col] = sum(p[0] for p in positions) / len(positions)
        col_avg_x1[col] = sum(p[1] for p in positions) / len(positions)
    
    # Sort rows and columns
    sorted_rows = sorted(cells_by_row.keys())
    
    # Render each cell with proper alignment
    for row_idx in sorted_rows:
        row_cells = cells_by_row[row_idx]
        sorted_cols = sorted(row_cells.keys())
        
        for col_idx in sorted_cols:
            cell = row_cells[col_idx]
            
            # Skip invalid cells
            if not _is_valid_english_text(cell.text):
                continue
            
            # Use actual cell coordinates (already in bottom-left origin)
            x = cell.x0
            y = cell.y0
            
            # Calculate font size based on cell height
            font_size = max(8, min(cell.height * 0.7, 12))
            
            # Check if text fits
            text = cell.text.strip()
            if not text:
                continue
            
            text_width = c.stringWidth(text, "Helvetica", font_size)
            cell_width = cell.width
            
            # Scale font if text doesn't fit
            if text_width > cell_width and cell_width > 0:
                scale_factor = (cell_width / text_width) * 0.9
                font_size = max(6, font_size * scale_factor)
                text_width = c.stringWidth(text, "Helvetica", font_size)
            
            # Set font and color
            c.setFont("Helvetica", font_size)
            c.setFillColor(colors.black)
            
            # Determine text alignment based on content
            # If text is mostly numeric, right-align; otherwise left-align
            is_numeric = re.match(r'^[\d,\s.()\-]+$', text.strip())
            
            if is_numeric:
                # Right-align numbers
                text_x = x + cell_width - text_width - 2  # 2pt padding from right
            else:
                # Left-align text
                text_x = x + 2  # 2pt padding from left
            
            # Center text vertically
            text_y = y + (cell.height - font_size) / 2
            
            # Ensure text is within page bounds
            if text_y >= 0 and text_y <= page_height:
                c.drawString(text_x, text_y, text)

def _get_pdf_page_size(pdf_path: str) -> Tuple[float, float]:
    """Get page size from original PDF"""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                page = pdf.pages[0]
                # pdfplumber returns dimensions in PDF points already
                width = page.width
                height = page.height
                return (width, height)
    except:
        pass
    
    return A4  # Default to A4

