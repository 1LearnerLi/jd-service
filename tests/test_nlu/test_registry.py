"""意图注册中心测试"""
import pytest
from app.nlu.models import IntentDefinition, SlotDef
from app.nlu.platform_intents import PLATFORM_INTENTS
from app.nlu.registry import IntentRegistry


class TestPlatformIntents:
    """平台意图定义测试"""

    def test_platform_intents_exist(self):
        """验证平台意图不为空"""
        assert len(PLATFORM_INTENTS) >= 2

    def test_unknown_intent_exists(self):
        """验证 unknown 意图存在"""
        names = [i.name for i in PLATFORM_INTENTS]
        assert "unknown" in names

    def test_transfer_human_intent_exists(self):
        """验证 transfer_human 意图存在"""
        names = [i.name for i in PLATFORM_INTENTS]
        assert "transfer_human" in names

    def test_all_platform_intents_are_valid(self):
        """验证所有平台意图都是有效的 IntentDefinition"""
        for intent in PLATFORM_INTENTS:
            assert isinstance(intent, IntentDefinition)
            assert intent.name != ""


class TestIntentRegistry:
    """意图注册中心测试"""

    def setup_method(self):
        """每个测试前清空注册中心"""
        IntentRegistry.clear()

    def test_singleton(self):
        """验证注册中心是单例"""
        r1 = IntentRegistry()
        r2 = IntentRegistry()
        assert r1 is r2

    def test_get_all_intents_returns_platform_intents(self):
        """验证无业务注册时返回平台意图"""
        all_intents = IntentRegistry.get_all_intents()
        names = {i.name for i in all_intents}
        assert "unknown" in names
        assert "transfer_human" in names

    def test_register_business(self):
        """验证注册业务意图"""
        biz_intents = [
            IntentDefinition(
                name="order_query",
                description="查询订单详情",
                required_slots=[
                    SlotDef(
                        name="order_id",
                        description="订单号",
                        ask_prompt="请提供您的订单号",
                    ),
                ],
            ),
        ]
        IntentRegistry.register_business("ecommerce", biz_intents)
        all_intents = IntentRegistry.get_all_intents()
        names = {i.name for i in all_intents}
        assert "order_query" in names
        # 平台意图仍应存在
        assert "unknown" in names

    def test_register_multiple_businesses(self):
        """验证注册多个业务线"""
        IntentRegistry.register_business(
            "ecommerce",
            [IntentDefinition(name="order_query", description="订单查询")],
        )
        IntentRegistry.register_business(
            "logistics",
            [IntentDefinition(name="logistics_track", description="物流追踪")],
        )
        all_intents = IntentRegistry.get_all_intents()
        names = {i.name for i in all_intents}
        assert "order_query" in names
        assert "logistics_track" in names
        assert "unknown" in names

    def test_get_intent_by_name_found(self):
        """验证按名称查找意图 - 命中"""
        intent = IntentRegistry.get_intent_by_name("unknown")
        assert intent is not None
        assert intent.name == "unknown"

    def test_get_intent_by_name_not_found(self):
        """验证按名称查找意图 - 未命中"""
        intent = IntentRegistry.get_intent_by_name("nonexistent_intent")
        assert intent is None

    def test_get_intent_by_name_after_register(self):
        """验证注册后可按名称查找"""
        IntentRegistry.register_business(
            "ecommerce",
            [IntentDefinition(name="order_query", description="订单查询")],
        )
        intent = IntentRegistry.get_intent_by_name("order_query")
        assert intent is not None
        assert intent.name == "order_query"

    def test_get_required_slot_names(self):
        """验证获取必填槽位名称"""
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
        slots = IntentRegistry.get_required_slot_names("order_query")
        assert slots == ["order_id"]

    def test_get_required_slot_names_unknown_intent(self):
        """验证获取不存在意图的必填槽位返回空列表"""
        slots = IntentRegistry.get_required_slot_names("nonexistent")
        assert slots == []

    def test_clear(self):
        """验证清空注册中心"""
        IntentRegistry.register_business(
            "ecommerce",
            [IntentDefinition(name="order_query", description="订单查询")],
        )
        IntentRegistry.clear()
        all_intents = IntentRegistry.get_all_intents()
        names = {i.name for i in all_intents}
        # 清空后只应保留平台意图
        assert "order_query" not in names
        assert "unknown" in names
