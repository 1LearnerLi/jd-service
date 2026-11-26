"""NLGEngine 单元测试"""
import pytest
from unittest.mock import AsyncMock, patch

from app.nlg.engine import NLGEngine
from app.business.base import BusinessResult, OptionItem


@pytest.mark.asyncio
async def test_generate_with_business_result():
    """测试有 business_result 时直接使用其 message"""
    engine = NLGEngine()

    # 测试 completed 类型
    result = await engine.generate(
        intent="order_query",
        business_result=BusinessResult.completed(message="订单查询成功"),
    )
    assert result == "订单查询成功"

    # 测试 ask_slot 类型
    result = await engine.generate(
        intent="postsale_return",
        business_result=BusinessResult.ask_slot(
            slot_to_fill="order_id",
            options=[OptionItem(label="ORD-001（已签收）", value="ORD-001")],
            message="请选择要申请售后的订单",
        ),
    )
    assert result == "请选择要申请售后的订单"

    # 测试 error 类型
    result = await engine.generate(
        intent="order_query",
        business_result=BusinessResult.error("订单不存在"),
    )
    assert result == "订单不存在"


@pytest.mark.asyncio
async def test_generate_transfer_human():
    """测试转人工返回固定文案"""
    engine = NLGEngine()
    result = await engine.generate(intent="transfer_human")

    assert "转接人工客服" in result


@pytest.mark.asyncio
async def test_generate_fallback_calls_llm():
    """测试兜底场景走 LLM 生成"""
    engine = NLGEngine()

    # Mock LLMGenerator.generate
    with patch.object(engine._llm, "generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "您好！请问有什么可以帮您的？"

        result = await engine.generate(
            intent="unknown",
            context={"user_input": "你好"},
        )

        mock_gen.assert_awaited_once_with("你好")
        assert result == "您好！请问有什么可以帮您的？"


@pytest.mark.asyncio
async def test_generate_business_result_takes_priority():
    """测试 business_result 优先级高于 intent 路由"""
    engine = NLGEngine()

    # 即使 intent 是 unknown，有 business_result 也应该用 business_result.message
    result = await engine.generate(
        intent="unknown",
        business_result=BusinessResult.completed(message="已为您找到相关信息"),
    )
    assert result == "已为您找到相关信息"
