# 电商智能客服系统 — 设计规格

## 概述

基于 LangGraph + FastAPI + SQLAlchemy + MySQL 的可扩展智能客服系统，默认内置电商业务线。平台负责 NLU、意图管理、槽位填充、会话管理、DM 编排和 NLG 回复生成；业务线负责具体意图的业务逻辑实现。

## 架构分层

```
通道层 (REST + SSE) → NLU 层 → DM 层 (LangGraph) → 业务层 → NLG 层 → 会话层
```

| 层 | 位置 | 职责 |
|-------|----------|------------|
| **通道层** | `app/api/` | REST + SSE 端点。无业务逻辑。 |
| **NLU 层** | `app/nlu/` | 意图分类 + 槽位提取，由 LLM 驱动。输出标准化的 `NLUResult`。 |
| **DM 层** | `app/dm/` | LangGraph StateGraph：对话状态流转、条件路由、槽位管理。 |
| **业务层** | `app/business/` | 意图处理器和槽位补充。唯一可替换的层。 |
| **NLG 层** | `app/nlg/` | 混合策略：Jinja2 模板用于精确业务结果，LLM 用于闲聊/兜底。 |
| **会话层** | `app/session/` | 会话/消息 ORM 模型和 CRUD 服务，持久化到 `ecs_platform`。 |

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/sessions` | 创建会话（入参 `user_id`） |
| GET | `/api/v1/sessions?user_id=xxx` | 获取会话列表，最多 10 个，按 `updated_at` 倒序 |
| GET | `/api/v1/sessions/{session_id}` | 获取会话详情 + 消息列表 |
| POST | `/api/v1/sessions/{session_id}/messages` | 发送消息，SSE 流式返回回复 |

- 所有 API 使用统一的 JSON 响应信封：`{ success, data, error, meta }`
- 消息发送返回 `text/event-stream`

## 双数据库分离

| 数据库 | 用途 | 配置 |
|----------|------|-------------|
| `ecs_platform` | 对话会话、消息历史 | `app/core/database.py` → `PLATFORM_DATABASE_URL`，Alembic 管理 |
| `ecs` | 电商业务数据（订单、物流、售后等） | `business/ecommerce/config.py` → `ECO_DATABASE_URL`，业务线自管 |

平台永远不感知业务数据库。

## 平台库表结构（ecs_platform）

### sessions

| 字段 | 类型 | 说明 |
|------|------|------|
| id | VARCHAR(50) PK | 会话唯一 ID |
| user_id | VARCHAR(50) NOT NULL | 用户 ID |
| title | VARCHAR(200) | 会话标题 |
| status | ENUM('active', 'closed') | 会话状态 |
| intents_json | JSON | 会话意图状态快照（多意图支持） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 最后更新时间 |

### messages

| 字段 | 类型 | 说明 |
|------|------|------|
| id | BIGINT PK AUTO_INCREMENT | 消息 ID |
| session_id | VARCHAR(50) FK → sessions.id | 关联会话 |
| role | ENUM('user', 'assistant') | 消息角色 |
| content | TEXT | 消息内容 |
| intent | VARCHAR(50) | 关联意图名 |
| slots_json | JSON | 槽位快照 |
| created_at | DATETIME | 创建时间 |

## NLU 层

### 意图识别方式

基于 LLM prompt 分类：将所有意图定义通过 system prompt 喂给 LLM，输出结构化 JSON（意图名 + 槽位键值对 + 缺失槽位）。

### 核心模型

- `IntentDefinition`: 意图定义（name, description, required_slots, optional_slots, handler）
- `SlotDef`: 槽位定义（name, description, ask_prompt）
- `NLUResult`: NLU 层增量式输出（action, target_intent, confidence, slots_update）

### 平台意图

| 意图名 | 描述 | 必填槽位 |
|--------|------|----------|
| `unknown` | 无法识别 | 无 |
| `transfer_human` | 转人工 | 无 |

### 电商业务意图（首期）

| 意图名 | 描述 | 必填槽位 | 可选槽位 |
|--------|------|----------|----------|
| `order_query` | 查询订单详情 | `order_id` | 无 |
| `postsale_return` | 售后退货/退款 | `order_id`, `postsale_type`, `postsale_reason` | 无 |
| `product_inquiry` | 商品咨询（RAG） | `query` | 无 |

### 意图注册机制

各业务线通过注册中心注册意图，NLU 层启动时加载所有已注册意图来构造 prompt。

## DM 层

### DialogState

```python
class IntentContext(TypedDict):
    """意图上下文 — 会话中产生的每个意图的完整状态"""
    name: str                       # 意图名
    confidence: float               # 识别置信度 0-1
    status: str                     # "active" | "suspended" | "completed" | "cancelled"
    slots: dict[str, object]        # 该意图独立槽位
    required_slots: list[str]       # 必填槽位名列表
    optional_slots: list[str]       # 可选槽位名列表

class DialogState(TypedDict):
    session_id: str
    user_id: str
    user_input: str
    messages: list[dict[str, str]]        # 对话历史
    all_intents: list[dict]               # 系统+业务线全部可用意图定义
    intents: dict[str, IntentContext]     # 会话中产生的意图（含 status + 独立 slots）
    active_intent: str                    # 当前活跃意图名
    business_result: BusinessResult | None
    final_response: str
    should_fallback: bool
```

**字段说明：**

- `messages`: 对话历史，API 层从 DB 加载后注入
- `all_intents`: 从 IntentRegistry 构建，供 NLU prompt 构造和前端渲染
- `intents`: 会话中实际产生的意图容器，每个意图自带独立 `slots`（不同意图的同名槽位不会混淆）
- `active_intent`: 当前活跃意图名，冗余字段方便路由和节点使用
- 已移除 `slots` 和 `missing_slots` 全局字段，槽位跟随意图管理

### 多意图支持（挂起/恢复模式）

同一个会话中可同时存在多个意图。当用户在处理一个意图的过程中发起另一个意图时，系统自动挂起当前意图，切换到新意图；完成后自动恢复被挂起的意图。

**意图生命周期状态：**

| 状态 | 含义 |
|------|------|
| `active` | 当前正在处理（唯一） |
| `suspended` | 被挂起，等待恢复 |
| `completed` | 已完成（从容器中移除） |
| `cancelled` | 用户取消（从容器中移除） |

**核心机制：**

- **IntentController**（`app/dm/intent_controller.py`）：纯逻辑类，封装意图 CRUD 和生命周期管理
- **增量式 NLU 输出**：NLU 不再返回完整意图状态，而是返回 `action`（new/continue/switch/cancel）+ `target_intent` + `slots_update`（增量槽位）
- **独立槽位**：每个意图的槽位嵌套在 `IntentContext.slots` 中，不同意图的槽位完全隔离
- **自动恢复**：当前意图完成/取消后，按 LIFO 顺序自动恢复最近被挂起的意图
- **持久化**：`Session.intents_json` 字段存储意图容器快照，每次对话回合结束后更新，下次同一会话运行时恢复

### 节点流程

```
entry → nlu → [条件路由]
  ├─ 平台意图 (unknown/transfer_human) → fallback → response
  └─ 业务意图 → business → response
```

槽位填充由业务 Handler 通过 `BusinessResult.ask_slot()` 处理，DM 图无需独立 `slot_filling` 节点。Handler 内部按 required_slots 顺序逐槽位检查：
- 槽位缺失 → 返回 `BusinessResult.ask_slot()`，NLGEngine 直接透传 `message` + `data`
- 槽位齐全 → 执行并返回 `BusinessResult.completed()`
- 执行失败 → 返回 `BusinessResult.error()`

### 意图管理

使用 **字典 + active_intent**（非栈式）：`intents: dict[str, IntentContext]` 保存所有意图及其独立槽位，`active_intent: str` 指向当前活跃意图。每个意图自带 `status` 字段标记生命周期状态。意图切换由 `IntentController` 统一管理，通过 NLU 的增量式输出来决定创建、挂起、恢复、取消或完成意图。

### 数据流示例

```
回合 1: 用户 "我要申请退货退款 ORD-001"
  → NLU: {action:"new", target_intent:"postsale_return", slots_update:{order_id:"ORD-001"}}
  → IntentController: 创建 postsale_return(active)
  → 业务: ask_slot(postsale_type)
  → 持久化 intents 快照: {postsale_return: {active, slots:{order_id:"ORD-001"}}}

回合 2: 用户 "帮我查一下订单 ORD-003"
  → NLU: {action:"new", target_intent:"order_query", slots_update:{order_id:"ORD-003"}}
  → IntentController: 挂起 postsale_return(suspended)，创建 order_query(active)
  → 业务: completed
  → IntentController: 完成 order_query → 自动恢复 postsale_return(active)
  → 持久化 intents 快照: {postsale_return: {active, slots:{order_id:"ORD-001"}}}

回合 3: 助手自动提示 "请选择售后方式..."
  （继续 postsale_return 流程）
```

## 业务层

### 核心抽象

- `IntentHandler`: 意图处理器，内部可自行查询业务数据库补充槽位并执行业务逻辑
- `BusinessContext`: 业务上下文（session_id, user_id, intent, slots）
- `BusinessResult`: 业务执行结果（success, data, error_message），提供三个工厂方法：
  - `BusinessResult.ask_slot(slot_to_fill, options, message)` — 需要用户选择一个槽位值
  - `BusinessResult.completed(message, **extra)` — 业务处理完成
  - `BusinessResult.error(message)` — 业务处理失败
- `OptionItem(label, value, disabled=False)`: 统一选项条目，`ask_slot` 时使用。前端据此渲染按钮列表

### 槽位驱动模式

意图处理器按 required_slots 顺序逐槽位检查，缺失时返回 `ask_slot` 让前端渲染选项按钮，用户点击后回传槽位值，所有槽位齐全后执行并返回 `completed`。

`ask_slot` 返回的统一 data 结构：
```json
{
    "action": "ask_slot",
    "message": "请选择要申请售后的订单",
    "slot_to_fill": "order_id",
    "options": [
        {"label": "ORD-001（已签收）", "value": "ORD-001", "disabled": false}
    ]
}
```

### 电商业务线

```
business/ecommerce/
├── config.py           # 电商数据库配置
├── intents.py          # 意图定义注册
├── handlers/
│   ├── order_query.py
│   └── postsale_return.py
├── models/             # 电商业务 ORM
└── repository/         # 数据访问层
```

## NLG 层

| 场景 | 策略 | 说明 |
|------|------|------|
| 业务操作结果（订单详情等） | `TemplateEngine` (Jinja2) | 模板位于业务线目录 `business/ecommerce/templates/{intent}.j2`，由 Handler 调用并填入 `BusinessResult.message` |
| 槽位追问 | `BusinessResult.ask_slot()` | 固定数据结构 `{ action, message, slot_to_fill, options }`，前端据此渲染选项按钮，无需模板 |
| 闲聊/兜底/unknown | `LLMGenerator` | 自由生成 |
| 转人工 | 硬编码 | 消息简短，直接返回固定文案 |

> **设计原则**：模板归属业务线，模板渲染输出只能作为 `BusinessResult.message` 内容。NLGEngine 不直接调用 TemplateEngine。

## 前端设计

### 路由

| 路由 | 组件 | 说明 |
|------|------|------|
| `/login` | `LoginView` | 输入 user_id（默认 1001），点击进入聊天 |
| `/chat` | `ChatView` | 聊天主界面 |

### 组件树

```
App
├── LoginView
└── ChatView
    ├── SessionSidebar（左侧 ~280px）
    │   ├── 创建新会话按钮
    │   └── SessionList（最近 10 个，按时间倒序）
    └── ChatMain（右侧）
        ├── ChatHeader（会话标题）
        ├── MessageList（可滚动消息区）
        │   └── MessageBubble（用户右侧蓝色，客服左侧灰色）
        └── ChatInput（底部输入框 + 发送按钮）
```

### 状态管理（Pinia）

- `useSessionStore`: userId, sessions[], activeSessionId
- `useChatStore`: messages[], isStreaming, streamingContent

### 通信方式

REST + SSE 流式：发送消息用 POST，接收回复用 SSE（EventSource），前端逐字展示。

## 测试策略

| 层级 | 类型 | 工具 |
|------|------|------|
| 后端单元测试 | 模型验证、纯逻辑 | pytest |
| 后端集成测试 | API + DB | pytest + httpx + AsyncSession |
| DM 层测试 | 状态机逻辑 | pytest |
| 业务层测试 | 意图处理器 | pytest（mock LLM） |
| 前端组件测试 | 组件渲染 | vitest |
| E2E | 全链路 | Playwright |

目标覆盖率：80%+
测试数据库：Docker Compose 启动真实 MySQL

## 错误处理

- API 层统一捕获异常，返回 `{ success: false, error: "..." }`
- NLU 失败 → 降级到 fallback 节点
- 业务处理失败 → 返回业务错误提示
- 未知异常 → 记录 loguru + 返回"系统繁忙"
- 不在错误消息中泄露内部细节
