"""
Pydantic models for manager routes
"""

from pydantic import BaseModel

class AskRequest(BaseModel):
    query_text: str

class AskResponse(BaseModel):
    response: str
    original_query: str
