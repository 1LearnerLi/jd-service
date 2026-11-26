"""电商业务线意图处理器测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.business.base import BusinessContext, BusinessResult
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler


class TestOrderQueryHandler:
    """OrderQueryHandler 订单查询处理器测试"""

    def test_handler_is_intent_handler_subclass(self):
        """验证 OrderQueryHandler 是 IntentHandler 的子类"""
        from app.business.base import IntentHandler
        assert issubclass(OrderQueryHandler, IntentHandler)

    def test_handler_can_instantiate(self):
        """验证 OrderQueryHandler 可以实例化"""
        handler = OrderQueryHandler()
        assert handler is not None

    @pytest.mark.asyncio
    async def test_handle_missing_order_id(self):
        """验证缺少 order_id 时返回失败"""
        handler = OrderQueryHandler()
        with patch.object(handler, "_repo", new=AsyncMock()):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="order_query",
                slots={},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "订单号" in result.error_message

    @pytest.mark.asyncio
    async def test_handle_order_not_found(self):
        """验证订单不存在时返回失败"""
        handler = OrderQueryHandler()
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.return_value = None
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="order_query",
                slots={"order_id": "NOTEXIST"},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "不存在" in result.error_message

    @pytest.mark.asyncio
    async def test_handle_success(self):
        """验证正常查询订单成功"""
        from datetime import datetime

        handler = OrderQueryHandler()
        mock_repo = AsyncMock()

        mock_order = MagicMock()
        mock_order.order_id = "ORD-001"
        mock_order.order_status = "已签收"
        mock_order.create_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_order.payment_time = datetime(2025, 1, 1, 12, 30, 0)
        mock_order.delivered_time = datetime(2025, 1, 3, 10, 0, 0)
        mock_repo.get_order_by_id.return_value = mock_order

        mock_detail = MagicMock()
        mock_detail.sku_id = "sku123456"
        mock_detail.sku_name = "男士纯棉T恤"
        mock_detail.sku_count = 2
        mock_detail.total_amount = 179.80
        mock_detail.discount_amount = 0.00
        mock_detail.final_amount = 179.80
        mock_repo.get_order_detail_by_order.return_value = [mock_detail]

        mock_sku = MagicMock()
        mock_sku.sku_price = 89.90
        mock_repo.get_sku_by_id.return_value = mock_sku

        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="order_query",
                slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is True
            assert result.data["order_id"] == "ORD-001"
            assert result.data["order_status"] == "已签收"
            assert len(result.data["details"]) == 1
            assert result.data["details"][0]["sku_name"] == "男士纯棉T恤"
            assert result.data["details"][0]["unit_price"] == 89.90

    @pytest.mark.asyncio
    async def test_handle_repo_exception(self):
        """验证数据库异常时返回失败"""
        handler = OrderQueryHandler()
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.side_effect = Exception("数据库连接失败")
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="order_query",
                slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "错误" in result.error_message


# ── PostsaleReturnHandler 多步流程测试 ──────────────────────


class TestPostsaleReturnStep1SelectOrder:
    """步骤 1: select_order — 校验订单并返回可售后商品"""

    @pytest.mark.asyncio
    async def test_missing_order_id(self):
        """验证缺少 order_id 时返回失败"""
        handler = PostsaleReturnHandler(repo=AsyncMock())
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "订单号" in result.error_message

    @pytest.mark.asyncio
    async def test_order_not_found(self):
        """验证订单不存在"""
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.return_value = None
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "NOTEXIST"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "不存在" in result.error_message

    @pytest.mark.asyncio
    async def test_wrong_user(self):
        """验证订单不属于当前用户"""
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "9999"
        mock_repo.get_order_by_id.return_value = mock_order
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "不属于" in result.error_message

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        """验证不支持的订单状态（待支付）"""
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "1001"
        mock_order.order_status = "待支付"
        mock_repo.get_order_by_id.return_value = mock_order
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "暂不支持" in result.error_message

    @pytest.mark.asyncio
    async def test_valid_status_paid(self):
        """验证已付款状态可以售后"""
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "1001"
        mock_order.order_status = "已付款"
        mock_repo.get_order_by_id.return_value = mock_order

        mock_detail = MagicMock()
        mock_detail.order_detail_id = "OD-001"
        mock_detail.sku_id = "sku123456"
        mock_detail.sku_name = "男士纯棉T恤"
        mock_detail.sku_count = 1
        mock_detail.final_amount = 89.90
        mock_repo.get_order_detail_by_order.return_value = [mock_detail]

        mock_sku = MagicMock()
        mock_sku.sku_price = 89.90
        mock_repo.get_sku_by_id.return_value = mock_sku

        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["step"] == "select_item"

    @pytest.mark.asyncio
    async def test_step1_success_shipped(self):
        """验证已发货状态返回商品列表"""
        mock_repo = _make_mock_repo(order_status="已发货")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["step"] == "select_item"
        assert len(result.data["items"]) == 1
        assert result.data["items"][0]["sku_name"] == "男士纯棉T恤"

    @pytest.mark.asyncio
    async def test_step1_db_exception(self):
        """验证数据库异常"""
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.side_effect = Exception("DB down")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "错误" in result.error_message


class TestPostsaleReturnStep2SelectItem:
    """步骤 2: select_item — 用户选了商品，返回方式和原因"""

    @pytest.mark.asyncio
    async def test_missing_detail_id(self):
        """验证缺少 order_detail_id"""
        mock_repo = _make_mock_repo()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001", "step": "select_item"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "商品" in result.error_message

    @pytest.mark.asyncio
    async def test_detail_not_found_in_order(self):
        """验证明细不属于该订单"""
        mock_repo = _make_mock_repo()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "WRONG-DETAIL",
                "step": "select_item",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "不存在" in result.error_message

    @pytest.mark.asyncio
    async def test_step2_success(self):
        """验证返回售后方式和原因"""
        mock_repo = _make_mock_repo()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "select_item",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["step"] == "confirm"
        assert len(result.data["types"]) == 2
        assert result.data["types"][0]["key"] in ("refund_only", "return_refund")
        assert len(result.data["reasons"]) >= 2
        assert "7天无理由" in result.data["reasons"]
        assert "sku_name" in result.data
        assert result.data["final_amount"] == 89.90


class TestPostsaleReturnStep3Confirm:
    """步骤 3: confirm — 确认执行售后"""

    @pytest.mark.asyncio
    async def test_missing_detail_id(self):
        """验证缺少 order_detail_id"""
        mock_repo = _make_mock_repo()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "step": "confirm",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "商品明细" in result.error_message

    @pytest.mark.asyncio
    async def test_missing_reason(self):
        """验证缺少售后原因"""
        mock_repo = _make_mock_repo()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "confirm",
                "postsale_type": "refund_only",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "原因" in result.error_message

    @pytest.mark.asyncio
    async def test_invalid_postsale_type(self):
        """验证不支持的售后方式"""
        mock_repo = _make_mock_repo()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "confirm",
                "postsale_type": "exchange_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "售后方式" in result.error_message

    @pytest.mark.asyncio
    async def test_order_not_found_at_confirm(self):
        """验证确认时订单不存在"""
        mock_repo = _make_mock_repo()
        mock_repo.get_order_by_id.return_value = None
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "confirm",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "不存在" in result.error_message

    @pytest.mark.asyncio
    async def test_confirm_success_refund_only(self):
        """验证仅退款成功"""
        mock_repo = _make_mock_repo()
        mock_postsale = MagicMock()
        mock_postsale.postsale_id = "PS-001"
        mock_repo.create_postsale = AsyncMock(return_value=mock_postsale)

        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "confirm",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["step"] == "completed"
        assert result.data["postsale_id"] == "PS-001"
        assert result.data["type"] == "仅退款"
        assert result.data["status"] == "审核中"

        # 验证 create_postsale 被正确调用
        mock_repo.create_postsale.assert_awaited_once_with(
            order_detail_id="OD-001",
            refund_amount=89.90,
            postsale_type="仅退款",
            postsale_reason="7天无理由",
            receive_id="RECV-001",
        )

    @pytest.mark.asyncio
    async def test_confirm_success_return_refund(self):
        """验证退货退款成功"""
        mock_repo = _make_mock_repo()
        mock_postsale = MagicMock()
        mock_postsale.postsale_id = "PS-002"
        mock_repo.create_postsale = AsyncMock(return_value=mock_postsale)

        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "confirm",
                "postsale_type": "return_refund",
                "postsale_reason": "商品瑕疵/破损",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["type"] == "退货退款"
        assert result.data["reason"] == "商品瑕疵/破损"

    @pytest.mark.asyncio
    async def test_confirm_db_exception(self):
        """验证数据库写入异常"""
        mock_repo = _make_mock_repo()
        mock_repo.create_postsale = AsyncMock(
            side_effect=Exception("数据库异常")
        )
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "order_detail_id": "OD-001",
                "step": "confirm",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert "错误" in result.error_message


# ── 辅助函数 ────────────────────────────────────────────


def _make_mock_repo(order_status: str = "已签收") -> AsyncMock:
    """创建带基础数据的 mock repo"""
    mock_repo = AsyncMock()

    mock_order = MagicMock()
    mock_order.user_id = "1001"
    mock_order.order_id = "ORD-001"
    mock_order.order_status = order_status
    mock_order.receive_id = "RECV-001"
    mock_repo.get_order_by_id.return_value = mock_order

    mock_detail = MagicMock()
    mock_detail.order_detail_id = "OD-001"
    mock_detail.sku_id = "sku123456"
    mock_detail.sku_name = "男士纯棉T恤"
    mock_detail.sku_count = 1
    mock_detail.final_amount = 89.90
    mock_detail.order_id = "ORD-001"
    mock_repo.get_order_detail_by_order.return_value = [mock_detail]

    mock_sku = MagicMock()
    mock_sku.sku_price = 89.90
    mock_sku.sku_category = "服装"
    mock_repo.get_sku_by_id.return_value = mock_sku

    return mock_repo
