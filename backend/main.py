from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
import os
import tempfile
from services.ocr_service import extract_arabic_text
from services.translate_service import translate_to_english
from services.translate_service import translate_to_english
from services.pdf_translation_service import translate_pdf_with_layout
from services.rag_service import rag_service
from pydantic import BaseModel
import uuid

app = FastAPI(title="Arabic OCR Translation API")

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Document-ID", "X-Translation-Stats"]
)

@app.get("/")
def read_root():
    return {
        "message": "Arabic OCR Translation API is running",
        "endpoints": {
            "/process": "Extract text and translate (returns JSON)",
            "/translate-pdf": "Translate PDF with layout preservation (returns PDF)",
            "/chat": "Chat with the translated document using AI"
        }
    }

class ChatRequest(BaseModel):
    doc_id: str
    query: str

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
        
        # Translate PDF with layout preservation
        stats = translate_pdf_with_layout(input_pdf_path, output_pdf_path)
        
        # Ensure stats has all required keys
        if not stats:
            stats = {
                'pages_processed': 0,
                'text_blocks_translated': 0,
                'tables_translated': 0
            }
        
        # Index content for RAG
        doc_id = str(uuid.uuid4())
        full_text = stats.get('full_text_content', '')
        
        if full_text:
            print(f"Indexing document {doc_id} for RAG...")
            # We run this synchronously for now to ensure it's ready when user wants to chat
            # In production, use BackgroundTasks
            rag_service.index_document(doc_id, full_text)
            print(f"Indexing complete for {doc_id}")
        
        # Return the translated PDF
        return FileResponse(
            output_pdf_path,
            media_type='application/pdf',
            filename='translated_english.pdf',
            headers={
                'X-Translation-Stats': f"pages={stats.get('pages_processed', 0)}, "
                                      f"blocks={stats.get('text_blocks_translated', 0)}, "
                                      f"tables={stats.get('tables_translated', 0)}",
                'X-Document-ID': doc_id
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

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Chat with a translated document using RAG (Ollama + Qdrant).
    """
    try:
        response = rag_service.chat_with_document(request.doc_id, request.query)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

