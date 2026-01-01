from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import uuid
import os
from services.pdf_translation_service import translate_pdf_with_layout
from services.rag_service import rag_service
from utils.validators import validate_pdf
from utils.file_utils import save_content_to_temp, cleanup_file

router = APIRouter()

@router.post("/translate-pdf")
async def translate_pdf_endpoint(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Translate PDF from Arabic to English with layout preservation.
    Returns a new PDF file with translated content.
    """
    input_pdf_path = None
    output_pdf_path = None
    
    try:
        content = await validate_pdf(file)
        
        # Save input file
        input_pdf_path = save_content_to_temp(content, suffix='.pdf')
        # Create placeholder for output
        output_pdf_path = save_content_to_temp(b"", suffix='.pdf')
        
        # Translate PDF with layout preservation
        stats = translate_pdf_with_layout(input_pdf_path, output_pdf_path)
        
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
            rag_service.index_document(doc_id, full_text)
            print(f"Indexing complete for {doc_id}")
        
        # Schedule cleanup of input file (immediate)
        # cleanup_file(input_pdf_path) # Doing it in finally block is safer
        
        # Schedule cleanup of output file after response
        background_tasks.add_task(cleanup_file, output_pdf_path)
        background_tasks.add_task(cleanup_file, input_pdf_path)

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
        
    except Exception as e:
        # Cleanup on error
        cleanup_file(input_pdf_path)
        cleanup_file(output_pdf_path)
        raise e
