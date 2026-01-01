from fastapi import HTTPException, UploadFile

async def validate_pdf(file: UploadFile) -> bytes:
    """
    Validates that the uploaded file is a PDF and returns its content.
    Raises HTTPException if validation fails.
    """
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    content = await file.read()
    
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    
    if not content.startswith(b'%PDF'):
        raise HTTPException(status_code=400, detail="File does not appear to be a valid PDF")
        
    return content
