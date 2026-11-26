"""电商业务线意图处理器测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.business.base import BusinessContext, BusinessResult, OptionItem
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler


class TestOrderQueryHandler:
    """OrderQueryHandler 订单查询处理器测试"""

    def test_handler_is_intent_handler_subclass(self):
        from app.business.base import IntentHandler
        assert issubclass(OrderQueryHandler, IntentHandler)

    @pytest.mark.asyncio
    async def test_missing_order_id_returns_options(self):
        """order_id 缺失 -> ask_slot"""
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.order_id = "ORD-001"
        mock_order.order_status = "已签收"
        mock_repo.get_orders_by_user.return_value = [mock_order]

        handler = OrderQueryHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="order_query", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "ask_slot"
        assert result.data["slot_to_fill"] == "order_id"
        assert len(result.data["options"]) == 1
        assert result.data["options"][0]["value"] == "ORD-001"

    @pytest.mark.asyncio
    async def test_with_order_id_queries(self):
        """有 order_id -> completed"""
        from datetime import datetime
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.order_id = "ORD-001"
        mock_order.order_status = "已签收"
        mock_order.create_time = datetime(2025, 1, 1, 12, 0, 0)
        mock_order.payment_time = None
        mock_order.delivered_time = None
        mock_repo.get_order_by_id.return_value = mock_order
        mock_repo.get_order_detail_by_order.return_value = []
        mock_repo.get_sku_by_id.return_value = None

        handler = OrderQueryHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="order_query", slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "completed"
        assert result.data["order_id"] == "ORD-001"

    @pytest.mark.asyncio
    async def test_order_not_found(self):
        mock_repo = AsyncMock()
        mock_repo.get_order_by_id.return_value = None
        handler = OrderQueryHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="order_query", slots={"order_id": "NOTEXIST"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert result.error_message != ""

    @pytest.mark.asyncio
    async def test_db_exception(self):
        mock_repo = AsyncMock()
        mock_repo.get_orders_by_user.side_effect = Exception("DB error")
        handler = OrderQueryHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="order_query", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is False


class TestPostsaleReturnMissingOrderId:
    """缺少 order_id -> ask_slot 返回订单列表"""

    @pytest.mark.asyncio
    async def test_returns_ask_slot(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "ask_slot"
        assert result.data["slot_to_fill"] == "order_id"
        assert len(result.data["options"]) == 1
        opt = result.data["options"][0]
        assert opt["label"] == "ORD-001（已签收）"
        assert opt["value"] == "ORD-001"
        assert opt["disabled"] is False

    @pytest.mark.asyncio
    async def test_non_refundable_disabled(self):
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
        assert result.data["options"][0]["disabled"] is True

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
        assert result.data["options"] == []

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
    """有 order_id，缺 postsale_type -> ask_slot"""

    @pytest.mark.asyncio
    async def test_returns_ask_slot(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return", slots={"order_id": "ORD-001"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "ask_slot"
        assert result.data["slot_to_fill"] == "postsale_type"
        assert len(result.data["options"]) == 2
        keys = [o["value"] for o in result.data["options"]]
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


class TestPostsaleReturnMissingReason:
    """有 order_id + type，缺 reason -> ask_slot"""

    @pytest.mark.asyncio
    async def test_returns_ask_slot(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={"order_id": "ORD-001", "postsale_type": "refund_only"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "ask_slot"
        assert result.data["slot_to_fill"] == "postsale_reason"
        assert len(result.data["options"]) >= 2


class TestPostsaleReturnExecute:
    """三个槽位齐全 -> completed"""

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
    async def test_invalid_type(self):
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "bad",
                "postsale_reason": "7天无理由",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_order_not_found(self):
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
    mock_repo = AsyncMock()
    mock_order = MagicMock()
    mock_order.user_id = "1001"
    mock_order.order_id = "ORD-001"
    mock_order.order_status = order_status
    mock_order.receive_id = "RECV-001"
    mock_repo.get_order_by_id.return_value = mock_order
    mock_repo.get_orders_by_user.return_value = [mock_order]
    return mock_repo
