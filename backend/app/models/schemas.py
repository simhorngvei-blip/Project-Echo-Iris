"""
Echo-Iris — Pydantic Request / Response Schemas

These models define the API contract for the REST and WebSocket endpoints.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Incoming chat message from a client."""

    message: str = Field(..., min_length=1, description="The user's message text.")


class ChatResponse(BaseModel):
    """Outgoing chat reply."""

    reply: str = Field(..., description="The AI-generated response.")
    ltm_hits: int = Field(
        default=0,
        description="Number of Long-Term Memory documents used for context.",
    )


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

class MemoryStoreRequest(BaseModel):
    """Manually store a fact in Long-Term Memory."""

    text: str = Field(..., min_length=1, description="The fact to remember.")
    metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Optional metadata tags for the memory entry.",
    )


class MemorySearchRequest(BaseModel):
    """Query Long-Term Memory directly."""

    query: str = Field(..., min_length=1, description="Search query text.")
    top_k: Optional[int] = Field(
        default=None,
        description="Override the default number of results to return.",
    )


class MemoryDocument(BaseModel):
    """A single document returned from a memory search."""

    content: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    score: Optional[float] = None


class MemorySearchResponse(BaseModel):
    """Results from a Long-Term Memory search."""

    results: List[MemoryDocument] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Server health status."""

    status: str = "ok"
    ollama_connected: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# WebSocket (JSON wire format)
# ---------------------------------------------------------------------------

class WSMessage(BaseModel):
    """WebSocket inbound message."""

    type: str = Field(default="chat", description="Message type: 'chat'.")
    message: str = Field(..., description="The user's message text.")


class WSResponse(BaseModel):
    """WebSocket outbound message."""

    type: str = Field(default="reply", description="Response type: 'reply' or 'error'.")
    reply: str = Field(default="", description="AI reply text.")
    error: Optional[str] = Field(default=None, description="Error detail, if any.")
