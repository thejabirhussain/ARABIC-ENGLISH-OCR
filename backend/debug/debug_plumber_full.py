
import pdfplumber
import sys

filename = "debug_reversal.pdf"
if len(sys.argv) > 1:
    filename = sys.argv[1]

print(f"Inspecting extraction with pdfplumber on {filename}...")

with pdfplumber.open(filename) as pdf:
    # Page 1
    page = pdf.pages[0]
    words = page.extract_words()
    print(f"Found {len(words)} words.")
    
    with open("debug_plumber_words.txt", "w", encoding="utf-8") as f:
        for i, w in enumerate(words):
            f.write(f"{i}: '{w['text']}' at x={w['x0']:.2f}, top={w['top']:.2f}\n")

print("Saved words to debug_plumber_words.txt")
