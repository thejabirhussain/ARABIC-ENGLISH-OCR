
import sys
import os
import fitz
import re
from PIL import Image

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.pdf_translation_service import translate_pdf_inplace

def run_single_test():
    input_pdf = "test_single.pdf"
    output_pdf = "test_single_output.pdf"
    
    if not os.path.exists(input_pdf):
        print(f"Error: {input_pdf} not found.")
        return
        
    print(f"Translating {input_pdf}...")
    try:
        stats = translate_pdf_inplace(input_pdf, output_pdf)
        print("Translation complete.")
        print(stats)
        
        # Verify output
        doc = fitz.open(output_pdf)
        page = doc[0]
        text = page.get_text()
        print("\n--- Output Text Sample ---")
        print(text[:500])
        print("--------------------------")
        
        # Check for numeric structure
        # Look for numbers that might be reversed or badly formatted
        # Regex for patterns like "123,456" or "123.456"
        numbers = re.findall(r'\d[\d,\.]*\d', text)
        print("\n--- Detected Numbers ---")
        print(numbers[:20])
        
    except Exception as e:
        print(f"Translation failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_single_test()
