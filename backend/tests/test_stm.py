"""
Tests for Short-Term Memory (STM).
"""

from app.core.stm import ShortTermMemory


class TestShortTermMemory:
    """Unit tests for the STM sliding window."""

    def test_append_and_count(self):
        stm = ShortTermMemory(max_messages=5)
        assert stm.count == 0

        stm.append("user", "Hello")
        assert stm.count == 1

        stm.append("assistant", "Hi there!")
        assert stm.count == 2

    def test_overflow_evicts_oldest(self):
        stm = ShortTermMemory(max_messages=3)
        stm.append("user", "msg1")
        stm.append("assistant", "msg2")
        stm.append("user", "msg3")
        stm.append("assistant", "msg4")  # should evict msg1

        assert stm.count == 3
        raw = stm.get_raw()
        contents = [r["content"] for r in raw]
        assert "msg1" not in contents
        assert contents == ["msg2", "msg3", "msg4"]

    def test_get_context_returns_langchain_messages(self):
        from langchain_core.messages import AIMessage, HumanMessage

        stm = ShortTermMemory(max_messages=10)
        stm.append("user", "Hello")
        stm.append("assistant", "Hi!")

        ctx = stm.get_context()
        assert len(ctx) == 2
        assert isinstance(ctx[0], HumanMessage)
        assert isinstance(ctx[1], AIMessage)
        assert ctx[0].content == "Hello"
        assert ctx[1].content == "Hi!"

    def test_clear(self):
        stm = ShortTermMemory(max_messages=5)
        stm.append("user", "Hello")
        stm.clear()
        assert stm.count == 0

    def test_get_raw_format(self):
        stm = ShortTermMemory(max_messages=5)
        stm.append("user", "test")
        raw = stm.get_raw()
        assert len(raw) == 1
        assert raw[0]["role"] == "user"
        assert raw[0]["content"] == "test"
        assert "ts" in raw[0]

    def test_invalid_role_raises(self):
        stm = ShortTermMemory(max_messages=5)
        try:
            stm.append("invalid_role", "oops")
            assert False, "Expected ValueError"
        except ValueError:
            pass
