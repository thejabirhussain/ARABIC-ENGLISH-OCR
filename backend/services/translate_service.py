from transformers import MarianMTModel, MarianTokenizer
import torch

# Global variables to cache the model and tokenizer
_model = None
_tokenizer = None
_device = None

def get_translation_model():
    """Load and cache the translation model - using better model for accuracy"""
    global _model, _tokenizer, _device
    
    if _model is None or _tokenizer is None:
        # Try better model first, fallback to original if it fails
        model_options = [
            "Helsinki-NLP/opus-mt-tc-big-ar-en",  # Bigger, more accurate model
            "Helsinki-NLP/opus-mt-ar-en"  # Fallback to original
        ]
        
        for model_name in model_options:
            try:
                print(f"Loading translation model: {model_name}")
                _tokenizer = MarianTokenizer.from_pretrained(model_name)
                _model = MarianMTModel.from_pretrained(model_name)
                
                # Set model to evaluation mode
                _model.eval()
                _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
                _model.to(_device)
                
                print(f"Translation model loaded successfully: {model_name}")
                break
            except Exception as e:
                print(f"Failed to load {model_name}: {e}")
                if model_name == model_options[-1]:
                    raise
                continue
    
    return _model, _tokenizer

def translate_to_english(arabic_text: str) -> str:
    """
    Translate Arabic text to English with improved accuracy.
    Uses sentence-by-sentence translation for better quality.
    """
    if not arabic_text or not arabic_text.strip():
        return ""

    # Check if input actually contains Arabic - if not, might already be English
    import re
    arabic_pattern = re.compile(r'[\u0600-\u06FF]')
    if not arabic_pattern.search(arabic_text):
        # No Arabic found - might already be English or numeric
        # Return as-is if it looks like valid text
        if re.search(r'[a-zA-Z]', arabic_text):
            return arabic_text.strip()
        # Otherwise, it's probably numeric/symbols, return as-is
        return arabic_text.strip()
    
    model, tokenizer = get_translation_model()
    
    # Clean and normalize the input text
    text = arabic_text.strip()
    
    # Preserve line breaks - they might be important for structure
    # Replace multiple spaces with single space, but keep line breaks
    text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces to single
    text = re.sub(r'\n\s*\n', '\n\n', text)  # Normalize paragraph breaks
    
    # Split into sentences more carefully
    # Arabic sentence endings: . ! ? ؟ ؛
    # But preserve line structure for paragraphs
    lines = text.split('\n')
    translated_lines = []
    
    for line in lines:
        if not line.strip():
            translated_lines.append("")
            continue
        
        # Split line into sentences
        sentence_endings = r'([.!؟!?؛]\s+)'
        sentences = re.split(sentence_endings, line)
        
        # Recombine sentences with their punctuation
        sentence_pairs = []
        for i in range(0, len(sentences) - 1, 2):
            sentence = sentences[i].strip()
            punct = sentences[i+1] if i+1 < len(sentences) else ""
            if sentence:
                sentence_pairs.append((sentence, punct))
        
        # If no sentence endings found, treat as single sentence
        if not sentence_pairs:
            sentence_pairs = [(line.strip(), "")]
        
        # Translate each sentence individually for better accuracy
        line_translated_parts = []
        for sentence, punct in sentence_pairs:
            if not sentence.strip():
                continue
            
            # Skip if no Arabic
            if not arabic_pattern.search(sentence):
                line_translated_parts.append(sentence + punct)
                continue
            
            # Translate sentence
            try:
                translated = _translate_batch(sentence, model, tokenizer)
                
                if translated and translated.strip():
                    # Validate translation
                    if arabic_pattern.search(translated):
                        # Still has Arabic, retry once
                        translated = _translate_batch(sentence, model, tokenizer)
                        if arabic_pattern.search(translated):
                            print(f"Warning: Failed to translate sentence: {sentence[:50]}...")
                            continue
                    
                    # Check for bad translation
                    if _is_bad_translation(translated, sentence):
                        print(f"Warning: Bad translation detected, skipping: {sentence[:50]}...")
                        continue
                    
                    line_translated_parts.append(translated.strip() + punct)
            except Exception as e:
                print(f"Translation error for sentence: {e}")
                continue
        
        if line_translated_parts:
            translated_lines.append(' '.join(line_translated_parts))
        else:
            translated_lines.append("")
    
    result = '\n'.join(translated_lines).strip()
    
    # Final validation
    if result and arabic_pattern.search(result):
        print(f"Warning: Translation result still contains Arabic characters")
    
    return result

def _is_bad_translation(translated: str, original: str) -> bool:
    """Detect if translation is clearly wrong/hallucinated"""
    if not translated or not original:
        return True
    
    import re
    
    # Check for common hallucination patterns (repetitive nonsense)
    bad_phrases = ['rabbit', 'lick', 'sleeve', 'european union']
    translated_lower = translated.lower()
    
    # Check for excessive repetition of bad phrases
    for phrase in bad_phrases:
        count = translated_lower.count(phrase)
        if count > 2:  # More than 2 occurrences is suspicious
            return True
    
    # Check for same phrase repeated multiple times
    words = translated_lower.split()
    if len(words) > 5:
        # Check if any word appears more than 40% of the time
        word_counts = {}
        for word in words:
            # Ignore common words
            if word not in ['the', 'a', 'an', 'and', 'or', 'in', 'on', 'at', 'to', 'for', 'of', 'with']:
                word_counts[word] = word_counts.get(word, 0) + 1
        if word_counts:
            max_count = max(word_counts.values())
            if max_count > len(words) * 0.4:  # More than 40% same word
                return True
    
    # Check if translation is suspiciously short compared to original
    # But be lenient - Arabic can be more compact than English
    if len(translated.strip()) < len(original.strip()) * 0.15:
        return True
    
    # Check for patterns like "X, X, X" (excessive repetition)
    if re.search(r'\b(\w+)\s*,\s*\1\s*,\s*\1', translated, re.IGNORECASE):
        return True
    
    return False

def _translate_batch(text: str, model, tokenizer) -> str:
    try:
        if not text or not text.strip():
            return ""
        
        # Skip if text doesn't contain Arabic (might be already English or numeric)
        import re
        arabic_pattern = re.compile(r'[\u0600-\u06FF]')
        if not arabic_pattern.search(text):
            # No Arabic - return as-is
            return text.strip()
        
        # Clean text - remove excessive whitespace
        text = ' '.join(text.split())
        
        # Tokenize input text with proper truncation
        inputs = tokenizer(
            text, 
            return_tensors="pt", 
            padding=True, 
            truncation=True, 
            max_length=512
        )
        if next(model.parameters()).is_cuda:
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
        
        # Translate with better generation parameters for accuracy
        with torch.no_grad():
            translated = model.generate(
                **inputs, 
                max_length=512,  # Output max length
                num_beams=5,  # Increased beams for better quality
                early_stopping=True,
                length_penalty=1.2,  # Prefer longer, more complete translations
                no_repeat_ngram_size=3,  # Reduce repetition
                do_sample=False  # Deterministic output
            )
        
        # Decode translated text
        translated_text = tokenizer.decode(translated[0].detach().cpu(), skip_special_tokens=True)
        
        result = translated_text.strip()
        
        # Validate result - should not contain Arabic
        if result and arabic_pattern.search(result):
            print(f"Warning: Translation result contains Arabic: {result[:50]}...")
            return ""
        
        # Check for bad translations
        if _is_bad_translation(result, text):
            print(f"Warning: Detected bad translation, retrying...")
            # Retry with different parameters
            with torch.no_grad():
                translated = model.generate(
                    **inputs,
                    max_length=512,
                    num_beams=8,  # More beams
                    early_stopping=True,
                    length_penalty=1.5,
                    no_repeat_ngram_size=4
                )
            result = tokenizer.decode(translated[0].detach().cpu(), skip_special_tokens=True).strip()
            
            # Check again
            if _is_bad_translation(result, text):
                print(f"Warning: Translation still appears bad: {result[:50]}...")
                return ""
        
        return result
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
                        if trans1 and trans2:
                            return (trans1 + " " + trans2).strip()
                    except:
                        pass
        # Return empty string instead of error message to avoid rendering errors
        return ""

def _translate_chunks(chunks, model, tokenizer, batch_size: int = 8):
    results = []
    i = 0
    while i < len(chunks):
        batch = [c for c in chunks[i:i+batch_size] if c and c.strip()]
        if not batch:
            results.extend(["" for _ in chunks[i:i+batch_size]])
            i += batch_size
            continue
        try:
            inputs = tokenizer(
                batch,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=512
            )
            if next(model.parameters()).is_cuda:
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = model.generate(
                    **inputs,
                    max_length=512,
                    num_beams=5,  # Increased for better quality
                    early_stopping=True,
                    length_penalty=1.2,
                    no_repeat_ngram_size=3
                )
            decoded = tokenizer.batch_decode(outputs.detach().cpu(), skip_special_tokens=True)
            results.extend([d.strip() for d in decoded])
        except Exception:
            for c in batch:
                results.append(_translate_batch(c, model, tokenizer))
        i += batch_size
    return results

