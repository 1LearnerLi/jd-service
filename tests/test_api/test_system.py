"""系统信息 API 集成测试"""

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI
from app.api.v1.router import api_router
from app.nlu.registry import IntentRegistry
from app.business.ecommerce.intents import INTENTS


def _create_test_app() -> FastAPI:
    """创建测试用 FastAPI 实例，注册电商业务线意图"""
    IntentRegistry.clear()
    IntentRegistry.register_business("ecommerce", INTENTS)
    app = FastAPI(title="test-system")
    app.include_router(api_router)
    return app


@pytest.fixture(scope="module")
async def client():
    """创建测试 HTTP 客户端"""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio(loop_scope="module")
async def test_list_intents(client):
    """测试获取意图列表"""
    response = await client.get("/api/v1/system/intents")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    # 至少应该包含平台意图和电商业务线意图
    intent_names = {item["name"] for item in body["data"]}
    assert "unknown" in intent_names, "应包含平台意图 unknown"
    assert "order_query" in intent_names, "应包含电商意图 order_query"


@pytest.mark.asyncio(loop_scope="module")
async def test_list_intents_has_slot_info(client):
    """测试意图列表返回槽位信息"""
    response = await client.get("/api/v1/system/intents")
    assert response.status_code == 200
    body = response.json()

    # 查找 order_query 意图
    order_query = next(
        (item for item in body["data"] if item["name"] == "order_query"), None
    )
    assert order_query is not None
    assert order_query["description"] != ""
    # order_query 需要 order_id 槽位
    slot_names = [s["name"] for s in order_query["required_slots"]]
    assert "order_id" in slot_names
