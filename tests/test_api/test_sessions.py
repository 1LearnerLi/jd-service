"""会话 API 集成测试

测试 REST 端点：会话 CRUD + 消息发送（SSE）。
使用真实 MySQL 数据库（需要 Docker 启动）。
"""
import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from fastapi import FastAPI
from app.api.v1.router import api_router


def _create_test_app() -> FastAPI:
    """创建测试用 FastAPI 实例（不依赖 main.py）"""
    app = FastAPI(title="test")
    app.include_router(api_router)
    return app


@pytest.fixture(scope="module")
async def client():
    """创建测试 HTTP 客户端（module 作用域）"""
    app = _create_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    # asyncmy 连接池清理前给一点时间
    await asyncio.sleep(0.1)


@pytest.mark.asyncio(loop_scope="module")
async def test_create_session(client):
    """测试创建会话"""
    response = await client.post("/api/v1/sessions?user_id=1001")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user_id"] == "1001"
    assert body["data"]["id"] != ""


@pytest.mark.asyncio(loop_scope="module")
async def test_create_session_missing_user_id(client):
    """测试创建会话缺少必填参数 → 422"""
    response = await client.post("/api/v1/sessions")
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="module")
async def test_list_sessions(client):
    """测试获取会话列表"""
    for _ in range(3):
        await client.post("/api/v1/sessions?user_id=2001")

    response = await client.get("/api/v1/sessions?user_id=2001")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]) >= 3


@pytest.mark.asyncio(loop_scope="module")
async def test_list_sessions_missing_user_id(client):
    """测试获取会话列表缺少必填参数 → 422"""
    response = await client.get("/api/v1/sessions")
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="module")
async def test_get_session(client):
    """测试获取会话详情（含消息列表）"""
    resp = await client.post("/api/v1/sessions?user_id=3001")
    session_id = resp.json()["data"]["id"]

    response = await client.get(f"/api/v1/sessions/{session_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["session"]["id"] == session_id
    assert "messages" in body["data"]


@pytest.mark.asyncio(loop_scope="module")
async def test_get_session_not_found(client):
    """测试获取不存在的会话 → 404"""
    response = await client.get("/api/v1/sessions/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="module")
async def test_send_message_session_not_found(client):
    """测试向不存在的会话发送消息 → 404"""
    response = await client.post(
        "/api/v1/sessions/nonexistent-id/messages?content=你好"
    )
    assert response.status_code == 404


@pytest.mark.asyncio(loop_scope="module")
async def test_send_message_missing_content(client):
    """测试发送消息缺少 content → 422"""
    resp = await client.post("/api/v1/sessions?user_id=4001")
    session_id = resp.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/sessions/{session_id}/messages"
    )
    assert response.status_code == 422


@pytest.mark.asyncio(loop_scope="module")
async def test_send_message_success(client):
    """测试发送消息成功，验证 SSE 流式事件格式"""
    resp = await client.post("/api/v1/sessions?user_id=5001")
    session_id = resp.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/sessions/{session_id}/messages?content=你好"
    )
    assert response.status_code == 200
    # 验证 SSE Content-Type
    content_type = response.headers.get("content-type", "")
    assert "text/event-stream" in content_type

    # 消费流并验证事件类型
    events = [line async for line in response.aiter_lines() if line.startswith("event:")]
    assert any("message" in e for e in events), f"缺少 message 事件: {events}"
    assert any("done" in e for e in events), f"缺少 done 事件: {events}"
