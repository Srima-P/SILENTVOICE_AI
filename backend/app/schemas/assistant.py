"""
Phase 3 assistant API schemas.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Body for POST /api/assistant/chat"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's natural language message.",
    )


class ChatResponse(BaseModel):
    """Response from POST /api/assistant/chat"""
    intent: str = Field(..., description="Detected intent")
    target_file: Optional[str] = Field(None, description="Resolved file path, if applicable")
    response: str = Field(..., description="AI-generated response text (Markdown)")
    error: bool = Field(False, description="True when the response is an error message")
    candidates: list[str] = Field(
        default_factory=list,
        description="File candidates when a reference is ambiguous",
    )
    groq_used: bool = Field(True, description="Whether Groq was called for this response")
