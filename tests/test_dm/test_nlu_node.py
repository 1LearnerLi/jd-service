"""DM 层 — NLU 节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.nlu_node import nlu_node, get_classifier, reset_classifier


class TestNluNode:
    """nlu_node 函数测试"""

    @staticmethod
    def _make_mock_classifier(return_value):
        """构造 mock IntentClassifier"""
        classifier = MagicMock()
        classifier.classify = AsyncMock(return_value=return_value)
        return classifier

    def setup_method(self):
        """每个测试前重置分类器单例"""
        reset_classifier()

    @pytest.mark.asyncio
    async def test_nlu_node_new_intent(self, monkeypatch):
        """验证创建新意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="order_query",
                confidence=0.95,
                slots_update={"order_id": "ORD-001"},
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
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "order_query"
        assert "order_query" in result["intents"]
        assert result["intents"]["order_query"]["status"] == "active"
        assert result["intents"]["order_query"]["slots"] == {"order_id": "ORD-001"}
        assert result["should_fallback"] is False

    @pytest.mark.asyncio
    async def test_nlu_node_continue_merges_slots(self, monkeypatch):
        """验证 continue action 合并槽位到活跃意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="continue",
                target_intent="postsale_return",
                confidence=0.88,
                slots_update={"postsale_type": "refund_only"},
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
            "all_intents": [],
            "intents": {
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                }
            },
            "active_intent": "postsale_return",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "postsale_return"
        assert result["intents"]["postsale_return"]["slots"] == {
            "order_id": "ORD-001",
            "postsale_type": "refund_only",
        }

    @pytest.mark.asyncio
    async def test_nlu_node_new_suspends_active(self, monkeypatch):
        """验证 new action 挂起当前活跃意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="order_query",
                confidence=0.92,
                slots_update={"order_id": "ORD-003"},
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "查订单 ORD-003",
            "all_intents": [],
            "intents": {
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                }
            },
            "active_intent": "postsale_return",
            "messages": [],
        }

        result = await nlu_node(state)

        # 旧意图被挂起
        assert result["intents"]["postsale_return"]["status"] == "suspended"
        # 新意图激活
        assert result["intents"]["order_query"]["status"] == "active"
        assert result["active_intent"] == "order_query"

    @pytest.mark.asyncio
    async def test_nlu_node_unknown_intent(self, monkeypatch):
        """验证 NLU 节点处理 unknown 意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="unknown",
                confidence=0.1,
                slots_update={},
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "user_input": "asdfghjkl",
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "unknown"
        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_nlu_node_transfer_human(self, monkeypatch):
        """验证 NLU 节点处理转人工意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="transfer_human",
                confidence=0.92,
                slots_update={},
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "user_input": "我要找人工客服",
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "transfer_human"
        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_nlu_node_passes_context_to_classifier(self, monkeypatch):
        """验证 NLU 节点将 all_intents 和 session_intents 传给分类器"""
        from app.nlu.models import NLUResult
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(
            return_value=NLUResult(
                action="continue",
                target_intent="order_query",
                confidence=0.9,
                slots_update={"order_id": "999"},
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        all_intents = [{"name": "order_query", "description": "订单查询"}]
        session_intents = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {},
                "required_slots": ["order_id"],
                "optional_slots": [],
            }
        }
        messages = [
            {"role": "user", "content": "查订单"},
            {"role": "assistant", "content": "请选择要查询的订单"},
        ]

        state = {
            "user_input": "999",
            "all_intents": all_intents,
            "intents": session_intents,
            "active_intent": "order_query",
            "messages": messages,
        }

        await nlu_node(state)

        # 验证 classify 被调用时参数正确
        mock_classifier.classify.assert_called_once_with(
            user_input="999",
            all_intents=all_intents,
            session_intents=session_intents,
            active_intent="order_query",
            messages=messages,
        )

    @pytest.mark.asyncio
    async def test_nlu_node_cancel_intent(self, monkeypatch):
        """验证 cancel action"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="cancel",
                target_intent="order_query",
                confidence=0.9,
                slots_update={},
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        state = {
            "user_input": "算了不查了",
            "all_intents": [],
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
            "active_intent": "order_query",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["intents"]["order_query"]["status"] == "cancelled"
        assert result["active_intent"] == ""

    @pytest.mark.asyncio
    async def test_nlu_node_with_empty_state(self, monkeypatch):
        """验证 NLU 节点处理空 state"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="unknown",
                confidence=0.0,
                slots_update={},
            )
        )
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )

        result = await nlu_node({})

        assert result["active_intent"] == "unknown"
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
