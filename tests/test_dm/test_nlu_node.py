"""DM 层 — NLU 节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.nlu_node import nlu_node, get_classifier, reset_classifier
from app.nlu.models import NLUResult


class TestNluNode:
    """nlu_node 函数测试"""

    @staticmethod
    def _make_mock_classifier(return_value: NLUResult):
        """构造 mock IntentClassifier"""
        classifier = MagicMock()
        classifier.classify = AsyncMock(return_value=return_value)
        return classifier

    def setup_method(self):
        """每个测试前重置分类器单例"""
        reset_classifier()

    @pytest.mark.asyncio
    async def test_nlu_node_basic_classification(self, monkeypatch):
        """验证 NLU 节点基本分类功能"""
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                intent="order_query",
                confidence=0.95,
                slots={"order_id": "ORD-001"},
                missing_slots=[],
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "帮我查订单 ORD-001",
            "slots": {},
            "active_intent": "",
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "order_query"
        assert result["slots"] == {"order_id": "ORD-001"}
        assert result["missing_slots"] == []
        assert result["should_fallback"] is False

    @pytest.mark.asyncio
    async def test_nlu_node_merges_slots(self, monkeypatch):
        """验证 NLU 节点合并已有槽位和新提取槽位"""
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                intent="postsale_return",
                confidence=0.88,
                slots={"postsale_type": "refund_only"},
                missing_slots=["postsale_reason"],
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "仅退款",
            "slots": {"order_id": "ORD-001"},
            "active_intent": "postsale_return",
        }

        result = await nlu_node(state)

        # 已有 order_id，新提取 postsale_type，应合并
        assert result["slots"] == {
            "order_id": "ORD-001",
            "postsale_type": "refund_only",
        }
        assert result["active_intent"] == "postsale_return"
        assert result["missing_slots"] == ["postsale_reason"]

    @pytest.mark.asyncio
    async def test_nlu_node_unknown_intent(self, monkeypatch):
        """验证 NLU 节点处理 unknown 意图"""
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                intent="unknown",
                confidence=0.1,
                slots={},
                missing_slots=[],
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "user_input": "asdfghjkl",
            "slots": {},
            "active_intent": "",
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "unknown"
        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_nlu_node_transfer_human(self, monkeypatch):
        """验证 NLU 节点处理转人工意图"""
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                intent="transfer_human",
                confidence=0.92,
                slots={},
                missing_slots=[],
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "user_input": "我要找人工客服",
            "slots": {},
            "active_intent": "",
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "transfer_human"
        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_nlu_node_passes_context_to_classifier(self, monkeypatch):
        """验证 NLU 节点将当前上下文正确传递给分类器"""
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(
            return_value=NLUResult(
                intent="order_query",
                confidence=0.8,
                slots={"order_id": "999"},
                missing_slots=[],
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        messages = [
            {"role": "user", "content": "查订单"},
            {"role": "assistant", "content": "请选择要查询的订单"},
        ]

        state = {
            "user_input": "999",
            "slots": {"order_id": "888"},
            "active_intent": "order_query",
            "messages": messages,
        }

        await nlu_node(state)

        # 验证 classify 被调用时参数正确
        mock_classifier.classify.assert_called_once_with(
            user_input="999",
            current_slots={"order_id": "888"},
            active_intent="order_query",
            messages=messages,
        )

    @pytest.mark.asyncio
    async def test_nlu_node_with_empty_state(self, monkeypatch):
        """验证 NLU 节点处理空 state"""
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                intent="unknown",
                confidence=0.0,
                slots={},
                missing_slots=[],
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        result = await nlu_node({})

        assert result["active_intent"] == "unknown"
        assert result["slots"] == {}
        assert result["should_fallback"] is True


class TestGetClassifier:
    """get_classifier 单例测试"""

    def setup_method(self):
        """每个测试前重置"""
        reset_classifier()

    def test_get_classifier_returns_instance(self):
        """验证获取分类器实例"""
        classifier = get_classifier()
        from app.nlu.classifier import IntentClassifier
        assert isinstance(classifier, IntentClassifier)

    def test_get_classifier_is_singleton(self):
        """验证分类器是单例"""
        c1 = get_classifier()
        c2 = get_classifier()
        assert c1 is c2

    def test_reset_classifier(self):
        """验证重置分类器"""
        c1 = get_classifier()
        reset_classifier()
        c2 = get_classifier()
        assert c1 is not c2
