import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.translate_service import translate_to_english

# Test cases from user input
test_cases = [
    "تقرير التمويل التجاري | 2016",
    "هذا مقطع عربي أطول قليالً لالختبار",
    """يهدف هذا النص إلى مساعدتك في تقييم مدى جودة نظام التعرف الضوئي على الحروف في قراءة الجمل العربية.
يمكنك استخدام هذا امللف ملعرفة دقة استخراج النص واملحافظة على التراكيب اللغوية."""
]

print("Starting Translation Debug...")
print("-" * 50)

for text in test_cases:
    print(f"Original: {text}")
    print("-" * 20)
    try:
        translated = translate_to_english(text)
        print(f"Translated: {translated}")
    except Exception as e:
        print(f"Error: {e}")
    print("-" * 50)
