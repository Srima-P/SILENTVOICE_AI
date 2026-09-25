"""
Phase 4 assistant API schemas.
Backward compatible — all new fields are optional with defaults.

Security hardening (audit fixes):
  - selected_file: max_length=512, path traversal / null-byte rejection
  - ConversationTurn.content: max_length=4000 per turn
  - conversation_history: max 20 turns enforced by field_validator
"""
from __future__ import annotations

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

# Reject any selected_file value that contains path traversal sequences,
# null bytes, or shell metacharacters that have no place in a file path.
_TRAVERSAL_RE = re.compile(r"\.\.|[\x00-\x1f]|[<>|*?]")

# Maximum number of conversation turns accepted per request.
_MAX_HISTORY_TURNS = 20


class ConversationTurn(BaseModel):
    """A single turn in the conversation history sent from the frontend."""
    role: str = Field(..., max_length=16, description="'user' or 'assistant'")
    content: str = Field(
        ...,
        max_length=4000,
        description="The text content of this turn (max 4 000 chars)",
    )


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
        max_length=512,
        description="Path of the file currently selected in the Project Explorer.",
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        description=f"Recent conversation turns (max {_MAX_HISTORY_TURNS}) for memory.",
    )

    @field_validator("selected_file")
    @classmethod
    def validate_selected_file(cls, v: Optional[str]) -> Optional[str]:
        """Reject path traversal sequences and control characters."""
        if v is None:
            return v
        stripped = v.strip()
        if not stripped:
            return None
        if _TRAVERSAL_RE.search(stripped):
            raise ValueError(
                "selected_file contains invalid characters or path traversal sequences"
            )
        return stripped

    @field_validator("conversation_history")
    @classmethod
    def validate_history_length(
        cls, v: list[ConversationTurn]
    ) -> list[ConversationTurn]:
        """Reject requests with more than _MAX_HISTORY_TURNS turns."""
        if len(v) > _MAX_HISTORY_TURNS:
            raise ValueError(
                f"conversation_history exceeds maximum of {_MAX_HISTORY_TURNS} turns "
                f"(received {len(v)})"
            )
        return v


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
