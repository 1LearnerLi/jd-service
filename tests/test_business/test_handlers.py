"""电商业务线意图处理器测试"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.business.base import BusinessContext, BusinessResult, OptionItem
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler
from app.business.ecommerce.handlers.product_inquiry import (
    ProductInquiryHandler,
    _reset_graphrag_singleton,
)
from app.business.ecommerce.product_retrieval import SearchResult


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
        mock_order.create_time = MagicMock()
        mock_order.create_time.strftime.return_value = "01-01 12:00"
        mock_order.details = []
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
        assert opt["label"] == "[01-01 12:00] 未知商品（已签收）"
        assert opt["value"] == "ORD-001"
        assert opt["disabled"] is False

    @pytest.mark.asyncio
    async def test_non_refundable_disabled(self):
        mock_repo = AsyncMock()
        mock_order = MagicMock()
        mock_order.order_id = "ORD-003"
        mock_order.order_status = "已取消"
        mock_order.create_time = MagicMock()
        mock_order.create_time.strftime.return_value = "01-01 12:00"
        mock_order.details = []
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
    async def test_type_normalized_from_label(self):
        """NLU 将内部 key 翻译为中文 label 时，应被反向映射规范化"""
        mock_repo = _make_repo("已签收")
        handler = PostsaleReturnHandler(repo=mock_repo)
        ctx = BusinessContext(
            session_id="sess-001", user_id="1001",
            intent="postsale_return",
            slots={
                "order_id": "ORD-001",
                "postsale_type": "退货退款",  # 中文 label，不是内部 key
                "postsale_reason": "商品瑕疵/破损",
            },
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "completed"
        assert result.data["postsale_type"] == "退货退款"
        mock_repo.update_order_status.assert_awaited_once_with("ORD-001", "售后中")

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
    mock_order.create_time = MagicMock()
    mock_order.create_time.strftime.return_value = "01-01 12:00"
    mock_order.details = []
    mock_repo.get_order_by_id.return_value = mock_order
    mock_repo.get_orders_by_user.return_value = [mock_order]
    return mock_repo


# ── 测试辅助：创建模拟 LLM ──────────────────────────────


def _make_mock_llm(answer_text: str = "这是 LLM 生成的优化答案"):
    """创建模拟 LLM，返回指定的答案文本"""
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = answer_text
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)
    return mock_llm


# ── ProductInquiryHandler 测试 ─────────────────────────


class TestProductInquiryHandler:
    """ProductInquiryHandler 产品咨询处理器测试"""

    def test_handler_is_intent_handler_subclass(self):
        from app.business.base import IntentHandler
        assert issubclass(ProductInquiryHandler, IntentHandler)

    @pytest.mark.asyncio
    async def test_missing_query_returns_ask_slot(self):
        """query 槽位缺失 → ask_slot，不调用 GraphRAG"""
        mock_graphrag = AsyncMock()
        handler = ProductInquiryHandler(graphrag=mock_graphrag)
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "ask_slot"
        assert result.data["slot_to_fill"] == "query"
        # 没有查询文本，不应调用 GraphRAG
        mock_graphrag.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_query_returns_ask_slot(self):
        """空字符串 query → ask_slot"""
        handler = ProductInquiryHandler(graphrag=AsyncMock())
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={"query": ""},
        )
        result = await handler.handle(ctx)
        assert result.data["action"] == "ask_slot"

    @pytest.mark.asyncio
    async def test_search_returns_completed(self):
        """有 query → GraphRAG 检索成功 → LLM 优化 → completed"""
        mock_graphrag = AsyncMock()
        mock_graphrag.search.return_value = [
            SearchResult(
                text="商品名称: 智能手机X1，价格: 2999.00",
                metadata={"source": "商品信息"},
                score=1.0,
            ),
        ]
        llm_answer = "您好！智能手机X1 的价格是 2999.00 元。"
        mock_llm = _make_mock_llm(llm_answer)

        handler = ProductInquiryHandler(graphrag=mock_graphrag, llm=mock_llm)
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={"query": "智能手机X1多少钱"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "completed"
        assert result.data["count"] == 1
        assert len(result.data["results"]) == 1
        assert result.data["message"] == llm_answer
        mock_graphrag.search.assert_awaited_once_with(
            "智能手机X1多少钱", top_k=5
        )
        # 验证 LLM 被调用且 prompt 包含检索数据
        mock_llm.ainvoke.assert_awaited_once()
        llm_messages = mock_llm.ainvoke.call_args[0][0]
        raw_text = llm_messages[-1].content  # HumanMessage
        assert "智能手机X1" in raw_text
        assert "2999.00" in raw_text

    @pytest.mark.asyncio
    async def test_search_no_results_returns_completed_with_hint(self):
        """GraphRAG 无结果 → completed 返回友好提示"""
        mock_graphrag = AsyncMock()
        mock_graphrag.search.return_value = []

        handler = ProductInquiryHandler(graphrag=mock_graphrag)
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={"query": "不存在的商品XYZ"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "completed"
        assert result.data["count"] == 0
        assert "没有找到" in result.data["message"]

    @pytest.mark.asyncio
    async def test_graphrag_exception_returns_error(self):
        """GraphRAG 异常 → error"""
        mock_graphrag = AsyncMock()
        mock_graphrag.search.side_effect = Exception("Neo4j 连接失败")

        handler = ProductInquiryHandler(graphrag=mock_graphrag)
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={"query": "手机有哪些"},
        )
        result = await handler.handle(ctx)
        assert result.success is False
        assert result.error_message != ""

    @pytest.mark.asyncio
    async def test_multiple_results_llm_optimized(self):
        """多条结果 → LLM 生成优化答案，message 为 LLM 输出"""
        mock_graphrag = AsyncMock()
        mock_graphrag.search.return_value = [
            SearchResult(
                text="商品名称: 智能手机X1，价格: 2999.00",
                metadata={"source": "商品信息"},
                score=1.0,
            ),
            SearchResult(
                text="商品名称: 智能手机X2，价格: 3999.00",
                metadata={"source": "商品信息"},
                score=0.9,
            ),
        ]
        llm_answer = "为您找到两款智能手机：\n1. 智能手机X1 — 2999.00元\n2. 智能手机X2 — 3999.00元"
        mock_llm = _make_mock_llm(llm_answer)

        handler = ProductInquiryHandler(graphrag=mock_graphrag, llm=mock_llm)
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={"query": "智能手机"},
        )
        result = await handler.handle(ctx)
        assert result.data["count"] == 2
        assert result.data["message"] == llm_answer
        # LLM prompt 应包含两条检索结果
        llm_messages = mock_llm.ainvoke.call_args[0][0]
        raw_text = llm_messages[-1].content
        assert "智能手机X1" in raw_text
        assert "智能手机X2" in raw_text

    @pytest.mark.asyncio
    async def test_llm_fails_fallback_to_raw_data(self):
        """LLM 调用失败 → 降级为原始数据格式"""
        mock_graphrag = AsyncMock()
        mock_graphrag.search.return_value = [
            SearchResult(
                text="商品名称: 智能手机X1，价格: 2999.00",
                metadata={"source": "商品信息"},
                score=1.0,
            ),
        ]
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM 超时"))

        handler = ProductInquiryHandler(graphrag=mock_graphrag, llm=mock_llm)
        ctx = BusinessContext(
            session_id="sess-001",
            user_id="1001",
            intent="product_inquiry",
            slots={"query": "智能手机X1多少钱"},
        )
        result = await handler.handle(ctx)
        assert result.success is True
        assert result.data["action"] == "completed"
        # 降级格式包含 📦 emoji
        assert "📦" in result.data["message"]
        assert "智能手机X1" in result.data["message"]
