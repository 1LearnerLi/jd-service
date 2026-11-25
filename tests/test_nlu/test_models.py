"""NLU 层模型测试"""
import pytest
from app.nlu.models import SlotDef, IntentDefinition, NLUResult


class TestSlotDef:
    """SlotDef 槽位定义测试"""

    def test_slot_def_creation(self):
        """验证 SlotDef 基本创建"""
        slot = SlotDef(
            name="order_id",
            description="订单号",
            ask_prompt="请提供您的订单号",
        )
        assert slot.name == "order_id"
        assert slot.description == "订单号"
        assert slot.ask_prompt == "请提供您的订单号"

    def test_slot_def_without_ask_prompt(self):
        """验证 SlotDef 可以不提供 ask_prompt"""
        slot = SlotDef(name="sku_name", description="商品名称")
        # ask_prompt 使用默认值
        assert slot.name == "sku_name"
        assert hasattr(slot, "ask_prompt")


class TestIntentDefinition:
    """IntentDefinition 意图定义测试"""

    def test_intent_definition_creation(self):
        """验证 IntentDefinition 基本创建（无槽位）"""
        intent = IntentDefinition(
            name="transfer_human",
            description="转接人工客服",
        )
        assert intent.name == "transfer_human"
        assert intent.description == "转接人工客服"
        assert intent.required_slots == []
        assert intent.optional_slots == []

    def test_intent_definition_with_required_slots(self):
        """验证 IntentDefinition 包含必填槽位"""
        slots = [
            SlotDef(
                name="order_id",
                description="订单号",
                ask_prompt="请提供您的订单号",
            )
        ]
        intent = IntentDefinition(
            name="order_query",
            description="查询订单详情",
            required_slots=slots,
        )
        assert intent.name == "order_query"
        assert len(intent.required_slots) == 1
        assert intent.required_slots[0].name == "order_id"

    def test_intent_definition_with_optional_slots(self):
        """验证 IntentDefinition 包含可选槽位"""
        optional = [
            SlotDef(name="sku_id", description="商品SKU"),
            SlotDef(name="sku_name", description="商品名称"),
        ]
        intent = IntentDefinition(
            name="product_inquiry",
            description="商品咨询",
            optional_slots=optional,
        )
        assert len(intent.optional_slots) == 2
        assert len(intent.required_slots) == 0

    def test_intent_definition_with_both_slots(self):
        """验证 IntentDefinition 同时包含必填和可选槽位"""
        intent = IntentDefinition(
            name="hybrid_intent",
            description="混合意图",
            required_slots=[
                SlotDef(name="user_phone", description="手机号", ask_prompt="请提供手机号"),
            ],
            optional_slots=[
                SlotDef(name="remark", description="备注"),
            ],
        )
        assert len(intent.required_slots) == 1
        assert len(intent.optional_slots) == 1


class TestNLUResult:
    """NLUResult NLU 输出测试"""

    def test_nlu_result_creation(self):
        """验证 NLUResult 基本创建"""
        result = NLUResult(
            intent="order_query",
            confidence=0.95,
            slots={"order_id": "123"},
            missing_slots=[],
        )
        assert result.intent == "order_query"
        assert result.confidence == 0.95
        assert result.slots == {"order_id": "123"}
        assert result.missing_slots == []

    def test_nlu_result_serialization(self):
        """验证 NLUResult 可以序列化为字典"""
        result = NLUResult(
            intent="order_query",
            confidence=0.95,
            slots={"order_id": "123"},
            missing_slots=[],
        )
        d = result.model_dump()
        assert d["intent"] == "order_query"
        assert d["confidence"] == 0.95
        assert d["slots"] == {"order_id": "123"}

    def test_nlu_result_with_missing_slots(self):
        """验证 NLUResult 包含缺失槽位"""
        result = NLUResult(
            intent="order_query",
            confidence=0.8,
            slots={},
            missing_slots=["order_id"],
        )
        assert result.missing_slots == ["order_id"]

    def test_nlu_result_default_values(self):
        """验证 NLUResult 默认值"""
        result = NLUResult(
            intent="unknown",
            confidence=0.0,
        )
        assert result.slots == {}
        assert result.missing_slots == []

    def test_nlu_result_confidence_range(self):
        """验证 confidence 在 0-1 范围内"""
        # 0 和 1 应该是合法的
        result_zero = NLUResult(intent="test", confidence=0.0)
        assert result_zero.confidence == 0.0

        result_one = NLUResult(intent="test", confidence=1.0)
        assert result_one.confidence == 1.0
