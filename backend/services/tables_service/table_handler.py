from typing import List, Dict, Tuple, Optional
import pandas as pd
from .models import BoundingBox
from .arabic_utils import fix_rtl_token, has_arabic_letter

class CellLayout:
    def __init__(self, text: str, x0: float, y0: float, x1: float, y1: float):
        self.text = text
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1
        self.bbox = (x0, y0, x1, y1)

class TableHandler:
    """Handles table-specific operations"""
    
    @staticmethod
    def words_to_table(words: List[Dict], col_bounds: List[float], y_tolerance: float = 8.0) -> Tuple[List[List[str]], List[List[CellLayout]]]:
        """
        Convert words to table structure using column boundaries.
        Returns both the text content (for CSV) and layout info (for PDF re-insertion).
        """
        if not words:
            return [], []
        
        # Sort by Y (line) then X
        words_sorted = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))
        
        # Group by Y (rows)
        rows = []
        current_row = []
        current_y = None
        
        # Track row vertical bounds
        row_bounds = [] # List containing (min_top, max_bottom) for each row
        
        def processing_row_bounds(row_words):
            if not row_words:
                return (0, 0)
            tops = [w["top"] for w in row_words]
            bottoms = [w["bottom"] for w in row_words]
            return (min(tops), max(bottoms))

        for w in words_sorted:
            if current_y is None:
                current_row.append(w)
                current_y = w["top"]
            elif abs(w["top"] - current_y) <= y_tolerance:
                current_row.append(w)
                # Keep current_y as the anchor (first word's top) or update? 
                # Original logic kept anchor.
            else:
                rows.append(current_row)
                row_bounds.append(processing_row_bounds(current_row))
                
                current_row = [w]
                current_y = w["top"]
        
        if current_row:
            rows.append(current_row)
            row_bounds.append(processing_row_bounds(current_row))
        
        # Build table
        n_cols = len(col_bounds) - 1
        table_rows_text = []
        table_rows_layout = []
        
        for r_idx, row_words in enumerate(rows):
            col_tokens = [[] for _ in range(n_cols)]
            
            # Distribute words into columns
            for w in row_words:
                x_center = (w["x0"] + w["x1"]) / 2
                for i in range(n_cols):
                    if col_bounds[i] <= x_center <= col_bounds[i + 1]:
                        col_tokens[i].append({
                            "text": w["text"].strip(), 
                            "x": x_center,
                            "x0": w["x0"],
                            "x1": w["x1"]
                        })
                        break
            
            # Build cell text with RTL handling
            row_text = []
            row_layout = []
            
            row_y0, row_y1 = row_bounds[r_idx]
            
            for c_idx, toks in enumerate(col_tokens):
                # Calculate Cell Box
                cell_x0 = col_bounds[c_idx]
                cell_x1 = col_bounds[c_idx+1]
                cell_y0 = row_y0
                cell_y1 = row_y1
                
                if not toks:
                    row_text.append("")
                    row_layout.append(CellLayout("", cell_x0, cell_y0, cell_x1, cell_y1))
                    continue
                
                rtl = any(has_arabic_letter(t["text"]) for t in toks)
                # Sort tokens visually from Right to Left if RTL
                toks_sorted = sorted(toks, key=lambda t: t["x"], reverse=rtl)
                
                parts = []
                for idx, t in enumerate(toks_sorted):
                    fixed_text = fix_rtl_token(t["text"])
                    
                    if idx > 0:
                        separator = " "
                        prev_t = toks_sorted[idx-1]
                        
                        if rtl:
                            # RTL: Sort Descending X. T[idx-1] is Right, T[idx] is Left.
                            # Gap = RightToken.LeftEdge - LeftToken.RightEdge
                            gap = prev_t["x0"] - t["x1"]
                            
                            # If gap is very small, likely fragments of same word
                            if gap < 3.0: 
                                separator = ""
                                # print(f"MERGE RTL: '{prev_t['text']}' - '{t['text']}' (Gap={gap:.2f})")
                            else:
                                # print(f"SPACE RTL: '{prev_t['text']}' - '{t['text']}' (Gap={gap:.2f})")
                                pass
                        else:
                            # LTR: Sort Ascending X. T[idx-1] is Left, T[idx] is Right.
                            # Gap = RightToken.LeftEdge - LeftToken.RightEdge
                            gap = t["x0"] - prev_t["x1"]
                            if gap < 2.0: # Stricter for English
                                separator = ""
                        
                        parts.append(separator)
                    
                    parts.append(fixed_text)

                final_text = "".join(p for p in parts if p).strip()
                # if rtl:
                #    print(f"ROW FRAGMENTS: {[t['text'] for t in toks_sorted]} -> FINAL: '{final_text}'")
                
                row_text.append(final_text)
                row_layout.append(CellLayout(final_text, cell_x0, cell_y0, cell_x1, cell_y1))
            
            # Only add non-empty rows? Original code: if any(c.strip() for c in cols_out):
            # If we filter rows, we lose layout alignment with the original PDF?
            # Original code:
            # if any(c.strip() for c in cols_out):
            #     table_rows.append([c.strip() for c in cols_out])
            
            # If we filter empty rows, we must ensure we don't try to overlay them later?
            # Actually, standardizing tables often removes empty separator rows.
            # But for "Reinsertion", if I remove a row from CSV, I won't have it to re-insert.
            # But the re-insertion logic will loop over the CSV.
            # If the visually detected row was empty, I probably want to ignore it or overwrite it with empty.
            
            if any(t.strip() for t in row_text):
                table_rows_text.append(row_text)
                table_rows_layout.append(row_layout)
        
        return table_rows_text, table_rows_layout
    
    @staticmethod
    def save_table_to_csv(table_rows: List[List[str]], output_path: str):
        """Save table data to CSV"""
        if not table_rows:
            return None
        
        df = pd.DataFrame(table_rows)
        df.to_csv(output_path, index=False, header=False, encoding='utf-8-sig')
        return output_path
