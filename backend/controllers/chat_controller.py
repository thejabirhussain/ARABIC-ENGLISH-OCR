from fastapi import APIRouter, HTTPException
from models.chat import ChatRequest
from services.rag_service import rag_service

router = APIRouter()

@router.get("/chat/models")
async def get_models():
    """List available models for chat"""
    models = rag_service.list_models()
    return {"models": models}

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    Chat with a translated document using RAG (Ollama + Qdrant).
    """
    try:
        response = rag_service.chat_with_document(request.doc_id, request.query, request.model)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
