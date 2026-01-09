
import pdfplumber
import sys

filename = "debug_reversal.pdf"
if len(sys.argv) > 1:
    filename = sys.argv[1]

print(f"Inspecting extraction with pdfplumber on {filename}...")

with pdfplumber.open(filename) as pdf:
    page = pdf.pages[0]
    words = page.extract_words()
    frag_words = [w for w in words if 250 < w['top'] < 260 and 700 < w['x0'] < 800]
    
    # Sort them by x0
    frag_words.sort(key=lambda w: w['x0'])
    
    print("Fragments in region sorted by X:")
    for i in range(len(frag_words)-1):
        w1 = frag_words[i]
        w2 = frag_words[i+1]
        gap = w2['x0'] - w1['x1']
        print(f"'{w1['text']}' (x1={w1['x1']:.2f}) -> Gap={gap:.2f} -> '{w2['text']}' (x0={w2['x0']:.2f})")
