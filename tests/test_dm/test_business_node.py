"""DM 层 — 业务节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.business_node import business_node
from app.business.base import BusinessResult, OptionItem
from app.nlu.registry import IntentRegistry
from app.nlu.models import IntentDefinition


class TestBusinessNode:
    """business_node 函数测试"""

    def setup_method(self):
        """每个测试前清空注册中心"""
        IntentRegistry.clear()

    def _register_mock_intent(self, intent_name: str, handler_cls):
        """向注册中心注册一个带 handler 的模拟意图"""
        intent_def = IntentDefinition(
            name=intent_name,
            description="测试意图",
            handler=handler_cls,
        )
        IntentRegistry.register_business("test", [intent_def])

    @pytest.mark.asyncio
    async def test_business_node_completed_updates_intent_status(self):
        """验证业务完成后意图状态变为 completed"""
        mock_result = BusinessResult.completed(
            message="📋 订单 ORD-001 详情已加载",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        assert result["business_result"] is not None
        br = result["business_result"]
        assert br.success is True
        assert br.data["action"] == "completed"
        # Controller 标记完成
        assert result["intents"]["order_query"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_business_node_completed_restores_suspended(self):
        """验证业务完成后自动恢复挂起的意图"""
        mock_result = BusinessResult.completed(
            message="📋 订单 ORD-003 详情已加载",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-003"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                },
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "suspended",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                },
            },
        }

        result = await business_node(state)

        assert result["intents"]["order_query"]["status"] == "completed"
        # 挂起的售后意图被恢复
        assert result["intents"]["postsale_return"]["status"] == "active"
        assert result["active_intent"] == "postsale_return"

    @pytest.mark.asyncio
    async def test_business_node_ask_slot(self):
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

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is True
        assert br.data["action"] == "ask_slot"
        assert br.data["slot_to_fill"] == "order_id"
        assert len(br.data["options"]) == 2

    @pytest.mark.asyncio
    async def test_business_node_error(self):
        """验证业务节点处理业务错误"""
        mock_result = BusinessResult.error("订单不存在")
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "INVALID"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "订单不存在"

    @pytest.mark.asyncio
    async def test_business_node_unregistered_intent(self):
        """验证未注册意图的处理（handler 为 None）"""
        intent_def = IntentDefinition(
            name="product_inquiry",
            description="商品咨询",
            handler=None,
        )
        IntentRegistry.register_business("test", [intent_def])

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "product_inquiry",
            "intents": {
                "product_inquiry": {
                    "name": "product_inquiry",
                    "confidence": 0.8,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["query"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "该功能暂未开放"

    @pytest.mark.asyncio
    async def test_business_node_nonexistent_intent(self):
        """验证完全未注册意图的处理"""
        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "nonexistent_intent",
            "intents": {},
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "该功能暂未开放"

    @pytest.mark.asyncio
    async def test_business_node_passes_correct_context(self):
        """验证业务节点构造并传递正确的 BusinessContext（含独立槽位）"""
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(
            return_value=BusinessResult.completed(message="ok")
        )
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-abc",
            "user_id": "user-xyz",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        await business_node(state)

        # 验证 handler.handle 被调用且参数正确
        mock_handler.handle.assert_called_once()
        from app.business.base import BusinessContext
        ctx = mock_handler.handle.call_args[0][0]
        assert isinstance(ctx, BusinessContext)
        assert ctx.session_id == "sess-abc"
        assert ctx.user_id == "user-xyz"
        assert ctx.intent == "order_query"
        assert ctx.slots == {"order_id": "ORD-001"}

    @pytest.mark.asyncio
    async def test_business_node_with_real_handler(self):
        """使用真实 Handler 类验证注册中心可获取 handler"""
        from app.business.ecommerce.handlers.order_query import OrderQueryHandler
        from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler

        # 注册电商意图（带真实 handler）
        IntentRegistry.register_business(
            "ecommerce",
            [
                IntentDefinition(
                    name="order_query",
                    description="订单查询",
                    handler=OrderQueryHandler,
                ),
                IntentDefinition(
                    name="postsale_return",
                    description="售后申请",
                    handler=PostsaleReturnHandler,
                ),
            ],
        )

        handler_cls = IntentRegistry.get_handler("order_query")
        assert handler_cls is OrderQueryHandler

        handler_cls2 = IntentRegistry.get_handler("postsale_return")
        assert handler_cls2 is PostsaleReturnHandler
