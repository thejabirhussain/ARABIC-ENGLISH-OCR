from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

async def global_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    
    error_msg = str(exc)
    
    # Default to 500
    status_code = 500
    detail = f"Internal server error: {error_msg}"
    
    # Specific error mapping based on message content (legacy support)
    if "encrypted" in error_msg.lower():
        status_code = 400
        detail = "PDF is encrypted. Please provide an unencrypted PDF."
    elif "corrupted" in error_msg.lower() or "invalid" in error_msg.lower():
        status_code = 400
        detail = "PDF appears to be corrupted or invalid."
    elif "empty" in error_msg.lower():
        status_code = 400
        detail = "PDF file is empty."
        
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )
