"""
Tests for Long-Term Memory (LTM).

Uses a temporary directory for ChromaDB so tests are fully isolated and
do not require a running Ollama server for embedding — we mock the
embedding function.

NOTE: ChromaDB currently has a known incompatibility with Python 3.14
      (pydantic v1 internals). These tests are skipped automatically
      when the import fails.
"""

from __future__ import annotations

import tempfile
from unittest.mock import MagicMock, patch

import pytest

# Guard for environments where ChromaDB cannot be imported (e.g. Python 3.14)
try:
    import chromadb  # noqa: F401

    _CHROMADB_AVAILABLE = True
except Exception:
    _CHROMADB_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _CHROMADB_AVAILABLE,
    reason="ChromaDB unavailable (known Python 3.14 / pydantic v1 incompatibility)",
)


@pytest.fixture()
def ltm(tmp_path):
    """
    Create an LTM instance backed by a temporary ChromaDB directory.

    We patch OllamaEmbeddings so that tests do not need a running Ollama
    server.  The mock returns deterministic 3-dimensional embeddings.
    """
    from app.core.ltm import LongTermMemory

    call_count = 0

    def _fake_embed(texts: list[str]) -> list[list[float]]:
        """Return simple deterministic vectors based on text length."""
        nonlocal call_count
        results = []
        for t in texts:
            call_count += 1
            n = len(t) % 10
            results.append([float(n) / 10, float(call_count) / 100, 0.5])
        return results

    with patch("app.core.ltm.OllamaEmbeddings") as MockEmbed:
        mock_instance = MagicMock()
        mock_instance.embed_documents.side_effect = _fake_embed
        mock_instance.embed_query.side_effect = lambda t: _fake_embed([t])[0]
        MockEmbed.return_value = mock_instance

        yield LongTermMemory(persist_dir=str(tmp_path / "chroma_test"))


class TestLongTermMemory:
    """Unit tests for the LTM vector store wrapper."""

    def test_store_returns_id(self, ltm):
        doc_id = ltm.store("The user's name is Alex.")
        assert isinstance(doc_id, str)
        assert len(doc_id) == 32  # uuid hex

    def test_store_increments_count(self, ltm):
        assert ltm.collection_count == 0
        ltm.store("fact one")
        assert ltm.collection_count == 1
        ltm.store("fact two")
        assert ltm.collection_count == 2

    def test_retrieve_returns_list(self, ltm):
        ltm.store("The user likes pizza.")
        ltm.store("The user has a cat named Miso.")
        results = ltm.retrieve("pizza", top_k=2)
        assert isinstance(results, list)
        assert len(results) <= 2
        for r in results:
            assert "content" in r
            assert "metadata" in r
            assert "score" in r

    def test_store_with_metadata(self, ltm):
        ltm.store("Important fact", metadata={"source": "manual"})
        results = ltm.retrieve("Important")
        assert len(results) >= 1
        meta = results[0]["metadata"]
        assert "stored_at" in meta
        assert meta.get("source") == "manual"
