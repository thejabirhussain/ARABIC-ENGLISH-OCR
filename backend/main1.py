# main.py
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
import uuid
import zipfile
import io

from services.extraction.detector import detect_all_tables
from services.extraction.extractor import extract_tables_from_pdf
from services.translation.translator import ArabicTranslator
from services.translation.processor import translate_all_tables

app = FastAPI()

# Directories
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
EXTRACTED_DIR = BASE_DIR / "tables" / "extracted"
TRANSLATED_DIR = BASE_DIR / "tables" / "translated"

for d in [UPLOAD_DIR, EXTRACTED_DIR, TRANSLATED_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Load translation model once at startup (efficient!)
translator = None

@app.on_event("startup")
async def startup_event():
    """Load heavy translation model once on server start"""
    global translator
    print("🚀 Loading translation model...")
    translator = ArabicTranslator()
    print("✅ Translation model ready!")


@app.post("/extract-and-translate")
async def extract_and_translate(file: UploadFile = File(...)):
    """
    Single API endpoint - ONE CLICK DOES EVERYTHING:
    1. Upload PDF
    2. Auto-detect all tables
    3. Extract tables to CSV
    4. Auto-translate all extracted tables
    """
    file_id = str(uuid.uuid4())
    pdf_path = UPLOAD_DIR / f"{file_id}.pdf"
    
    # Step 1: Save PDF
    print(f"[1/4] 📄 Uploading PDF: {file_id}")
    with open(pdf_path, "wb") as f:
        f.write(await file.read())
    
    # Step 2: Auto-detect tables
    print(f"[2/4] 🔍 Detecting tables...")
    table_configs = detect_all_tables(str(pdf_path), file_id)
    print(f"       Found {len(table_configs)} tables")
    
    # Step 3: Extract to CSV
    print(f"[3/4] 📊 Extracting tables...")
    extracted_files = extract_tables_from_pdf(
        str(pdf_path), 
        table_configs, 
        str(EXTRACTED_DIR),
        file_id
    )
    print(f"       Extracted {len(extracted_files)} CSV files")
    
    # Step 4: Auto-translate (your batch processor logic)
    print(f"[4/4] 🌐 Translating tables...")
    translated_files = translate_all_tables(
        extracted_files,
        str(TRANSLATED_DIR),
        translator
    )
    print(f"       Translated {len(translated_files)} files")
    
    return {
        "status": "success",
        "file_id": file_id,
        "workflow": {
            "tables_detected": len(table_configs),
            "tables_extracted": len(extracted_files),
            "tables_translated": len(translated_files)
        },
        "output": {
            "extracted_csvs": [f.name for f in extracted_files],
            "translated_csvs": [f.name for f in translated_files]
        }
    }


@app.get("/download-results/{file_id}")
async def download_results(file_id: str, translated_only: bool = True):
    """
    Download all translated CSVs as a ZIP file
    """
    folder = TRANSLATED_DIR if translated_only else EXTRACTED_DIR
    files = list(folder.glob(f"{file_id}_table_*"))
    
    if not files:
        return JSONResponse({"error": "No files found"}, status_code=404)
    
    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in files:
            zip_file.write(file_path, file_path.name)
    
    zip_buffer.seek(0)
    
    return Response(
        content=zip_buffer.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={file_id}_results.zip"}
    )
