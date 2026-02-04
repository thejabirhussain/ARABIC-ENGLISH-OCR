from typing import Optional
from pydantic import BaseModel

class ChatRequest(BaseModel):
    doc_id: str
    query: str
    model: Optional[str] = None
