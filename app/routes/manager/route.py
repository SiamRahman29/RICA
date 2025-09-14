"""
Manager routes for RICA API
"""

from fastapi import APIRouter
from .models import AskRequest, AskResponse

from .helpers import get_inquirer_name

from app.crews.qna import qna_crew

# Create router instance
router = APIRouter(prefix="/manager", tags=["manager"])

@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Ask endpoint that echoes back the query_text
    """
    query_text = request.query_text
    
    # TODO: Add a function to infer if it's actually a qna task
    is_qna_task = True
    
    if is_qna_task:
        inquirer_name = get_inquirer_name()
        inputs = {
            "inquirer": f"{inquirer_name}",
            "inquiry": f"{query_text}"
        }
        result = qna_crew.kickoff(inputs=inputs)

    return AskResponse(
        response=result.raw if hasattr(result, 'raw') else str(result),
        original_query=request.query_text
    )
