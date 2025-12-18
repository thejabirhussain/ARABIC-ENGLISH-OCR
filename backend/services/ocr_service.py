import ocrmypdf
import ocrmypdf.exceptions
import pytesseract
import tempfile
import os
import re
from pdf2image import convert_from_path
from PyPDF2 import PdfReader
import cv2
import numpy as np

def extract_arabic_text(pdf_path: str) -> str:
    """
    Extract Arabic text from scanned PDF using OCR.
    Uses direct pytesseract OCR with optimized settings for Arabic text.
    """
    # Validate PDF file exists and is not empty
    if not os.path.exists(pdf_path):
        raise Exception(f"PDF file not found: {pdf_path}")
    
    if os.path.getsize(pdf_path) == 0:
        raise Exception("PDF file is empty")
    
    # Convert PDF pages directly to images for better accuracy
    try:
        # Use higher DPI for better OCR accuracy
        images = convert_from_path(pdf_path, dpi=400, fmt='png')
        
        if not images:
            raise Exception("Could not convert PDF pages to images. The PDF might be corrupted.")
        
        # Extract text from each page with optimized settings for Arabic
        extracted_texts = []
        for i, image in enumerate(images):
            try:
                # Optimize image for better OCR
                # Convert to RGB if needed
                if image.mode != 'RGB':
                    image = image.convert('RGB')

                # OpenCV preprocessing: grayscale, denoise, binarize, deskew
                preprocessed = _preprocess_for_ocr(image)
                
                # Try multiple PSM modes for best results
                # PSM 6: Assume a single uniform block of text (good for paragraphs)
                # PSM 3: Fully automatic page segmentation
                # PSM 4: Assume a single column of text of variable sizes
                psm_modes = ['6', '3', '4']
                best_text = None
                
                for psm in psm_modes:
                    try:
                        # Use LSTM engine and preserve spacing for layout fidelity
                        config = f"--oem 1 --psm {psm} -l ara -c preserve_interword_spaces=1"
                        text = pytesseract.image_to_string(
                            preprocessed,
                            lang='ara',
                            config=config
                        )
                        
                        if text and text.strip():
                            # Clean up the text
                            cleaned_text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
                            if cleaned_text:
                                # Prefer longer, more complete text
                                if best_text is None or len(cleaned_text) > len(best_text):
                                    best_text = cleaned_text
                    except:
                        continue
                
                if best_text:
                    extracted_texts.append(best_text)
                        
            except Exception as e:
                # Try alternative PSM mode if first attempt fails
                try:
                    config = '--oem 1 --psm 3 -l ara -c preserve_interword_spaces=1'
                    text = pytesseract.image_to_string(preprocessed, lang='ara', config=config)
                    if text and text.strip():
                        cleaned_text = '\n'.join(line.strip() for line in text.split('\n') if line.strip())
                        if cleaned_text:
                            extracted_texts.append(cleaned_text)
                except:
                    # Skip this page if both attempts fail
                    continue
        
        if not extracted_texts:
            raise Exception("No text could be extracted from the PDF. The PDF might not contain readable text or the OCR failed.")
        
        # Combine all pages with proper line breaks
        full_text = '\n\n'.join(extracted_texts)
        
        # Final cleanup - remove OCR artifacts
        # Remove duplicate Arabic characters (common OCR error)
        # Fix common OCR errors: duplicate characters
        # Pattern: same Arabic character repeated 2+ times (except spaces)
        full_text = re.sub(r'([\u0600-\u06FF])\1+', r'\1', full_text)
        
        # Fix punctuation errors
        full_text = full_text.replace('؛', '؛')  # Keep Arabic semicolon
        full_text = full_text.replace('،', '،')  # Keep Arabic comma
        # Remove common OCR artifacts
        full_text = full_text.replace('ءء', 'ء')
        full_text = full_text.replace('  ', ' ')  # Double spaces
        
        # Clean up line breaks - preserve intentional breaks but remove excessive ones
        lines = full_text.split('\n')
        cleaned_lines = []
        for line in lines:
            line = line.strip()
            if line:  # Only add non-empty lines
                cleaned_lines.append(line)
        
        full_text = '\n'.join(cleaned_lines)
        
        return full_text.strip()
        
    except Exception as e:
        # Fallback: Try using ocrmypdf first, then extract
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_output:
                output_path = tmp_output.name
            
            try:
                # Run OCR on PDF with Arabic language
                ocrmypdf.ocr(
                    pdf_path,
                    output_path,
                    language='ara',
                    force_ocr=True,
                    progress_bar=False,
                    tesseract_config='--psm 6'
                )
                
                # Try to extract from OCR'd PDF
                reader = PdfReader(output_path)
                extracted_texts = []
                for page in reader.pages:
                    try:
                        text = page.extract_text()
                        if text and text.strip():
                            extracted_texts.append(text.strip())
                    except:
                        continue
                
                if extracted_texts:
                    return '\n\n'.join(extracted_texts)
                    
            finally:
                if os.path.exists(output_path):
                    try:
                        os.unlink(output_path)
                    except:
                        pass
        except:
            pass
        
        # If all methods fail, raise the original error
        raise Exception(f"Image-based text extraction failed: {str(e)}")

def _preprocess_for_ocr(pil_image):
    """Preprocess PIL image for better Arabic OCR using OpenCV."""
    # Convert PIL to OpenCV BGR
    img = np.array(pil_image)
    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    # Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Denoise while preserving edges
    gray = cv2.bilateralFilter(gray, d=9, sigmaColor=75, sigmaSpace=75)

    # Binarization (adaptive for uneven illumination)
    bin_img = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 35, 15
    )

    # Invert text to black on white if needed
    # Ensure text is dark for Tesseract
    pixels_mean = np.mean(bin_img)
    if pixels_mean > 127:
        bin_img = cv2.bitwise_not(bin_img)

    # Morphological opening to remove small noise
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    bin_img = cv2.morphologyEx(bin_img, cv2.MORPH_OPEN, kernel, iterations=1)

    # Deskew using Hough line-based angle estimation
    angle = _estimate_skew_angle(bin_img)
    if abs(angle) > 0.5 and abs(angle) < 15:
        bin_img = _rotate_image(bin_img, angle)

    # Return as RGB PIL-compatible image for pytesseract
    bin_img = cv2.cvtColor(bin_img, cv2.COLOR_GRAY2RGB)
    return bin_img

def _estimate_skew_angle(binary_img):
    edges = cv2.Canny(binary_img, 50, 150, apertureSize=3)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=200)
    if lines is None:
        return 0.0
    angles = []
    for rho_theta in lines[:100]:
        rho, theta = rho_theta[0]
        # Convert to degrees, map near horizontal lines to small angles
        angle = (theta * 180 / np.pi) - 90
        if -15 <= angle <= 15:
            angles.append(angle)
    if not angles:
        return 0.0
    return float(np.median(angles))

def _rotate_image(img, angle):
    (h, w) = img.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

