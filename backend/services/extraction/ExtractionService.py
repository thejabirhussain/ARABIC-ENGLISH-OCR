# main.py
import os
import uuid
from typing import List, Dict

import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

import logging
import re

from collections import defaultdict
import numpy as np

# ==== Basic setup ====

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
IMG_DIR = os.path.join(BASE_DIR, "page_images")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

for d in [UPLOAD_DIR, IMG_DIR, OUTPUT_DIR]:
    os.makedirs(d, exist_ok=True)

# In-memory registries (for demo; in prod, store in DB)
PDF_FILES: Dict[str, str] = {}          # file_id -> pdf_path
TABLE_CONFIGS: Dict[str, List[dict]] = {}  # file_id -> list of table configs


logger = logging.getLogger("pdf_debug")
logging.basicConfig(level=logging.INFO)

# ==== Models ====

class TableConfig(BaseModel):
    page: int
    bbox: List[float]      # [x0, y0, x1, y1] in image coordinates
    columns: List[float]   # [x0, x1, ...] vertical lines in image coordinates
    img_width: float
    img_height: float

# ==== Utility functions ====

def fix_rtl(text: str) -> str:
    tokens = text.split()
    fixed = []
    for t in tokens:
        if any('\u0600' <= ch <= '\u06FF' for ch in t):  # Arabic range
            fixed.append(t[::-1])  # reverse Arabic token
        else:
            fixed.append(t)       # keep numbers / Latin as is
    return " ".join(fixed)

def render_page_to_image(pdf_path: str, page_num: int, file_id: str) -> str:
    """
    Render the given page to PNG and return image path.
    """
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    pix = page.get_pixmap(dpi=120)
    img_path = os.path.join(IMG_DIR, f"{file_id}_page_{page_num}.png")
    pix.save(img_path)
    logger.info(f"RENDER page={page_num} img_size={pix.width}x{pix.height}")
    doc.close()
    return img_path


def image_to_pdf_coords(img_x: float, img_y: float, img_w: float, img_h: float,
                        pdf_w: float, pdf_h: float):
    """
    Map image coordinates back to PDF coordinates (no rotation, uniform scale).
    """
    scale_x = pdf_w / img_w
    scale_y = pdf_h / img_h
    return img_x * scale_x, img_y * scale_y

ARABIC_BLOCKS = [
    (0x0600, 0x06FF), (0x0750, 0x077F),
    (0x08A0, 0x08FF), (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
]
ARABIC_INDIC_DIGITS = ''.join(chr(c) for c in range(0x0660, 0x066A))

def has_arabic_letter(s: str) -> bool:
    for ch in s:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in ARABIC_BLOCKS):
            # exclude tatweel and punctuation if needed, but keep letters here
            return True
    return False

def has_any_digit(s: str) -> bool:
    return any(ch.isdigit() or ch in ARABIC_INDIC_DIGITS for ch in s)

def fix_token_text(tok: str) -> str:
    # Reverse only Arabic-letters tokens that do NOT contain digits
    if has_arabic_letter(tok) and not has_any_digit(tok):
        return tok[::-1]
    return tok  # numbers and mixed tokens left as-is

def column_is_rtl(tokens_in_col) -> bool:
    # Decide RTL if majority tokens have Arabic letters and are not numeric
    arabic_word_count = sum(1 for t in tokens_in_col
                            if has_arabic_letter(t["text"]) and not has_any_digit(t["text"]))
    # Use a simple majority threshold
    return arabic_word_count >= max(1, len(tokens_in_col) // 2)

def words_to_table(words, col_bounds_pdf, y_tolerance=8.0):
    if not words:
        return []

    # Sort by Y (line) then X
    words_sorted = sorted(words, key=lambda w: (round(w["top"], 1), w["x0"]))

    # Group by Y
    rows, current_row, current_y = [], [], None
    for w in words_sorted:
        if current_y is None or abs(w["top"] - current_y) <= y_tolerance:
            current_row.append(w)
            current_y = w["top"] if current_y is None else current_y
        else:
            rows.append(current_row)
            current_row, current_y = [w], w["top"]
    if current_row:
        rows.append(current_row)

    n_cols = len(col_bounds_pdf) - 1
    table_rows = []

    for row_words in rows:
        # Collect tokens per column first
        col_tokens = [[] for _ in range(n_cols)]
        for w in row_words:
            x_center = (w["x0"] + w["x1"]) / 2
            for i in range(n_cols):
                if col_bounds_pdf[i] <= x_center <= col_bounds_pdf[i + 1]:
                    col_tokens[i].append({"text": w["text"].strip(), "x": x_center})
                    break

        # Decide direction per column and build text
        cols_out = []
        for i in range(n_cols):
            toks = col_tokens[i]
            if not toks:
                cols_out.append("")
                continue

            rtl = column_is_rtl(toks)
            toks_sorted = sorted(toks, key=lambda t: t["x"], reverse=rtl)
            parts = [fix_token_text(t["text"]) for t in toks_sorted]
            cols_out.append(" ".join(p for p in parts if p))

        if any(c.strip() for c in cols_out):
            table_rows.append([c.strip() for c in cols_out])

    return table_rows

# ==== Routes ====
@app.post("/auto-detect-tables/{file_id}")
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


@app.get("/", response_class=HTMLResponse)
def index():
    """
    Just a simple landing response (frontend is served separately).
    """
    return "<h1>PDF Table Extractor API</h1>"


@app.post("/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF and return a file_id.
    """
    file_id = str(uuid.uuid4())
    pdf_path = os.path.join(UPLOAD_DIR, f"{file_id}.pdf")
    with open(pdf_path, "wb") as f:
        f.write(await file.read())

    PDF_FILES[file_id] = pdf_path

    # Get page count
    doc = fitz.open(pdf_path)
    page_count = doc.page_count
    doc.close()

    return {"file_id": file_id, "page_count": page_count}


@app.get("/page-image/{file_id}/{page_num}")
def get_page_image(file_id: str, page_num: int):
    """
    Return the rendered PNG of a page.
    """
    if file_id not in PDF_FILES:
        return JSONResponse({"error": "Unknown file_id"}, status_code=404)

    pdf_path = PDF_FILES[file_id]
    img_path = render_page_to_image(pdf_path, page_num, file_id)
    return FileResponse(img_path, media_type="image/png")


@app.get("/page-metadata/{file_id}/{page_num}")
def page_metadata(file_id: str, page_num: int):
    """
    Return PDF page width/height in points.
    """
    if file_id not in PDF_FILES:
        return JSONResponse({"error": "Unknown file_id"}, status_code=404)

    pdf_path = PDF_FILES[file_id]
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    w, h = page.rect.width, page.rect.height
    doc.close()
    return {"pdf_width": w, "pdf_height": h}


@app.post("/save-table/{file_id}")
def save_table(file_id: str, config: TableConfig):
    """
    Save one table config (interactive input from frontend).
    """
    if file_id not in PDF_FILES:
        return JSONResponse({"error": "Unknown file_id"}, status_code=404)

    logger.info(f"SAVE_TABLE page={config.page} bbox_img={config.bbox} cols_img={config.columns}")

    logger.info(
        f"SAVE_TABLE page={config.page} "
        f"bbox_img={config.bbox} cols_img={config.columns} "
        f"img_size={config.img_width}x{config.img_height}"
    )

    TABLE_CONFIGS.setdefault(file_id, []).append(config.dict())
    return {"status": "ok", "file_id": file_id, "tables_for_file": len(TABLE_CONFIGS[file_id])}


@app.get("/list-tables/{file_id}")
def list_tables(file_id: str):
    """
    List stored table configs for a file.
    """
    return {"file_id": file_id, "tables": TABLE_CONFIGS.get(file_id, [])}



@app.post("/extract-tables/{file_id}")
def extract_tables(file_id: str):
    """
    For each saved table config:
    - Take the bbox and column lines
    - Extract words within bbox using pdfplumber.page.words
    - Group words into rows/columns using words_to_table
    - Save proper multi-row CSV per table
    """
    if file_id not in PDF_FILES:
        return JSONResponse({"error": "Unknown file_id"}, status_code=404)

    pdf_path = PDF_FILES[file_id]
    configs = TABLE_CONFIGS.get(file_id, [])
    if not configs:
        return JSONResponse({"error": "No table configs for this file"}, status_code=400)

    csv_paths = []
    with pdfplumber.open(pdf_path) as pdf:
        for idx, cfg in enumerate(configs, 1):
            page = pdf.pages[cfg["page"]]
            pdf_w, pdf_h = page.width, page.height
            img_w, img_h = cfg["img_width"], cfg["img_height"] # 1:1 scale

            # Convert bbox from image coords to PDF coords (unchanged)
            x0_pdf, y0_pdf = image_to_pdf_coords(cfg["bbox"][0], cfg["bbox"][1], img_w, img_h, pdf_w, pdf_h)
            x1_pdf, y1_pdf = image_to_pdf_coords(cfg["bbox"][2], cfg["bbox"][3], img_w, img_h, pdf_w, pdf_h)

            col_bounds_pdf = []
            for x_img in cfg["columns"]:
                x_pdf, _ = image_to_pdf_coords(x_img, 0, img_w, img_h, pdf_w, pdf_h)
                x_pdf = max(x0_pdf, min(x_pdf, x1_pdf))
                col_bounds_pdf.append(x_pdf)

            # Clamp bbox to page bounds (unchanged)
            x0_pdf = max(0, min(x0_pdf, pdf_w))
            x1_pdf = max(0, min(x1_pdf, pdf_w))
            y0_pdf = max(0, min(y0_pdf, pdf_h))
            y1_pdf = max(0, min(y1_pdf, pdf_h))

            logger.info(f"TABLE {idx} bbox PDF coords: ({x0_pdf:.2f}, {y0_pdf:.2f}, {x1_pdf:.2f}, {y1_pdf:.2f})")

            if x1_pdf <= x0_pdf or y1_pdf <= y0_pdf:
                continue

            # Convert column bounds to PDF (unchanged)
            col_bounds_pdf = []
            for x_img in cfg["columns"]:
                x_pdf, _ = image_to_pdf_coords(x_img, 0, img_w, img_h, pdf_w, pdf_h)
                x_pdf = max(x0_pdf, min(x_pdf, x1_pdf))
                col_bounds_pdf.append(x_pdf)

            col_bounds_pdf = sorted(col_bounds_pdf)
            if not col_bounds_pdf:
                logger.warning(f"TABLE {idx} has no column lines, skipping")
                continue

            # Ensure bbox edges included (unchanged)
            if col_bounds_pdf[0] > x0_pdf:
                col_bounds_pdf.insert(0, x0_pdf)
            if col_bounds_pdf[-1] < x1_pdf:
                col_bounds_pdf.append(x1_pdf)

            logger.info(f"TABLE {idx} col bounds PDF: {[f'{x:.2f}' for x in col_bounds_pdf]}")

            # *** NEW: Extract words within bbox and build table ***
            bbox_tuple = (x0_pdf, y0_pdf, x1_pdf, y1_pdf)
            all_words = page.extract_words() # Get ALL words from page
            
            words = [
                w for w in all_words 
                if (w["x1"] > x0_pdf and w["x0"] < x1_pdf and  # Overlaps X bounds
                    w["bottom"] > y0_pdf and w["top"] < y1_pdf) # Overlaps Y bounds
            ]

            debug_words = [
                {"text": w["text"], "x0": w["x0"], "y": w["top"]}
                for w in words
            ]
            logger.info(f"TABLE {idx} sample words: {debug_words[:20]}")

            logger.info(f"TABLE {idx} found {len(words)} words in bbox (from {len(all_words)} total)")
            logger.info(f"TABLE {idx} found {len(words)} words in bbox")
            
            if words:
                table_rows = words_to_table(words, col_bounds_pdf, y_tolerance=8.0)
                logger.info(f"TABLE {idx} produced {len(table_rows)} rows")
            else:
                logger.warning(f"TABLE {idx} no words found in bbox")
                table_rows = []

            # Create DataFrame (handles empty case)
            n_cols = len(col_bounds_pdf) - 1
            if table_rows and len(table_rows[0]) == n_cols:
                df = pd.DataFrame(table_rows)
            else:
                df = pd.DataFrame([[""] * n_cols])  # Single empty row fallback

            csv_path = os.path.join(OUTPUT_DIR, f"{file_id}_table_{idx}.csv")
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            csv_paths.append(csv_path)

    return {"file_id": file_id, "tables_extracted": len(csv_paths), "csv_paths": csv_paths}


@app.get("/debug-blue/{file_id}/{page_num}")
def debug_blue(file_id: str, page_num: int):
    if file_id not in PDF_FILES:
        return JSONResponse({"error": "Unknown file_id"}, status_code=404)

    pdf_path = PDF_FILES[file_id]
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]

        # Hard-code a bbox that *visually matches* the blue column region,
        # by manually experimenting until you see a clean result.
        # Example numbers - you will need to tweak them based on your PDF:
        x0_pdf = 400
        x1_pdf = 550
        y0_pdf = 250
        y1_pdf = 600

        col_page = page.crop((x0_pdf, y0_pdf, x1_pdf, y1_pdf))
        text = col_page.extract_text(layout=True) or ""
        # Save out to a debug file
        debug_path = os.path.join(OUTPUT_DIR, f"{file_id}_debug_blue.txt")
        with open(debug_path, "w", encoding="utf-8") as f:
            f.write(text)
    return {"debug_blue_path": debug_path}
