# 智能客服系统意图端到端测试设计

**日期**: 2026-07-06
**状态**: 已确认
**类型**: 测试设计

## 1. 目标

通过真实 LLM 的 API 端到端测试，验证所有意图在完整链路（API → NLU → DM → 业务层 → NLG）中是否能正常工作。

## 2. 测试方式

- **LLM**: 真实调用（通过 `.env` 中配置的 OpenAI key）
- **测试工具**: `httpx.AsyncClient` + `pytest-asyncio`
- **标记**: `@pytest.mark.e2e`（与现有单元测试区分，CI 中可选择性跳过）
- **数据管理**: pytest fixture（module scope）在测试前向 `ecs` 库插入测试数据，测试后清理

## 3. 被刻意试的意图

| 意图 | 类型 | 必填槽位 | Handler 状态 |
|------|------|---------|-------------|
| `unknown` | 平台 | 无 | ✅ 走 fallback |
| `transfer_human` | 平台 | 无 | ✅ 走 fallback |
| `order_query` | 业务 | `order_id` | ✅ OrderQueryHandler |
| `postsale_return` | 业务 | `order_id`, `postsale_type`, `postsale_reason` | ✅ PostsaleReturnHandler |
| `product_inquiry` | 业务 | `query` | ❌ handler=None |

## 4. 测试数据设计

### 4.1 数据源

复用 `docker/mysql/ecs.sql` 中已有的数据：
- **用户**: 1001~1010（10 个）
- **商品**: sku123456~sku123555（60 个，覆盖 7 个品类）
- **区域**: 全国省市区（数千条）
- **售后原因**: 按品类分类（50+ 条）
- **物流公司**: 6 家

### 4.2 需要额外插入的测试数据

#### 收货地址

| receive_id | user_id | receiver_name | receiver_phone | 省 | 市 | 区 | 详细地址 |
|-----------|---------|---------------|----------------|-----|-----|-----|---------|
| RECV-TEST-001 | 1001 | 张三 | 13800138001 | 上海 | 上海市 | 浦东新区 | 张江路100号 |
| RECV-TEST-002 | 1001 | 张三 | 13800138001 | 上海 | 上海市 | 徐汇区 | 漕河泾路200号 |
| RECV-TEST-003 | 1002 | 李四 | 13900139002 | 上海 | 上海市 | 静安区 | 南京西路300号 |

#### 订单

| order_id | user_id | receive_id | 状态 | 用途 |
|----------|---------|-----------|------|------|
| ORD-TEST-001 | 1001 | RECV-TEST-001 | 已签收 | 正常可查可售后 |
| ORD-TEST-002 | 1001 | RECV-TEST-002 | 已发货 | 运输中可售后 |
| ORD-TEST-003 | 1001 | RECV-TEST-001 | 已取消 | postsale 不可选(disabled) |
| ORD-TEST-004 | 1001 | RECV-TEST-001 | 待支付 | postsale 不可选(disabled) |
| ORD-TEST-005 | 1002 | RECV-TEST-003 | 已签收 | 属于 1002，测试跨用户校验 |

#### 订单明细

| order_detail_id | order_id | sku_id | sku_name | sku_count | total_amount | final_amount |
|-----------------|----------|--------|----------|-----------|-------------|-------------|
| OD-TEST-001 | ORD-TEST-001 | sku123456 | 男士纯棉T恤 | 2 | 179.80 | 179.80 |
| OD-TEST-002 | ORD-TEST-002 | sku123458 | 智能手机X1 | 1 | 2999.00 | 2899.00 |
| OD-TEST-003 | ORD-TEST-003 | sku123460 | 保湿面霜 | 1 | 129.00 | 129.00 |
| OD-TEST-004 | ORD-TEST-004 | sku123461 | 进口巧克力礼盒 | 3 | 294.00 | 264.60 |
| OD-TEST-005 | ORD-TEST-005 | sku123462 | 实木餐桌 | 1 | 1299.00 | 1299.00 |

### 4.3 数据生命周期

```
测试开始 → fixture 插入数据 → 所有测试执行 → fixture 清理数据 → 测试结束
```

使用 module-scoped fixture，所有测试共享同一批数据。

## 5. 测试用例设计

全部 8 个用例，位于 `tests/test_api/test_intent_flows.py`。

### 用例 1: `test_unknown_intent`

**场景**: 用户输入无法理解的乱码 → 走 fallback

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "asdfghjkl123456胡乱输入" | SSE 事件包含 `done`，回复非空，合理兜底 |

### 用例 2: `test_transfer_human`

**场景**: 用户请求转人工 → 走 fallback

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "我要转人工客服" | 回复包含"人工"或"转接"等字样 |

### 用例 3: `test_order_query_full_flow`

**场景**: 多轮对话完成订单查询

| 轮次 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "帮我查一下我的订单" | 回复包含订单列表（ask_slot 渲染为文本），包含 ORD-TEST-001 |
| 3 | 发送 "ORD-TEST-001" | 回复包含订单详情：已签收、男士纯棉T恤、金额等 |

### 用例 4: `test_postsale_return_full_flow`

**场景**: 完整售后申请四轮流程

| 轮次 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "我要申请退货退款" | 回复包含订单列表，不可售后订单置灰说明 |
| 3 | 发送 "ORD-TEST-001" | 回复包含售后方式选择（仅退款/退货退款） |
| 4 | 发送 "退货退款" | 回复包含售后原因选择 |
| 5 | 发送 "商品瑕疵/破损" | 回复确认售后申请已提交，状态变为售后中 |

### 用例 5: `test_product_inquiry_fallback`

**场景**: Handler 为 None 的意图，验证系统不崩溃

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "这个智能手机X1有什么功能" | 返回非空回复，HTTP 200，不崩溃 |

### 用例 6: `test_multi_intent_suspend_resume`

**场景**: 多意图切换 — 售后流程中插入订单查询，验证挂起/恢复

| 轮次 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "我要退货" | 进入 postsale_return，回复要求选择订单 |
| 3 | 发送 "先帮我查一下 ORD-TEST-001 这个订单" | 切换到 order_query，回复订单详情 |
| 4 | 发送 "好的，继续退货" | 恢复到 postsale_return，继续选订单或自动填充 order_id |

> **注意**: 第 4 步的自动恢复依赖 LLM 判断 — 需要 NLU 识别用户意图为"返回到之前挂起的售后流程"。如果 LLM 不稳定，此用例可能标记为 `@pytest.mark.flaky`。

### 用例 7: `test_order_query_not_found`

**场景**: 查询不存在的订单号

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "查询订单 NONEXIST-999" | 回复包含"不存在"或错误提示 |

### 用例 8: `test_session_persistence`

**场景**: 对话后验证会话和消息持久化

| 步骤 | 操作 | 验证 |
|------|------|------|
| 1 | 创建会话 (user_id=1001) | 200 |
| 2 | 发送 "查订单 ORD-TEST-001" | 200 |
| 3 | GET `/sessions/{session_id}` | 包含 2 条消息（user + assistant），会话状态正确 |

## 6. 测试代码结构

```
tests/
├── conftest.py                          # [新建] 共享 fixtures
│   ├── e2e_test_data()                  #   module scope — 插入/清理测试数据
│   └── api_client()                     #   module scope — httpx AsyncClient
│
└── test_api/
    ├── __init__.py
    ├── test_sessions.py                 # [已有] 会话 CRUD 测试
    └── test_intent_flows.py             # [新建] 意图端到端测试
        ├── class TestUnknownAndFallback
        │   ├── test_unknown_intent
        │   └── test_transfer_human
        ├── class TestOrderQuery
        │   ├── test_order_query_full_flow
        │   └── test_order_query_not_found
        ├── class TestPostsaleReturn
        │   └── test_postsale_return_full_flow
        ├── class TestProductInquiry
        │   └── test_product_inquiry_fallback
        ├── class TestMultiIntent
        │   └── test_multi_intent_suspend_resume
        └── class TestSessionPersistence
            └── test_session_persistence
```

### 辅助函数

```python
async def _create_session(client, user_id: str) -> str:
    """创建会话并返回 session_id"""

async def _send_message(client, session_id: str, content: str) -> str:
    """发送消息并消费 SSE 流，返回完整的 AI 回复文本"""

async def _get_messages(client, session_id: str) -> list[dict]:
    """获取会话消息列表"""
```

## 7. conftest.py 设计

```python
# tests/conftest.py

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

@pytest.fixture(scope="module")
def e2e_test_data():
    """E2E 测试数据管理 — 插入/清理"""
    # 插入接收地址
    # 插入订单
    # 插入订单明细
    yield
    # 按 order_detail_id / order_id / receive_id 顺序删除

@pytest.fixture(scope="module")
async def api_client():
    """创建测试 HTTP 客户端"""
    # 复用现有 tests/test_api/test_sessions.py 中的模式
```

## 8. 技术要点

### 8.1 SSE 流消费

发送消息 API 返回 `text/event-stream`，测试需要消费完整流并提取回复文本：

```python
async def _send_message(client, session_id, content) -> str:
    response = await client.post(
        f"/api/v1/sessions/{session_id}/messages?content={content}"
    )
    assert response.status_code == 200
    full_text = ""
    async for line in response.aiter_lines():
        if line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk:
                full_text += chunk
    return full_text
```

### 8.2 真实 LLM 的不确定性

真实 LLM 测试的关键策略：
- **宽松断言**: 不检查精确文本，而是检查关键字/语义存在
- **需要人工判断的用例**: 标记为 `@pytest.mark.e2e`，CI 中按需执行
- **多意图切换**: LLM 对"恢复上一个意图"的判断可能不稳定，标注为 flaky

### 8.3 测试隔离

- 每次创建新会话，避免意图状态交叉污染
- 测试数据使用独立的 `ORD-TEST-*` 前缀，不影响生产数据
- 使用 module scope fixture 保证数据插入一次、所有测试共享

## 9. 运行方式

```bash
# 运行全部 E2E 测试
uv run pytest tests/test_api/test_intent_flows.py -v -m e2e

# 运行单个测试
uv run pytest tests/test_api/test_intent_flows.py::TestOrderQuery -v -m e2e

# 跳过 E2E 测试（CI 中）
uv run pytest -m "not e2e"
```

前置条件：
1. Docker MySQL 运行中（`docker compose -f docker/docker-compose.yaml up -d`）
2. `ecs` 库已有基础数据（已导入 `ecs.sql`）
3. `.env` 中已配置有效的 `OPENAI_API_KEY`
