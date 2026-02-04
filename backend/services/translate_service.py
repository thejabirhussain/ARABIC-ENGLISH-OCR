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
    
    # Check for numeric hallucinations (e.g., "6x4x6x4", "22 22 22")
    if re.search(r'\d+x\d+x\d+', translated, re.IGNORECASE):
        return True
        
    # Check for excessive number repetition
    digits = re.findall(r'\d+', translated)
    if len(digits) > 3:
        # Check if same digit sequence repeats
        if len(set(digits)) == 1: # All same numbers e.g. "20 20 20 20"
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
                num_beams=1,  # Greedy decoding for speed
                early_stopping=True,
                length_penalty=1.0,
                no_repeat_ngram_size=3,  # Reduce repetition
                do_sample=False  # Deterministic output
            )
        
        # Decode translated text
        translated_text = tokenizer.decode(translated[0].detach().cpu(), skip_special_tokens=True)
        
        result = translated_text.strip()
        
        # Validate result - should not contain Arabic
        if result and arabic_pattern.search(result):
            print(f"Warning: Translation result contains Arabic: {result[:50]}...")
            return text # Fallback to original

        
        # Check for bad translations
        if _is_bad_translation(result, text):
            # print(f"Warning: Detected bad translation, fallback to original...")
            return text
        
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



def _is_translatable(text: str) -> bool:
    """
    Check if text should be sent to the model.
    Returns False for "junk" (mixed symbols, short ambiguous strings).
    """
    if not text or len(text.strip()) == 0:
        return False
        
    import re
    # If text is very short (<4 chars) and contains mixed types (digits + letters), it's likely noise/codes
    # e.g. "4x4", "5a", "f-5"
    clean = text.strip()
    if len(clean) < 5:
        # Check for mixed alphanumeric
        has_alpha = bool(re.search(r'[a-zA-Z\u0600-\u06FF]', clean))
        has_digit = bool(re.search(r'\d', clean))
        has_symbol = bool(re.search(r'[^\w\s]', clean))
        
        if has_digit and (has_alpha or has_symbol):
            return False
            
    # Check for symbol density (e.g. "- - -", "/ /", "...")
    # Count non-alphanumeric chars
    non_alnum = len(re.findall(r'[^\w\s\u0600-\u06FF]', clean))
    if len(clean) > 0 and (non_alnum / len(clean)) > 0.6:
         return False
         
    return True

def translate_batch(texts: list[str], batch_size: int = 16) -> list[str]:
    """
    Translate a list of Arabic texts to English in batch.
    Preserves structure and uses sentence splitting for quality.
    """
    if not texts:
        return []

    model, tokenizer = get_translation_model()

    # Pre-processing:
    # 1. Identify which texts actually need translation (have Arabic)
    # 2. For those that do, split into sentences/segments if they are long
    # 3. Create a flat list of segments to translate
    
    import re
    # Comprehensive Arabic pattern including presentation forms
    arabic_pattern = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    sentence_endings = r'([.!؟!?؛]\s+)'
    
    # Store the mapping to reconstruct original texts
    # operations[i] = { 'type': 'direct' | 'split', 'indices': [idx1, idx2...] | value }
    operations = []
    flat_segments = []
    
    for text in texts:
        if not text or not text.strip():
            operations.append({'type': 'const', 'value': ""})
            continue
            
        if not arabic_pattern.search(text):
            # No Arabic, keep as is
            operations.append({'type': 'const', 'value': text})
            continue

        # CHECK FOR PURE NUMERIC CONTENT (Bypass model)
        # If text consists only of Arabic/English digits and punctuation, convert directly.
        # This fixes issues where model hallucinates on pure numbers (e.g. 36794 -> 64).
        clean_for_check = re.sub(r'[ \t\r\n]', '', text)
        # Match digits (Arabic/English), commas, dots, parens, dashes, percent, extended digits
        if re.match(r'^[\u0660-\u0669\u06F0-\u06F9\d\.,\(\)\-\+%\[\]]+$', clean_for_check):
            # Convert directly
            mapping = {
                '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
                '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
                '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
                '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
                '،': ',', '٪': '%'
            }
            converted = "".join(mapping.get(c, c) for c in text)
            operations.append({'type': 'const', 'value': converted})
            # print(f"Directly converted numeric: {text} -> {converted}")
            continue
            
        # Check junk filter
        if not _is_translatable(text):
             operations.append({'type': 'const', 'value': text}) # Return original
             continue

        # Clean text
        clean_text = text.strip()
        clean_text = re.sub(r'[ \t]+', ' ', clean_text)
        
        # Split logic similar to translate_to_english
        lines = clean_text.split('\n')
        text_ops = {'type': 'rebuild_lines', 'lines': []}
        
        for line in lines:
            if not line.strip():
                text_ops['lines'].append({'type': 'const', 'value': ""})
                continue
                
            # Split line into sentences
            parts = re.split(sentence_endings, line)
            
            line_ops = {'type': 'rebuild_segments', 'indices': []}
            
            # We need to handle the split carefully to reconstruct exactly
            # re.split with groups returns [text, sep, text, sep...]
            
            tokens = re.split(r'([.!؟!?؛]\s+)', line)
            
            for token in tokens:
                if not token: continue
                
                if arabic_pattern.search(token):
                    # Needs translation
                    flat_segments.append(token)
                    line_ops['indices'].append({'type': 'ref', 'idx': len(flat_segments)-1})
                else:
                    # Keep as is
                    line_ops['indices'].append({'type': 'const', 'value': token})
                    
            text_ops['lines'].append(line_ops)
            
        operations.append(text_ops)

    # Now batch translate `flat_segments`
    translated_segments = []
    if flat_segments:
        # Sort by length to minimize padding overhead
        indexed_segments = list(enumerate(flat_segments))
        indexed_segments.sort(key=lambda x: len(x[1]))
        
        sorted_texts = [x[1] for x in indexed_segments]
        original_indices = [x[0] for x in indexed_segments]
        
        print(f"Batch translating {len(flat_segments)} segments (sorted by length)...")
        sorted_results = _translate_chunks(sorted_texts, model, tokenizer, batch_size=batch_size)
        
        # Restore original order
        result_map = {idx: res for idx, res in zip(original_indices, sorted_results)}
        translated_segments = [result_map[i] for i in range(len(flat_segments))]

    # Reconstruct
    results = []
    for op in operations:
        if op['type'] == 'const':
            results.append(op['value'])
        elif op['type'] == 'rebuild_lines':
            lines = []
            for line_op in op['lines']:
                if line_op['type'] == 'const':
                    lines.append(line_op['value'])
                elif line_op['type'] == 'rebuild_segments':
                    segment_parts = []
                    for item in line_op['indices']:
                        if item['type'] == 'const':
                            segment_parts.append(item['value'])
                        else:
                            # ref
                            seg_idx = item['idx']
                            trans = translated_segments[seg_idx]
                            segment_parts.append(trans if trans is not None else "")
                    lines.append("".join(segment_parts))
            results.append("\n".join(lines))
            
    return results

def _translate_chunks(chunks, model, tokenizer, batch_size: int = 8):
    results = []
    i = 0
    import re
    # Comprehensive Arabic detection for validation
    arabic_pattern = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
            
    while i < len(chunks):
        batch = chunks[i:i+batch_size]
        if not batch:
             break
             
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
                    num_beams=1, # Greedy for speed
                    early_stopping=True,
                    length_penalty=1.0,
                    no_repeat_ngram_size=3
                )
            decoded = tokenizer.batch_decode(outputs.detach().cpu(), skip_special_tokens=True)
            
            # Validate batch results
            batch_results = []
            
            for k, res in enumerate(decoded):
                clean_res = res.strip()
                original_text = batch[k]
                
                bad_translation = False
                
                # CRITICAL: Check for ANY Arabic characters (including presentation forms)
                if (clean_res and arabic_pattern.search(clean_res)):
                     bad_translation = True
                     print(f"Warning: Translation result contains Arabic: {clean_res[:50]}...")
                
                # Only run heavy validation check if text length > 5
                # Short texts trigger false positives too often
                elif len(original_text) > 5 and _is_bad_translation(clean_res, original_text):
                     bad_translation = True
                     
                if bad_translation:
                    # AGGRESSIVE FALLBACK:
                    # For ANY Arabic leakage, force re-translation
                    if arabic_pattern.search(clean_res):
                        print(f"CRITICAL: Arabic detected in output, forcing re-translation: '{original_text[:30]}...'")
                        try:
                            # Try single translation with higher quality settings
                            clean_res = _translate_batch(original_text, model, tokenizer)
                            # If still has Arabic, use transliteration or return normalized
                            if arabic_pattern.search(clean_res):
                                from services.layout_extraction_service import normalize_arabic_numerals
                                clean_res = normalize_arabic_numerals(original_text)
                                print(f"  Fallback to normalization: {clean_res[:30]}...")
                        except Exception as e:
                            from services.layout_extraction_service import normalize_arabic_numerals
                            clean_res = normalize_arabic_numerals(original_text)
                    # HEURISTIC FALLBACK for other bad translations:
                    # If model failed on a short string, it's likely noise/symbol that looks like Arabic
                    # Just return original or empty, DO NOT RETRY SINGLE (Too slow)
                    elif len(original_text) < 20:
                         # print(f"Skipping retry for short text artifact: '{clean_res[:20]}...'")
                         clean_res = original_text # Fallback to original
                    else:
                        print(f"Batch artifact detected: '{clean_res[:30]}...' -> Retrying single.")
                        try:
                            # Limited retry for long text
                            clean_res = _translate_batch(original_text, model, tokenizer)
                        except Exception as e:
                            clean_res = original_text
                
                # Apply deterministic post-processing rules to eliminate residual Arabic
                clean_res = _apply_post_processing_rules(clean_res)
                
                batch_results.append(clean_res)
                
            results.extend(batch_results)
        except Exception as e:
            print(f"Batch translation error: {e}. Return empty.")
            results.extend([""] * len(batch)) # Fail block fast
            
        i += batch_size
    return results

def _apply_post_processing_rules(text: str) -> str:
    """
    Deterministicly replace known Arabic fragments that the model might miss.
    Focuses on currency, abbreviations, and common financial terms.
    """
    if not text:
        return ""
        
    import re
    from services.layout_extraction_service import normalize_arabic_numerals
    
    # 1. First normalize any accidental Arabic numerals or presentation forms
    text = normalize_arabic_numerals(text)
    
    # 2. Dictionary of common fragments (Mapped to English)
    # Using regex to ensure we match whole words or common abbreviations
    replacements = {
        # Currency
        r'ر\.س\.': 'SAR',
        r'ر\.س': 'SAR',
        r'ريال سعودي': 'Saudi Riyal',
        r'﷼': 'SAR',
        r'هللة': 'Halala',
        
        # Dates / Calendars
        r'هـ': 'H',
        r'م': 'G', # Gregorian
        
        # Organizational / Title suffixes
        r'شركة': 'Company',
        r'مساهمة': 'Joint Stock',
        r'السعودية': 'Saudi',
        r'الأساسية': 'Basic',
        r'الأساسية': 'Basic', # Duplicate for different forms
        r'للبتروكيماويات': 'Petrochemical',
        r'مقفلة': 'Closed',
        r'محدودة': 'Limited',
        r'ذات مسؤولية محدودة': 'Limited Liability Company',
        r'ش\.م\.م': 'LLC',
        r'س\.ت\.': 'C.R.',
        r'ر\.م\.': 'M.N.', 
        
        # Financial Headings / Keywords
        r'سابك': 'SABIC',
        r'القوائم المالية': 'Financial Statements',
        r'الموحدة': 'Consolidated',
        r'السنوية': 'Annual',
        r'للسنة المنتهية في': 'For the year ended',
        r'٣١ ديسيمبر': '31 December',
        r'٣١ ديسمبر': '31 December',
        r'ديسمبر': 'December',
        r'يناير': 'January',
        r'فبراير': 'February',
        r'مارس': 'March',
        r'أبريل': 'April',
        r'مايو': 'May',
        r'يونيو': 'June',
        r'يوليو': 'July',
        r'أغسطس': 'August',
        r'سبتمبر': 'September',
        r'أكتوبر': 'October',
        r'نوفمبر': 'November',
        
        # Report parts & Audit
        r'تقرير المراجع': 'Auditor\'s Report',
        r'المستقل': 'Independent',
        r'المحتويات': 'Contents',
        r'قائمة المركز المالي': 'Statement of Financial Position',
        r'الأمر الرئيسي للمراجعة': 'Key Audit Matter',
        r'التتمة': 'Continuation',
        r'تتمة': 'Continuation',
        r'إلى السادة': 'To the Shareholders',
        r'مساهمي': 'Shareholders',
        r'المحترمين': 'Honorable',
        r'الوطني': 'National',
        r'العنوان': 'Address',
        r'البريدي': 'Postal',
        r'ص\.ب\.': 'P.O. Box',
        r'الرياض': 'Riyadh',
        r'المملكة العربية السعودية': 'Kingdom of Saudi Arabia',
        
        # Directional / Artifacts
        r'عن': 'For',
        r'في': 'In',
        r'إلى': 'To',
        r'من': 'From',
        r'تتمة': 'Continuation',
        r'رقم': 'Number',
        r'إجمالي': 'Total',
        r'صافي': 'Net',
    }
    
    processed_text = text
    for pattern, replacement in replacements.items():
        processed_text = re.sub(pattern, replacement, processed_text)
        
    # 3. Handle mixed spacing artifacts (e.g. "Word123" -> "Word 123")
    processed_text = re.sub(r'([a-zA-Z])(\d)', r'\1 \2', processed_text)
    processed_text = re.sub(r'(\d)([a-zA-Z])', r'\1 \2', processed_text)
    
    # 4. Final safety check: if still has Arabic but very short, it might be noise
    arabic_pattern = re.compile(r'[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]')
    if arabic_pattern.search(processed_text) and len(processed_text.strip()) < 4:
        # Just strip it if it's very short and still Arabic (likely noise/symbols)
        if not re.match(r'^[\d\s\.,]+$', processed_text):
            return re.sub(arabic_pattern, '', processed_text).strip()

    return processed_text


