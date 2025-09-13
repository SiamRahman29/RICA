"""
FastAPI application for RICA - Rather Intelligent Conversational Assistant
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any
import uvicorn

# Import routers
from app.routes.manager.route import router as manager_router

# Create FastAPI instance
app = FastAPI(
    title="RICA API",
    description="Rather Intelligent Conversational Assistant API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(manager_router)

# Pydantic models
class HealthResponse(BaseModel):
    status: str
    message: str

class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    user_id: str
    timestamp: str

# Routes
@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint"""
    return {"message": "Welcome to RICA API", "version": "0.1.0"}

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        message="RICA API is running successfully"
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint for conversational AI"""
    # This is a placeholder - you'll implement the actual AI logic here
    response_text = f"Hello! You said: '{request.message}'. This is a placeholder response from RICA."
    
    from datetime import datetime
    return ChatResponse(
        response=response_text,
        user_id=request.user_id,
        timestamp=datetime.now().isoformat()
    )

@app.get("/api/v1/status")
async def api_status():
    """API status endpoint"""
    return {
        "api_version": "v1",
        "status": "operational",
        "endpoints": [
            "/",
            "/health",
            "/chat",
            "/manager/ask",
            "/docs",
            "/redoc"
        ]
    }

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {"error": "Endpoint not found", "detail": str(exc)}

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    return {"error": "Internal server error", "detail": "An unexpected error occurred"}

if __name__ == "__main__":
    # Run with uvicorn when script is executed directly
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload for development
        log_level="info"
    )
