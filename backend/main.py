from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from controllers.ocr_controller import router as ocr_router
from controllers.pdf_controller import router as pdf_router
from controllers.chat_controller import router as chat_router
from handlers.error_handler import global_exception_handler

app = FastAPI(title="Arabic OCR Translation API")

# CORS middleware to allow frontend requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:5174", "http://127.0.0.1:5173", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Document-ID", "X-Translation-Stats"]
)

# Exception Handler
app.add_exception_handler(Exception, global_exception_handler)

# Routes
app.include_router(ocr_router)
app.include_router(pdf_router)
app.include_router(chat_router)

@app.get("/")
def read_root():
    return {
        "message": "Arabic OCR Translation API is running",
        "endpoints": {
            "/process": "Extract text and translate (returns JSON)",
            "/translate-pdf": "Translate PDF with layout preservation (returns PDF)",
            "/chat": "Chat with the translated document using AI"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
