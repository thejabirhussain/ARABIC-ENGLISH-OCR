
import pdfplumber
import sys

filename = "debug_reversal.pdf"
if len(sys.argv) > 1:
    filename = sys.argv[1]

print(f"Inspecting extraction with pdfplumber on {filename}...")

print("--- Default (x_tolerance=3) ---")
with pdfplumber.open(filename) as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    print(f"Found {len(words)} words.")
    # Check specific region (Fragments around X=720-740, Top=256)
    frag_words = [w for w in words if 250 < w['top'] < 260 and 700 < w['x0'] < 800]
    print("Fragments found:", [w['text'] for w in frag_words])

print("--- With x_tolerance=6 ---")
with pdfplumber.open(filename) as pdf:
    page = pdf.pages[0]
    words = page.extract_words(x_tolerance=6)
    print(f"Found {len(words)} words.")
    frag_words = [w for w in words if 250 < w['top'] < 260 and 700 < w['x0'] < 800]
    print("Fragments found:", [w['text'] for w in frag_words])

print("--- With x_tolerance=10 ---")
with pdfplumber.open(filename) as pdf:
    page = pdf.pages[0]
    words = page.extract_words(x_tolerance=10)
    print(f"Found {len(words)} words.")
    frag_words = [w for w in words if 250 < w['top'] < 260 and 700 < w['x0'] < 800]
    print("Fragments found:", [w['text'] for w in frag_words])
