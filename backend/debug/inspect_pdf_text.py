
import fitz
import sys

filename = "debug_reversal_output.pdf"
if len(sys.argv) > 1:
    filename = sys.argv[1]

print(f"Inspecting {filename}...")
try:
    doc = fitz.open(filename)
    for i, page in enumerate(doc):
        print(f"--- Page {i+1} ---")
        text = page.get_text("text")
        print(text)
        print("-" * 20)
except Exception as e:
    print(f"Error: {e}")
