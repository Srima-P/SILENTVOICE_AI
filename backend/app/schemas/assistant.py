"""
Phase 4 assistant API schemas.
Backward compatible — all new fields are optional with defaults.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """A single turn in the conversation history sent from the frontend."""
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., description="The text content of this turn")


class ChatRequest(BaseModel):
    """Body for POST /api/assistant/chat"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The user's natural language message.",
    )
    # Phase 4: optional context fields — backward compatible (both default to None/[])
    selected_file: Optional[str] = Field(
        None,
        description="Path of the file currently selected in the Project Explorer.",
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Recent conversation turns (max ~10) sent by the frontend for memory.",
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
    # Phase 4: follow-up suggestions — empty list when not available
    follow_up_suggestions: list[str] = Field(
        default_factory=list,
        description="Suggested follow-up prompts the user can click to continue the conversation.",
    )
    # Phase 4: where the active file came from (for frontend diagnostics)
    context_source: str = Field(
        "none",
        description="How the active file was resolved: explicit | selected | memory | none",
    )
