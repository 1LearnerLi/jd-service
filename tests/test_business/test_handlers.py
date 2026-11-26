"""电商业务线意图处理器测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.business.base import BusinessContext, BusinessResult
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler


class TestOrderQueryHandler:
    """OrderQueryHandler 订单查询处理器测试"""

    def test_handler_is_intent_handler_subclass(self):
        from app.business.base import IntentHandler
        assert issubclass(OrderQueryHandler, IntentHandler)

    def test_handler_can_instantiate(self):
        handler = OrderQueryHandler()
        assert handler is not None

    @pytest.mark.asyncio
    async def test_handle_missing_order_id(self):
        handler = OrderQueryHandler()
        with patch.object(handler, "_repo", new=AsyncMock()):
            ctx = BusinessContext(
                session_id="sess-001", user_id="1001",
                intent="order_query", slots={},
            )
            result = await handler.handle(ctx)
            assert result.success is False

    @pytest.mark.asyncio
    async def test_handle_order_not_found(self):
        handler = OrderQueryHandler()
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.return_value = None
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001", user_id="1001",
                intent="order_query", slots={"order_id": "NOTEXIST"},
            )
            result = await handler.handle(ctx)
            assert result.success is False

    @pytest.mark.asyncio
    async def test_handle_success(self):
        from datetime import datetime
        handler = OrderQueryHandler()
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.order_id = "ORD-001"
        mock_order.order_status = "delivered"
        mock_order.create_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_order.payment_time = None
        mock_order.delivered_time = None
        mock_repo.get_order_by_id.return_value = mock_order
        mock_detail = MagicMock()
        mock_detail.sku_id = "sku001"
        mock_detail.sku_name = "item"
        mock_detail.sku_count = 1
        mock_detail.total_amount = 100.00
        mock_detail.discount_amount = 0.00
        mock_detail.final_amount = 100.00
        mock_repo.get_order_detail_by_order.return_value = [mock_detail]
        mock_sku = MagicMock()
        mock_sku.sku_price = 100.00
        mock_repo.get_sku_by_id.return_value = mock_sku
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001", user_id="1001",
                intent="order_query", slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is True
            assert result.data["order_id"] == "ORD-001"

    @pytest.mark.asyncio
    async def test_handle_repo_exception(self):
        handler = OrderQueryHandler()
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.side_effect = Exception("DB error")
        with patch.object(handler, "_repo", mock_repo):
            ctx = BusinessContext(
                session_id="sess-001", user_id="1001",
                intent="order_query", slots={"order_id": "ORD-001"},
            )
            result = await handler.handle(ctx)
            assert result.success is False


# PostsaleReturnHandler - slot-driven flow tests

class TestPostsaleReturnMissingOrderId:
    """Missing order_id -> return recent order list"""

    @pytest.mark.asyncio
    async def test_returns_order_list(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "select_order"
        assert len(result.data["orders"]) == 1
        assert result.data["orders"][0]["can_apply"] is True

    @pytest.mark.asyncio
    async def test_empty_orders(self):
        mock_repo = _make_repo("已签收")
        mock_repo.get_orders_by_user.return_value = []
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["orders"] == []

    @pytest.mark.asyncio
    async def test_non_refundable_marked(self):
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.order_id = "ORD-003"
        mock_order.order_status = "已取消"
        mock_repo.get_orders_by_user.return_value = [mock_order]
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={},
        )
        result = await handler.handle(ctx)
        assert result.data["orders"][0]["can_apply"] is False

    @pytest.mark.asyncio
    async def test_db_exception(self):
        mock_repo = AsyncMock()
        mock_repo.get_orders_by_user.side_effect = Exception("DB down")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is False


class TestPostsaleReturnMissingType:
    """Has order_id, missing postsale_type -> return type options"""

    @pytest.mark.asyncio
    async def test_returns_type_list(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "select_type"
        keys = [t["key"] for t in result.data["types"]]
        assert "refund_only" in keys
        assert "return_refund" in keys

    @pytest.mark.asyncio
    async def test_order_not_found(self):
        mock_repo = _make_repo("已签收")
        mock_repo.get_order_by_id.return_value = None
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={"order_id": "NOTEXIST"},
        )
        result = await handler.handle(ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_wrong_user(self):
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "9999"
        mock_repo.get_order_by_id.return_value = mock_order
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_invalid_status(self):
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.user_id = "1001"
        mock_order.order_status = "已取消"
        mock_repo.get_order_by_id.return_value = mock_order
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_db_exception(self):
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.side_effect = Exception("DB down")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is False


class TestPostsaleReturnMissingReason:
    """Has order_id + type, missing reason -> return reason list"""

    @pytest.mark.asyncio
    async def test_returns_reason_list(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001", "postsale_type": "refund_only"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "select_reason"
        assert len(result.data["reasons"]) >= 2


class TestPostsaleReturnExecute:
    """All 3 slots present -> execute"""

    @pytest.mark.asyncio
    async def test_execute_success(self):
        mock_repo = _make_repo("已签收")
        mock_repo.update_order_status = AsyncMock()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "completed"
        assert result.data["new_status"] == "售后中"
        mock_repo.update_order_status.assert_awaited_once_with("ORD-001", "售后中")

    @pytest.mark.asyncio
    async def test_execute_return_refund(self):
        mock_repo = _make_repo("已签收")
        mock_repo.update_order_status = AsyncMock()
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "return_refund",
                "postsale_reason": "商品瑕疵/破损",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_invalid_postsale_type(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "bad_type",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_order_not_found_at_execute(self):
        mock_repo = _make_repo("已签收")
        mock_repo.get_order_by_id.return_value = None
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_db_exception(self):
        mock_repo = _make_repo("已签收")
        mock_repo.update_order_status = AsyncMock(side_effect=Exception("DB error"))
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "refund_only",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False


def _make_repo(order_status="已签收"):
    """Create a mock repo with a valid order.  order_status must be one of the Chinese values（已付款/已发货/已签收）for the order to pass validation."""
    mock_repo = AsyncMock()
    mock_order = MagicMock()
    mock_order.user_id = "1001"
    mock_order.order_id = "ORD-001"
    mock_order.order_status = order_status
    mock_order.receive_id = "RECV-001"
    mock_repo.get_order_by_id.return_value = mock_order
    mock_repo.get_orders_by_user.return_value = [mock_order]
    return mock_repo
