"""
Echo-Iris — LLM Wrapper

Thin abstraction over LangChain's Ollama integration.  Provides both
a chat interface and a raw health-check ping.
"""

from __future__ import annotations

import logging

import httpx
from langchain_core.messages import BaseMessage
from langchain_ollama import ChatOllama

from app.config import settings

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Wrapper around ChatOllama that exposes:

    * ``invoke(messages)`` — send a list of LangChain messages, get a reply.
    * ``ping()``           — check if Ollama is reachable.
    """

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ):
        self._model = model or settings.ollama_model
        self._base_url = base_url or settings.ollama_base_url

        self._chat = ChatOllama(
            model=self._model,
            base_url=self._base_url,
        )
        self._chat_with_tools = None
        logger.info("LLM client initialised — model=%s  url=%s", self._model, self._base_url)

    async def invoke(self, messages: list[BaseMessage]) -> str:
        """Send messages to the LLM and return the text response."""
        response = await self._chat.ainvoke(messages)
        text: str = response.content  # type: ignore[assignment]
        logger.debug("LLM response (%d chars): %s", len(text), text[:80])
        return text

    async def stream(self, messages: list[BaseMessage]):
        """Yield text chunks as they stream from the LLM."""
        async for chunk in self._chat.astream(messages):
            token = chunk.content  # type: ignore[union-attr]
            if token:
                yield token

    def bind_tools(self, tools: list) -> None:
        """Bind LangChain tools to the ChatOllama instance."""
        self._chat_with_tools = self._chat.bind_tools(tools)
        logger.info("Tools bound to LLM: %s", [t.name for t in tools])

    async def invoke_with_tools(self, messages: list[BaseMessage]):
        """
        Invoke with tool-calling capability.
        Returns the raw AIMessage so the caller can inspect tool_calls.
        """
        model = self._chat_with_tools or self._chat
        return await model.ainvoke(messages)

    async def ping(self) -> bool:
        """Return *True* if the Ollama server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(self._base_url)
                return resp.status_code == 200
        except Exception:
            logger.warning("Ollama ping failed at %s", self._base_url)
            return False
