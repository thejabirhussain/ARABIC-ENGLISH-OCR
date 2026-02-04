from transformers import MarianMTModel, MarianTokenizer
import torch
from typing import List, Dict
import re
import logging

logger = logging.getLogger(__name__)

class TranslatorModel:
    """Batch translator with caching and retry logic"""
    
    _instance = None  # Singleton pattern
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, model_name: str = "Helsinki-NLP/opus-mt-tc-big-ar-en"):
        if self._initialized:
            return
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Loading translation model '{model_name}' on {self.device}...")
        
        try:
            self.tokenizer = MarianTokenizer.from_pretrained(model_name)
            self.model = MarianMTModel.from_pretrained(model_name).to(self.device)
            self.cache: Dict[str, str] = {}
            self._initialized = True
            logger.info("✅ Model loaded!")
        except Exception as e:
            logger.error(f"Failed to load model {model_name}: {e}")
            if model_name != "Helsinki-NLP/opus-mt-ar-en":
                logger.info("Falling back to 'Helsinki-NLP/opus-mt-ar-en'...")
                try:
                    fallback = "Helsinki-NLP/opus-mt-ar-en"
                    self.tokenizer = MarianTokenizer.from_pretrained(fallback)
                    self.model = MarianMTModel.from_pretrained(fallback).to(self.device)
                    self.cache = {}
                    self._initialized = True
                    logger.info("✅ Fallback model loaded!")
                    return
                except Exception as e2:
                    logger.error(f"Fallback failed: {e2}")
                    raise e2
            raise e
    
    def _has_arabic(self, text: str) -> bool:
        """Check if text still contains Arabic characters"""
        if not isinstance(text, str):
            return False
        return bool(re.search(r"[\u0600-\u06FF]", text))
    
    def translate_batch(self, texts: List[str], batch_size: int = 32) -> List[str]:
        """
        Translate a list of strings in batches (FAST!)
        Uses caching to avoid re-translating identical strings
        """
        if not texts:
            return []
        
        results = [""] * len(texts)
        uncached_indices = []
        uncached_texts = []
        
        # Check cache first
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = text
                continue
            
            if text in self.cache:
                results[i] = self.cache[text]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)
        
        if not uncached_texts:
            logger.info("All strings found in cache!")
            return results
        
        logger.info(f"Translating {len(uncached_texts)} new strings (cached: {len(texts) - len(uncached_texts)})...")
        
        # Batch translate uncached strings
        translated_segments = []
        for i in range(0, len(uncached_texts), batch_size):
            batch = uncached_texts[i : i + batch_size]
            
            # Tokenize
            encoded = self.tokenizer(
                batch, 
                return_tensors="pt", 
                padding=True, 
                truncation=True,
                max_length=128
            ).to(self.device)
            
            # Generate translations
            with torch.no_grad():
                generated_tokens = self.model.generate(
                    **encoded,
                    num_beams=4,
                    max_new_tokens=128,
                    early_stopping=True,
                    no_repeat_ngram_size=3,
                )
            
            # Decode
            decoded_batch = self.tokenizer.batch_decode(
                generated_tokens, 
                skip_special_tokens=True
            )
            translated_segments.extend(decoded_batch)
            
            logger.info(f"  Batch {i//batch_size + 1}/{(len(uncached_texts)-1)//batch_size + 1} done")
        
        # Retry failed translations (still contain Arabic)
        retry_indices = []
        retry_texts = []
        
        for local_i, (original, translated) in enumerate(zip(uncached_texts, translated_segments)):
            if self._has_arabic(translated):
                retry_indices.append(local_i)
                retry_texts.append(original)
        
        if retry_texts:
            logger.info(f"Retrying {len(retry_texts)} poor translations with better settings...")
            
            for i in range(0, len(retry_texts), batch_size):
                batch = retry_texts[i : i + batch_size]
                encoded = self.tokenizer(
                    batch, 
                    return_tensors="pt", 
                    padding=True, 
                    truncation=True,
                    max_length=128
                ).to(self.device)
                
                with torch.no_grad():
                    generated_tokens = self.model.generate(
                        **encoded,
                        num_beams=8,  # More beams = better quality
                        max_new_tokens=128,
                        early_stopping=True,
                        no_repeat_ngram_size=3,
                        length_penalty=0.8,
                    )
                
                decoded_batch = self.tokenizer.batch_decode(
                    generated_tokens, 
                    skip_special_tokens=True
                )
                
                for j, decoded in enumerate(decoded_batch):
                    translated_segments[retry_indices[i + j]] = decoded
        
        # Update cache and results
        for idx, original, translated in zip(uncached_indices, uncached_texts, translated_segments):
            self.cache[original] = translated
            results[idx] = translated
        
        return results
