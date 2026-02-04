
import os
import time
import sys
import fitz
import re

# Add current directory to path so imports work
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.pdf_translation_service import translate_pdf_with_layout

def check_pdf_language(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for i in range(min(3, len(doc))):
        text += doc[i].get_text()
    
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    match = arabic_pattern.search(text)
    page_count = len(doc)
    doc.close()
    return bool(match), page_count

def run_verification():
    # Use the file user specified
    input_pdf = "output/Sabek Financial Statement.pdf"
    output_pdf = "output/verify_optimized.pdf"
    
    if not os.path.exists(input_pdf):
        print(f"Error: Input file not found: {input_pdf}")
        # Try to find any PDF with Sabek in name
        for root, dirs, files in os.walk("."):
            for file in files:
                if "Sabek" in file and file.endswith(".pdf") and "verify" not in file:
                    input_pdf = os.path.join(root, file)
                    print(f"Found alternative: {input_pdf}")
                    break
            if input_pdf != "output/Sabek Financial Statement.pdf": break
    
    if not os.path.exists(input_pdf):
        print("Could not find suitable input PDF.")
        return

    print(f"Checking file: {input_pdf}")
    is_arabic, page_count = check_pdf_language(input_pdf)
    
    if is_arabic:
        print(f"File contains Arabic text. Pages: {page_count}. Proceeding with translation.")
    else:
        print(f"Warning: File might NOT contain Arabic (or is image-based without OCR info). Pages: {page_count}.")
        # Continue anyway to test pipeline
        
    print(f"Starting optimized translation...")
    start_time = time.time()
    
    try:
        stats = translate_pdf_with_layout(input_pdf, output_pdf)
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"\nSUCCESS: Translation completed in {duration:.2f} seconds.")
        print(f"Output saved to {output_pdf}")
        print(f"Stats: {stats['tables_translated']} tables, {stats['text_blocks_translated']} text blocks.")
        
    except Exception as e:
        print(f"\nFAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_verification()
