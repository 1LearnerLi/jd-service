"""DM 层 — 兜底节点测试"""
import pytest

from app.dm.nodes.fallback_node import fallback_node


class TestFallbackNode:
    """fallback_node 函数测试"""

    @pytest.mark.asyncio
    async def test_fallback_node_unknown(self):
        """验证 unknown 意图触发兜底"""
        state = {
            "active_intent": "unknown",
        }

        result = await fallback_node(state)

        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_fallback_node_transfer_human(self):
        """验证 transfer_human 意图触发兜底"""
        state = {
            "active_intent": "transfer_human",
        }

        result = await fallback_node(state)

        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_fallback_node_empty_intent(self):
        """验证空意图也触发兜底（安全兜底）"""
        state = {
            "active_intent": "",
        }

        result = await fallback_node(state)

        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_fallback_node_preserves_other_state(self):
        """验证兜底节点不修改 state 其他字段"""
        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "unknown",
            "slots": {"order_id": "ORD-001"},
            "final_response": "",
        }

        result = await fallback_node(state)

        # 只应设置 should_fallback，不应修改其他字段
        assert result == {"should_fallback": True}
