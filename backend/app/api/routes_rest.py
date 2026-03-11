"""
Echo-Iris — REST API Routes

Endpoints:
    GET  /health          — liveness check
    POST /chat            — synchronous chat
    POST /memory/search   — query long-term memory
    POST /memory/store    — manually store a fact
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    MemoryDocument,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStoreRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check():
    """Check if the server and Ollama are alive."""
    from app.main import get_brain  # deferred to avoid circular import

    brain = get_brain()
    ollama_ok = await brain.llm.ping()
    return HealthResponse(status="ok", ollama_connected=ollama_ok)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(req: ChatRequest):
    """Send a message to Echo-Iris and receive a reply."""
    from app.main import get_brain

    brain = get_brain()
    try:
        result = await brain.process(req.message)
        return ChatResponse(reply=result["reply"], ltm_hits=result["ltm_hits"])
    except Exception as exc:
        logger.exception("Chat processing failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Memory — Search
# ---------------------------------------------------------------------------

@router.post("/memory/search", response_model=MemorySearchResponse, tags=["memory"])
async def memory_search(req: MemorySearchRequest):
    """Directly query the Long-Term Memory vector store."""
    from app.main import get_brain

    brain = get_brain()
    raw = brain.ltm.retrieve(req.query, top_k=req.top_k)
    docs = [
        MemoryDocument(
            content=d["content"],
            metadata=d.get("metadata", {}),
            score=d.get("score"),
        )
        for d in raw
    ]
    return MemorySearchResponse(results=docs)


# ---------------------------------------------------------------------------
# Memory — Store
# ---------------------------------------------------------------------------

@router.post("/memory/store", tags=["memory"], status_code=201)
async def memory_store(req: MemoryStoreRequest):
    """Manually store a fact in Long-Term Memory."""
    from app.main import get_brain

    brain = get_brain()
    doc_id = brain.ltm.store(req.text, metadata=req.metadata)
    return {"id": doc_id, "stored": True}
