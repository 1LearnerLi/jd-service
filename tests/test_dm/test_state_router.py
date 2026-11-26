"""DM 层 — 状态与路由单元测试"""
import pytest

from app.dm.state import DialogState, IntentContext
from app.dm.router import is_platform_intent


class TestIntentContext:
    """IntentContext 类型测试"""

    def test_intent_context_structure(self):
        """验证 IntentContext 可构造并包含所有字段"""
        ctx: IntentContext = {
            "name": "order_query",
            "confidence": 0.95,
            "required_slots": ["order_id"],
            "optional_slots": [],
        }
        assert ctx["name"] == "order_query"
        assert ctx["confidence"] == 0.95
        assert ctx["required_slots"] == ["order_id"]
        assert ctx["optional_slots"] == []

    def test_intent_context_empty_slots(self):
        """验证 IntentContext 可以为空槽位列表"""
        ctx: IntentContext = {
            "name": "unknown",
            "confidence": 0.0,
            "required_slots": [],
            "optional_slots": [],
        }
        assert ctx["required_slots"] == []
        assert ctx["optional_slots"] == []


class TestDialogState:
    """DialogState 类型测试"""

    def test_dialog_state_structure(self):
        """验证 DialogState 可构造并包含所有字段"""
        state: DialogState = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "查订单",
            "messages": [],
            "intents": {},
            "active_intent": "",
            "slots": {},
            "missing_slots": [],
            "business_result": None,
            "final_response": "",
            "should_fallback": False,
        }
        assert state["session_id"] == "sess-001"
        assert state["user_id"] == "user-001"
        assert state["user_input"] == "查订单"
        assert state["messages"] == []
        assert state["intents"] == {}
        assert state["active_intent"] == ""
        assert state["slots"] == {}
        assert state["missing_slots"] == []
        assert state["business_result"] is None
        assert state["final_response"] == ""
        assert state["should_fallback"] is False

    def test_dialog_state_with_data(self):
        """验证 DialogState 包含业务数据"""
        state: DialogState = {
            "session_id": "sess-002",
            "user_id": "user-002",
            "user_input": "ORD-001",
            "messages": [
                {"role": "user", "content": "查订单"},
                {"role": "assistant", "content": "请选择要查询的订单"},
            ],
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
            "slots": {"order_id": "ORD-001"},
            "missing_slots": [],
            "business_result": {"action": "completed", "message": "查询完成"},
            "final_response": "您的订单详情...",
            "should_fallback": False,
        }
        assert state["active_intent"] == "order_query"
        assert state["slots"]["order_id"] == "ORD-001"
        assert state["intents"]["order_query"]["confidence"] == 0.9
        assert state["business_result"]["action"] == "completed"

    def test_dialog_state_with_messages(self):
        """验证 messages 字段格式"""
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "您好，有什么可以帮您的？"},
            {"role": "user", "content": "查订单"},
        ]
        state: DialogState = {
            "session_id": "sess-003",
            "user_id": "user-003",
            "user_input": "ORD-001",
            "messages": messages,
            "intents": {},
            "active_intent": "order_query",
            "slots": {},
            "missing_slots": ["order_id"],
            "business_result": None,
            "final_response": "",
            "should_fallback": False,
        }
        assert len(state["messages"]) == 3
        assert state["messages"][0]["role"] == "user"
        assert state["messages"][1]["role"] == "assistant"


class TestIsPlatformIntent:
    """is_platform_intent 路由函数测试"""

    def test_unknown_is_platform(self):
        """验证 unknown 被识别为平台意图"""
        assert is_platform_intent({"active_intent": "unknown"}) is True

    def test_transfer_human_is_platform(self):
        """验证 transfer_human 被识别为平台意图"""
        assert is_platform_intent({"active_intent": "transfer_human"}) is True

    def test_order_query_is_not_platform(self):
        """验证 order_query 不是平台意图"""
        assert is_platform_intent({"active_intent": "order_query"}) is False

    def test_postsale_return_is_not_platform(self):
        """验证 postsale_return 不是平台意图"""
        assert is_platform_intent({"active_intent": "postsale_return"}) is False

    def test_product_inquiry_is_not_platform(self):
        """验证 product_inquiry 不是平台意图"""
        assert is_platform_intent({"active_intent": "product_inquiry"}) is False

    def test_empty_intent_is_not_platform(self):
        """验证空意图不是平台意图"""
        assert is_platform_intent({"active_intent": ""}) is False

    def test_missing_key_defaults_to_false(self):
        """验证 state 中没有 active_intent 时返回 False"""
        assert is_platform_intent({}) is False
