"""电商业务线意图定义测试"""
import pytest
from app.business.ecommerce.intents import ECOMMERCE_INTENTS
from app.nlu.models import IntentDefinition, SlotDef


class TestEcommerceIntents:
    """ECOMMERCE_INTENTS 电商意图定义测试"""

    def test_ecommerce_intents_is_list(self):
        """验证 ECOMMERCE_INTENTS 是列表"""
        assert isinstance(ECOMMERCE_INTENTS, list)

    def test_ecommerce_intents_count(self):
        """验证电商业务线注册了 3 个意图"""
        assert len(ECOMMERCE_INTENTS) == 3

    def test_ecommerce_intents_are_valid(self):
        """验证所有意图都是 IntentDefinition 实例"""
        for intent in ECOMMERCE_INTENTS:
            assert isinstance(intent, IntentDefinition)

    def test_order_query_intent_exists(self):
        """验证 order_query 意图存在"""
        names = [i.name for i in ECOMMERCE_INTENTS]
        assert "order_query" in names

    def test_postsale_return_intent_exists(self):
        """验证 postsale_return 意图存在"""
        names = [i.name for i in ECOMMERCE_INTENTS]
        assert "postsale_return" in names

    def test_product_inquiry_intent_exists(self):
        """验证 product_inquiry 意图存在"""
        names = [i.name for i in ECOMMERCE_INTENTS]
        assert "product_inquiry" in names


class TestOrderQueryIntent:
    """order_query 意图定义详细测试"""

    def test_order_query_has_required_slots(self):
        """验证 order_query 有必填槽位"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "order_query")
        assert len(intent.required_slots) == 1
        assert intent.required_slots[0].name == "order_id"

    def test_order_query_no_optional_slots(self):
        """验证 order_query 没有可选槽位"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "order_query")
        assert len(intent.optional_slots) == 0

    def test_order_query_slot_has_ask_prompt(self):
        """验证 order_query 的槽位有追问提示"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "order_query")
        slot = intent.required_slots[0]
        assert slot.ask_prompt != ""


class TestPostsaleReturnIntent:
    """postsale_return 意图定义详细测试"""

    def test_postsale_return_has_required_slots(self):
        """验证 postsale_return 有必填槽位"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "postsale_return")
        assert len(intent.required_slots) == 1
        assert intent.required_slots[0].name == "order_id"

    def test_postsale_return_no_optional_slots(self):
        """验证 postsale_return 没有可选槽位"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "postsale_return")
        assert len(intent.optional_slots) == 0


class TestProductInquiryIntent:
    """product_inquiry 意图定义详细测试"""

    def test_product_inquiry_no_required_slots(self):
        """验证 product_inquiry 没有必填槽位"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "product_inquiry")
        assert len(intent.required_slots) == 0

    def test_product_inquiry_has_optional_slots(self):
        """验证 product_inquiry 有可选槽位"""
        intent = next(i for i in ECOMMERCE_INTENTS if i.name == "product_inquiry")
        assert len(intent.optional_slots) == 2
        names = [s.name for s in intent.optional_slots]
        assert "sku_id" in names
        assert "sku_name" in names


class TestEcommerceIntentRegistration:
    """意图注册集成测试"""

    def test_register_ecommerce_intents(self):
        """验证电商意图可成功注册到注册中心"""
        from app.nlu.registry import IntentRegistry

        # 确保注册
        IntentRegistry.register_business("ecommerce", ECOMMERCE_INTENTS)

        all_intents = IntentRegistry.get_all_intents()
        names = [i.name for i in all_intents]
        assert "order_query" in names
        assert "postsale_return" in names
        assert "product_inquiry" in names
        # 平台意图仍然在
        assert "unknown" in names
        assert "transfer_human" in names
