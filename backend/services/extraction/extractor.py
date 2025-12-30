import pandas as pd
import pdfplumber
from pathlib import Path

def extract_tables_from_pdf(pdf_path: str, table_configs: list, output_dir: str, file_id: str):
    """
    Extract tables based on configs and save to CSV
    """
    extracted_files = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for idx, cfg in enumerate(table_configs, 1):
            page = pdf.pages[cfg["page"]]
            
            # Get bbox and columns
            x0, y0, x1, y1 = cfg["bbox"]
            col_bounds = sorted(cfg["columns"])
            
            # Ensure bbox edges in columns
            if col_bounds[0] > x0:
                col_bounds.insert(0, x0)
            if col_bounds[-1] < x1:
                col_bounds.append(x1)
            
            # Extract words in bbox
            all_words = page.extract_words()
            words = [
                w for w in all_words 
                if (w["x1"] > x0 and w["x0"] < x1 and
                    w["bottom"] > y0 and w["top"] < y1)
            ]
            
            # Build table from words
            if words:
                table_rows = words_to_table(words, col_bounds, y_tolerance=8.0)
            else:
                table_rows = []
            
            # Save to CSV
            n_cols = len(col_bounds) - 1
            if table_rows and len(table_rows[0]) == n_cols:
                df = pd.DataFrame(table_rows)
            else:
                df = pd.DataFrame([[""] * n_cols])
            
            csv_path = Path(output_dir) / f"{file_id}_table_{idx}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8-sig")
            extracted_files.append(csv_path)
            
            print(f"Extracted table {idx} from page {cfg['page']}: {csv_path}")
    
    return extracted_files

# Copy your words_to_table function and helper functions here
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
