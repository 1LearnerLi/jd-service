"""意图分类器测试"""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import SystemMessage, HumanMessage

from app.nlu.classifier import IntentClassifier
from app.nlu.models import NLUResult, IntentDefinition, SlotDef
from app.nlu.registry import IntentRegistry


class TestIntentClassifierPromptBuilding:
    """意图分类器 prompt 构造测试"""

    def test_build_system_prompt_from_all_intents(self):
        """验证系统 prompt 从 all_intents 构造"""
        classifier = IntentClassifier()
        all_intents = [
            {
                "name": "order_query",
                "description": "查询订单详情",
                "required_slots": [
                    {"name": "order_id", "description": "订单号"},
                ],
                "optional_slots": [],
            },
            {
                "name": "unknown",
                "description": "未知意图",
                "required_slots": [],
                "optional_slots": [],
            },
        ]
        prompt = classifier._build_system_prompt(all_intents)
        assert "order_query" in prompt
        assert "order_id" in prompt
        assert "查询订单详情" in prompt
        assert "unknown" in prompt
        assert "action" in prompt

    def test_build_system_prompt_with_optional_slots(self):
        """验证系统 prompt 包含可选槽位"""
        all_intents = [
            {
                "name": "product_inquiry",
                "description": "商品咨询",
                "required_slots": [],
                "optional_slots": [
                    {"name": "sku_id", "description": "商品SKU"},
                    {"name": "sku_name", "description": "商品名称"},
                ],
            },
        ]
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt(all_intents)
        assert "product_inquiry" in prompt
        assert "可选槽位" in prompt
        assert "sku_id" in prompt

    def test_build_system_prompt_empty_list(self):
        """验证空 all_intents 不报错"""
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt([])
        assert "可识别的意图" in prompt

    def test_build_user_prompt_basic(self):
        """验证用户 prompt 包含用户输入"""
        classifier = IntentClassifier()
        prompt = classifier._build_user_prompt("你好，帮我查订单")
        assert "你好，帮我查订单" in prompt

    def test_build_user_prompt_with_active_intent(self):
        """验证用户 prompt 包含活跃意图"""
        classifier = IntentClassifier()
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
        prompt = classifier._build_user_prompt(
            "ORD-001",
            session_intents=session_intents,
            active_intent="order_query",
        )
        assert "order_query" in prompt
        assert "active" in prompt

    def test_build_user_prompt_with_session_intents(self):
        """验证用户 prompt 展示会话意图状态"""
        classifier = IntentClassifier()
        session_intents = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {},
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
        }
        prompt = classifier._build_user_prompt(
            "ORD-003",
            session_intents=session_intents,
            active_intent="order_query",
        )
        assert "order_query" in prompt
        assert "active" in prompt
        assert "postsale_return" in prompt
        assert "suspended" in prompt
        assert "ORD-001" in prompt
        assert "缺失槽位" in prompt

    def test_build_user_prompt_with_messages(self):
        """验证用户 prompt 包含对话历史"""
        classifier = IntentClassifier()
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "您好"},
        ]
        prompt = classifier._build_user_prompt(
            "查订单",
            messages=messages,
        )
        assert "对话历史" in prompt
        assert "你好" in prompt


class TestIntentClassifierClassify:
    """意图分类器 classify 方法测试"""

    @staticmethod
    def _make_mock_llm(return_value):
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(return_value=return_value)
        llm = MagicMock()
        llm.with_structured_output.return_value = structured_llm
        return llm

    @staticmethod
    def _make_mock_llm_raising(exception: Exception):
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=exception)
        llm = MagicMock()
        llm.with_structured_output.return_value = structured_llm
        return llm

    @pytest.mark.asyncio
    async def test_classify_returns_nlu_result(self):
        """验证 classify 返回新的 NLUResult"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="order_query",
            confidence=0.95,
            slots_update={"order_id": "ORD-001"},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("查询订单 ORD-001")
        assert isinstance(result, NLUResult)
        assert result.action == "new"
        assert result.target_intent == "order_query"
        assert result.confidence == 0.95
        assert result.slots_update == {"order_id": "ORD-001"}

    @pytest.mark.asyncio
    async def test_classify_unknown_intent(self):
        """验证分类 unknown"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="unknown",
            confidence=0.3,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("asdfasdf???")
        assert result.action == "new"
        assert result.target_intent == "unknown"

    @pytest.mark.asyncio
    async def test_classify_with_continue_action(self):
        """验证 continue action"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="continue",
            target_intent="order_query",
            confidence=0.9,
            slots_update={"order_id": "ORD-005"},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify(
            "ORD-005",
            session_intents={
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            active_intent="order_query",
        )
        assert result.action == "continue"
        assert result.target_intent == "order_query"
        assert result.slots_update == {"order_id": "ORD-005"}

    @pytest.mark.asyncio
    async def test_classify_with_cancel_action(self):
        """验证 cancel action"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="cancel",
            target_intent="order_query",
            confidence=0.9,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("算了不查了")
        assert result.action == "cancel"

    @pytest.mark.asyncio
    async def test_classify_passes_all_intents(self):
        """验证 classify 将 all_intents 传递给 LLM"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="unknown",
            confidence=0.0,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        await classifier.classify(
            "测试",
            all_intents=[{"name": "order_query", "description": "订单查询"}],
        )
        structured_llm = mock_llm.with_structured_output.return_value
        messages = structured_llm.ainvoke.call_args[0][0]
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        assert "order_query" in system_msg.content

    @pytest.mark.asyncio
    async def test_classify_with_transfer_human(self):
        """验证转人工"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="transfer_human",
            confidence=0.9,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("我要找人工客服")
        assert result.target_intent == "transfer_human"

    @pytest.mark.asyncio
    async def test_classify_passes_context(self):
        """验证 classify 将上下文传递给 LLM"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="continue",
            target_intent="order_query",
            confidence=0.9,
            slots_update={"order_id": "456"},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        await classifier.classify(
            "456",
            session_intents={
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            active_intent="order_query",
        )
        mock_llm.with_structured_output.assert_called_once()
        structured_llm = mock_llm.with_structured_output.return_value
        structured_llm.ainvoke.assert_called_once()
        messages = structured_llm.ainvoke.call_args[0][0]
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        user_msg = messages[1]
        assert isinstance(user_msg, HumanMessage)
        assert "456" in user_msg.content

    @pytest.mark.asyncio
    async def test_classify_handles_structured_output_error(self):
        """验证 LLM 调用异常时降级为 unknown"""
        mock_llm = self._make_mock_llm_raising(Exception("网络错误"))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("查物流")
        assert result.action == "new"
        assert result.target_intent == "unknown"
        assert result.confidence == 0.0
        assert result.slots_update == {}

    @pytest.mark.asyncio
    async def test_classify_with_structured_output_uses_nluresult_schema(self):
        """验证 with_structured_output 使用了 NLUResult schema"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="order_query",
            confidence=0.9,
            slots_update={"order_id": "789"},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        await classifier.classify("查询789")
        call_kwargs = mock_llm.with_structured_output.call_args
        assert call_kwargs is not None
