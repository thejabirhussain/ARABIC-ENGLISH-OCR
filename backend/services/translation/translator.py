# services/translation/translator.py
from transformers import MarianMTModel, MarianTokenizer


class ArabicTranslator:
    """
    Arabic to English translator using Helsinki-NLP model
    """
    def __init__(self, model_name: str = "Helsinki-NLP/opus-mt-ar-en"):
        print(f"Loading translation model: {model_name}")
        self.tokenizer = MarianTokenizer.from_pretrained(model_name)
        self.model = MarianMTModel.from_pretrained(model_name)
        print("Model loaded successfully!")
    
    def translate(self, text: str, max_length: int = 512) -> str:
        """
        Translate Arabic text to English
        """
        if not text or not isinstance(text, str):
            return text
        
        # Tokenize and translate
        inputs = self.tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=max_length)
        translated = self.model.generate(**inputs)
        result = self.tokenizer.decode(translated[0], skip_special_tokens=True)
        
        return result
