# PDF Translation Architecture

## Overview

This system extends the basic Arabic OCR → English translation to handle complex financial PDFs with layout preservation.

## Architecture

```
┌─────────────────┐
│   FastAPI App   │
│   main.py       │
└────────┬────────┘
         │
         ├─── /process (existing)
         │    └─── Returns JSON with text
         │
         └─── /translate-pdf (new)
              └─── Returns translated PDF
                   │
                   └─── pdf_translation_service.py
                        │
                        ├─── layout_extraction_service.py
                        │    ├─── pdfplumber (text-based)
                        │    └─── pytesseract (scanned)
                        │
                        ├─── table_extraction_service.py
                        │    ├─── Camelot (text-based tables)
                        │    ├─── pdfplumber (fallback)
                        │    └─── OCR-based detection
                        │
                        ├─── translate_service.py (existing)
                        │
                        └─── pdf_renderer_service.py
                             └─── ReportLab
```

## Services

### 1. Layout Extraction Service (`layout_extraction_service.py`)

**Purpose**: Extract text blocks with bounding boxes from PDFs.

**Methods**:
- `extract_text_blocks_with_layout()`: Main entry point
- `_group_words_into_blocks()`: Groups words into text blocks
- `_extract_with_ocr()`: OCR-based extraction with bounding boxes
- `normalize_arabic_numerals()`: Converts ٠-٩ to 0-9

**Handles**:
- Text-based PDFs (pdfplumber)
- Scanned PDFs (pytesseract with TSV output)
- Mixed PDFs

### 2. Table Extraction Service (`table_extraction_service.py`)

**Purpose**: Extract tables with cell-level content and positions.

**Methods**:
- `extract_tables_from_pdf()`: Main entry point
- `_extract_tables_with_pdfplumber()`: Fallback method
- `extract_tables_from_ocr()`: OCR-based table detection
- `_detect_table_structure()`: Detects table structure from blocks

**Handles**:
- Text-based tables (Camelot)
- OCR-based tables (bounding box analysis)
- Complex layouts

### 3. PDF Translation Service (`pdf_translation_service.py`)

**Purpose**: Orchestrates the entire translation pipeline.

**Flow**:
1. Extract text blocks with layout
2. Extract tables
3. Translate text blocks (normalize numerals first)
4. Translate table cells
5. Render new PDF

### 4. PDF Renderer Service (`pdf_renderer_service.py`)

**Purpose**: Render translated content into a new PDF.

**Methods**:
- `render_translated_pdf()`: Main rendering function
- `_render_text_block()`: Renders individual text blocks
- `_render_table()`: Renders tables
- `_get_pdf_page_size()`: Gets original page dimensions

**Features**:
- Preserves page size
- Maintains layout
- Auto-adjusts font size for overflow
- Handles LTR alignment

## Data Structures

### TextBlock
```python
class TextBlock:
    text: str
    x0, y0, x1, y1: float  # Bounding box
    page_num: int
    is_table: bool
```

### TableCell
```python
class TableCell:
    text: str
    row, col: int
    x0, y0, x1, y1: float
    page_num: int
```

### Table
```python
class Table:
    cells: List[TableCell]
    page_num: int
    num_rows: int
    num_cols: int
```

## API Endpoints

### POST /translate-pdf

**Input**: PDF file (multipart/form-data)

**Output**: Translated PDF file

**Process**:
1. Save uploaded PDF
2. Extract layout and text
3. Extract tables
4. Translate content
5. Render new PDF
6. Return PDF file

**Response Headers**:
- `X-Translation-Stats`: Statistics about translation

## Dependencies

- `pdfplumber`: Text extraction with coordinates
- `camelot-py`: Table extraction
- `reportlab`: PDF rendering
- `pytesseract`: OCR with bounding boxes
- `pandas`: Data manipulation for tables

## Limitations

1. **Font Matching**: Currently uses Helvetica. Original fonts not preserved.
2. **Complex Layouts**: Very complex layouts may not be perfectly preserved.
3. **Images**: Images are not translated or preserved.
4. **Handwriting**: Handwritten text not supported.
5. **Multi-column**: Complex multi-column layouts may need refinement.
6. **Table Detection**: OCR-based table detection is basic; can be improved with ML.

## Future Improvements

1. **Font Detection**: Detect and use original fonts
2. **Image Handling**: Preserve and optionally translate images
3. **Better Table Detection**: Use ML models for table structure detection
4. **Layout Analysis**: Use layout analysis models (e.g., LayoutLM)
5. **Caching**: Cache translation results
6. **Batch Processing**: Support multiple PDFs
7. **Progress Tracking**: WebSocket for progress updates
8. **Quality Metrics**: Add translation quality scores

## Example Flow

```
1. User uploads Arabic PDF
   ↓
2. Extract text blocks with coordinates
   ↓
3. Extract tables with cell positions
   ↓
4. Normalize Arabic numerals (٠→0)
   ↓
5. Translate Arabic → English
   ↓
6. Render new PDF with:
   - Original page size
   - Translated text in original positions
   - Translated tables
   ↓
7. Return translated PDF
```

## Testing

Test with:
- Simple text PDFs
- Scanned PDFs
- PDFs with tables
- Financial documents
- Multi-page PDFs

