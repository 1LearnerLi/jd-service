"""DM 层 — 图构建与集成测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.graph import build_dialog_graph
from app.dm.state import DialogState
from app.nlu.models import NLUResult


class TestGraphBuild:
    """图构建测试"""

    def test_build_graph_returns_compiled_graph(self):
        """验证 build_dialog_graph 返回编译后的图"""
        graph = build_dialog_graph()
        assert graph is not None
        # LangGraph 编译后的图应该有 ainvoke 方法
        assert hasattr(graph, "ainvoke")
        assert hasattr(graph, "get_graph")

    def test_graph_has_required_nodes(self):
        """验证图包含所有必需的节点"""
        graph = build_dialog_graph()
        graph_spec = graph.get_graph()

        node_names = {node.name for node in graph_spec.nodes.values()}
        assert "nlu" in node_names
        assert "business" in node_names
        assert "response" in node_names
        assert "fallback" in node_names

    def test_graph_is_singleton_compile(self):
        """验证每次调用 build_dialog_graph 返回新编译实例"""
        g1 = build_dialog_graph()
        g2 = build_dialog_graph()
        # 不同的编译实例
        assert g1 is not g2


class TestGraphIntegration:
    """图集成测试 — 模拟完整流程"""

    def _setup_mock_classifier(self, monkeypatch, intent_result: NLUResult):
        """搭建 mock 的意图分类器"""
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(return_value=intent_result)
        monkeypatch.setattr(
            "app.dm.nodes.nlu_node._classifier",
            mock_classifier,
        )
        return mock_classifier

    def _make_initial_state(self, **overrides) -> dict:
        """构造初始 DialogState"""
        state = {
            "session_id": "sess-test",
            "user_id": "user-test",
            "user_input": "测试输入",
            "intents": {},
            "active_intent": "",
            "slots": {},
            "missing_slots": [],
            "business_result": None,
            "final_response": "",
            "should_fallback": False,
        }
        state.update(overrides)
        return state

    @pytest.mark.asyncio
    async def test_unknown_intent_flow(self, monkeypatch):
        """验证 unknown → fallback → response 的完整流程"""
        self._setup_mock_classifier(
            monkeypatch,
            NLUResult(
                intent="unknown",
                confidence=0.0,
                slots={},
                missing_slots=[],
            ),
        )

        # mock NLGEngine 避免 LLM 调用
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="抱歉，我不太明白您的意思，请换个说法试试。"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        graph = build_dialog_graph()
        state = self._make_initial_state(user_input="asdfghjkl")

        final_state = await graph.ainvoke(state)

        # 应走 unknown → fallback → response 路径
        assert final_state["active_intent"] == "unknown"
        assert final_state["should_fallback"] is True
        assert final_state["final_response"] != ""
        assert "不明白" in final_state["final_response"] or "抱歉" in final_state["final_response"]

    @pytest.mark.asyncio
    async def test_transfer_human_flow(self, monkeypatch):
        """验证 transfer_human → fallback → response 的完整流程"""
        self._setup_mock_classifier(
            monkeypatch,
            NLUResult(
                intent="transfer_human",
                confidence=0.9,
                slots={},
                missing_slots=[],
            ),
        )

        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="正在为您转接人工客服，请稍候..."
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        graph = build_dialog_graph()
        state = self._make_initial_state(user_input="转人工")

        final_state = await graph.ainvoke(state)

        assert final_state["active_intent"] == "transfer_human"
        assert final_state["should_fallback"] is True
        assert "转接人工" in final_state["final_response"]

    @pytest.mark.asyncio
    async def test_business_completed_flow(self, monkeypatch):
        """验证业务意图 → business → response 的完整流程（completed）"""
        self._setup_mock_classifier(
            monkeypatch,
            NLUResult(
                intent="order_query",
                confidence=0.95,
                slots={"order_id": "ORD-001"},
                missing_slots=[],
            ),
        )

        # mock handler 返回 completed
        from app.business.base import BusinessResult
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(
            return_value=BusinessResult.completed(
                message="📋 订单 ORD-001 详情已加载",
                order_id="ORD-001",
                order_status="已签收",
            )
        )
        handler_cls = MagicMock(return_value=mock_handler)

        import app.dm.nodes.business_node as bn
        bn._handler_map["order_query"] = handler_cls

        # mock NLG engine
        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="📋 订单 ORD-001 详情已加载"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        graph = build_dialog_graph()
        state = self._make_initial_state(user_input="查订单 ORD-001")

        final_state = await graph.ainvoke(state)

        assert final_state["active_intent"] == "order_query"
        assert final_state["business_result"] is not None
        assert final_state["should_fallback"] is False
        assert "ORD-001" in final_state["final_response"]

    @pytest.mark.asyncio
    async def test_business_ask_slot_flow(self, monkeypatch):
        """验证业务意图 → business（ask_slot） → response 流程"""
        self._setup_mock_classifier(
            monkeypatch,
            NLUResult(
                intent="postsale_return",
                confidence=0.85,
                slots={},
                missing_slots=["order_id", "postsale_type", "postsale_reason"],
            ),
        )

        from app.business.base import BusinessResult, OptionItem

        options = [OptionItem(label="ORD-001（已签收）", value="ORD-001")]
        mock_result = BusinessResult.ask_slot(
            slot_to_fill="order_id",
            options=options,
            message="请选择要申请售后的订单",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        import app.dm.nodes.business_node as bn
        bn._handler_map["postsale_return"] = handler_cls

        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="请选择要申请售后的订单"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        graph = build_dialog_graph()
        state = self._make_initial_state(user_input="我要退货")

        final_state = await graph.ainvoke(state)

        assert final_state["active_intent"] == "postsale_return"
        assert final_state["business_result"].data["action"] == "ask_slot"
        assert "选择" in final_state["final_response"] or "售后" in final_state["final_response"]

    @pytest.mark.asyncio
    async def test_business_error_flow(self, monkeypatch):
        """验证业务意图 → business（error） → response 流程"""
        self._setup_mock_classifier(
            monkeypatch,
            NLUResult(
                intent="order_query",
                confidence=0.9,
                slots={"order_id": "INVALID"},
                missing_slots=[],
            ),
        )

        from app.business.base import BusinessResult
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(
            return_value=BusinessResult.error("订单 INVALID 不存在")
        )
        handler_cls = MagicMock(return_value=mock_handler)

        import app.dm.nodes.business_node as bn
        bn._handler_map["order_query"] = handler_cls

        mock_engine = MagicMock()
        mock_engine.generate = AsyncMock(
            return_value="订单 INVALID 不存在"
        )
        monkeypatch.setattr(
            "app.dm.nodes.response_node._engine",
            mock_engine,
        )

        graph = build_dialog_graph()
        state = self._make_initial_state(user_input="查订单 INVALID")

        final_state = await graph.ainvoke(state)

        assert final_state["business_result"].success is False
        assert "不存在" in final_state["final_response"]

    def test_graph_nodes_order(self):
        """验证图的节点连接关系"""
        graph = build_dialog_graph()
        graph_spec = graph.get_graph()

        # 收集边
        edges = list(graph_spec.edges)
        edge_pairs = set()
        conditional_edges = set()
        for edge in edges:
            if edge.source and edge.target:
                edge_pairs.add((edge.source, edge.target))
            elif edge.source:
                # 条件边
                pass

        # 验证关键连接存在
        # nlu → business (业务意图)
        # nlu → fallback (平台意图)
        # business → response
        # fallback → response
        # response → END

        assert ("business", "response") in edge_pairs
        assert ("fallback", "response") in edge_pairs
        # 验证 nlu 有出路（条件路由）
        nlu_has_out = any(
            e.source == "nlu" for e in edges
        )
        assert nlu_has_out, "nlu 节点应连接到其他节点"
