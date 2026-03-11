"""
Echo-Iris — Brain Orchestrator

The Brain ties Short-Term Memory, Long-Term Memory, the LLM, and
OS Tools together. It handles the full request lifecycle:

    1. Append the user message to STM.
    2. Retrieve relevant context from LTM.
    3. Build the prompt (system + LTM context + STM window).
    4. Invoke the LLM (with tool awareness).
    5. If the LLM requests tool calls → execute → re-invoke.
    6. Append the AI reply to STM.
    7. Optionally extract and store new facts in LTM.
"""

from __future__ import annotations

import logging

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from app.config import settings
from app.core.llm import LLMClient
from app.core.ltm import LongTermMemory
from app.core.stm import ShortTermMemory

logger = logging.getLogger(__name__)

# Prompt template used by the Brain to ask the LLM to extract memorable facts.
_FACT_EXTRACTION_PROMPT = (
    "You are a memory curator. Given the following conversation exchange, "
    "extract ONLY concrete, personally relevant facts worth remembering long-term "
    "(e.g., the user's name, preferences, important life events). "
    "If there is nothing worth remembering, reply with exactly: NONE\n\n"
    "User: {user_msg}\n"
    "Assistant: {ai_msg}\n\n"
    "Extracted facts (one per line, or NONE):"
)


class Brain:
    """
    Central orchestrator for Echo-Iris's reasoning pipeline.

    Usage::

        brain = Brain()
        reply = await brain.process("Hello, my name is Alex!")
    """

    def __init__(
        self,
        stm: ShortTermMemory | None = None,
        ltm: LongTermMemory | None = None,
        llm: LLMClient | None = None,
    ):
        self.stm = stm or ShortTermMemory()
        self.ltm = ltm or LongTermMemory()
        self.llm = llm or LLMClient()
        self._tool_executor = None

        # Bind tools if enabled
        if settings.tools_enabled:
            self._init_tools()

        logger.info("Brain initialised")

    def _init_tools(self) -> None:
        """Set up LangChain tools and bind them to the LLM."""
        from app.tools.registry import ALL_TOOLS, set_stm_reference
        from app.tools.executor import ToolExecutor

        set_stm_reference(self.stm)
        self.llm.bind_tools(ALL_TOOLS)
        self._tool_executor = ToolExecutor(ALL_TOOLS)
        logger.info("Tools initialised and bound to LLM")

    # -- public API -----------------------------------------------------------

    async def process(self, user_message: str) -> dict:
        """
        Full reasoning cycle.  Returns::

            {"reply": "...", "ltm_hits": 2}
        """
        # 1. Append user message to short-term memory
        self.stm.append("user", user_message)

        # 2. Retrieve relevant long-term memories
        ltm_docs = self.ltm.retrieve(user_message)
        ltm_hits = len(ltm_docs)

        # 3. Build the prompt
        messages = self._build_prompt(ltm_docs)

        # 4. Invoke the LLM (tool-aware)
        ai_reply = await self._invoke_with_tool_loop(messages)

        # 5. Append assistant reply to STM
        self.stm.append("assistant", ai_reply)

        # 6. Background: extract & store facts (best-effort)
        await self._maybe_store_facts(user_message, ai_reply)

        return {"reply": ai_reply, "ltm_hits": ltm_hits}

    async def stream_process(self, user_message: str):
        """
        Same as :meth:`process`, but yields LLM reply tokens as they
        stream in.  If a tool call is detected, the tool is executed
        first (non-streaming), then the verbal reply is streamed.

        Yields
        ------
        str
            Individual text tokens / chunks from the LLM.
        """
        # 1. Append user message to STM
        self.stm.append("user", user_message)

        # 2. Retrieve LTM context
        ltm_docs = self.ltm.retrieve(user_message)

        # 3. Build prompt
        messages = self._build_prompt(ltm_docs)

        # 4. First pass — check for tool calls (non-streaming)
        if self._tool_executor is not None:
            response = await self.llm.invoke_with_tools(messages)

            if hasattr(response, "tool_calls") and response.tool_calls:
                # Execute tools and append results
                messages = self._execute_tool_calls(messages, response)

                # Stream the second pass (verbal reply)
                full_reply_parts = []
                async for token in self.llm.stream(messages):
                    full_reply_parts.append(token)
                    yield token

                full_reply = "".join(full_reply_parts)
                self.stm.append("assistant", full_reply)
                await self._maybe_store_facts(user_message, full_reply)
                return
            else:
                # No tool calls — use the response directly if it has content
                ai_text = response.content if hasattr(response, "content") else ""
                if ai_text:
                    yield ai_text
                    self.stm.append("assistant", ai_text)
                    await self._maybe_store_facts(user_message, ai_text)
                    return

        # Fallback: stream without tools
        full_reply_parts = []
        async for token in self.llm.stream(messages):
            full_reply_parts.append(token)
            yield token

        full_reply = "".join(full_reply_parts)
        self.stm.append("assistant", full_reply)
        await self._maybe_store_facts(user_message, full_reply)

    # -- internal helpers -----------------------------------------------------

    async def _invoke_with_tool_loop(self, messages: list) -> str:
        """
        Invoke the LLM with tool support. If the LLM requests tool
        calls, execute them and re-invoke to get the verbal reply.
        Supports up to 3 rounds of tool calls to prevent infinite loops.
        """
        if self._tool_executor is None:
            # No tools — simple invoke
            return await self.llm.invoke(messages)

        for _ in range(3):  # max 3 tool rounds
            response = await self.llm.invoke_with_tools(messages)

            if not hasattr(response, "tool_calls") or not response.tool_calls:
                # No tool calls — return text
                return response.content if hasattr(response, "content") else str(response)

            # Execute tools and extend message chain
            messages = self._execute_tool_calls(messages, response)

        # Final invoke after tool rounds exhausted
        return await self.llm.invoke(messages)

    def _execute_tool_calls(self, messages: list, response: AIMessage) -> list:
        """Execute all tool calls in an AIMessage and return updated messages."""
        messages = list(messages)  # copy
        messages.append(response)  # AIMessage with tool_calls

        for tc in response.tool_calls:
            result = self._tool_executor.execute(tc)
            messages.append(
                ToolMessage(
                    content=result,
                    tool_call_id=tc.get("id", ""),
                )
            )
            logger.info("Tool %s → %s", tc.get("name"), result[:80])

        return messages

    def _build_prompt(self, ltm_docs: list[dict]) -> list:
        """Assemble the full message list for the LLM."""
        messages = []

        # a) System prompt (personality)
        messages.append(SystemMessage(content=settings.system_prompt))

        # b) LTM context — inject relevant memories as a system-level hint
        if ltm_docs:
            memory_block = "\n".join(
                f"- {doc['content']}" for doc in ltm_docs
            )
            messages.append(
                SystemMessage(
                    content=(
                        "Here are relevant things you remember about this person "
                        "and past conversations:\n" + memory_block
                    )
                )
            )

        # c) STM window (recent conversation)
        messages.extend(self.stm.get_context())

        return messages

    async def _maybe_store_facts(self, user_msg: str, ai_msg: str) -> None:
        """
        Ask the LLM to extract memorable facts from the latest exchange.

        This is a *best-effort* background step — failures are logged but
        never surface to the user.
        """
        try:
            extraction_prompt = _FACT_EXTRACTION_PROMPT.format(
                user_msg=user_msg, ai_msg=ai_msg
            )
            result = await self.llm.invoke(
                [SystemMessage(content=extraction_prompt)]
            )
            result = result.strip()
            if result.upper() == "NONE" or not result:
                return

            # Each non-empty line is treated as a separate fact
            facts = [line.strip("- ").strip() for line in result.splitlines() if line.strip()]
            for fact in facts:
                if fact.upper() != "NONE":
                    self.ltm.store(fact, metadata={"source": "auto_extraction"})
                    logger.info("LTM auto-stored: %s", fact[:60])
        except Exception:
            logger.exception("Fact extraction failed (non-fatal)")
