from fastapi import APIRouter, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
import uuid
import os
import time
import json
from pathlib import Path
from services.pdf_translation_service import translate_pdf_with_layout
from services.rag_service import rag_service
import pandas as pd
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
    
    # Timing Tracking
    timings = {
        "start": time.time(),
        "upload_processed": 0,
        "translation_complete": 0,
        "vector_indexing_complete": 0
    }
    
    try:
        print(f"\n[START] Processing new PDF translation request")
        
        # 1. Validation & Setup
        content = await validate_pdf(file)
        timings["upload_processed"] = time.time()
        print(f"[STEP] File uploaded and validated ({len(content)} bytes)")
        
        # Save input file
        input_pdf_path = save_content_to_temp(content, suffix='.pdf')
        # Create placeholder for output
        output_pdf_path = save_content_to_temp(b"", suffix='.pdf')
        
        # 2. Translation & Layout Preservation
        print(f"[STEP] Starting Translation & Layout Preservation...")
        translation_start = time.time()
        stats = translate_pdf_with_layout(input_pdf_path, output_pdf_path)
        timings["translation_complete"] = time.time()
        print(f"[STEP] Translation complete in {timings['translation_complete'] - translation_start:.2f}s")
        
        if not stats:
            stats = {
                'pages_processed': 0,
                'text_blocks_translated': 0,
                'tables_translated': 0
            }
        

        # 3. Pre-Vector Storage (Verified English & Arabic Source)
        doc_id = str(uuid.uuid4())
        full_text = stats.get('full_text_content', '')
        full_original_text = stats.get('full_original_content', '')
        
        if full_text:
            try:
                # Create storage directory for English
                storage_dir = os.path.join(os.getcwd(), "verified_english_docs")
                os.makedirs(storage_dir, exist_ok=True)
                
                # Save English text file
                text_file_path = os.path.join(storage_dir, f"{doc_id}.txt")
                with open(text_file_path, "w", encoding="utf-8") as f:
                    f.write(full_text)
                print(f"[STEP] Verified English text saved to: {text_file_path}")
            except Exception as e:
                print(f"[WARNING] Failed to save verified English text: {e}")

        if full_original_text:
            try:
                # Create storage directory for Arabic
                storage_dir_ar = os.path.join(os.getcwd(), "verified_arabic_docs")
                os.makedirs(storage_dir_ar, exist_ok=True)
                
                # Save Arabic text file
                text_file_path_ar = os.path.join(storage_dir_ar, f"{doc_id}.txt")
                with open(text_file_path_ar, "w", encoding="utf-8") as f:
                    f.write(full_original_text)
                print(f"[STEP] Verified Arabic text saved to: {text_file_path_ar}")
            except Exception as e:
                print(f"[WARNING] Failed to save verified Arabic text: {e}")

        # 3.1 Save Structured Data (Excel & JSON)
        segments = stats.get('segments', [])
        if segments:
            try:
                # Excel Export
                excel_dir = os.path.join(os.getcwd(), "verified_excel_docs")
                os.makedirs(excel_dir, exist_ok=True)
                excel_path = os.path.join(excel_dir, f"{doc_id}.xlsx")
                
                df = pd.DataFrame(segments)
                # Reorder columns for better readability if keys exist
                cols = [c for c in ['page', 'type', 'original', 'translated'] if c in df.columns]
                df = df[cols]
                df.to_excel(excel_path, index=False)
                print(f"[STEP] Verified Excel saved to: {excel_path}")

                # JSON Export
                json_dir = os.path.join(os.getcwd(), "verified_json_docs")
                os.makedirs(json_dir, exist_ok=True)
                json_path = os.path.join(json_dir, f"{doc_id}.json")
                
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(segments, f, indent=2, ensure_ascii=False)
                print(f"[STEP] Verified JSON saved to: {json_path}")
            
            except Exception as e:
                print(f"[WARNING] Failed to save structured data: {e}")

        # 4. Vector Storage (RAG Indexing)
        if full_text:
            print(f"[STEP] Indexing document {doc_id} to Qdrant...")
            indexing_start = time.time()
            rag_service.index_document(doc_id, full_text)
            timings["vector_indexing_complete"] = time.time()
            print(f"[STEP] Indexing complete in {timings['vector_indexing_complete'] - indexing_start:.2f}s")
        else:
            timings["vector_indexing_complete"] = time.time()
        
        # Calculate full duration
        total_duration = time.time() - timings["start"]
        print(f"[DONE] Request processed in {total_duration:.2f}s\n")
        
        # Schedule cleanup of output file after response
        background_tasks.add_task(cleanup_file, output_pdf_path)
        background_tasks.add_task(cleanup_file, input_pdf_path)

        # Build detailed stats header
        translation_stats = {
            "pages": stats.get('pages_processed', 0),
            "blocks": stats.get('text_blocks_translated', 0),
            "tables": stats.get('tables_translated', 0)
        }
        
        timing_stats = {
            "total_sec": round(total_duration, 2),
            "translation_sec": round(timings["translation_complete"] - timings["upload_processed"], 2),
            "indexing_sec": round(timings["vector_indexing_complete"] - timings["translation_complete"], 2) if full_text else 0
        }

        return FileResponse(
            output_pdf_path,
            media_type='application/pdf',
            filename='translated_english.pdf',
            headers={
                'X-Translation-Stats': json.dumps(translation_stats),
                'X-Translation-Timing': json.dumps(timing_stats),
                'X-Document-ID': doc_id,
                # Legacy header for backward compatibility if simple parsing used
                'X-Legacy-Stats': f"pages={stats.get('pages_processed', 0)}, blocks={stats.get('text_blocks_translated', 0)}"
            }
        )
        
    except Exception as e:
        # Cleanup on error
        cleanup_file(input_pdf_path)
        cleanup_file(output_pdf_path)
        raise e
