"""DM 层 — 回复节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.response_node import response_node, get_engine, reset_engine
from app.business.base import BusinessResult


class TestResponseNode:
    """response_node 函数测试"""

    def setup_method(self):
        """每个测试前重置 NLG 引擎单例"""
        reset_engine()

    @pytest.mark.asyncio
    async def test_response_node_with_business_result(self, monkeypatch):
        """验证有 business_result 时直接使用其 message"""
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="📋 订单 ORD-001 详情已加载"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        state = {
            "active_intent": "order_query",
            "business_result": BusinessResult.completed(
                message="📋 订单 ORD-001 详情已加载",
                order_id="ORD-001",
            ),
            "should_fallback": False,
            "user_input": "查订单",
        }

        result = await response_node(state)

        assert result["final_response"] == "📋 订单 ORD-001 详情已加载"

        # 验证 NLGEngine.generate 被正确调用
        mock_engine.generate.assert_called_once_with(
            intent="order_query",
            business_result=state["business_result"],
            context=None,
        )

    @pytest.mark.asyncio
    async def test_response_node_ask_slot(self, monkeypatch):
        """验证 ask_slot 的 message 被正确传递"""
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="请选择要查询的订单"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        state = {
            "active_intent": "order_query",
            "business_result": BusinessResult.ask_slot(
                slot_to_fill="order_id",
                options=[],
                message="请选择要查询的订单",
            ),
            "should_fallback": False,
            "user_input": "",
        }

        result = await response_node(state)

        assert result["final_response"] == "请选择要查询的订单"

    @pytest.mark.asyncio
    async def test_response_node_transfer_human(self, monkeypatch):
        """验证转人工回复"""
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="正在为您转接人工客服，请稍候..."
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        state = {
            "active_intent": "transfer_human",
            "business_result": None,
            "should_fallback": True,
            "user_input": "转人工",
        }

        result = await response_node(state)

        assert "转接人工" in result["final_response"]

        # 兜底场景应传入 context
        mock_engine.generate.assert_called_once_with(
            intent="transfer_human",
            business_result=None,
            context={"user_input": "转人工"},
        )

    @pytest.mark.asyncio
    async def test_response_node_unknown_with_fallback(self, monkeypatch):
        """验证兜底场景传入 context"""
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="抱歉，我不太明白您的意思，请换个说法试试。"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        state = {
            "active_intent": "unknown",
            "business_result": None,
            "should_fallback": True,
            "user_input": "asdfghjkl",
        }

        result = await response_node(state)

        assert result["final_response"] != ""

        # should_fallback 时传入 user_input
        mock_engine.generate.assert_called_once_with(
            intent="unknown",
            business_result=None,
            context={"user_input": "asdfghjkl"},
        )

    @pytest.mark.asyncio
    async def test_response_node_error_result(self, monkeypatch):
        """验证业务错误消息被正确传递"""
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="订单不存在，请确认订单号是否正确"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        state = {
            "active_intent": "order_query",
            "business_result": BusinessResult.error(
                "订单不存在，请确认订单号是否正确"
            ),
            "should_fallback": False,
            "user_input": "",
        }

        result = await response_node(state)

        assert "订单不存在" in result["final_response"]


class TestGetEngine:
    """get_engine 单例测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_engine()

    def test_get_engine_returns_instance(self):
        """验证获取引擎实例"""
        engine = get_engine()
        from app.nlg.engine import NLGEngine
        assert isinstance(engine, NLGEngine)

    def test_get_engine_is_singleton(self):
        """验证引擎是单例"""
        e1 = get_engine()
        e2 = get_engine()
        assert e1 is e2

    def test_reset_engine(self):
        """验证重置引擎"""
        e1 = get_engine()
        reset_engine()
        e2 = get_engine()
        assert e1 is not e2
