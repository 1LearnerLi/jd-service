"""项目级测试夹具 — 提供 E2E 测试数据管理和 API 客户端"""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from fastapi import FastAPI
from app.api.v1.router import api_router
from app.nlu.registry import IntentRegistry
from app.business.ecommerce.intents import INTENTS
from app.business.ecommerce.repository.order_repo import EcoSessionLocal

# ── 测试数据标识符清单 ──────────────────────────────────

_TEST_RECEIVE_IDS = ["RECV-TEST-001", "RECV-TEST-002", "RECV-TEST-003"]
_TEST_ORDER_IDS = [
    "ORD-TEST-001", "ORD-TEST-002", "ORD-TEST-003",
    "ORD-TEST-004", "ORD-TEST-005",
]
_TEST_ORDER_DETAIL_IDS = [
    "OD-TEST-001", "OD-TEST-002", "OD-TEST-003",
    "OD-TEST-004", "OD-TEST-005",
]


# ── 应用工厂 ───────────────────────────────────────────

def _create_test_app() -> FastAPI:
    """创建测试用 FastAPI 实例，注册电商业务线意图"""
    IntentRegistry.clear()
    IntentRegistry.register_business("ecommerce", INTENTS)
    app = FastAPI(title="test-e2e")
    app.include_router(api_router)
    return app


# ── 数据库辅助 ─────────────────────────────────────────

async def _async_insert_test_data():
    """向 ecs 库插入 E2E 测试数据"""
    async with EcoSessionLocal() as db:
        # 收货地址（region 表已内置上海各区）
        await db.execute(text("""
            INSERT INTO receive_info
                (receive_id, user_id, receiver_name, receiver_phone,
                 receive_province, receive_city, receive_district, receive_street_address)
            VALUES
            ('RECV-TEST-001', '1001', '张三', '13800138001',
             '上海', '上海市', '浦东新区', '张江路100号'),
            ('RECV-TEST-002', '1001', '张三', '13800138001',
             '上海', '上海市', '徐汇区', '漕河泾路200号'),
            ('RECV-TEST-003', '1002', '李四', '13900139002',
             '上海', '上海市', '静安区', '南京西路300号')
        """))

        # 订单（依赖 user_info、receive_info、order_status）
        await db.execute(text("""
            INSERT INTO order_info
                (order_id, create_time, user_id, receive_id, order_status)
            VALUES
            ('ORD-TEST-001', NOW(), '1001', 'RECV-TEST-001', '已签收'),
            ('ORD-TEST-002', NOW(), '1001', 'RECV-TEST-002', '已发货'),
            ('ORD-TEST-003', NOW(), '1001', 'RECV-TEST-001', '已取消'),
            ('ORD-TEST-004', NOW(), '1001', 'RECV-TEST-001', '待支付'),
            ('ORD-TEST-005', NOW(), '1002', 'RECV-TEST-003', '已签收')
        """))

        # 订单明细（依赖 order_info、sku_info）
        await db.execute(text("""
            INSERT INTO order_detail
                (order_detail_id, order_id, sku_id, sku_name,
                 sku_count, total_amount, discount_amount, final_amount)
            VALUES
            ('OD-TEST-001', 'ORD-TEST-001', 'sku123456', '男士纯棉T恤',
             2, 179.80, 0.00, 179.80),
            ('OD-TEST-002', 'ORD-TEST-002', 'sku123458', '智能手机X1',
             1, 2999.00, 100.00, 2899.00),
            ('OD-TEST-003', 'ORD-TEST-003', 'sku123460', '保湿面霜',
             1, 129.00, 0.00, 129.00),
            ('OD-TEST-004', 'ORD-TEST-004', 'sku123461', '进口巧克力礼盒',
             3, 294.00, 29.40, 264.60),
            ('OD-TEST-005', 'ORD-TEST-005', 'sku123462', '实木餐桌',
             1, 1299.00, 0.00, 1299.00)
        """))

        await db.commit()


async def _async_cleanup_test_data():
    """清理 E2E 测试数据（按 FK 依赖逆序删除）"""
    async with EcoSessionLocal() as db:
        for od_id in _TEST_ORDER_DETAIL_IDS:
            await db.execute(
                text("DELETE FROM order_detail WHERE order_detail_id = :id"),
                {"id": od_id},
            )
        for o_id in _TEST_ORDER_IDS:
            await db.execute(
                text("DELETE FROM order_info WHERE order_id = :id"),
                {"id": o_id},
            )
        for r_id in _TEST_RECEIVE_IDS:
            await db.execute(
                text("DELETE FROM receive_info WHERE receive_id = :id"),
                {"id": r_id},
            )
        await db.commit()


# ── Fixtures ───────────────────────────────────────────

@pytest.fixture(scope="module")
async def e2e_test_data():
    """E2E 测试数据管理 — 插入测试数据并在所有测试结束后清理

    使用 module scope，同一模块内的所有测试共享同一批数据。
    """
    try:
        await _async_insert_test_data()
    except IntegrityError:
        # 数据可能已存在（上次测试未正常清理），先清理再重新插入
        await _async_cleanup_test_data()
        await _async_insert_test_data()

    yield

    try:
        await _async_cleanup_test_data()
    except Exception:
        pass  # 清理失败不阻塞测试


@pytest.fixture(scope="module")
async def api_client(e2e_test_data):
    """创建测试 HTTP 客户端（module scope）

    依赖 e2e_test_data 确保数据已插入后再创建客户端。
    """
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # 给异步连接池一些时间清理
    await asyncio.sleep(0.1)
