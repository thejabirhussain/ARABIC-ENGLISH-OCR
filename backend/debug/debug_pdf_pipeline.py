
import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.pdf_translation_service import translate_pdf_with_layout

input_file = "debug_reversal.pdf"
output_file = "debug_reversal_output.pdf"

if not os.path.exists(input_file):
    print(f"Error: {input_file} not found.")
    sys.exit(1)

print(f"Translating {input_file} to {output_file}...")

try:
    stats = translate_pdf_with_layout(input_file, output_file)
    print("Translation successful!")
    print("Stats:", stats)
except Exception as e:
    print(f"Error during translation: {e}")
    sys.exit(1)
