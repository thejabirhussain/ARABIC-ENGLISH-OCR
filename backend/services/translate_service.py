from transformers import MarianMTModel, MarianTokenizer
import torch

# Global variables to cache the model and tokenizer
_model = None
_tokenizer = None

def get_translation_model():
    """Load and cache the translation model"""
    global _model, _tokenizer
    
    if _model is None or _tokenizer is None:
        model_name = "Helsinki-NLP/opus-mt-ar-en"
        print(f"Loading translation model: {model_name}")
        
        _tokenizer = MarianTokenizer.from_pretrained(model_name)
        _model = MarianMTModel.from_pretrained(model_name)
        
        # Set model to evaluation mode
        _model.eval()
        
        print("Translation model loaded successfully")
    
    return _model, _tokenizer

def translate_to_english(arabic_text: str) -> str:
    """
    Translate Arabic text to English using Helsinki-NLP/opus-mt-ar-en model.
    Handles long texts by splitting into sentences and translating each chunk.
    """
    if not arabic_text or not arabic_text.strip():
        return ""
    
    model, tokenizer = get_translation_model()
    
    # Split text into sentences/paragraphs for better translation
    # Split by sentence endings (period, exclamation, question mark) or line breaks
    import re
    
    # Split by Arabic sentence endings and line breaks
    # Arabic punctuation: . ! ? ؛
    sentences = re.split(r'([.!?؛]\s*)', arabic_text)
    
    # Recombine sentences with their punctuation
    chunks = []
    current_chunk = ""
    max_chunk_length = 400  # Characters, not tokens (safer)
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i] if i < len(sentences) else ""
        punctuation = sentences[i+1] if i+1 < len(sentences) else ""
        full_sentence = sentence + punctuation
        
        if not full_sentence.strip():
            continue
            
        # If adding this sentence would exceed max length, translate current chunk first
        if current_chunk and len(current_chunk) + len(full_sentence) > max_chunk_length:
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = full_sentence
        else:
            current_chunk += full_sentence
    
    # Add remaining chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    # If no sentences found, split by line breaks
    if not chunks:
        lines = arabic_text.split('\n')
        current_chunk = ""
        for line in lines:
            if not line.strip():
                if current_chunk.strip():
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                chunks.append("")  # Preserve empty lines
            else:
                if current_chunk and len(current_chunk) + len(line) > max_chunk_length:
                    chunks.append(current_chunk.strip())
                    current_chunk = line
                else:
                    if current_chunk:
                        current_chunk += " " + line
                    else:
                        current_chunk = line
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
    
    # Translate each chunk
    translated_chunks = []
    for chunk in chunks:
        if not chunk.strip():
            translated_chunks.append("")
        else:
            translated = _translate_batch(chunk, model, tokenizer)
            if translated:
                translated_chunks.append(translated)
    
    # Join all translated chunks
    translated_text = ' '.join(translated_chunks)
    
    # Clean up extra spaces
    translated_text = re.sub(r'\s+', ' ', translated_text)
    translated_text = translated_text.strip()
    
    return translated_text

def _translate_batch(text: str, model, tokenizer) -> str:
    """Translate a batch of text"""
    try:
        if not text or not text.strip():
            return ""
        
        # Tokenize input text with proper truncation
        # Use max_length=512 for input, but allow longer output
        inputs = tokenizer(
            text, 
            return_tensors="pt", 
            padding=True, 
            truncation=True, 
            max_length=512
        )
        
        # Translate with longer max_length for output
        with torch.no_grad():
            translated = model.generate(
                **inputs, 
                max_length=512,  # Output max length
                num_beams=4,
                early_stopping=True
            )
        
        # Decode translated text
        translated_text = tokenizer.decode(translated[0], skip_special_tokens=True)
        
        return translated_text.strip()
    except Exception as e:
        # If translation fails, try with smaller chunk
        print(f"Translation error: {str(e)}")
        # Try splitting in half and translating separately
        if len(text) > 100:
            mid = len(text) // 2
            # Try to split at sentence boundary
            for i in range(mid, min(mid + 50, len(text))):
                if text[i] in '.!?؛':
                    part1 = text[:i+1]
                    part2 = text[i+1:]
                    try:
                        trans1 = _translate_batch(part1, model, tokenizer)
                        trans2 = _translate_batch(part2, model, tokenizer)
                        return (trans1 + " " + trans2).strip()
                    except:
                        pass
        return f"[Translation error: {str(e)}]"

