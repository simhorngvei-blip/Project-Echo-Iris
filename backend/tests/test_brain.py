"""
Tests for the Brain orchestrator.

All external dependencies (LLM and LTM embeddings) are mocked so
tests run without Ollama.

NOTE: ChromaDB currently has a known incompatibility with Python 3.14
      (pydantic v1 internals). These tests are skipped automatically
      when the import fails.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
def mock_llm():
    """An LLMClient whose ``invoke`` is an AsyncMock."""
    from app.core.llm import LLMClient

    llm = MagicMock(spec=LLMClient)
    llm.invoke = AsyncMock(return_value="Hello! Nice to meet you.")
    llm.ping = AsyncMock(return_value=True)
    return llm


@pytest.fixture()
def mock_ltm(tmp_path):
    """An LTM with mocked embeddings and a temp directory."""
    from app.core.ltm import LongTermMemory

    call_count = 0

    def _fake_embed(texts: list[str]) -> list[list[float]]:
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

        yield LongTermMemory(persist_dir=str(tmp_path / "chroma_brain"))


@pytest.fixture()
def brain(mock_llm, mock_ltm):
    """A Brain wired with mocked LLM and LTM."""
    from app.core.brain import Brain
    from app.core.stm import ShortTermMemory

    return Brain(stm=ShortTermMemory(max_messages=10), ltm=mock_ltm, llm=mock_llm)


class TestBrain:
    """Integration-style tests for the Brain orchestrator."""

    @pytest.mark.asyncio
    async def test_process_returns_reply(self, brain, mock_llm):
        mock_llm.invoke = AsyncMock(side_effect=["Hi there!", "NONE"])
        result = await brain.process("Hello!")
        assert "reply" in result
        assert result["reply"] == "Hi there!"
        assert "ltm_hits" in result

    @pytest.mark.asyncio
    async def test_process_appends_to_stm(self, brain, mock_llm):
        mock_llm.invoke = AsyncMock(side_effect=["Reply!", "NONE"])
        await brain.process("Test message")
        assert brain.stm.count == 2
        raw = brain.stm.get_raw()
        assert raw[0]["role"] == "user"
        assert raw[0]["content"] == "Test message"
        assert raw[1]["role"] == "assistant"
        assert raw[1]["content"] == "Reply!"

    @pytest.mark.asyncio
    async def test_process_calls_llm(self, brain, mock_llm):
        mock_llm.invoke = AsyncMock(side_effect=["Answer", "NONE"])
        await brain.process("Question?")
        assert mock_llm.invoke.call_count >= 1

    @pytest.mark.asyncio
    async def test_fact_extraction_stores_to_ltm(self, brain, mock_llm):
        mock_llm.invoke = AsyncMock(
            side_effect=["Nice to meet you, Alex!", "The user's name is Alex"]
        )
        initial_count = brain.ltm.collection_count
        await brain.process("Hi, my name is Alex!")
        assert brain.ltm.collection_count > initial_count

    @pytest.mark.asyncio
    async def test_fact_extraction_none_does_not_store(self, brain, mock_llm):
        mock_llm.invoke = AsyncMock(side_effect=["Hello!", "NONE"])
        initial_count = brain.ltm.collection_count
        await brain.process("Hello!")
        assert brain.ltm.collection_count == initial_count
