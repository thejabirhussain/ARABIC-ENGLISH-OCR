from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import JSONResponse
from services.ocr_service import extract_arabic_text
from services.translate_service import translate_to_english
from utils.validators import validate_pdf
from utils.file_utils import temporary_file

router = APIRouter()

@router.post("/process")
async def process_pdf(file: UploadFile = File(...)):
    """
    Process uploaded PDF file:
    1. Extract Arabic text using OCR
    2. Translate to English
    3. Return both texts
    """
    try:
        # Validate and read content
        content = await validate_pdf(file)
        
        # Use context manager for temp file handling
        with temporary_file(content, suffix='.pdf') as tmp_file_path:
            # Extract Arabic text using OCR
            arabic_text = extract_arabic_text(tmp_file_path)
            
            if not arabic_text or not arabic_text.strip():
                raise HTTPException(
                    status_code=400, 
                    detail="No Arabic text could be extracted from the PDF. Please ensure the PDF contains readable Arabic text."
                )
            
            # Translate to English
            english_text = translate_to_english(arabic_text)
            
            return JSONResponse(
                status_code=200,
                content={
                    "arabic_text": arabic_text,
                    "english_text": english_text
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        # Let the global handler catch it, or re-raise generic
        raise e
