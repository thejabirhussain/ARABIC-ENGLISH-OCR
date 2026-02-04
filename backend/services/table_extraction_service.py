"""
Table extraction service for PDFs.
Handles both text-based and OCR-based tables.
"""
import pdfplumber
import tempfile
import os
import pandas as pd
from typing import List, Dict, Tuple
from services.layout_extraction_service import TextBlock

# Try to import camelot, but make it optional
try:
    import camelot
    CAMELOT_AVAILABLE = True
except ImportError:
    CAMELOT_AVAILABLE = False
    print("Warning: camelot-py not installed. Table extraction will use pdfplumber only.")

class TableCell:
    """Represents a table cell with position and content"""
    def __init__(self, text: str, row: int, col: int, x0: float, y0: float, 
                 x1: float, y1: float, page_num: int):
        self.text = text.strip()
        self.row = row
        self.col = col
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.width = x1 - x0
        self.height = y1 - y0
        self.page_num = page_num

class Table:
    """Represents a table with cells"""
    def __init__(self, cells: List[TableCell], page_num: int):
        self.cells = cells
        self.page_num = page_num
        self.num_rows = max(cell.row for cell in cells) + 1 if cells else 0
        self.num_cols = max(cell.col for cell in cells) + 1 if cells else 0
        # Compute bounding box from cells
        if cells:
            self.x0 = min(c.x0 for c in cells)
            self.y0 = min(c.y0 for c in cells)
            self.x1 = max(c.x1 for c in cells)
            self.y1 = max(c.y1 for c in cells)
        else:
            self.x0 = self.y0 = self.x1 = self.y1 = 0.0

    def bbox(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

def extract_tables_from_pdf(pdf_path: str) -> List[Table]:
    """
    Extract tables from PDF.
    Tries Camelot first (for text-based), then falls back to pdfplumber.
    """
    tables = []
    
    # Try Camelot for text-based tables (if available)
    if CAMELOT_AVAILABLE:
        for flavor in ("lattice", "stream"):
            try:
                camelot_tables = camelot.read_pdf(pdf_path, pages='all', flavor=flavor)
                for table_idx, camelot_table in enumerate(camelot_tables):
                    try:
                        page_num = camelot_table.page if hasattr(camelot_table, 'page') else 1
                        # Convert Camelot table to our Table format
                        cells = []
                        df = camelot_table.df
                        # Get table bounding box
                        table_bbox = getattr(camelot_table, '_bbox', None)
                        for row_idx, row in df.iterrows():
                            for col_idx, cell_text in enumerate(row):
                                if pd.notna(cell_text) and str(cell_text).strip():
                                    if table_bbox:
                                        num_cols = len(row)
                                        num_rows = len(df)
                                        cell_width = (table_bbox[2] - table_bbox[0]) / max(num_cols, 1)
                                        cell_height = (table_bbox[3] - table_bbox[1]) / max(num_rows, 1)
                                        x0 = table_bbox[0] + col_idx * cell_width
                                        y0 = table_bbox[1] + row_idx * cell_height
                                        x1 = x0 + cell_width
                                        y1 = y0 + cell_height
                                    else:
                                        x0, y0, x1, y1 = 0, 0, 100, 20
                                    cell = TableCell(
                                        str(cell_text).strip(),
                                        int(row_idx),
                                        int(col_idx),
                                        x0, y0, x1, y1,
                                        page_num
                                    )
                                    cells.append(cell)
                        if cells:
                            table = Table(cells, page_num)
                            tables.append(table)
                    except Exception as e:
                        print(f"Error processing Camelot table {flavor} {table_idx}: {e}")
                        continue
                if tables:
                    break  # Stop if any tables found with current flavor
            except Exception as e:
                print(f"Camelot {flavor} extraction failed: {e}")
        if not tables:
            print("Camelot found no tables; trying pdfplumber...")
            tables = _extract_tables_with_pdfplumber(pdf_path)
    else:
        # Camelot not available, use pdfplumber directly
        print("Camelot not available, using pdfplumber for table extraction...")
        tables = _extract_tables_with_pdfplumber(pdf_path)
    
    return tables

def _extract_tables_with_pdfplumber(pdf_path: str) -> List[Table]:
    """Extract tables using pdfplumber with actual cell positions"""
    tables = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Find all tables on the page
                found_tables = page.find_tables()
                
                if not found_tables:
                    continue
                
                page_height = page.height
                
                # Extract table data and cell positions
                for table_idx, table_obj in enumerate(found_tables):
                    try:
                        # Extract table data (text content)
                        table_data = table_obj.extract()
                        
                        if not table_data:
                            continue
                        
                        cells = []
                        
                        # Get table bounding box (pdfplumber uses top-left origin: x0, top, x1, bottom)
                        table_x0, table_top, table_x1, table_bottom = table_obj.bbox
                        
                        # Get actual cell positions from pdfplumber table
                        # pdfplumber Table objects have a .cells property that's a list
                        # We need to access cells through the table's rows structure
                        cell_bbox_map = {}
                        try:
                            # Try to access cells through table.rows
                            if hasattr(table_obj, 'rows'):
                                for row_idx, row_obj in enumerate(table_obj.rows):
                                    if hasattr(row_obj, 'cells'):
                                        for col_idx, cell_obj in enumerate(row_obj.cells):
                                            try:
                                                if hasattr(cell_obj, 'bbox') and cell_obj.bbox:
                                                    cell_bbox_map[(row_idx, col_idx)] = cell_obj.bbox
                                            except:
                                                continue
                            # Alternative: try direct .cells access
                            elif hasattr(table_obj, 'cells'):
                                # If cells is a flat list, we need to reconstruct row/col from table structure
                                cell_list = list(table_obj.cells)
                                for idx, cell_obj in enumerate(cell_list):
                                    try:
                                        # Try to get row/col from cell
                                        if hasattr(cell_obj, 'row') and hasattr(cell_obj, 'col'):
                                            row_idx = cell_obj.row
                                            col_idx = cell_obj.col
                                            if hasattr(cell_obj, 'bbox') and cell_obj.bbox:
                                                cell_bbox_map[(row_idx, col_idx)] = cell_obj.bbox
                                    except:
                                        continue
                        except Exception as e:
                            print(f"  Warning: Could not access table cell positions: {e}")
                        
                        # Process each cell from extracted data
                        num_rows = len(table_data)
                        num_cols = max(len(r) for r in table_data) if table_data else 1
                        
                        for row_idx, row in enumerate(table_data):
                            if not row:
                                continue
                            
                            for col_idx, cell_text in enumerate(row):
                                if cell_text is None:
                                    continue
                                
                                cell_text = str(cell_text).strip()
                                if not cell_text:
                                    continue
                                
                                # Get cell bounding box
                                if (row_idx, col_idx) in cell_bbox_map:
                                    # Use actual cell bbox from pdfplumber (top-left origin)
                                    x0, top, x1, bottom = cell_bbox_map[(row_idx, col_idx)]
                                    # Convert to bottom-left origin for ReportLab
                                    y0 = page_height - bottom
                                    y1 = page_height - top
                                else:
                                    # Fallback: calculate from table bbox
                                    cell_width = (table_x1 - table_x0) / num_cols
                                    cell_height = (table_bottom - table_top) / num_rows
                                    
                                    x0 = table_x0 + col_idx * cell_width
                                    x1 = x0 + cell_width
                                    # Convert from top-left to bottom-left origin
                                    y0 = page_height - (table_top + (row_idx + 1) * cell_height)
                                    y1 = page_height - (table_top + row_idx * cell_height)
                                
                                cell = TableCell(
                                    cell_text,
                                    row_idx,
                                    col_idx,
                                    x0, y0, x1, y1,
                                    page_num
                                )
                                cells.append(cell)
                        
                        if cells:
                            table = Table(cells, page_num)
                            tables.append(table)
                            print(f"Extracted table {table_idx+1} on page {page_num} with {len(cells)} cells")
                    except Exception as e:
                        print(f"Error processing table {table_idx} on page {page_num}: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                        
    except Exception as e:
        print(f"pdfplumber table extraction failed: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"Total tables extracted: {len(tables)}")
    return tables

def extract_tables_from_ocr(text_blocks: List[TextBlock]) -> List[Table]:
    """
    Detect and extract tables from OCR text blocks using bounding box analysis.
    This is a fallback when Camelot/pdfplumber fail.
    """
    # Group blocks by page
    blocks_by_page = {}
    for block in text_blocks:
        if block.page_num not in blocks_by_page:
            blocks_by_page[block.page_num] = []
        blocks_by_page[block.page_num].append(block)
    
    tables = []
    
    for page_num, blocks in blocks_by_page.items():
        # Simple table detection: look for aligned blocks
        # This is a basic implementation - can be improved with ML
        table_blocks = _detect_table_structure(blocks)
        
        if table_blocks:
            cells = []
            for row_idx, row_blocks in enumerate(table_blocks):
                for col_idx, block in enumerate(row_blocks):
                    cell = TableCell(
                        block.text,
                        row_idx,
                        col_idx,
                        block.x0, block.y0, block.x1, block.y1,
                        page_num
                    )
                    cells.append(cell)
            
            if cells:
                table = Table(cells, page_num)
                tables.append(table)
    
    return tables

def _detect_table_structure(blocks: List[TextBlock]) -> List[List[TextBlock]]:
    """
    Detect table structure from blocks using alignment analysis.
    Returns list of rows, each row is a list of blocks.
    """
    if not blocks:
        return []
    
    # Sort blocks by y position (top to bottom)
    sorted_blocks = sorted(blocks, key=lambda b: b.y0)
    
    # Group into rows based on y-position
    rows = []
    current_row = []
    y_tolerance = 5
    
    for block in sorted_blocks:
        if not current_row:
            current_row = [block]
        else:
            # Check if block is on same row (similar y0)
            avg_y = sum(b.y0 for b in current_row) / len(current_row)
            if abs(block.y0 - avg_y) <= y_tolerance:
                current_row.append(block)
            else:
                # New row
                rows.append(sorted(current_row, key=lambda b: b.x0))  # Sort by x
                current_row = [block]
    
    if current_row:
        rows.append(sorted(current_row, key=lambda b: b.x0))
    
    # Filter rows that look like tables (multiple columns)
    table_rows = [row for row in rows if len(row) >= 2]
    
    return table_rows if len(table_rows) >= 2 else []

