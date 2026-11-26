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
        # Mock OrderRepo 以防止真实数据库连接
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

        # Mock 订单
        mock_order = MagicMock()
        mock_order.order_id = "ORD-001"
        mock_order.order_status = "已签收"
        mock_order.create_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_order.payment_time = datetime(2025, 1, 1, 12, 30, 0)
        mock_order.delivered_time = datetime(2025, 1, 3, 10, 0, 0)
        mock_repo.get_order_by_id.return_value = mock_order

        # Mock 订单明细
        mock_detail = MagicMock()
        mock_detail.sku_id = "sku123456"
        mock_detail.sku_name = "男士纯棉T恤"
        mock_detail.sku_count = 2
        mock_detail.total_amount = 179.80
        mock_detail.discount_amount = 0.00
        mock_detail.final_amount = 179.80
        mock_repo.get_order_detail_by_order.return_value = [mock_detail]

        # Mock SKU
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


class TestPostsaleReturnHandler:
    """PostsaleReturnHandler 售后申请处理器测试"""

    def test_handler_is_intent_handler_subclass(self):
        """验证 PostsaleReturnHandler 是 IntentHandler 的子类"""
        from app.business.base import IntentHandler
        assert issubclass(PostsaleReturnHandler, IntentHandler)

    def test_handler_can_instantiate(self):
        """验证 PostsaleReturnHandler 可以实例化"""
        handler = PostsaleReturnHandler()
        assert handler is not None

    @pytest.mark.asyncio
    async def test_handle_missing_order_id(self):
        """验证缺少 order_id 时返回失败"""
        handler = PostsaleReturnHandler()
        with patch.object(handler, "_repo", new=AsyncMock()):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="postsale_return",
                slots={},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "订单号" in result.error_message

    @pytest.mark.asyncio
    async def test_handle_order_not_found(self):
        """验证订单不存在时返回失败"""
        handler = PostsaleReturnHandler()
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.return_value = None
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="postsale_return",
                slots={"order_id": "NOTEXIST"},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "不存在" in result.error_message

    @pytest.mark.asyncio
    async def test_handle_wrong_user(self):
        """验证订单不属于当前用户时返回失败"""
        handler = PostsaleReturnHandler()
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "9999"  # 不属于 1001
        mock_repo.get_order_by_id.return_value = mock_order
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="postsale_return",
                slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "不属于" in result.error_message

    @pytest.mark.asyncio
    async def test_handle_invalid_status(self):
        """验证订单状态不支持售后时返回失败"""
        handler = PostsaleReturnHandler()
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "1001"
        mock_order.order_status = "待支付"
        mock_repo.get_order_by_id.return_value = mock_order
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="postsale_return",
                slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "暂不支持" in result.error_message

    @pytest.mark.asyncio
    async def test_handle_success(self):
        """验证售后查询成功"""
        handler = PostsaleReturnHandler()
        mock_repo = AsyncMock()

        mock_order = MagicMock()
        mock_order.user_id = "1001"
        mock_order.order_id = "ORD-001"
        mock_order.order_status = "已签收"
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

        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="postsale_return",
                slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is True
            assert result.data["order_id"] == "ORD-001"
            assert len(result.data["items"]) == 1
            assert result.data["items"][0]["sku_name"] == "男士纯棉T恤"

    @pytest.mark.asyncio
    async def test_handle_repo_exception(self):
        """验证数据库异常时返回失败"""
        handler = PostsaleReturnHandler()
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.side_effect = Exception("数据库连接失败")
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001",
                user_id="1001",
                intent="postsale_return",
                slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is False
            assert "错误" in result.error_message
