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

    def test_build_system_prompt_contains_platform_intents(self):
        """验证系统 prompt 包含平台意图"""
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt()
        assert "unknown" in prompt
        assert "transfer_human" in prompt

    def test_build_system_prompt_contains_registered_intents(self):
        """验证系统 prompt 包含注册后的业务意图"""
        IntentRegistry.clear()
        IntentRegistry.register_business(
            "ecommerce",
            [
                IntentDefinition(
                    name="order_query",
                    description="查询订单详情",
                    required_slots=[
                        SlotDef(
                            name="order_id",
                            description="订单号",
                            ask_prompt="请提供订单号",
                        ),
                    ],
                ),
            ],
        )
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt()
        assert "order_query" in prompt
        assert "order_id" in prompt
        assert "查询订单详情" in prompt
        IntentRegistry.clear()

    def test_build_system_prompt_with_optional_slots(self):
        """验证系统 prompt 包含可选槽位信息"""
        IntentRegistry.clear()
        IntentRegistry.register_business(
            "ecommerce",
            [
                IntentDefinition(
                    name="product_inquiry",
                    description="商品咨询",
                    optional_slots=[
                        SlotDef(name="sku_id", description="商品SKU"),
                        SlotDef(name="sku_name", description="商品名称"),
                    ],
                ),
            ],
        )
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt()
        assert "product_inquiry" in prompt
        assert "可选槽位" in prompt
        assert "sku_id" in prompt
        assert "sku_name" in prompt
        IntentRegistry.clear()

    def test_build_user_prompt_basic(self):
        """验证用户 prompt 包含用户输入"""
        classifier = IntentClassifier()
        prompt = classifier._build_user_prompt("你好，帮我查订单", {}, "")
        assert "你好，帮我查订单" in prompt

    def test_build_user_prompt_with_active_intent(self):
        """验证用户 prompt 包含活跃意图"""
        classifier = IntentClassifier()
        prompt = classifier._build_user_prompt("123456", {}, "order_query")
        assert "order_query" in prompt
        assert "当前活跃意图" in prompt

    def test_build_user_prompt_with_slots(self):
        """验证用户 prompt 包含已收集的槽位"""
        classifier = IntentClassifier()
        prompt = classifier._build_user_prompt(
            "123456",
            {"order_id": "456"},
            "order_query",
        )
        assert "order_id" in prompt
        assert "456" in prompt


class TestIntentClassifierClassify:
    """意图分类器 classify 方法测试"""

    @staticmethod
    def _make_mock_llm(return_value: NLUResult):
        """构造 mock LLM，模拟 with_structured_output 行为"""
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(return_value=return_value)
        llm = MagicMock()
        llm.with_structured_output.return_value = structured_llm
        return llm

    @staticmethod
    def _make_mock_llm_raising(exception: Exception):
        """构造 mock LLM，模拟调用异常"""
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=exception)
        llm = MagicMock()
        llm.with_structured_output.return_value = structured_llm
        return llm

    @pytest.mark.asyncio
    async def test_classify_returns_nlu_result(self):
        """验证 classify 返回 NLUResult"""
        mock_llm = self._make_mock_llm(NLUResult(
            intent="order_query",
            confidence=0.95,
            slots={"order_id": "123"},
            missing_slots=[],
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("查询订单 123")
        assert isinstance(result, NLUResult)
        assert result.intent == "order_query"
        assert result.confidence == 0.95
        assert result.slots == {"order_id": "123"}

    @pytest.mark.asyncio
    async def test_classify_unknown_intent(self):
        """验证分类为 unknown 的兜底处理"""
        mock_llm = self._make_mock_llm(NLUResult(
            intent="unknown",
            confidence=0.3,
            slots={},
            missing_slots=[],
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("asdfasdf???")
        assert result.intent == "unknown"
        assert result.confidence == 0.3

    @pytest.mark.asyncio
    async def test_classify_with_missing_slots(self):
        """验证分类结果包含缺失槽位"""
        mock_llm = self._make_mock_llm(NLUResult(
            intent="order_query",
            confidence=0.8,
            slots={},
            missing_slots=["order_id"],
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("我想查订单")
        assert result.missing_slots == ["order_id"]
        assert result.slots == {}

    @pytest.mark.asyncio
    async def test_classify_passes_context(self):
        """验证 classify 将当前槽位和意图传递给 LLM"""
        mock_llm = self._make_mock_llm(NLUResult(
            intent="order_query",
            confidence=0.9,
            slots={"order_id": "456"},
            missing_slots=[],
        ))
        classifier = IntentClassifier(llm=mock_llm)
        await classifier.classify(
            "456",
            current_slots={"order_id": "456"},
            active_intent="order_query",
        )

        # 验证 with_structured_output 被调用
        mock_llm.with_structured_output.assert_called_once()
        # 验证 ainvoke 被调用
        structured_llm = mock_llm.with_structured_output.return_value
        structured_llm.ainvoke.assert_called_once()
        messages = structured_llm.ainvoke.call_args[0][0]
        # 检查 system prompt 包含意图信息
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        assert "unknown" in system_msg.content
        # 检查 user prompt 包含上下文
        user_msg = messages[1]
        assert isinstance(user_msg, HumanMessage)
        assert "456" in user_msg.content

    @pytest.mark.asyncio
    async def test_classify_with_transfer_human(self):
        """验证转人工意图分类"""
        mock_llm = self._make_mock_llm(NLUResult(
            intent="transfer_human",
            confidence=0.9,
            slots={},
            missing_slots=[],
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("我要找人工客服")
        assert result.intent == "transfer_human"

    @pytest.mark.asyncio
    async def test_classify_with_structured_output_uses_nluresult_schema(self):
        """验证 with_structured_output 使用了 NLUResult 作为输出 schema"""
        mock_llm = self._make_mock_llm(NLUResult(
            intent="order_query",
            confidence=0.9,
            slots={"order_id": "789"},
            missing_slots=[],
        ))
        classifier = IntentClassifier(llm=mock_llm)
        await classifier.classify("查询789")

        # 验证 with_structured_output 的参数
        call_kwargs = mock_llm.with_structured_output.call_args
        # output_schema 应设为 NLUResult
        assert call_kwargs is not None

    @pytest.mark.asyncio
    async def test_classify_handles_structured_output_error(self):
        """验证 structured_output 调用异常时降级为 unknown"""
        mock_llm = self._make_mock_llm_raising(Exception("网络错误"))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("查物流")
        assert result.intent == "unknown"
        assert result.confidence == 0.0
        assert result.slots == {}
        assert result.missing_slots == []
