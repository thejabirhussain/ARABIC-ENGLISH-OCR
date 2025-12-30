import fitz
import pdfplumber
from collections import defaultdict

def detect_all_tables(pdf_path: str, file_id: str) -> list:
    """
    Auto-detect tables from all pages in PDF
    Returns list of table configs with bbox and column boundaries
    """
    all_configs = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages):
            words = page.extract_words()
            
            # Detect table regions
            table_regions = detect_table_regions(words, page.height)
            
            # Split wide regions
            split_regions = []
            for reg in table_regions:
                split_regions.extend(
                    split_region_horizontally(reg, pdf_path, page_num)
                )
            
            # Detect columns for each region
            for idx, region in enumerate(split_regions):
                region_words = [w for w in words if is_in_region(w, region)]
                columns = detect_columns(region_words, region)
                
                # Get image dimensions
                doc = fitz.open(pdf_path)
                page_fitz = doc[page_num]
                pix = page_fitz.get_pixmap(dpi=120)
                img_w, img_h = pix.width, pix.height
                doc.close()
                
                # Scale to image coords
                pdf_w, pdf_h = page.width, page.height
                scale_x = img_w / pdf_w
                scale_y = img_h / pdf_h
                
                config = {
                    "page": page_num,
                    "bbox": [
                        region['x0'], region['y0'],
                        region['x1'], region['y1']
                    ],
                    "columns": columns,
                    "img_width": img_w,
                    "img_height": img_h,
                    "pdf_width": pdf_w,
                    "pdf_height": pdf_h
                }
                all_configs.append(config)
    
    return all_configs

# Copy your existing helper functions here:
# - detect_table_regions()
# - split_region_horizontally()
# - detect_columns()
# - is_in_region()

def auto_detect_tables(file_id: str, page_num: int):
    """
    Auto-detect tables and column separators for PDFs without borders.
    Uses word clustering and alignment patterns.
    """
    if file_id not in PDF_FILES:
        return JSONResponse({"error": "Unknown file_id"}, status_code=404)
    
    pdf_path = PDF_FILES[file_id]
    
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        pdf_w, pdf_h = page.width, page.height
        words = page.extract_words()
        
        # Step 1: Detect table regions
        table_regions = detect_table_regions(words, pdf_h)
        
        # Split wide regions horizontally into subregions (multiple tables per band)
        split_regions = []
        for reg in table_regions: 
            split_regions.extend(split_region_horizontally(reg, pdf_path, page_num, min_gap_ratio=0.10))


        # Step 2: For each region, detect column boundaries
        suggestions = []
        for idx, region in enumerate(split_regions):
            region_words = [w for w in words if is_in_region(w, region)]
            columns = detect_columns(region_words, region)
            
            # Convert to image coordinates (assume 1:1 for now, frontend will scale)
            doc = fitz.open(pdf_path)
            page_fitz = doc[page_num]
            pix = page_fitz.get_pixmap(dpi=120)
            img_w, img_h = pix.width, pix.height
            doc.close()
            
            # Scale to image coords
            scale_x = img_w / pdf_w
            scale_y = img_h / pdf_h
            
            bbox_img = [
                region['x0'] * scale_x,
                region['y0'] * scale_y,
                region['x1'] * scale_x,
                region['y1'] * scale_y
            ]
            columns_img = [x * scale_x for x in columns]
            
            suggestions.append({
                "table_index": idx,
                "bbox_pdf": [region['x0'], region['y0'], region['x1'], region['y1']],
                "columns_pdf": columns,
                "bbox_img": bbox_img,
                "columns_img": columns_img,
                "img_width": img_w,
                "img_height": img_h,
                "confidence": region.get('confidence', 0.8)
            })
    
    return {"file_id": file_id, "page": page_num, "tables": suggestions}


def detect_table_regions(words, page_height, min_rows=3, row_tolerance=12):
    """
    Detect rectangular regions with aligned, dense text (likely tables).
    """
    if not words:
        return []
    
    # Group words into rows by Y position
    rows = defaultdict(list)
    for w in words:
        y_key = round(w['top'] / row_tolerance) * row_tolerance
        rows[y_key].append(w)
    
    # Find sequences of rows with similar word counts (table-like)
    sorted_rows = sorted(rows.items())
    regions = []
    current_region = None
    
    for y, row_words in sorted_rows:
        # Check if row has multiple aligned items (table characteristic)
        if len(row_words) >= 2:
            # Check horizontal spread (wide rows suggest table)
            x_span = max(w['x1'] for w in row_words) - min(w['x0'] for w in row_words)
            
            if x_span > 200:  # Minimum table width threshold
                if current_region is None:
                    current_region = {
                        'x0': min(w['x0'] for w in row_words),
                        'x1': max(w['x1'] for w in row_words),
                        'y0': y,
                        'y1': y + row_tolerance,
                        'rows': [row_words]
                    }
                else:
                    # Extend current region if rows are close
                    if y - current_region['y1'] < row_tolerance * 2:
                        current_region['x0'] = min(current_region['x0'], min(w['x0'] for w in row_words))
                        current_region['x1'] = max(current_region['x1'], max(w['x1'] for w in row_words))
                        current_region['y1'] = y + row_tolerance
                        current_region['rows'].append(row_words)
                    else:
                        # Gap too large, save current region and start new
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
            # Single word or gap, close current region if exists
            if current_region and len(current_region['rows']) >= min_rows:
                regions.append(current_region)
            current_region = None
    
    # Don't forget last region
    if current_region and len(current_region['rows']) >= min_rows:
        regions.append(current_region)
    
    return regions

def split_region_horizontally(region, pdf_path: str, page_num: int, min_gap_ratio=0.10):
    """
    Split a wide region into (at most) two table regions by finding one
    dominant vertical 'valley' in word density.
    """
    all_rows = region["rows"]
    words = [w for row in all_rows for w in row]
    if not words:
        return [region]

    x0, x1 = region["x0"], region["x1"]
    width = x1 - x0
    if width <= 0:
        return [region]

    # Only split very wide bands
    if width < 300:
        return [region]

    # === build density histogram (your existing code) ===
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
    
    # --- NEW: collapse counts into left/center/right and check for 2 blocks ---
    center_bin = num_bins // 2
    left_bins = range(0, center_bin)
    right_bins = range(center_bin, num_bins)

    left_max = max(counts[i] for i in left_bins) if left_bins else 0
    right_max = max(counts[i] for i in right_bins) if right_bins else 0
    center_max = max(counts[center_bin-1:center_bin+2]) if num_bins >= 3 else max_count

    # If the center is nearly as dense as sides, treat as single table
    if center_max >= 0.7 * max(left_max, right_max):
        return [region]

    print("density check: left_max", left_max,
      "center_max", center_max, "right_max", right_max)


    # group contiguous valley bins to get centers
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

    print("REGION width:", width, "counts max:", max_count,
          "valley_bins:", valley_bins)
    print("split_xs:", split_xs)

    # === NEW: choose a single best split near the region center ===
        # === NEW: decide whether to split or not ===
    if not split_xs:
        return [region]

    mid_region = (x0 + x1) / 2.0
    best_split = min(split_xs, key=lambda x: abs(x - mid_region))
    dist_from_center = abs(best_split - mid_region) / width  # 0..0.5

    # Measure valley depth at the chosen split bin
    best_bin = int((best_split - x0) / bin_size)
    best_bin = max(0, min(num_bins - 1, best_bin))
    valley_depth = 1.0 - (counts[best_bin] / max_count if max_count else 0.0)

    print("density check: left_max", left_max,
          "center_max", center_max, "right_max", right_max)
    print("REGION width:", width, "counts max:", max_count,
          "valley_bins:", valley_bins)
    print("split_xs:", split_xs, "best_split:", best_split,
          "valley_depth:", valley_depth, "dist_from_center:", dist_from_center)


        # Heuristics:
    # - Split only if valley is deep enough AND near the middle
    if valley_depth < 0.6 or dist_from_center > 0.25:
        print("→ Weak valley or off-center → single table")
        return [region]

# Collect words on left and right sides
# NEW: ROW ALIGNMENT CHECK - do rows span across the split?
    # NEW: STRICT ROW ALIGNMENT CHECK - exact Y-matching
    left_side_words = [w for w in words if (w["x0"] + w["x1"]) / 2 < best_split]
    right_side_words = [w for w in words if (w["x0"] + w["x1"]) / 2 >= best_split]

    left_y_positions = sorted(set(round(w["top"], 1) for w in left_side_words))
    right_y_positions = sorted(set(round(w["top"], 1) for w in right_side_words))

    # NEW: Count EXACT matches with strict tolerance (for truly shared rows)
    exact_matches = 0
    for ly in left_y_positions:
        # For single table, rows should align within 2 points (same baseline)
        if any(abs(ly - ry) <= 2.0 for ry in right_y_positions):
            exact_matches += 1

# Calculate match ratio for SMALLER side (stricter test)
    smaller_row_count = min(len(left_y_positions), len(right_y_positions))
    exact_match_ratio = exact_matches / max(1, smaller_row_count)

# Check row count balance
    row_count_ratio = smaller_row_count / max(1, max(len(left_y_positions), len(right_y_positions)))

    print(f"[ROW-ALIGN] left_rows={len(left_y_positions)} right_rows={len(right_y_positions)} "
          f"exact_matches={exact_matches} exact_ratio={exact_match_ratio:.2f} row_balance={row_count_ratio:.2f}")

# Single table requires:
# 1. >80% of rows have EXACT Y-alignment (shared baseline) AND
# 2. Row counts are similar (>60% balance)
    if exact_match_ratio > 0.80 and row_count_ratio > 0.60:
        print("→ ROWS ALIGN: single table")
        return [region]

    print("→ ROWS INDEPENDENT: split into 2 tables")

        # NEW: VERTICAL GAP CHECK - count words LEFT vs RIGHT of split
    

    subregions = []
    for sx0, sx1 in [(x0, best_split), (best_split, x1)]:
        # keep reasonably wide halves; if too strict, drop to 200
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


def detect_columns(words, region):
    """
    Detect column boundaries using word clustering and whitespace gaps.
    """
    if not words:
        return [region['x0'], region['x1']]
    
    # Collect all word edges (left and right)
    x_positions = []
    for w in words:
        x_positions.append(w['x0'])
        x_positions.append(w['x1'])
    
    x_positions = sorted(set(x_positions))
    
    # Find gaps (whitespace) in X distribution
    gaps = []
    for i in range(len(x_positions) - 1):
        gap_size = x_positions[i+1] - x_positions[i]
        if gap_size > 6:  # Minimum gap threshold for column separator
            # Check if gap spans multiple rows (strong column signal)
            gap_center = (x_positions[i] + x_positions[i+1]) / 2
            crossing_words = [w for w in words if w['x0'] < gap_center < w['x1']]
            if len(crossing_words) == 0:  # No words cross this gap
                gaps.append(gap_center)
    
    # Start with region edges, add detected gaps
    columns = [region['x0']] + gaps + [region['x1']]
    
    # Remove columns that are too close (min spacing 30 points)
    filtered = [columns[0]]
    for col in columns[1:]:
        if col - filtered[-1] > 18:
            filtered.append(col)
    
    return sorted(filtered)


def is_in_region(word, region):
    """Check if word overlaps with region."""
    return (word['x0'] < region['x1'] and word['x1'] > region['x0'] and
            word['top'] < region['y1'] and word['bottom'] > region['y0'])

def is_likely_table_region(region, words) -> bool:
    """
    Filter out paragraph text by checking table characteristics:
    - Multiple distinct vertical columns (>3)
    - Numeric content ratio (tables have numbers)
    - Consistent column spacing
    - Low text-to-space ratio (tables are sparse)
    """
    region_words = [w for w in words if is_in_region(w, region)]
    if not region_words:
        return False
    
    # 1. Check column count (real tables have 3+ distinct columns)
    columns = detect_columns(region_words, region)
    if len(columns) < 4:  # <3 columns + boundaries = likely text
        return False
    
    # 2. Check numeric content (tables have >30% numbers)
    total_chars = sum(len(w['text']) for w in region_words)
    numeric_chars = sum(len([c for c in w['text'] if c.isdigit() or c in '٠١٢٣٤٥٦٧٨٩']) 
                       for w in region_words)
    numeric_ratio = numeric_chars / max(1, total_chars)
    
    if numeric_ratio < 0.15:  # Tables have significant numeric data
        return False
    
    # 3. Check row uniformity (tables have consistent columns per row)
    rows = defaultdict(list)
    for w in region_words:
        y_key = round(w['top'] / 12) * 12
        rows[y_key].append(w)
    
    words_per_row = [len(row) for row in rows.values()]
    if not words_per_row:
        return False
    
    avg_words = sum(words_per_row) / len(words_per_row)
    variance = sum((x - avg_words)**2 for x in words_per_row) / len(words_per_row)
    
    # Tables have low variance (consistent column counts)
    if variance > avg_words * 2:  # High variance = paragraph text
        return False
    
    # 4. Check horizontal spread (tables span >60% page width)
    width = region['x1'] - region['x0']
    if width < 400:  # Narrow region = likely single text column
        return False
    
    return True
