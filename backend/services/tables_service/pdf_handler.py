import fitz
import pdfplumber
from typing import List, Dict

class PDFHandler:
    """Handles PDF file operations"""
    
    @staticmethod
    def get_page_count(pdf_path: str) -> int:
        """Get number of pages in PDF"""
        doc = fitz.open(pdf_path)
        count = doc.page_count
        doc.close()
        return count
    
    @staticmethod
    def extract_words_from_page(pdf_path: str, page_num: int) -> List[Dict]:
        """Extract all words from a PDF page"""
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]
            return page.extract_words()
    
    @staticmethod
    def get_page_dimensions(pdf_path: str, page_num: int) -> tuple:
        """Get page width and height"""
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]
            return page.width, page.height
    
    @staticmethod
    def render_page_to_image(pdf_path: str, page_num: int, output_path: str, dpi: int = 120):
        """Render page to PNG image"""
        doc = fitz.open(pdf_path)
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        pix.save(output_path)
        doc.close()
        return output_path
