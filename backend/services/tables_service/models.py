from pydantic import BaseModel
from typing import List

class BoundingBox(BaseModel):
    """Bounding box coordinates"""
    x0: float
    y0: float
    x1: float
    y1: float

class TableConfig(BaseModel):
    """Configuration for a detected table"""
    page: int
    bbox: BoundingBox
    columns: List[float]
    img_width: float = 0.0
    img_height: float = 0.0

class TableData(BaseModel):
    """Extracted table data"""
    table_id: str
    page: int
    rows: List[List[str]]
    column_count: int
