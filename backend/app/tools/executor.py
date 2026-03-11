"""
Echo-Iris — Tool Executor

Safely executes tool calls returned by the LLM.
Wraps each call with timeout and error handling.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Any

logger = logging.getLogger(__name__)

# Dedicated thread pool for tool execution
_tool_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="tool")

# Default timeout per tool call (seconds)
_TOOL_TIMEOUT = 5.0


class ToolExecutor:
    """
    Executes LangChain tool calls safely.

    Usage::

        executor = ToolExecutor(tools)
        result = executor.execute(tool_call)
    """

    def __init__(self, tools: list):
        self._tool_map = {t.name: t for t in tools}
        logger.info(
            "ToolExecutor ready — %d tools: %s",
            len(self._tool_map),
            ", ".join(self._tool_map.keys()),
        )

    def execute(self, tool_call: dict[str, Any]) -> str:
        """
        Execute a single tool call.

        Parameters
        ----------
        tool_call : dict
            LangChain tool call dict with 'name', 'args', and 'id'.

        Returns
        -------
        str
            Tool result string (always returns something, never raises).
        """
        name = tool_call.get("name", "")
        args = tool_call.get("args", {})
        call_id = tool_call.get("id", "unknown")

        logger.info("Executing tool: %s(%s)  [id=%s]", name, args, call_id)

        tool_fn = self._tool_map.get(name)
        if tool_fn is None:
            msg = f"Unknown tool: {name}"
            logger.warning(msg)
            return msg

        try:
            # Run tool in thread pool with timeout
            future = _tool_pool.submit(tool_fn.invoke, args)
            result = future.result(timeout=_TOOL_TIMEOUT)
            logger.info("Tool %s returned: %s", name, str(result)[:100])
            return str(result)
        except FuturesTimeout:
            msg = f"Tool '{name}' timed out after {_TOOL_TIMEOUT}s"
            logger.error(msg)
            return msg
        except Exception as e:
            msg = f"Tool '{name}' failed: {e}"
            logger.exception(msg)
            return msg
