
import pdfplumber
import sys

filename = "debug_reversal.pdf"
if len(sys.argv) > 1:
    filename = sys.argv[1]

print(f"Inspecting extraction with pdfplumber on {filename}...")

with pdfplumber.open(filename) as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    print(f"Found {len(words)} words.")
    for i, w in enumerate(words[:20]):
        print(f"{i}: '{w['text']}' at x={w['x0']:.2f}")

    # Check for specific known words
    # Expecting "الموجودات" (Assets) or "المطلوبات" (Liabilities)
    print("\nSearch for known words:")
    content = [w['text'] for w in words]
    print("Content sample:", " ".join(content[:20]))
