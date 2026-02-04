from .models import BoundingBox

def has_arabic_letter(s: str) -> bool:
    """Check if string contains Arabic characters"""
    ARABIC_BLOCKS = [
        (0x0600, 0x06FF), (0x0750, 0x077F),
        (0x08A0, 0x08FF), (0xFB50, 0xFDFF),
        (0xFE70, 0xFEFF),
    ]
    for ch in s:
        cp = ord(ch)
        if any(lo <= cp <= hi for lo, hi in ARABIC_BLOCKS):
            return True
    return False

def has_any_digit(s: str) -> bool:
    """Check if string contains digits"""
    ARABIC_INDIC_DIGITS = ''.join(chr(c) for c in range(0x0660, 0x066A))
    return any(ch.isdigit() or ch in ARABIC_INDIC_DIGITS for ch in s)

def fix_rtl_token(token: str) -> str:
    """Fix RTL text direction for Arabic tokens"""
    if has_arabic_letter(token) and not has_any_digit(token):
        return token[::-1]
    return token

def is_point_in_bbox(x: float, y: float, bbox: BoundingBox) -> bool:
    """Check if point is inside bounding box"""
    return bbox.x0 <= x <= bbox.x1 and bbox.y0 <= y <= bbox.y1

def bbox_area(bbox: BoundingBox) -> float:
    """Calculate bounding box area"""
    return (bbox.x1 - bbox.x0) * (bbox.y1 - bbox.y0)

def merge_bboxes(bbox1: BoundingBox, bbox2: BoundingBox) -> BoundingBox:
    """Merge two bounding boxes"""
    return BoundingBox(
        x0=min(bbox1.x0, bbox2.x0),
        y0=min(bbox1.y0, bbox2.y0),
        x1=max(bbox1.x1, bbox2.x1),
        y1=max(bbox1.y1, bbox2.y1)
    )
