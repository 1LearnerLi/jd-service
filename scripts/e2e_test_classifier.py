"""IntentClassifier 端到端测试 — 调用真实 LLM 验证意图识别效果

使用方法:
    uv run python scripts/e2e_test_classifier.py
"""
import asyncio
from dataclasses import dataclass

from app.nlu.classifier import IntentClassifier
from app.nlu.models import IntentDefinition, SlotDef, NLUResult
from app.nlu.registry import IntentRegistry


# ── 准备测试数据 ──────────────────────────────────────────────

@dataclass
class TestCase:
    user_input: str
    expected_intent: str
    description: str


# 注册电商业务意图（模拟真实场景）
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

IntentRegistry.register_business("ecommerce", ECOMMERCE_INTENTS)

# 测试用例：覆盖不同类型的用户输入
TEST_CASES = [
    # ── order_query 意图 ──
    TestCase("帮我查一下订单 2024070123456", "order_query", "明确提供订单号"),
    TestCase("我的订单发货了吗", "order_query", "询问订单状态（缺订单号）"),
    TestCase("订单号 JD20240701-001 现在到哪了", "order_query", "含订单号的状态查询"),
    TestCase("查订单", "order_query", "简略表达（缺订单号）"),

    # ── postsale_return 意图 ──
    TestCase("我要退货，订单号 20240701001", "postsale_return", "明确退货+订单号"),
    TestCase("这个订单我不想要了，帮我退款", "postsale_return", "退款请求（缺订单号）"),
    TestCase("申请售后，订单 20240701001", "postsale_return", "售后+订单号"),
    TestCase("买的东西质量有问题，能退吗", "postsale_return", "质量问题退货（缺订单号）"),

    # ── product_inquiry 意图 ──
    TestCase("这款手机有什么颜色", "product_inquiry", "商品属性咨询"),
    TestCase("SKU12345 现在多少钱", "product_inquiry", "含 SKU 的询价"),
    TestCase("有没有适合送长辈的礼物推荐", "product_inquiry", "商品推荐"),
    TestCase("这个和那个有什么区别", "product_inquiry", "商品对比咨询"),

    # ── transfer_human 意图 ──
    TestCase("转人工", "transfer_human", "明确要求转人工"),
    TestCase("你们的客服电话是多少", "transfer_human", "索要人工联系方式"),
    TestCase("我要投诉", "transfer_human", "投诉"),
    TestCase("机器人听不懂人话，给我换真人", "transfer_human", "对 AI 不满要求人工"),

    # ── unknown 意图 ──
    TestCase("今天天气真好", "unknown", "无关话题"),
    TestCase("asdfghjkl", "unknown", "乱码输入"),
    TestCase("帮我写一首诗", "unknown", "超出客服范围"),
]


def print_separator(title: str = ""):
    print(f"\n{'─' * 60}")
    if title:
        print(f"  {title}")
        print(f"{'─' * 60}")


def print_result(user_input: str, expected: str, result: NLUResult, ok: bool):
    status = "✅" if ok else "❌"
    print(f"{status} 输入: 「{user_input}」")
    print(f"   期望意图: {expected:<20} | 实际意图: {result.intent:<20} | 置信度: {result.confidence:.2f}")
    if result.slots:
        print(f"   提取槽位: {result.slots}")
    if result.missing_slots:
        print(f"   缺失槽位: {result.missing_slots}")
    if not ok:
        print(f"   >>> 不匹配！期望 {expected}，实际 {result.intent}")


async def main():
    print_separator("IntentClassifier 端到端测试")
    print(f"LLM 模型: deepseek-v4-flash")
    print(f"测试用例数: {len(TEST_CASES)}")

    classifier = IntentClassifier()

    passed = 0
    failed = 0
    results_detail = []

    # ── 逐个执行测试 ──
    for i, tc in enumerate(TEST_CASES, 1):
        print(f"\n[{i}/{len(TEST_CASES)}] {tc.description}")
        result = await classifier.classify(tc.user_input)
        ok = result.intent == tc.expected_intent

        if ok:
            passed += 1
        else:
            failed += 1

        print_result(tc.user_input, tc.expected_intent, result, ok)
        results_detail.append((tc, result, ok))

    # ── 汇总报告 ──
    print_separator("测试汇总")
    total = len(TEST_CASES)
    accuracy = passed / total * 100 if total > 0 else 0

    print(f"  总计: {total}  |  通过: {passed}  |  失败: {failed}  |  准确率: {accuracy:.1f}%")

    # 按意图分组统计
    print(f"\n  按意图分组:")
    intents_order = ["order_query", "postsale_return", "product_inquiry", "transfer_human", "unknown"]
    for intent_name in intents_order:
        cases = [r for r in results_detail if r[0].expected_intent == intent_name]
        if cases:
            ok_count = sum(1 for r in cases if r[2])
            print(f"    {intent_name:<20}: {ok_count}/{len(cases)} ({ok_count/len(cases)*100:.0f}%)")

    # 失败详情
    if failed > 0:
        print_separator("失败用例详情")
        for tc, result, _ in results_detail:
            if result.intent != tc.expected_intent:
                print(f"  输入: 「{tc.user_input}」")
                print(f"  期望: {tc.expected_intent} → 实际: {result.intent} (置信度: {result.confidence:.2f})")
                print()

    print_separator()
    print(f"测试{'全部通过 🎉' if failed == 0 else f'完成，{failed} 个用例未通过'}")


if __name__ == "__main__":
    asyncio.run(main())
