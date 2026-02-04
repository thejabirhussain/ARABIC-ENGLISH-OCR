
import fitz
import sys
import os

# Add backend directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from services.tables_service import (
        TableDetectionService, 
        PDFExtractionService, 
    TranslatorModel
    )
    import logging
    logging.basicConfig(level=logging.INFO)
    print("Maryum Services imported.")
except ImportError as e:
    print(f"Error importing services: {e}")
    sys.exit(1)

def debug_exclusion_visual(pdf_path, output_path):
    doc = fitz.open(pdf_path)
    detector = TableDetectionService()
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        print(f"--- Page {page_num+1} ---")
        
        # 1. Detect Tables (Red)
        table_configs = detector.detect_tables_on_page(pdf_path, page_num)
        exclusion_rects = []
        
        # Draw detected tables
        for config in table_configs:
            bbox = config.bbox
            rect = fitz.Rect(bbox.x0, bbox.y0, bbox.x1, bbox.y1)
            exclusion_rects.append(rect)
            
            # Draw Red Box (Table)
            shape = page.new_shape()
            shape.draw_rect(rect)
            shape.finish(color=(1, 0, 0), width=2) # Red
            shape.commit()
            print(f"Table Rect: {rect}")

        # 2. Get Text Blocks
        text_dict = page.get_text("dict")
        
        for block in text_dict["blocks"]:
            if "bbox" not in block:
                continue
            
            b_rect = fitz.Rect(block["bbox"])
            
            # Check intersection
            is_excluded = False
            for t_rect in exclusion_rects:
                if t_rect.intersects(b_rect):
                    is_excluded = True
                    # Calculate intersection area to report
                    intersect = t_rect & b_rect
                    area_intersect = intersect.get_area()
                    area_block = b_rect.get_area()
                    ratio = area_intersect / area_block if area_block > 0 else 0
                    print(f"  Block {b_rect} intersects Table {t_rect} (Ratio: {ratio:.2f})")
                    break
            
            if is_excluded:
                # Draw Blue Box (Excluded)
                shape = page.new_shape()
                shape.draw_rect(b_rect)
                shape.finish(color=(0, 0, 1), width=1) # Blue
                shape.commit()
            else:
                # Draw Green Box (Processed)
                shape = page.new_shape()
                shape.draw_rect(b_rect)
                shape.finish(color=(0, 1, 0), width=1) # Green
                shape.commit()
                # print(f"  Processed Block: {b_rect}")

    doc.save(output_path)
    print(f"Debug PDF saved to {output_path}")

if __name__ == "__main__":
    debug_exclusion_visual("debug_reversal.pdf", "debug_overlap_visual.pdf")
