import re
import unicodedata

class Normalizer:
    """Normalizes Arabic/Persian text for better translation quality"""
    
    def __init__(self):
        # BOTH Arabic (٠-٩) AND Persian (۰-۹) numerals to English
        self.numeral_map = str.maketrans(
        # ... (rest of init)

            "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",  # Arabic + Persian
            "01234567890123456789"     # English (twice)
        )
        
        # Arabic to English punctuation
        self.punctuation_map = str.maketrans({
            "،": ",",  # Arabic comma
            "؛": ";",  # Arabic semicolon
            "؟": "?",  # Arabic question mark
            "٪": "%",  # Arabic percent
            "٫": ".",  # Arabic decimal separator
            "٬": ",",  # Arabic thousands separator
        })
        
        # Remove diacritics and tatweel (elongation mark)
        self.diacritics_re = re.compile(r"[\u064B-\u065F\u0670\u06D6-\u06ED]")
        self.tatweel_re = re.compile("\u0640")
        
        # Normalize letter variations
        self.letter_norm_map = str.maketrans({
            "أ": "ا", "إ": "ا", "آ": "ا",
            "ى": "ي", "ئ": "ي",
            "ؤ": "و",
            "ۀ": "ة", "ة": "ه",
        })
    
    def normalize_numerals(self, text: str) -> str:
        """Convert Arabic AND Persian numerals to English"""
        if not isinstance(text, str):
            return text
        return text.translate(self.numeral_map)
    
    def normalize_punctuation(self, text: str) -> str:
        """Convert Arabic punctuation to English"""
        if not isinstance(text, str):
            return text
        return text.translate(self.punctuation_map)
    
    def normalize_letters(self, text: str) -> str:
        """Remove diacritics and normalize letter variations"""
        if not isinstance(text, str):
            return text
        text = self.diacritics_re.sub("", text)
        text = self.tatweel_re.sub("", text)
        return text.translate(self.letter_norm_map)
    
    def clean_text(self, text: str) -> str:
        """
        Full normalization pipeline:
        1. Normalize numerals (Arabic + Persian → English)
        2. Normalize punctuation
        3. Normalize letters
        4. Strip whitespace
        """
        if not isinstance(text, str):
            return text
            
        # NFKC Normalization: Converts presentation forms (e.g. 0xFEF3) to standard Arabic
        text = unicodedata.normalize('NFKC', text)
        
        text = self.normalize_numerals(text)
        text = self.normalize_punctuation(text)
        text = self.normalize_letters(text)
        
        # --- Enhanced PDF Artifact Cleaning ---
        
        # 1. Remove specific artifacts
        text = re.sub(r'[\ufffd\u200b\u200e\u200f]', '', text)
        
        # 2. Collapse multiple spaces FIRST to ensure predictable spacing for regex
        text = re.sub(r'\s+', ' ', text)
        
        original_text_cleaned = text
        
        # 3. Fix broken words
        # Regex: Word (2+ chars) + Space + Single Char
        # Removed \b as it can be unreliable with non-ASCII
        # Instead, rely on spaces or end of string.
        # \1 = Word, \2 = Single Char
        # Pattern: (Start or non-word)(Word)(Space)(SingleChar)(End or non-word)
        # Actually, let's just match any Arabic word + space + single Arabic char
        
        # Merge: Word + Space + Single Char
        # Ensure 'Single Char' is strictly single (not start of another word)
        # Lookahead: Not followed by Arabic char
        text = re.sub(r'([\u0600-\u06FF]{2,})\s+([\u0600-\u06FF])(?![\u0600-\u06FF])', r'\1\2', text)
        
        # Merge: Single Char + Space + Word
        # Lookbehind: Not preceded by Arabic char
        text = re.sub(r'(?<![\u0600-\u06FF])([\u0600-\u06FF])\s+([\u0600-\u06FF]{2,})', r'\1\2', text)

        return text.strip()
    
    def is_numeric_only(self, text: str) -> bool:
        """Check if text is only numbers and punctuation (NO Arabic letters)"""
        if not isinstance(text, str):
            return False
        
        cleaned = self.clean_text(text)
        
        # Remove financial symbols and whitespace
        for char in ".,%$-+()[] ":
            cleaned = cleaned.replace(char, "")
        
        # Empty or all digits = numeric only
        if not cleaned:
            return True
        
        return cleaned.isdigit()
    
    def has_arabic_letters(self, text: str) -> bool:
        """Check if text contains actual Arabic letters (not just numbers)"""
        if not isinstance(text, str):
            return False
        # Arabic letter blocks (excludes numerals and punctuation)
        return bool(re.search(r"[\u0621-\u063A\u0641-\u064A\u0671-\u06D3\u06F0-\u06FC]", text))
