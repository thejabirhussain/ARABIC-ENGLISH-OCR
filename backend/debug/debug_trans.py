
from services.translate_service import translate_to_english

sample_text = """
هذا نص عربي للفحص.
نحن نقوم باختبار ترجمة النصوص.
12345
"""

print(f"Original: {sample_text}")
try:
    translated = translate_to_english(sample_text)
    print(f"Translated: '{translated}'")
except Exception as e:
    print(f"Error: {e}")
