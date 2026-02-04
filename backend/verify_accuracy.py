
import fitz
import re
import sys
import os

def check_accuracy(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"Error: File {pdf_path} not found.")
        sys.exit(1)

    doc = fitz.open(pdf_path)
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    
    doc.close()

    if not full_text.strip():
        print("Error: No text extracted from PDF.")
        sys.exit(1)

    # Regex for Arabic
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    
    total_chars = len(full_text)
    arabic_chars = len([c for c in full_text if arabic_pattern.match(c)])
    
    arabic_ratio = (arabic_chars / total_chars) * 100 if total_chars > 0 else 0
    
    print(f"Total Characters: {total_chars}")
    print(f"Arabic Characters: {arabic_chars}")
    print(f"Arabic Character Ratio: {arabic_ratio:.2f}%")
    
    # Key terms check
    key_terms = ["Financial Statement", "Assets", "Liabilities", "Equity", "Revenue", "Expenses"]
    found_terms = []
    missing_terms = []
    
    lower_text = full_text.lower()
    for term in key_terms:
        if term.lower() in lower_text:
            found_terms.append(term)
        else:
            missing_terms.append(term)
            
    print(f"Found Key Terms: {found_terms}")
    print(f"Missing Key Terms: {missing_terms}")
    
    if arabic_ratio < 1.0: # Expecting < 1% Arabic
        print("SUCCESS: Translation Accuracy is High.")
    elif arabic_ratio < 5.0:
        print("WARNING: Some Arabic text remains.")
        # Print sample Arabic text
        arabic_matches = arabic_pattern.findall(full_text)
        print(f"Sample Residual Arabic: {''.join(arabic_matches[:50])}...")
    else:
        print("FAILURE: Significant Arabic text remaining.")
        
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_accuracy.py <pdf_path>")
        sys.exit(1)
    
    check_accuracy(sys.argv[1])
