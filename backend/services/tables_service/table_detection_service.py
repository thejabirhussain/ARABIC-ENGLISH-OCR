from typing import List
from collections import defaultdict
import logging

# Local imports
from .pdf_handler import PDFHandler
from .models import TableConfig, BoundingBox

logger = logging.getLogger(__name__)

class TableDetectionService:
    """Service for detecting tables in PDFs"""
    
    def __init__(self):
        self.pdf_handler = PDFHandler()
    
    def detect_all_tables(self, pdf_path: str) -> List[TableConfig]:
        """Detect all tables in PDF"""
        all_configs = []
        page_count = self.pdf_handler.get_page_count(pdf_path)
        
        for page_num in range(page_count):
            page_configs = self.detect_tables_on_page(pdf_path, page_num)
            all_configs.extend(page_configs)
            logger.info(f"Page {page_num}: Detected {len(page_configs)} tables")
        
        return all_configs
    
    def detect_tables_on_page(self, pdf_path: str, page_num: int) -> List[TableConfig]:
        """Detect tables on a specific page"""
        words = self.pdf_handler.extract_words_from_page(pdf_path, page_num)
        pdf_w, pdf_h = self.pdf_handler.get_page_dimensions(pdf_path, page_num)
        
        # Step 1: Detect table regions
        table_regions = self._detect_table_regions(words, pdf_h)
        logger.info(f"Initial regions detected: {len(table_regions)}")
        
        # Step 2: Split wide regions (using your proven logic)
        split_regions = []
        for reg in table_regions:
            splits = self._split_region_horizontally(reg, words, min_gap_ratio=0.10)
            split_regions.extend(splits)
        
        logger.info(f"After splitting: {len(split_regions)} tables")
        
        # Step 3: Create configs
        configs = []
        for idx, region in enumerate(split_regions):
            region_words = [w for w in words if self._is_in_region(w, region)]
            columns = self._detect_columns(region_words, region)
            
            # Filter: A valid table must have at least 2 columns (1 internal separator)
            num_cols = len(columns) - 1
            if num_cols < 2:
                logger.info(f"Ignoring Region {idx} (bbox={region['x0']:.1f},{region['y0']:.1f}): Only 1 column (likely paragraph)")
                continue

            logger.info(f"Table {idx+1}: bbox=({region['x0']:.1f}, {region['y0']:.1f}, {region['x1']:.1f}, {region['y1']:.1f}), columns={num_cols}")
            
            configs.append(TableConfig(
                page=page_num,
                bbox=BoundingBox(
                    x0=region['x0'],
                    y0=region['y0'],
                    x1=region['x1'],
                    y1=region['y1']
                ),
                columns=columns,
                img_width=pdf_w,
                img_height=pdf_h
            ))
        
        return configs
    
    def _split_region_horizontally(self, region, all_page_words, min_gap_ratio=0.10):
        """
        Split a wide region into (at most) two table regions by finding one
        dominant vertical 'valley' in word density.
        
        This is your ORIGINAL proven logic - preserves all heuristics!
        """
        all_rows = region["rows"]
        # Flatten rows to a list of words for histogram
        words = [w for row in all_rows for w in row] 
        # Note: Original code logic: words = [w for row in all_rows for w in row]
        # But 'all_rows' in _detect_table_regions stores lists of words. Correct.

        if not words:
            return [region]
        
        x0, x1 = region["x0"], region["x1"]
        width = x1 - x0
        if width <= 0:
            return [region]
        
        # Only split very wide bands
        if width < 300:
            return [region]
        
        # === Build density histogram ===
        num_bins = 60
        bin_size = width / num_bins
        counts = [0] * num_bins
        
        for w in words:
            xc = (w["x0"] + w["x1"]) / 2
            if xc < x0 or xc > x1:
                continue
            idx = int((xc - x0) / bin_size)
            idx = max(0, min(num_bins - 1, idx))
            counts[idx] += 1
        
        max_count = max(counts) if counts else 0
        if max_count == 0:
            return [region]
        
        threshold = max_count * min_gap_ratio
        valley_bins = [i for i, c in enumerate(counts) if c <= threshold]
        if not valley_bins:
            return [region]
        
        # === Check left/center/right density ===
        center_bin = num_bins // 2
        left_bins = range(0, center_bin)
        right_bins = range(center_bin, num_bins)
        
        left_max = max(counts[i] for i in left_bins) if left_bins else 0
        right_max = max(counts[i] for i in right_bins) if right_bins else 0
        center_max = max(counts[center_bin-1:center_bin+2]) if num_bins >= 3 else max_count
        
        # If center is nearly as dense as sides, treat as single table
        if center_max >= 0.7 * max(left_max, right_max):
            logger.debug(f"Center dense (center={center_max}, left={left_max}, right={right_max}) → single table")
            return [region]
        
        # === Group contiguous valley bins ===
        split_xs = []
        start = valley_bins[0]
        prev = start
        for b in valley_bins[1:]:
            if b == prev + 1:
                prev = b
            else:
                mid_bin = (start + prev) / 2.0
                split_xs.append(x0 + (mid_bin + 0.5) * bin_size)
                start = prev = b
        mid_bin = (start + prev) / 2.0
        split_xs.append(x0 + (mid_bin + 0.5) * bin_size)
        
        if not split_xs:
            return [region]
        
        # === Choose best split near center ===
        mid_region = (x0 + x1) / 2.0
        best_split = min(split_xs, key=lambda x: abs(x - mid_region))
        dist_from_center = abs(best_split - mid_region) / width
        
        # Measure valley depth
        best_bin = int((best_split - x0) / bin_size)
        best_bin = max(0, min(num_bins - 1, best_bin))
        valley_depth = 1.0 - (counts[best_bin] / max_count if max_count else 0.0)
        
        logger.debug(f"Split candidate: x={best_split:.1f}, depth={valley_depth:.2f}, dist_from_center={dist_from_center:.2f}")
        
        # Heuristics: Split only if valley is deep enough AND near the middle
        if valley_depth < 0.6 or dist_from_center > 0.25:
            logger.debug("→ Weak valley or off-center → single table")
            return [region]
        
        # === ROW ALIGNMENT CHECK (the key difference!) ===
        left_side_words = [w for w in words if (w["x0"] + w["x1"]) / 2 < best_split]
        right_side_words = [w for w in words if (w["x0"] + w["x1"]) / 2 >= best_split]
        
        left_y_positions = sorted(set(round(w["top"], 1) for w in left_side_words))
        right_y_positions = sorted(set(round(w["top"], 1) for w in right_side_words))
        
        # Count EXACT matches with strict tolerance
        exact_matches = 0
        for ly in left_y_positions:
            if any(abs(ly - ry) <= 2.0 for ry in right_y_positions):
                exact_matches += 1
        
        # Calculate match ratio for SMALLER side
        smaller_row_count = min(len(left_y_positions), len(right_y_positions))
        exact_match_ratio = exact_matches / max(1, smaller_row_count)
        
        # Check row count balance
        row_count_ratio = smaller_row_count / max(1, max(len(left_y_positions), len(right_y_positions)))
        
        logger.debug(f"[ROW-ALIGN] left_rows={len(left_y_positions)} right_rows={len(right_y_positions)} "
                    f"exact_matches={exact_matches} exact_ratio={exact_match_ratio:.2f} row_balance={row_count_ratio:.2f}")
        
        # Single table requires:
        # 1. >80% of rows have EXACT Y-alignment (shared baseline) AND
        # 2. Row counts are similar (>60% balance)
        if exact_match_ratio > 0.80 and row_count_ratio > 0.60:
            logger.info("→ ROWS ALIGN: single table")
            return [region]
        
        logger.info("→ ROWS INDEPENDENT: split into 2 tables")
        
        # === Create subregions ===
        subregions = []
        for sx0, sx1 in [(x0, best_split), (best_split, x1)]:
            if sx1 - sx0 < 250:
                continue
            
            sub_rows = []
            for row in all_rows:
                rw = [w for w in row if w["x1"] > sx0 and w["x0"] < sx1]
                if rw:
                    sub_rows.append(rw)
            
            if sub_rows:
                subregions.append({
                    "x0": sx0,
                    "x1": sx1,
                    "y0": region["y0"],
                    "y1": region["y1"],
                    "rows": sub_rows,
                    "confidence": region.get("confidence", 0.8),
                })
        
        return subregions or [region]
    
    def _detect_table_regions(self, words, page_height, min_rows=3, row_tolerance=12):
        """Detect rectangular regions with table-like content"""
        if not words:
            return []
        
        # Group words into rows by Y position
        rows = defaultdict(list)
        for w in words:
            y_key = round(w['top'] / row_tolerance) * row_tolerance
            rows[y_key].append(w)
        
        sorted_rows = sorted(rows.items())
        regions = []
        current_region = None
        
        for y, row_words in sorted_rows:
            if len(row_words) >= 2:
                x_span = max(w['x1'] for w in row_words) - min(w['x0'] for w in row_words)
                
                if x_span > 200:  # Minimum table width
                    if current_region is None:
                        current_region = {
                            'x0': min(w['x0'] for w in row_words),
                            'x1': max(w['x1'] for w in row_words),
                            'y0': y,
                            'y1': y + row_tolerance,
                            'rows': [row_words]
                        }
                    else:
                        if y - current_region['y1'] < row_tolerance * 2:
                            current_region['x0'] = min(current_region['x0'], min(w['x0'] for w in row_words))
                            current_region['x1'] = max(current_region['x1'], max(w['x1'] for w in row_words))
                            current_region['y1'] = y + row_tolerance
                            current_region['rows'].append(row_words)
                        else:
                            if len(current_region['rows']) >= min_rows:
                                regions.append(current_region)
                            current_region = {
                                'x0': min(w['x0'] for w in row_words),
                                'x1': max(w['x1'] for w in row_words),
                                'y0': y,
                                'y1': y + row_tolerance,
                                'rows': [row_words]
                            }
            else:
                if current_region and len(current_region['rows']) >= min_rows:
                    regions.append(current_region)
                current_region = None
        
        if current_region and len(current_region['rows']) >= min_rows:
            regions.append(current_region)
        
        return regions
    
    def _detect_columns(self, words, region):
        """Detect column boundaries"""
        if not words:
            return [region['x0'], region['x1']]
        
        x_positions = []
        for w in words:
            x_positions.append(w['x0'])
            x_positions.append(w['x1'])
        
        x_positions = sorted(set(x_positions))
        
        gaps = []
        for i in range(len(x_positions) - 1):
            gap_size = x_positions[i+1] - x_positions[i]
            # Increased threshold from 6 to 15 to avoid detecting 'rivers' in justified text as columns
            if gap_size > 15:  # Minimum gap threshold
                gap_center = (x_positions[i] + x_positions[i+1]) / 2
                crossing_words = [w for w in words if w['x0'] < gap_center < w['x1']]
                if len(crossing_words) == 0:
                    gaps.append(gap_center)
        
        columns = [region['x0']] + gaps + [region['x1']]
        
        # Remove columns too close together
        filtered = [columns[0]]
        for col in columns[1:]:
            if col - filtered[-1] > 18:
                filtered.append(col)
        
        return sorted(filtered)
    
    def _is_in_region(self, word, region):
        """Check if word overlaps with region"""
        return (word['x0'] < region['x1'] and word['x1'] > region['x0'] and
                word['top'] < region['y1'] and word['bottom'] > region['y0'])
