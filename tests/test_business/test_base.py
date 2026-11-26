"""业务层基础抽象组件测试"""
import pytest
from pydantic import ValidationError

from app.business.base import (
    BusinessContext,
    BusinessResult,
    IntentHandler,
    OptionItem,
)


class TestOptionItem:
    """OptionItem 选项条目测试"""

    def test_basic_creation(self):
        item = OptionItem(label="ORD-001（已签收）", value="ORD-001")
        assert item.label == "ORD-001（已签收）"
        assert item.value == "ORD-001"
        assert item.disabled is False

    def test_disabled_default(self):
        item = OptionItem(label="test", value="v")
        assert item.disabled is False

    def test_disabled_explicit(self):
        item = OptionItem(label="ORD-002（待支付）", value="ORD-002", disabled=True)
        assert item.disabled is True

    def test_serialization(self):
        item = OptionItem(label="仅退款", value="refund_only", disabled=True)
        d = item.model_dump()
        assert d == {"label": "仅退款", "value": "refund_only", "disabled": True}

    def test_required_fields(self):
        with pytest.raises(ValidationError):
            OptionItem()
        with pytest.raises(ValidationError):
            OptionItem(label="missing value")


class TestBusinessResultAskSlot:
    """BusinessResult.ask_slot 工厂方法测试"""

    def test_basic(self):
        options = [
            OptionItem(label="仅退款", value="refund_only"),
            OptionItem(label="退货退款", value="return_refund"),
        ]
        result = BusinessResult.ask_slot(
            slot_to_fill="postsale_type",
            options=options,
            message="请选择售后方式",
        )
        assert result.success is True
        assert result.data["action"] == "ask_slot"
        assert result.data["slot_to_fill"] == "postsale_type"
        assert result.data["message"] == "请选择售后方式"
        assert len(result.data["options"]) == 2
        assert result.data["options"][0]["label"] == "仅退款"
        assert result.data["options"][0]["value"] == "refund_only"
        assert result.data["options"][0]["disabled"] is False

    def test_empty_options(self):
        result = BusinessResult.ask_slot(
            slot_to_fill="order_id",
            options=[],
            message="您暂无订单",
        )
        assert result.success is True
        assert result.data["options"] == []

    def test_serialization(self):
        options = [OptionItem(label="a", value="v")]
        result = BusinessResult.ask_slot("slot", options, "msg")
        d = result.model_dump()
        assert d["success"] is True
        assert d["data"]["action"] == "ask_slot"
        assert d["data"]["slot_to_fill"] == "slot"
        assert d["data"]["options"][0]["label"] == "a"


class TestBusinessResultCompleted:
    """BusinessResult.completed 工厂方法测试"""

    def test_basic(self):
        result = BusinessResult.completed(message="操作成功")
        assert result.success is True
        assert result.data["action"] == "completed"
        assert result.data["message"] == "操作成功"

    def test_with_extra(self):
        result = BusinessResult.completed(
            message="售后已提交",
            order_id="ORD-001",
            new_status="售后中",
        )
        assert result.data["order_id"] == "ORD-001"
        assert result.data["new_status"] == "售后中"
        assert result.data["message"] == "售后已提交"

    def test_serialization(self):
        result = BusinessResult.completed(message="ok", x="y")
        d = result.model_dump()
        assert d["success"] is True
        assert d["data"]["action"] == "completed"
        assert d["data"]["x"] == "y"


class TestBusinessResultError:
    """BusinessResult.error 工厂方法测试"""

    def test_basic(self):
        result = BusinessResult.error("出错了")
        assert result.success is False
        assert result.error_message == "出错了"
        assert result.data is None

    def test_serialization(self):
        result = BusinessResult.error("订单不存在")
        d = result.model_dump()
        assert d["success"] is False
        assert d["error_message"] == "订单不存在"


class TestBusinessContext:
    """BusinessContext 业务上下文测试"""

    def test_business_context_creation(self):
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="order_query",
            slots={"order_id": "123"},
        )
        assert ctx.session_id == "sess-001"
        assert ctx.user_id == "user-001"
        assert ctx.intent == "order_query"
        assert ctx.slots == {"order_id": "123"}

    def test_business_context_required_fields(self):
        with pytest.raises(ValidationError):
            BusinessContext()

    def test_business_context_slots_default(self):
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="unknown",
        )
        assert ctx.slots == {}


class TestBusinessResult:
    """BusinessResult 业务结果测试"""

    def test_business_result_success(self):
        result = BusinessResult(
            success=True,
            data={"order_id": "123", "status": "已发货"},
        )
        assert result.success is True
        assert result.data == {"order_id": "123", "status": "已发货"}
        assert result.error_message == ""

    def test_business_result_failure(self):
        result = BusinessResult(
            success=False,
            error_message="订单不存在",
        )
        assert result.success is False
        assert result.error_message == "订单不存在"

    def test_business_result_default_values(self):
        result = BusinessResult(success=True)
        assert result.data is None
        assert result.error_message == ""

    def test_business_result_required_success(self):
        with pytest.raises(ValidationError):
            BusinessResult()


class TestIntentHandler:
    """IntentHandler 抽象基类测试"""

    def test_intent_handler_is_abstract(self):
        with pytest.raises(TypeError):
            IntentHandler()

    def test_intent_handler_subclass_can_instantiate(self):
        class DummyHandler(IntentHandler):
            async def handle(self, ctx: BusinessContext) -> BusinessResult:
                return BusinessResult(success=True)

        handler = DummyHandler()
        assert isinstance(handler, IntentHandler)

    def test_intent_handler_subclass_must_implement_handle(self):
        class IncompleteHandler(IntentHandler):
            pass

        with pytest.raises(TypeError):
            IncompleteHandler()

    @pytest.mark.asyncio
    async def test_intent_handler_subclass_handle(self):
        class DummyHandler(IntentHandler):
            async def handle(self, ctx: BusinessContext) -> BusinessResult:
                return BusinessResult(
                    success=True,
                    data={"message": f"处理意图: {ctx.intent}"},
                )

        handler = DummyHandler()
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="test_intent",
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["message"] == "处理意图: test_intent"
