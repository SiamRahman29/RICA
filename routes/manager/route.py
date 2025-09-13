"""
Manager routes for RICA API
"""

from fastapi import APIRouter
from .models import AskRequest, AskResponse

# Create router instance
router = APIRouter(prefix="/manager", tags=["manager"])

@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Ask endpoint that echoes back the query_text
    """
    return AskResponse(
        response=f"Echo: {request.query_text}",
        original_query=request.query_text
    )
