"""IntentClassifier 端到端测试 — 调用真实 LLM 验证意图识别效果

使用方法:
    uv run pytest tests/test_nlu/test_classifier_e2e.py -v -s

注意: 此测试依赖 .env 中配置的真实 LLM 服务。
"""
import pytest

from app.nlu.classifier import IntentClassifier
from app.nlu.models import IntentDefinition, SlotDef
from app.nlu.registry import IntentRegistry


# ── 注册电商业务意图（模拟真实场景） ──────────────────────────

ECOMMERCE_INTENTS = [
    IntentDefinition(
        name="order_query",
        description="用户查询自己的订单详情、订单状态或订单信息",
        required_slots=[
            SlotDef(
                name="order_id",
                description="订单号",
                ask_prompt="请提供您的订单号，我帮您查询详情",
            ),
        ],
    ),
    IntentDefinition(
        name="postsale_return",
        description="用户申请退货退款或售后退款",
        required_slots=[
            SlotDef(
                name="order_id",
                description="订单号",
                ask_prompt="请提供您要申请售后的订单号",
            ),
        ],
    ),
    IntentDefinition(
        name="product_inquiry",
        description="用户咨询商品信息，包括商品价格、规格、库存、使用说明等",
        optional_slots=[
            SlotDef(name="sku_id", description="商品 SKU ID"),
            SlotDef(name="sku_name", description="商品名称"),
        ],
    ),
]


@pytest.fixture(scope="module")
def classifier():
    """初始化分类器并注册电商业务意图"""
    IntentRegistry.clear()
    IntentRegistry.register_business("ecommerce", ECOMMERCE_INTENTS)
    return IntentClassifier()


# ── order_query 意图 ────────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_order_query_with_id(classifier):
    """明确提供订单号 → order_query"""
    result = await classifier.classify("帮我查一下订单 2024070123456")
    assert result.target_intent == "order_query"
    assert "2024070123456" in str(result.slots_update.get("order_id", ""))


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_order_query_ship_status(classifier):
    """询问订单状态（缺订单号）→ order_query"""
    result = await classifier.classify("我的订单发货了吗")
    assert result.target_intent == "order_query"
    # missing_slots 不再由 NLU 输出，由 IntentController 动态计算


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_order_query_track(classifier):
    """含订单号的物流查询 → order_query"""
    result = await classifier.classify("订单号 JD20240701-001 现在到哪了")
    assert result.target_intent == "order_query"
    slots_lower = {k.lower(): str(v).lower() for k, v in result.slots_update.items()}
    assert any("jd20240701" in v for v in slots_lower.values())


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_order_query_vague(classifier):
    """简略表达查订单 → order_query"""
    result = await classifier.classify("查订单")
    assert result.target_intent == "order_query"


# ── postsale_return 意图 ────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_postsale_return_with_id(classifier):
    """明确退货+订单号 → postsale_return"""
    result = await classifier.classify("我要退货，订单号 20240701001")
    assert result.target_intent == "postsale_return"
    assert "20240701001" in str(result.slots_update.get("order_id", ""))


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_postsale_return_refund(classifier):
    """退款请求（缺订单号）→ postsale_return"""
    result = await classifier.classify("这个订单我不想要了，帮我退款")
    assert result.target_intent == "postsale_return"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_postsale_return_aftersale(classifier):
    """申请售后+订单号 → postsale_return"""
    result = await classifier.classify("申请售后，订单 20240701001")
    assert result.target_intent == "postsale_return"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_postsale_return_quality_issue(classifier):
    """质量问题退货（缺订单号）→ postsale_return"""
    result = await classifier.classify("买的东西质量有问题，能退吗")
    assert result.target_intent == "postsale_return"


# ── product_inquiry 意图 ────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_product_inquiry_color(classifier):
    """商品属性咨询 → product_inquiry"""
    result = await classifier.classify("这款手机有什么颜色")
    assert result.target_intent == "product_inquiry"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_product_inquiry_sku_price(classifier):
    """含 SKU 的询价 → product_inquiry"""
    result = await classifier.classify("SKU12345 现在多少钱")
    assert result.target_intent == "product_inquiry"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_product_inquiry_gift_recommend(classifier):
    """商品推荐 → product_inquiry"""
    result = await classifier.classify("有没有适合送长辈的礼物推荐")
    assert result.target_intent == "product_inquiry"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_product_inquiry_compare(classifier):
    """商品对比 → product_inquiry"""
    result = await classifier.classify("这个和那个有什么区别")
    assert result.target_intent == "product_inquiry"


# ── transfer_human 意图 ─────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_transfer_human_direct(classifier):
    """明确要求转人工 → transfer_human"""
    result = await classifier.classify("转人工")
    assert result.target_intent == "transfer_human"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_transfer_human_phone(classifier):
    """索要人工联系方式 → transfer_human"""
    result = await classifier.classify("你们的客服电话是多少")
    assert result.target_intent == "transfer_human"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_transfer_human_complaint(classifier):
    """投诉 → transfer_human"""
    result = await classifier.classify("我要投诉")
    assert result.target_intent == "transfer_human"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_transfer_human_angry(classifier):
    """对 AI 不满 → transfer_human"""
    result = await classifier.classify("机器人听不懂人话，给我换真人")
    assert result.target_intent == "transfer_human"


# ── unknown 意图 ────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_unknown_weather(classifier):
    """无关话题 → unknown"""
    result = await classifier.classify("今天天气真好")
    assert result.target_intent == "unknown"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_unknown_gibberish(classifier):
    """乱码输入 → unknown"""
    result = await classifier.classify("asdfghjkl")
    assert result.target_intent == "unknown"


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_e2e_unknown_out_of_scope(classifier):
    """超出客服范围 → unknown"""
    result = await classifier.classify("帮我写一首诗")
    assert result.target_intent == "unknown"
