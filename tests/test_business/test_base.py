"""业务层基础抽象组件测试"""
import pytest
from pydantic import ValidationError

from app.business.base import BusinessContext, BusinessResult, IntentHandler


class TestBusinessContext:
    """BusinessContext 业务上下文测试"""

    def test_business_context_creation(self):
        """验证 BusinessContext 基本创建"""
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
        """验证 BusinessContext 必填字段校验"""
        # 缺少必填字段应抛出 ValidationError
        with pytest.raises(ValidationError):
            BusinessContext()

    def test_business_context_slots_default(self):
        """验证 BusinessContext slots 默认值为空字典"""
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="unknown",
        )
        assert ctx.slots == {}

    def test_business_context_serialization(self):
        """验证 BusinessContext 可以序列化为字典"""
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="order_query",
            slots={"order_id": "123"},
        )
        d = ctx.model_dump()
        assert d["session_id"] == "sess-001"
        assert d["user_id"] == "user-001"
        assert d["intent"] == "order_query"
        assert d["slots"] == {"order_id": "123"}

    def test_business_context_empty_slots(self):
        """验证 BusinessContext 空槽位场景"""
        ctx = BusinessContext(
            session_id="sess-002",
            user_id="user-002",
            intent="product_inquiry",
        )
        assert ctx.slots == {}
        assert ctx.model_dump()["slots"] == {}


class TestBusinessResult:
    """BusinessResult 业务结果测试"""

    def test_business_result_success(self):
        """验证业务执行成功的 BusinessResult"""
        result = BusinessResult(
            success=True,
            data={"order_id": "123", "status": "已发货"},
        )
        assert result.success is True
        assert result.data == {"order_id": "123", "status": "已发货"}
        assert result.error_message == ""

    def test_business_result_failure(self):
        """验证业务执行失败的 BusinessResult"""
        result = BusinessResult(
            success=False,
            error_message="订单不存在",
        )
        assert result.success is False
        assert result.error_message == "订单不存在"

    def test_business_result_default_values(self):
        """验证 BusinessResult 默认值"""
        result = BusinessResult(success=True)
        assert result.data is None
        assert result.error_message == ""

    def test_business_result_serialization(self):
        """验证 BusinessResult 可以序列化为字典"""
        result = BusinessResult(
            success=True,
            data={"key": "value"},
            error_message="",
        )
        d = result.model_dump()
        assert d["success"] is True
        assert d["data"] == {"key": "value"}
        assert d["error_message"] == ""

    def test_business_result_required_success(self):
        """验证 BusinessResult 缺少必填字段时抛出异常"""
        with pytest.raises(ValidationError):
            BusinessResult()

    def test_business_result_with_list_data(self):
        """验证 BusinessResult 的 data 可以是列表"""
        result = BusinessResult(
            success=True,
            data=[{"id": 1}, {"id": 2}],
        )
        assert isinstance(result.data, list)
        assert len(result.data) == 2

    def test_business_result_with_none_data(self):
        """验证失败时 data 可以为 None"""
        result = BusinessResult(
            success=False,
            error_message="查询失败",
        )
        assert result.data is None
        assert result.error_message == "查询失败"


class TestIntentHandler:
    """IntentHandler 抽象基类测试"""

    def test_intent_handler_is_abstract(self):
        """验证 IntentHandler 是抽象类，不能直接实例化"""
        with pytest.raises(TypeError):
            IntentHandler()

    def test_intent_handler_subclass_can_instantiate(self):
        """验证 IntentHandler 的子类可以实例化"""

        class DummyHandler(IntentHandler):
            async def handle(self, ctx: BusinessContext) -> BusinessResult:
                return BusinessResult(success=True)

        handler = DummyHandler()
        assert isinstance(handler, IntentHandler)
        assert hasattr(handler, "handle")

    def test_intent_handler_subclass_must_implement_handle(self):
        """验证 IntentHandler 子类必须实现 handle 方法"""

        class IncompleteHandler(IntentHandler):
            pass

        with pytest.raises(TypeError):
            IncompleteHandler()

    @pytest.mark.asyncio
    async def test_intent_handler_subclass_handle(self):
        """验证 IntentHandler 子类的 handle 方法可正常调用"""

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

    @pytest.mark.asyncio
    async def test_intent_handler_error_case(self):
        """验证 IntentHandler 子类可以返回错误结果"""

        class ErrorHandler(IntentHandler):
            async def handle(self, ctx: BusinessContext) -> BusinessResult:
                return BusinessResult(
                    success=False,
                    error_message="模拟错误",
                )

        handler = ErrorHandler()
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="test_intent",
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert result.error_message == "模拟错误"

    @pytest.mark.asyncio
    async def test_intent_handler_with_slots(self):
        """验证 IntentHandler 子类可以访问 slots 中的值"""

        class SlotHandler(IntentHandler):
            async def handle(self, ctx: BusinessContext) -> BusinessResult:
                order_id = ctx.slots.get("order_id", "未知")
                return BusinessResult(
                    success=True,
                    data={"queried_order": order_id},
                )

        handler = SlotHandler()
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="user-001",
            intent="order_query",
            slots={"order_id": "ORD-999"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["queried_order"] == "ORD-999"
