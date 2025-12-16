from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import os
import tempfile
from services.ocr_service import extract_arabic_text
from services.translate_service import translate_to_english
from services.pdf_translation_service import translate_pdf_with_layout

app = FastAPI(title="Arabic OCR Translation API")

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {
        "message": "Arabic OCR Translation API is running",
        "endpoints": {
            "/process": "Extract text and translate (returns JSON)",
            "/translate-pdf": "Translate PDF with layout preservation (returns PDF)"
        }
    }

@app.post("/process")
async def process_pdf(file: UploadFile = File(...)):
    """
    Process uploaded PDF file:
    1. Extract Arabic text using OCR
    2. Translate to English
    3. Return both texts
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Create temporary file to save uploaded PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file_path = None
        try:
            # Save uploaded file to temporary location
            content = await file.read()
            
            # Validate file is not empty
            if len(content) == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            
            # Validate it's a valid PDF (check PDF header)
            if not content.startswith(b'%PDF'):
                raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF")
            
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
            tmp_file.flush()
            
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
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            error_msg = str(e)
            # Provide more helpful error messages
            if "encrypted" in error_msg.lower():
                raise HTTPException(status_code=400, detail="PDF is encrypted. Please provide an unencrypted PDF.")
            elif "corrupted" in error_msg.lower() or "invalid" in error_msg.lower():
                raise HTTPException(status_code=400, detail="PDF appears to be corrupted or invalid.")
            elif "empty" in error_msg.lower():
                raise HTTPException(status_code=400, detail="PDF file is empty.")
            else:
                raise HTTPException(status_code=500, detail=f"Error processing PDF: {error_msg}")
        finally:
            # Clean up temporary file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass

@app.post("/translate-pdf")
async def translate_pdf_endpoint(file: UploadFile = File(...)):
    """
    Translate PDF from Arabic to English with layout preservation.
    Returns a new PDF file with translated content.
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    # Create temporary files
    input_pdf_path = None
    output_pdf_path = None
    
    try:
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_input:
            content = await file.read()
            
            if len(content) == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            
            if not content.startswith(b'%PDF'):
                raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF")
            
            tmp_input.write(content)
            input_pdf_path = tmp_input.name
            tmp_input.flush()
        
        # Create output PDF path
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_output:
            output_pdf_path = tmp_output.name
        
        # Translate PDF with layout
        stats = translate_pdf_with_layout(input_pdf_path, output_pdf_path)
        
        # Return the translated PDF
        return FileResponse(
            output_pdf_path,
            media_type='application/pdf',
            filename='translated_english.pdf',
            headers={
                'X-Translation-Stats': f"pages={stats['pages_processed']}, "
                                      f"blocks={stats['text_blocks_translated']}, "
                                      f"tables={stats['tables_translated']}"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        raise HTTPException(status_code=500, detail=f"Error translating PDF: {error_msg}")
    finally:
        # Clean up input file
        if input_pdf_path and os.path.exists(input_pdf_path):
            try:
                os.unlink(input_pdf_path)
            except:
                pass
        # Note: output file will be deleted after response is sent
        # For production, you might want to keep it temporarily or use a cleanup task

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

