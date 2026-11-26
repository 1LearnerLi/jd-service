# 多意图支持设计 — 挂起/恢复模式 + 独立槽位管理 + 意图状态持久化

## 概述

将会话中单一 `active_intent` 模式升级为支持多意图并存的挂起/恢复模式。用户在一个会话中可同时处理多个业务意图（如售后申请未完成时查询订单），系统自动挂起未完成的意图，完成后自动恢复。每个意图独立维护自己的槽位，不再共享全局槽位字典。

## 核心决策

| 决策项 | 选择 |
|--------|------|
| 意图切换行为 | **挂起/恢复**：新意图到达时挂起当前意图，保留已填槽位 |
| 恢复触发方式 | **自动恢复**：完成当前意图后自动弹出最近挂起的意图 |
| 槽位存储 | **嵌套在意图内**：每个 `IntentContext` 自带独立 `slots` 字段 |
| 意图状态 | `active` / `suspended` / `completed` / `cancelled` |
| NLU 输出 | **增量式**：输出 action + target_intent + slots_update |
| 架构方案 | **IntentController**：纯逻辑类封装意图生命周期，图结构不变 |
| 持久化方式 | Session 表新增 `intents_json` JSON 字段 |

---

## 1. DialogState 变更 (`app/dm/state.py`)

### 1.1 IntentContext 扩展

```python
class IntentContext(TypedDict):
    """意图上下文 — 会话中产生的每个意图的完整状态"""
    name: str                       # 意图名，如 "order_query"
    confidence: float               # 识别置信度 0-1
    status: str                     # "active" | "suspended" | "completed" | "cancelled"
    slots: dict[str, object]        # 该意图独立槽位（不再共享全局 slots）
    required_slots: list[str]       # 必填槽位名列表
    optional_slots: list[str]       # 可选槽位名列表
```

### 1.2 DialogState 调整

```python
class DialogState(TypedDict):
    session_id: str
    user_id: str
    user_input: str
    messages: list[dict[str, str]]
    all_intents: list[dict]              # 新增：系统+业务线全部意图定义
    intents: dict[str, IntentContext]    # 扩展：含 status + 独立 slots
    active_intent: str                   # 当前活跃意图名（冗余方便路由/节点使用）
    business_result: object
    final_response: str
    should_fallback: bool
    # 移除: slots, missing_slots
```

**变更点：**

- `all_intents` 新增 — 从 `IntentRegistry` 构建，包含所有可用意图的名称、描述、必填/可选槽位列表，供 NLU prompt 构造使用
- `intents` 的 value 从简单 `IntentContext` 扩展为含 `status` + 独立 `slots`
- `slots` 移除 — 槽位跟随意图，不再全局扁平存储
- `missing_slots` 移除 — 由 `IntentController` 按需从活跃意图的 `required_slots - slots.keys()` 动态计算

---

## 2. IntentController 设计 (`app/dm/intent_controller.py`)

新增 `app/dm/intent_controller.py`，纯逻辑类，不持有状态。所有操作基于传入的 state 返回更新字典。

### 2.1 接口

```python
class IntentController:
    """意图生命周期管理器 — 纯逻辑，不持有状态"""

    # ── 核心决策 ──────────────────────────────
    @staticmethod
    def decide(state: dict, nlu_result: NLUResult) -> dict:
        """根据 NLU 输出更新意图容器和 active_intent
        返回可合并到 state 的更新字典
        """

    # ── 查询 ──────────────────────────────────
    @staticmethod
    def get_active_context(state: dict) -> BusinessContext:
        """从活跃意图构建业务节点所需的 BusinessContext"""

    @staticmethod
    def get_active_slots(state: dict) -> dict[str, object]:
        """快捷：获取当前活跃意图的槽位"""

    @staticmethod
    def get_missing_slots(state: dict) -> list[str]:
        """动态计算：活跃意图 required_slots - 已填 slots"""

    @staticmethod
    def find_active(intents: dict) -> str:
        """从意图容器中找到 status="active" 的意图名，无则返回 "" """

    # ── 序列化 ────────────────────────────────
    @staticmethod
    def to_snapshot(intents: dict) -> dict:
        """将意图容器序列化为纯 dict，用于 Session.intents_json 持久化"""

    @staticmethod
    def from_snapshot(data: dict) -> dict[str, IntentContext]:
        """从 DB 快照恢复意图容器"""

    # ── 辅助 ──────────────────────────────────
    @staticmethod
    def build_all_intents() -> list[dict]:
        """从 IntentRegistry 构建 all_intents 列表，每个条目含：
        {name, description, required_slots: [{name, description}],
         optional_slots: [{name, description}]}
        """
```

### 2.2 decide() 核心逻辑

```python
@staticmethod
def decide(state: dict, nlu_result: NLUResult) -> dict:
    action = nlu_result.action
    target = nlu_result.target_intent
    intents = dict(state.get("intents", {}))

    if action == "continue":
        # 合并槽位到活跃意图（增量）
        _merge_slots(intents, target, nlu_result.slots_update)

    elif action == "new":
        # 挂起当前活跃意图
        _suspend_active(intents)
        # 创建新意图并设为 active
        intents[target] = IntentController._create_intent(target, nlu_result)
        active_intent = target

    elif action == "switch":
        # 挂起当前活跃意图
        _suspend_active(intents)
        # 激活目标意图（目标必须已存在于容器中）
        if target in intents:
            intents[target]["status"] = "active"
        active_intent = target

    elif action == "cancel":
        _set_status(intents, target, "cancelled")
        # 自动恢复最近的挂起意图
        active_intent = _restore_suspended(intents)

    elif action == "complete":
        _set_status(intents, target, "completed")
        active_intent = _restore_suspended(intents)

    return {"intents": intents, "active_intent": active_intent}
```

### 2.3 关键业务规则

1. **唯一 active**：同一时刻最多一个意图处于 `active` 状态
2. **自动恢复顺序**：complete/cancel 后，如有挂起意图，按 **最近挂起** 的顺序（LIFO/栈式）恢复
3. **同名去重**：同个意图名在容器中只能出现一次。如果 NLU 返回 `action="new"` 且意图名已存在：
   - 如果旧意图状态为 `completed` 或 `cancelled` → 覆盖创建新意图
   - 否则 → 降级为 `action="switch"`，直接激活
4. **continue 防御**：如果 `action="continue"` 但 `target_intent` 与当前活跃意图不匹配，降级为 `action="new"`（防止槽位写入错误意图）
5. **空闲状态**：无活跃意图时，`active_intent = ""`，路由走 fallback，等待 NLU 识别新意图
6. **已完成的意图清理**：`completed` 和 `cancelled` 的意图在序列化到 snapshot 时不保存，以实现"容器中删除"的效果

---

## 3. NLU 层变更

### 3.1 NLUResult 模型扩展 (`app/nlu/models.py`)

```python
class NLUResult(BaseModel):
    """NLU 层输出 — 增量式意图变化

    只描述"本轮发生了什么变化"，不输出整个会话的意图状态。
    """
    action: str = Field(
        default="continue",
        description="变化类型：continue | switch | new | cancel | complete"
    )
    target_intent: str = Field(
        default="",
        description="目标意图名"
    )
    confidence: float = Field(default=0.0, description="置信度 0-1")
    slots_update: dict[str, object] = Field(
        default_factory=dict,
        description="本次新增/更新的槽位（增量，仅对目标意图有效）"
    )
```

**字段移除**：`intent`、`slots`、`missing_slots` 不再适用，由新字段替代。

### 3.2 分类器 Prompt 变更 (`app/nlu/classifier.py`)

#### 3.2a classify() 签名

```python
async def classify(
    self,
    user_input: str,
    all_intents: list[dict] | None = None,       # 新增
    session_intents: dict[str, IntentContext] | None = None,  # 新增
    active_intent: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> NLUResult:
```

**移除** `current_slots` 参数，槽位信息已包含在 `session_intents` 各意图的 `slots` 字段中。

#### 3.2b 系统 Prompt 构造

系统 prompt 输入分为三部分：

1. **所有可用意图**（从 `all_intents` 构造）— "你可以识别以下意图：..."
2. **会话中的意图状态**（从 `session_intents` 构造）— "当前会话中已存在以下意图：..."
   - 对于每个意图，输出：名称、状态、已填槽位、缺失槽位
3. **输出格式与规则**

核心规则：
```
1. 如果用户输入是在当前活跃意图的上下文中填槽位 → action="continue"
2. 如果用户表达了新意图需求，且与当前活跃意图不同 → action="new"（首次创建）或 action="switch"（切回已有的 suspended 意图）
3. 如果用户说"取消"、"不办了"、"算了" → action="cancel"
4. 如果用户输入无法匹配任何已知意图 → target_intent="unknown"，action="new"
5. 如果用户要求转人工 → target_intent="transfer_human"，action="new"
6. 槽位值识别（保留现有规则）：如果用户输入是单个值（如订单号），且当前有活跃意图的缺失槽位，则识别为缺失槽位的填充值，action="continue"
7. slots_update 只填本次提取到的值，不重复已填槽位
```

#### 3.2c 用户 Prompt 构造

```
对话历史:
[user]: xxx
[assistant]: xxx

当前活跃意图: order_query（状态: active，已填槽位: {}，缺失槽位: [order_id]）

会话中其他意图:
- postsale_return（状态: suspended，已填槽位: {order_id: "ORD-001"}）

用户输入: ORD-003
```

#### 3.2d structured_output 调整

`self.llm.with_structured_output(schema=NLUResult, method="json_mode")` 自动适配新的 `NLUResult` 模型。

### 3.3 NLU 节点变更 (`app/dm/nodes/nlu_node.py`)

```python
async def nlu_node(state: dict) -> dict:
    user_input = state.get("user_input", "")

    classifier = get_classifier()
    result = await classifier.classify(
        user_input=user_input,
        all_intents=state.get("all_intents", []),
        session_intents=state.get("intents", {}),
        active_intent=state.get("active_intent", ""),
        messages=state.get("messages", []),
    )

    # 委托 Controller 处理意图生命周期
    update = IntentController.decide(state, result)

    logger.info(
        f"NLU 节点输出: action={result.action}, "
        f"target={result.target_intent}, "
        f"confidence={result.confidence}, "
        f"slots_update={result.slots_update}"
    )

    # 判断是否兜底
    update["should_fallback"] = (
        result.target_intent in ("unknown", "transfer_human")
    )

    return update
```

---

## 4. DM 图 & 节点变更

### 4.1 图结构 (`app/dm/graph.py`)

图结构**保持不变**：

```
entry → nlu → [条件路由]
  ├─ 平台意图 / 无活跃意图 → fallback → response → END
  └─ 业务意图 → business → response → END
```

### 4.2 路由逻辑 (`app/dm/router.py`)

```python
def is_platform_intent(state: dict) -> bool:
    active = state.get("active_intent", "")
    # 无活跃意图时也走 fallback
    if not active:
        return True
    return active in ("unknown", "transfer_human")
```

### 4.3 业务节点 (`app/dm/nodes/business_node.py`)

```python
async def business_node(state: dict) -> dict:
    active_intent = state.get("active_intent", "")

    handler_cls = IntentRegistry.get_handler(active_intent)
    if handler_cls is None:
        logger.warning(f"未找到意图处理器: {active_intent}")
        return {"business_result": BusinessResult.error("该功能暂未开放")}

    # 通过 Controller 构建上下文，包含该意图的独立槽位
    ctx = IntentController.get_active_context(state)

    handler = handler_cls()
    result = await handler.handle(ctx)

    # 业务完成时标记意图为 completed，Controller 自动恢复挂起意图
    if result.success and isinstance(result.data, dict):
        if result.data.get("action") == "completed":
            intent_update = IntentController.decide(
                state,
                NLUResult(action="complete", target_intent=active_intent),
            )
            return {**intent_update, "business_result": result}

    return {"business_result": result}
```

### 4.4 回复节点 (`app/dm/nodes/response_node.py`)

无需变更。`response_node` 通过 `business_result.message` 获取回复文本，不直接依赖 `slots`。

---

## 5. 数据库 & 会话层变更

### 5.1 Session 表 (`app/session/models.py`)

```python
class Session(Base):
    # ... 现有字段保持不变 ...
    intents_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="会话意图状态快照: {intent_name: {status, slots, confidence, ...}}"
    )
```

**Alembic 迁移**：自动生成 `ALTER TABLE sessions ADD COLUMN intents_json JSON NULL`。

### 5.2 SessionService 扩展 (`app/session/service.py`)

```python
@staticmethod
async def save_intents_snapshot(
    db: AsyncSession, session_id: str, intents: dict
) -> None:
    """将意图容器快照存入 Session.intents_json"""
    snapshot = IntentController.to_snapshot(intents)
    await db.execute(
        update(Session)
        .where(Session.id == session_id)
        .values(intents_json=snapshot)
    )
    await db.commit()

@staticmethod
async def load_intents_snapshot(
    db: AsyncSession, session_id: str
) -> dict | None:
    """从 Session.intents_json 加载意图容器快照"""
    session = await SessionService.get_session(db, session_id)
    if session and session.intents_json:
        return IntentController.from_snapshot(session.intents_json)
    return None
```

### 5.3 Chat API (`app/api/v1/chat.py`)

**请求入口变更**：

```python
# 从 DB 恢复意图状态
saved_intents = await SessionService.load_intents_snapshot(db, session_id)
initial_intents = saved_intents if saved_intents else {}

initial_state = {
    # ... 其他字段不变 ...
    "all_intents": IntentController.build_all_intents(),  # 新增
    "intents": initial_intents,                            # 从 DB 恢复
    "active_intent": IntentController.find_active(initial_intents),  # 由 Controller 确定
    # 移除: "slots", "missing_slots"
}
```

**请求出口变更**：

```python
final_state = await _dialog_graph.ainvoke(initial_state)

# 新增：持久化意图状态
await SessionService.save_intents_snapshot(
    db, session_id, final_state.get("intents", {})
)

reply = final_state.get("final_response", "抱歉，我不知道该如何回答。")
active_intent = final_state.get("active_intent", "")
# slots 不再需要单独保存，意图状态已在 intents_json 中
```

### 5.4 Message 表

`Message` 表的 `intent` 和 `slots_json` 字段**保留不变**，继续记录每条消息对应的意图标签和该轮槽位更新，仅用于展示/日志/历史记录。不再作为恢复意图状态的唯一来源。

---

## 6. 数据流示例

### 场景：售后处理中被订单查询打断

```
回合 1: 用户 "我要申请退货退款 ORD-001"
  → NLU: {action:"new", target_intent:"postsale_return", slots_update:{"order_id":"ORD-001"}}
  → Controller: 创建 postsale_return(active)，slots={order_id:"ORD-001"}
  → 业务: ask_slot(postsale_type)
  → intents 快照: {postsale_return: {active, slots:{order_id:"ORD-001"}}}

回合 2: 用户 "帮我查一下订单 ORD-003"
  → NLU: {action:"new", target_intent:"order_query", slots_update:{"order_id":"ORD-003"}}
  → Controller: 挂起 postsale_return(suspended)，创建 order_query(active)
  → 业务: completed("订单 ORD-003 详情...")
  → Controller: 完成 order_query → 从容器移除，自动恢复 postsale_return(active)
  → intents 快照: {postsale_return: {active, slots:{order_id:"ORD-001"}}}

回合 3: 助手自动提示 "您之前的售后申请还没完成，请选择售后方式：仅退款 / 退货退款"
  （继续 postsale_return 流程）
```

---

## 7. 文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/dm/state.py` | **修改** | IntentContext 扩展，DialogState 增删字段 |
| `app/dm/intent_controller.py` | **新增** | 意图生命周期管理器 |
| `app/nlu/models.py` | **修改** | NLUResult 改为增量式输出 |
| `app/nlu/classifier.py` | **修改** | Prompt 重构，签名变更 |
| `app/dm/nodes/nlu_node.py` | **修改** | 委托 Controller，传递 all_intents + session_intents |
| `app/dm/nodes/business_node.py` | **修改** | 通过 Controller 获取上下文，完成后标记意图 |
| `app/dm/graph.py` | **可能不改** | 图结构保持不变 |
| `app/dm/router.py` | **修改** | 无活跃意图时走 fallback |
| `app/session/models.py` | **修改** | Session 新增 intents_json 字段 |
| `app/session/service.py` | **修改** | 新增 save/load_intents_snapshot 方法 |
| `app/api/v1/chat.py` | **修改** | initial_state 构造和意图持久化 |
| Alembic 迁移 | **新增** | sessions 表加 intents_json 列 |
| 相关测试文件 | **修改/新增** | Controller 单元测试，NLU/API 集成测试更新 |

---

## 8. 风险与注意事项

1. **LLM 输出可靠性**：增量式 `action` + `slots_update` 比完整意图状态输出更可靠，但仍需做好降级处理（LLM 返回异常时降级为 `action="continue"` 或 `unknown`）
2. **栈式恢复行为**：LIFO 恢复顺序可能不是所有场景下最优，如果后续发现需要按优先级恢复，可在 Controller 中扩展
3. **槽位冲突**：不同意图可能有同名槽位（如 `order_id`），独立槽位设计已解决此问题；但 LLM prompt 需清晰展示哪个槽位属于哪个意图
4. **DB 快照一致性**：每次回合结束后保存快照，如果图执行过程中异常退出，快照不会更新（安全：不会产生脏数据）
5. **向后兼容**：`intents_json` 字段对存量 session 为 NULL，`load_intents_snapshot` 返回 None 时使用空字典，不影响现有会话
