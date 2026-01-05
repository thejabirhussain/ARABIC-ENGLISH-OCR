
import sys
import os

# Add backend to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    print("Testing tables_service integration...")
    from services.tables_service import (
        TableDetectionService, 
        PDFExtractionService, 
        TranslationService
    )
    print("✅ Successfully imported services.tables_service components")
    
    # Check pdf_translation_service imports
    from services.pdf_translation_service import translate_pdf_inplace
    print("✅ Successfully imported pdf_translation_service")
    
except Exception as e:
    print(f"❌ Integration Test Failed: {e}")
    sys.exit(1)
