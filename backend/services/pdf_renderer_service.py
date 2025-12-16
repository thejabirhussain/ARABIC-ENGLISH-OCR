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
from typing import List, Tuple
from services.layout_extraction_service import TextBlock
from services.table_extraction_service import Table, TableCell

def render_translated_pdf(
    text_blocks: List[TextBlock],
    tables: List[Table],
    output_path: str,
    page_size: Tuple[float, float] = None,
    original_pdf_path: str = None
):
    """
    Render a new PDF with translated English text.
    
    Args:
        text_blocks: List of translated text blocks with positions
        tables: List of translated tables
        output_path: Path to save the new PDF
        page_size: (width, height) in points. If None, uses A4
        original_pdf_path: Path to original PDF for page size reference
    """
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
    
    for block in text_blocks:
        if block.page_num not in blocks_by_page:
            blocks_by_page[block.page_num] = []
        blocks_by_page[block.page_num].append(block)
    
    for table in tables:
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
    # Convert coordinates (PDF uses bottom-left origin)
    # Original coordinates might be top-left, so we need to convert
    x = block.x0
    y = page_height - block.y1  # Convert from top-left to bottom-left
    
    # Calculate font size based on block height
    font_size = max(8, min(block.height * 0.8, 14))  # Reasonable range
    
    # Handle text overflow by adjusting font size
    text = block.text
    text_width = c.stringWidth(text, "Helvetica", font_size)
    block_width = block.width
    
    if text_width > block_width and block_width > 0:
        # Scale font down to fit
        scale_factor = block_width / text_width * 0.95  # 95% to add margin
        font_size = max(6, font_size * scale_factor)
    
    # Word wrap if needed
    if text_width > block_width and block_width > 0:
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
        
        # Render each line
        line_height = font_size * 1.2
        for i, line in enumerate(lines):
            line_y = y - (i * line_height)
            if line_y < 0:  # Don't render if off page
                break
            c.setFont("Helvetica", font_size)
            c.drawString(x, line_y, line)
    else:
        # Single line
        c.setFont("Helvetica", font_size)
        c.drawString(x, y, text)

def _render_table(c: canvas.Canvas, table: Table, page_height: float):
    """Render a table using canvas (simpler approach)"""
    if not table.cells:
        return
    
    # Group cells by row
    cells_by_row = {}
    for cell in table.cells:
        if cell.row not in cells_by_row:
            cells_by_row[cell.row] = {}
        cells_by_row[cell.row][cell.col] = cell
    
    num_rows = max(cells_by_row.keys()) + 1 if cells_by_row else 0
    num_cols = max(max(row.keys()) for row in cells_by_row.values()) + 1 if cells_by_row else 0
    
    # Render each cell individually
    for cell in table.cells:
        x = cell.x0
        y = page_height - cell.y1  # Convert to bottom-left origin
        
        # Calculate font size
        font_size = max(8, min(cell.height * 0.7, 12))
        
        # Check if text fits
        text = cell.text
        text_width = c.stringWidth(text, "Helvetica", font_size)
        
        if text_width > cell.width and cell.width > 0:
            scale_factor = (cell.width / text_width) * 0.9
            font_size = max(6, font_size * scale_factor)
        
        # Draw cell border
        c.setStrokeColor(colors.black)
        c.setLineWidth(0.5)
        c.rect(x, y, cell.width, cell.height, stroke=1, fill=0)
        
        # Draw text
        c.setFont("Helvetica", font_size)
        c.setFillColor(colors.black)
        
        # Center text vertically and align left
        text_y = y + (cell.height - font_size) / 2
        c.drawString(x + 2, text_y, text)  # 2pt padding from left

def _get_pdf_page_size(pdf_path: str) -> Tuple[float, float]:
    """Get page size from original PDF"""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            if pdf.pages:
                page = pdf.pages[0]
                width = page.width * 72  # Convert to points
                height = page.height * 72
                return (width, height)
    except:
        pass
    
    return A4  # Default to A4

