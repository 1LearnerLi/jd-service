"""TemplateEngine 单元测试"""
import tempfile
import os
import pytest
from pathlib import Path

from app.nlg.template_engine import TemplateEngine


@pytest.mark.asyncio
async def test_render_basic_template():
    """测试基本模板渲染"""
    # Arrange: 创建临时模板目录和文件
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpl_path = Path(tmpdir) / "test.j2"
        tmpl_path.write_text("Hello, {{ name }}!", encoding="utf-8")

        engine = TemplateEngine(tmpdir)

        # Act
        result = await engine.render("test.j2", {"name": "World"})

        # Assert
        assert result == "Hello, World!"


@pytest.mark.asyncio
async def test_render_with_conditional():
    """测试条件渲染"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpl_path = Path(tmpdir) / "cond.j2"
        tmpl_path.write_text(
            "{% if show %}可见{% else %}隐藏{% endif %}",
            encoding="utf-8",
        )

        engine = TemplateEngine(tmpdir)

        assert await engine.render("cond.j2", {"show": True}) == "可见"
        assert await engine.render("cond.j2", {"show": False}) == "隐藏"


@pytest.mark.asyncio
async def test_render_with_loop():
    """测试循环渲染"""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpl_path = Path(tmpdir) / "loop.j2"
        tmpl_path.write_text(
            "{% for item in items %}{{ item }}{% if not loop.last %}, {% endif %}{% endfor %}",
            encoding="utf-8",
        )

        engine = TemplateEngine(tmpdir)
        result = await engine.render("loop.j2", {"items": ["a", "b", "c"]})

        assert result == "a, b, c"


@pytest.mark.asyncio
async def test_render_template_not_found():
    """测试模板不存在的降级处理"""
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = TemplateEngine(tmpdir)
        result = await engine.render("nonexistent.j2", {})

        # 模板不存在时返回降级提示
        assert "抱歉" in result


@pytest.mark.asyncio
async def test_render_order_query_template():
    """测试业务线模板 — 订单详情"""
    template_dir = str(
        Path(__file__).parent.parent.parent
        / "app" / "business" / "ecommerce" / "templates"
    )
    if not os.path.isdir(template_dir):
        pytest.skip("模板目录不存在")

    engine = TemplateEngine(template_dir)
    result = await engine.render(
        "order_query.j2",
        {
            "order_id": "ORD-001",
            "order_status": "已签收",
            "create_time": "2025-06-01 10:00:00",
            "payment_time": "2025-06-01 10:05:00",
            "delivered_time": "2025-06-03 14:00:00",
            "details": [
                {
                    "sku_name": "智能手机",
                    "sku_count": 1,
                    "unit_price": 2999.00,
                    "final_amount": 2899.00,
                },
            ],
        },
    )

    assert "ORD-001" in result
    assert "已签收" in result
    assert "智能手机" in result
    assert "2999.00" in result


@pytest.mark.asyncio
async def test_render_postsale_return_template():
    """测试业务线模板 — 售后申请"""
    template_dir = str(
        Path(__file__).parent.parent.parent
        / "app" / "business" / "ecommerce" / "templates"
    )
    if not os.path.isdir(template_dir):
        pytest.skip("模板目录不存在")

    engine = TemplateEngine(template_dir)
    result = await engine.render(
        "postsale_return.j2",
        {
            "order_id": "ORD-001",
            "postsale_type": "退货退款",
            "postsale_reason": "商品瑕疵/破损",
            "new_status": "售后中",
        },
    )

    assert "ORD-001" in result
    assert "退货退款" in result
    assert "商品瑕疵/破损" in result
    assert "售后中" in result
