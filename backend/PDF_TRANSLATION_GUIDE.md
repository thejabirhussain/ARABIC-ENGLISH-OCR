# PDF Translation with Layout Preservation - User Guide

## Overview

The system now supports translating Arabic PDFs to English while preserving the original layout, including:
- Text positioning
- Table structures
- Page dimensions
- Spacing and alignment

## API Endpoints

### 1. Existing Endpoint: `/process`

**Purpose**: Extract and translate text (returns JSON)

**Request**:
```bash
curl -X POST "http://localhost:8000/process" \
  -F "file=@arabic_document.pdf"
```

**Response**:
```json
{
  "arabic_text": "...",
  "english_text": "..."
}
```

### 2. New Endpoint: `/translate-pdf`

**Purpose**: Translate PDF with layout preservation (returns PDF)

**Request**:
```bash
curl -X POST "http://localhost:8000/translate-pdf" \
  -F "file=@arabic_document.pdf" \
  -o translated_english.pdf
```

**Response**: PDF file (`translated_english.pdf`)

**Response Headers**:
- `X-Translation-Stats`: `pages=3, blocks=45, tables=2`

## Features

### ✅ Supported

- Text-based PDFs (native text)
- Scanned PDFs (OCR)
- Mixed PDFs (text + scanned pages)
- Tables (text-based and OCR-detected)
- Arabic numerals → Western numerals (٠→0)
- Multi-page documents
- Layout preservation
- Font size auto-adjustment

### ⚠️ Limitations

- **Fonts**: Uses Helvetica (original fonts not preserved)
- **Images**: Images are not translated or preserved
- **Handwriting**: Not supported
- **Complex Layouts**: Very complex layouts may need manual adjustment
- **Table Detection**: OCR-based table detection is basic

## Installation

Install additional dependencies:

```bash
cd backend
source venv/bin/activate
pip install pdfplumber camelot-py[cv] reportlab pandas
```

**Note**: Camelot requires additional system dependencies:
```bash
# macOS
brew install ghostscript tcl-tk

# Ubuntu/Debian
sudo apt-get install ghostscript python3-tk
```

## Usage Examples

### Python

```python
import requests

# Translate PDF
with open('arabic_document.pdf', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/translate-pdf',
        files={'file': f}
    )
    
    with open('translated.pdf', 'wb') as out:
        out.write(response.content)
    
    # Get statistics
    stats = response.headers.get('X-Translation-Stats')
    print(f"Translation stats: {stats}")
```

### JavaScript/Frontend

```javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('http://localhost:8000/translate-pdf', {
  method: 'POST',
  body: formData
})
.then(response => response.blob())
.then(blob => {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'translated_english.pdf';
  a.click();
});
```

## Processing Flow

1. **Extraction**
   - Text blocks with coordinates (pdfplumber or pytesseract)
   - Tables with cell positions (Camelot or OCR detection)

2. **Normalization**
   - Arabic numerals → Western numerals
   - Text cleaning

3. **Translation**
   - Block-by-block translation
   - Table cell translation
   - Preserves numbers

4. **Rendering**
   - New PDF with original page size
   - Text placed in original positions
   - Tables reconstructed
   - Font size adjusted for overflow

## Troubleshooting

### Camelot Installation Issues

If Camelot fails to install:
```bash
# Install system dependencies first
brew install ghostscript tcl-tk  # macOS
sudo apt-get install ghostscript python3-tk  # Linux

# Then install Camelot
pip install camelot-py[cv]
```

### Table Detection Not Working

- For text-based PDFs: Ensure Camelot is installed
- For scanned PDFs: Table detection uses bounding box analysis (basic)
- Consider pre-processing PDFs to improve table detection

### Layout Issues

- Very complex layouts may need refinement
- Font size auto-adjustment may not always be perfect
- Consider manual post-processing for critical documents

## Performance

- **Small PDFs** (< 10 pages): ~10-30 seconds
- **Medium PDFs** (10-50 pages): ~1-3 minutes
- **Large PDFs** (> 50 pages): ~5-10 minutes

Performance depends on:
- PDF complexity
- Number of tables
- Text length
- Translation model loading time

## Next Steps

1. Test with your financial PDFs
2. Adjust font sizes if needed
3. Refine table detection for your specific use case
4. Consider adding custom fonts
5. Implement caching for repeated translations

