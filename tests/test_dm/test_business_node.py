"""DM 层 — 业务节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.business_node import business_node, get_handler_map
from app.business.base import BusinessContext, BusinessResult, OptionItem


class TestBusinessNode:
    """business_node 函数测试"""

    @pytest.mark.asyncio
    async def test_business_node_order_query_completed(self, monkeypatch):
        """验证订单查询完成后返回 completed"""
        mock_result = BusinessResult.completed(
            message="📋 订单 ORD-001 详情已加载",
            order_id="ORD-001",
            order_status="已签收",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        monkeypatch.setitem(
            __import__("app.dm.nodes.business_node", fromlist=["_handler_map"])._handler_map,
            "order_query",
            handler_cls,
        )

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "slots": {"order_id": "ORD-001"},
        }

        result = await business_node(state)

        assert result["business_result"] is not None
        br = result["business_result"]
        assert br.success is True
        assert br.data["action"] == "completed"
        assert br.data["message"] == "📋 订单 ORD-001 详情已加载"

    @pytest.mark.asyncio
    async def test_business_node_ask_slot(self, monkeypatch):
        """验证业务节点返回 ask_slot"""
        options = [
            OptionItem(label="ORD-001（已签收）", value="ORD-001"),
            OptionItem(label="ORD-002（已付款）", value="ORD-002"),
        ]
        mock_result = BusinessResult.ask_slot(
            slot_to_fill="order_id",
            options=options,
            message="请选择要查询的订单",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        monkeypatch.setitem(
            __import__("app.dm.nodes.business_node", fromlist=["_handler_map"])._handler_map,
            "order_query",
            handler_cls,
        )

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "slots": {},
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is True
        assert br.data["action"] == "ask_slot"
        assert br.data["slot_to_fill"] == "order_id"
        assert len(br.data["options"]) == 2

    @pytest.mark.asyncio
    async def test_business_node_error(self, monkeypatch):
        """验证业务节点处理业务错误"""
        mock_result = BusinessResult.error("订单不存在")
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        monkeypatch.setitem(
            __import__("app.dm.nodes.business_node", fromlist=["_handler_map"])._handler_map,
            "order_query",
            handler_cls,
        )

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "slots": {"order_id": "INVALID"},
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "订单不存在"

    @pytest.mark.asyncio
    async def test_business_node_passes_correct_context(self, monkeypatch):
        """验证业务节点构造并传递正确的 BusinessContext"""
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(
            return_value=BusinessResult.completed(message="ok")
        )
        handler_cls = MagicMock(return_value=mock_handler)

        monkeypatch.setitem(
            __import__("app.dm.nodes.business_node", fromlist=["_handler_map"])._handler_map,
            "order_query",
            handler_cls,
        )

        state = {
            "session_id": "sess-abc",
            "user_id": "user-xyz",
            "active_intent": "order_query",
            "slots": {"order_id": "ORD-001", "extra": "foo"},
        }

        await business_node(state)

        # 验证 handler.handle 被调用且参数正确
        mock_handler.handle.assert_called_once()
        ctx = mock_handler.handle.call_args[0][0]
        assert isinstance(ctx, BusinessContext)
        assert ctx.session_id == "sess-abc"
        assert ctx.user_id == "user-xyz"
        assert ctx.intent == "order_query"
        assert ctx.slots == {"order_id": "ORD-001", "extra": "foo"}

    @pytest.mark.asyncio
    async def test_business_node_unregistered_intent(self):
        """验证未注册意图的处理"""
        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "nonexistent_intent",
            "slots": {},
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "该功能暂未开放"

    @pytest.mark.asyncio
    async def test_business_node_with_real_handler(self):
        """使用真实 OrderQueryHandler 测试业务节点（需 mock repo）"""
        # 此测试验证 handler 注册表包含预期的意图
        handler_map = get_handler_map()
        assert "order_query" in handler_map
        assert "postsale_return" in handler_map

        from app.business.ecommerce.handlers.order_query import OrderQueryHandler
        from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler

        assert handler_map["order_query"] is OrderQueryHandler
        assert handler_map["postsale_return"] is PostsaleReturnHandler
