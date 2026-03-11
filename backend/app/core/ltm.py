"""
Echo-Iris — Long-Term Memory (LTM)

Wraps a persistent ChromaDB vector store using Ollama embeddings so
the AI can store and retrieve important facts across sessions.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

import chromadb
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings

from app.config import settings

logger = logging.getLogger(__name__)


class LongTermMemory:
    """
    Persistent vector memory backed by ChromaDB + OllamaEmbeddings.

    * ``store(text, metadata)`` — embed and persist a new fact.
    * ``retrieve(query, top_k)``  — similarity-search for relevant facts.
    """

    COLLECTION_NAME = "echo_iris_memory"

    def __init__(
        self,
        persist_dir: str | None = None,
        embed_model: str | None = None,
        ollama_base_url: str | None = None,
    ):
        self._persist_dir = persist_dir or settings.chroma_persist_dir
        _embed_model = embed_model or settings.ollama_embed_model
        _ollama_url = ollama_base_url or settings.ollama_base_url

        # Embedding function (local Ollama model)
        self._embeddings = OllamaEmbeddings(
            model=_embed_model,
            base_url=_ollama_url,
        )

        # Persistent ChromaDB client
        self._chroma_client = chromadb.PersistentClient(path=self._persist_dir)

        # LangChain-Chroma vector store
        self._store = Chroma(
            client=self._chroma_client,
            collection_name=self.COLLECTION_NAME,
            embedding_function=self._embeddings,
        )

        logger.info(
            "LTM initialised — collection=%s  persist=%s  embed_model=%s",
            self.COLLECTION_NAME,
            self._persist_dir,
            _embed_model,
        )

    # -- public API -----------------------------------------------------------

    def store(self, text: str, metadata: dict[str, str] | None = None) -> str:
        """
        Embed *text* and store it in the vector database.

        Returns the generated document ID.
        """
        doc_id = uuid4().hex
        meta = {
            "stored_at": datetime.now(timezone.utc).isoformat(),
            **(metadata or {}),
        }
        self._store.add_texts(texts=[text], metadatas=[meta], ids=[doc_id])
        logger.info("LTM stored  id=%s  text=%s", doc_id, text[:60])
        return doc_id

    def retrieve(
        self, query: str, top_k: int | None = None
    ) -> list[dict]:
        """
        Similarity-search the vector store.

        Returns a list of dicts: ``{"content": ..., "metadata": ..., "score": ...}``
        """
        k = top_k or settings.ltm_top_k
        results = self._store.similarity_search_with_relevance_scores(query, k=k)
        docs = [
            {
                "content": doc.page_content,
                "metadata": doc.metadata,
                "score": round(score, 4),
            }
            for doc, score in results
        ]
        logger.debug("LTM retrieve  query=%s  hits=%d", query[:40], len(docs))
        return docs

    @property
    def collection_count(self) -> int:
        """Number of documents currently stored."""
        collection = self._chroma_client.get_or_create_collection(self.COLLECTION_NAME)
        return collection.count()
