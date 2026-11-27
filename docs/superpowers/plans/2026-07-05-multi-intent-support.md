# 多意图支持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将单意图模式升级为多意图挂起/恢复模式，每个意图独立维护槽位，状态持久化到数据库。

**Architecture:** 新增 IntentController 纯逻辑类封装意图生命周期管理（创建/挂起/恢复/取消/完成）；DialogState 中的 slots 字段移除，槽位嵌套在 IntentContext 内；NLU 输出改为增量式（action + target_intent + slots_update）；Session 表新增 intents_json 字段持久化意图快照。

**Tech Stack:** Python 3.14+, LangGraph, Pydantic v2, SQLAlchemy 2.x 异步, Alembic, pytest + pytest-asyncio

---

## Global Constraints

- Python 环境使用 **uv** 管理
- 平台库建表通过 **Alembic** 管理
- 所有代码使用异步（`async def`）
- 日志使用 `loguru`
- 变量/文件名使用英文，注释使用中文
- 所有层间通信使用 Pydantic 模型
- 不修改 DM 图结构（不新增/删除节点）
- 已完成/已取消意图在序列化到 snapshot 时不保存
- 向后兼容：`intents_json` 为 NULL 的存量 session 使用空字典

---

### Task 1: 更新 DialogState 和 NLUResult 数据模型

**Files:**
- Modify: `app/dm/state.py`
- Modify: `app/nlu/models.py`

**Interfaces:**
- Produces:
  - `IntentContext(TypedDict)` — 新增 `status: str`, `slots: dict[str, object]` 字段
  - `DialogState(TypedDict)` — 新增 `all_intents: list[dict]`，移除 `slots`, `missing_slots`
  - `NLUResult(BaseModel)` — 字段重组为 `action`, `target_intent`, `confidence`, `slots_update`

- [ ] **Step 1a: 扩展 IntentContext**

```python
# app/dm/state.py — 替换 IntentContext
class IntentContext(TypedDict):
    """意图上下文 — 会话中产生的每个意图的完整状态"""
    name: str                       # 意图名，如 "order_query"
    confidence: float               # 识别置信度 0-1
    status: str                     # "active" | "suspended" | "completed" | "cancelled"
    slots: dict[str, object]        # 该意图独立槽位
    required_slots: list[str]       # 必填槽位名列表
    optional_slots: list[str]       # 可选槽位名列表
```

- [ ] **Step 1b: 调整 DialogState**

```python
# app/dm/state.py — 替换 DialogState
class DialogState(TypedDict):
    """对话状态"""
    session_id: str
    user_id: str
    user_input: str
    messages: list[dict[str, str]]
    all_intents: list[dict]              # 新增：系统+业务线全部意图定义
    intents: dict[str, IntentContext]    # 扩展：含 status + 独立 slots
    active_intent: str
    business_result: object
    final_response: str
    should_fallback: bool
```

- [ ] **Step 1c: 重写 NLUResult**

```python
# app/nlu/models.py — 替换 NLUResult 类
class NLUResult(BaseModel):
    """NLU 层输出 — 增量式意图变化"""
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
        description="本次新增/更新的槽位（增量）"
    )
```

- [ ] **Step 1d: 运行现有测试确认破坏点**

```bash
uv run pytest tests/test_dm/test_state_router.py tests/test_nlu/test_models.py -v 2>&1 | tail -20
```

Expected: 多个 FAIL（因为旧代码引用 `slots`、`missing_slots`、`intent` 等已移除字段）

- [ ] **Step 1e: 提交**

```bash
git add app/dm/state.py app/nlu/models.py
git commit -m "refactor: 重构 DialogState 和 NLUResult 支持多意图 — 槽位嵌套在意图内，NLU 输出改为增量式"
```

---

### Task 2: 实现 IntentController

**Files:**
- Create: `app/dm/intent_controller.py`
- Create: `tests/test_dm/test_intent_controller.py`

**Interfaces:**
- Consumes: `DialogState` (Task 1), `NLUResult` (Task 1), `BusinessContext` (existing), `IntentRegistry` (existing)
- Produces: `IntentController.decide()`, `IntentController.get_active_context()`, `IntentController.get_active_slots()`, `IntentController.get_missing_slots()`, `IntentController.find_active()`, `IntentController.to_snapshot()`, `IntentController.from_snapshot()`, `IntentController.build_all_intents()`

- [ ] **Step 2a: 编写 IntentController 测试（RED）**

```python
# tests/test_dm/test_intent_controller.py
import pytest
from app.dm.intent_controller import IntentController
from app.nlu.models import NLUResult


class TestIntentControllerDecide:
    """IntentController.decide() 测试"""

    def test_decide_new_creates_intent_and_suspends_active(self):
        """验证 new action：创建新意图 + 挂起当前活跃意图"""
        state = {
            "intents": {
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                }
            },
            "active_intent": "postsale_return",
        }

        result = NLUResult(
            action="new",
            target_intent="order_query",
            confidence=0.95,
            slots_update={"order_id": "ORD-003"},
        )

        update = IntentController.decide(state, result)

        # 旧意图被挂起
        assert update["intents"]["postsale_return"]["status"] == "suspended"
        # 新意图创建并激活
        assert update["intents"]["order_query"]["status"] == "active"
        assert update["intents"]["order_query"]["slots"] == {"order_id": "ORD-003"}
        assert update["active_intent"] == "order_query"

    def test_decide_continue_merges_slots_to_active(self):
        """验证 continue action：槽位合并到活跃意图"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
        }

        result = NLUResult(
            action="continue",
            target_intent="order_query",
            confidence=0.85,
            slots_update={"order_id": "ORD-005"},
        )

        update = IntentController.decide(state, result)

        assert update["intents"]["order_query"]["status"] == "active"
        assert update["intents"]["order_query"]["slots"] == {"order_id": "ORD-005"}
        assert update["active_intent"] == "order_query"

    def test_decide_switch_suspends_active_and_activates_target(self):
        """验证 switch action：挂起当前，激活目标"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-003"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                },
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "suspended",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                },
            },
            "active_intent": "order_query",
        }

        result = NLUResult(
            action="switch",
            target_intent="postsale_return",
            confidence=0.88,
            slots_update={},
        )

        update = IntentController.decide(state, result)

        assert update["intents"]["order_query"]["status"] == "suspended"
        assert update["intents"]["postsale_return"]["status"] == "active"
        assert update["active_intent"] == "postsale_return"

    def test_decide_cancel_marks_cancelled_and_restores_suspended(self):
        """验证 cancel action：标记 cancelled + 自动恢复最近挂起的意图"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-003"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                },
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "suspended",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                },
            },
            "active_intent": "order_query",
        }

        result = NLUResult(
            action="cancel",
            target_intent="order_query",
            confidence=0.9,
            slots_update={},
        )

        update = IntentController.decide(state, result)

        assert update["intents"]["order_query"]["status"] == "cancelled"
        assert update["intents"]["postsale_return"]["status"] == "active"
        assert update["active_intent"] == "postsale_return"

    def test_decide_complete_marks_completed_and_restores_suspended(self):
        """验证 complete action：标记 completed + 自动恢复最近挂起的意图"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.95,
                    "status": "active",
                    "slots": {"order_id": "ORD-003"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                },
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "suspended",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                },
            },
            "active_intent": "order_query",
        }

        result = NLUResult(
            action="complete",
            target_intent="order_query",
            confidence=1.0,
            slots_update={},
        )

        update = IntentController.decide(state, result)

        assert update["intents"]["order_query"]["status"] == "completed"
        assert update["intents"]["postsale_return"]["status"] == "active"
        assert update["active_intent"] == "postsale_return"

    def test_decide_complete_with_no_suspended_returns_empty(self):
        """验证 complete 后无挂起意图时 active_intent 为空"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.95,
                    "status": "active",
                    "slots": {"order_id": "ORD-003"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
        }

        result = NLUResult(
            action="complete",
            target_intent="order_query",
            confidence=1.0,
            slots_update={},
        )

        update = IntentController.decide(state, result)

        assert update["intents"]["order_query"]["status"] == "completed"
        assert update["active_intent"] == ""


class TestIntentControllerQuery:
    """IntentController 查询方法测试"""

    def test_get_active_context_returns_correct_business_context(self):
        """验证 get_active_context 从活跃意图构建 BusinessContext"""
        from app.business.base import BusinessContext

        state = {
            "session_id": "sess-abc",
            "user_id": "user-xyz",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
        }

        ctx = IntentController.get_active_context(state)

        assert isinstance(ctx, BusinessContext)
        assert ctx.session_id == "sess-abc"
        assert ctx.user_id == "user-xyz"
        assert ctx.intent == "order_query"
        assert ctx.slots == {"order_id": "ORD-001"}

    def test_get_active_context_no_active_intent(self):
        """验证无活跃意图时返回空槽位的 BusinessContext"""
        from app.business.base import BusinessContext

        state = {
            "session_id": "sess-abc",
            "user_id": "user-xyz",
            "intents": {},
            "active_intent": "",
        }

        ctx = IntentController.get_active_context(state)

        assert ctx.intent == ""
        assert ctx.slots == {}

    def test_get_active_slots(self):
        """验证获取活跃意图槽位"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001", "extra": "val"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
        }

        slots = IntentController.get_active_slots(state)
        assert slots == {"order_id": "ORD-001", "extra": "val"}

    def test_get_active_slots_no_active(self):
        """验证无活跃意图时返回空字典"""
        assert IntentController.get_active_slots({"intents": {}, "active_intent": ""}) == {}

    def test_get_missing_slots(self):
        """验证 missing_slots 动态计算"""
        state = {
            "intents": {
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                }
            },
            "active_intent": "postsale_return",
        }

        missing = IntentController.get_missing_slots(state)
        assert missing == ["postsale_type", "postsale_reason"]

    def test_get_missing_slots_none_missing(self):
        """验证所有槽位已填时返回空列表"""
        state = {
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
        }

        assert IntentController.get_missing_slots(state) == []

    def test_find_active(self):
        """验证 find_active 找到正确的活跃意图"""
        intents = {
            "order_query": {"name": "order_query", "status": "suspended", "slots": {}},
            "postsale_return": {"name": "postsale_return", "status": "active", "slots": {}},
        }
        assert IntentController.find_active(intents) == "postsale_return"

    def test_find_active_none(self):
        """验证无活跃意图时返回空字符串"""
        intents = {
            "order_query": {"name": "order_query", "status": "suspended", "slots": {}},
        }
        assert IntentController.find_active(intents) == ""

    def test_find_active_empty(self):
        """验证空容器返回空字符串"""
        assert IntentController.find_active({}) == ""


class TestIntentControllerSnapshot:
    """IntentController 序列化/反序列化测试"""

    def test_to_snapshot_excludes_completed_and_cancelled(self):
        """验证 to_snapshot 不保存 completed 和 cancelled 的意图"""
        intents = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {"order_id": "ORD-001"},
                "required_slots": ["order_id"],
                "optional_slots": [],
            },
            "postsale_return": {
                "name": "postsale_return",
                "confidence": 0.85,
                "status": "completed",
                "slots": {"order_id": "ORD-002", "postsale_type": "refund_only", "postsale_reason": "不想要了"},
                "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                "optional_slots": [],
            },
            "product_inquiry": {
                "name": "product_inquiry",
                "confidence": 0.7,
                "status": "cancelled",
                "slots": {},
                "required_slots": ["query"],
                "optional_slots": [],
            },
            "transfer_human": {
                "name": "transfer_human",
                "confidence": 0.9,
                "status": "suspended",
                "slots": {},
                "required_slots": [],
                "optional_slots": [],
            },
        }

        snapshot = IntentController.to_snapshot(intents)

        assert "order_query" in snapshot
        assert "transfer_human" in snapshot
        assert "postsale_return" not in snapshot
        assert "product_inquiry" not in snapshot

    def test_from_snapshot_restores_intents(self):
        """验证 from_snapshot 正确恢复意图容器"""
        data = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {"order_id": "ORD-001"},
                "required_slots": ["order_id"],
                "optional_slots": [],
            },
            "postsale_return": {
                "name": "postsale_return",
                "confidence": 0.85,
                "status": "suspended",
                "slots": {"order_id": "ORD-002"},
                "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                "optional_slots": [],
            },
        }

        restored = IntentController.from_snapshot(data)

        assert "order_query" in restored
        assert restored["order_query"]["status"] == "active"
        assert restored["order_query"]["slots"] == {"order_id": "ORD-001"}
        assert restored["postsale_return"]["status"] == "suspended"

    def test_from_snapshot_handles_none(self):
        """验证 from_snapshot 对 None 返回空字典"""
        assert IntentController.from_snapshot(None) == {}

    def test_roundtrip(self):
        """验证序列化后反序列化保持数据一致"""
        original = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {"order_id": "ORD-001"},
                "required_slots": ["order_id"],
                "optional_slots": [],
            }
        }

        snapshot = IntentController.to_snapshot(original)
        restored = IntentController.from_snapshot(snapshot)

        assert restored == original


class TestIntentControllerBuildAllIntents:
    """build_all_intents 测试"""

    def setup_method(self):
        from app.nlu.registry import IntentRegistry
        IntentRegistry.clear()

    def test_build_all_intents_includes_platform_intents(self):
        """验证 all_intents 包含平台意图"""
        result = IntentController.build_all_intents()
        names = [i["name"] for i in result]
        assert "unknown" in names
        assert "transfer_human" in names

    def test_build_all_intents_includes_registered_business_intents(self):
        """验证 all_intents 包含已注册的业务意图"""
        from app.nlu.registry import IntentRegistry
        from app.nlu.models import IntentDefinition, SlotDef

        IntentRegistry.register_business("ecommerce", [
            IntentDefinition(
                name="order_query",
                description="订单查询",
                required_slots=[SlotDef(name="order_id", description="订单号")],
            ),
        ])

        result = IntentController.build_all_intents()
        names = [i["name"] for i in result]
        assert "order_query" in names

        # 验证结构
        order_query = next(i for i in result if i["name"] == "order_query")
        assert order_query["description"] == "订单查询"
        assert len(order_query["required_slots"]) == 1
        assert order_query["required_slots"][0]["name"] == "order_id"

    def test_build_all_intents_has_required_structure(self):
        """验证 all_intents 每个条目都有正确的结构"""
        result = IntentController.build_all_intents()
        for item in result:
            assert "name" in item
            assert "description" in item
            assert "required_slots" in item
            assert "optional_slots" in item
            for slot in item["required_slots"]:
                assert "name" in slot
                assert "description" in slot
```

- [ ] **Step 2b: 运行测试确认失败**

```bash
uv run pytest tests/test_dm/test_intent_controller.py -v 2>&1 | tail -10
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.dm.intent_controller'`

- [ ] **Step 2c: 实现 IntentController（GREEN）**

```python
# app/dm/intent_controller.py
"""意图生命周期管理器 — 封装意图的创建、挂起、恢复、取消、完成逻辑"""
from loguru import logger

from app.business.base import BusinessContext
from app.nlu.registry import IntentRegistry


class IntentController:
    """意图生命周期管理器

    纯逻辑类，不持有状态。所有操作基于传入的 state 返回更新字典。
    """

    # ── 核心决策 ──────────────────────────────────────────

    @staticmethod
    def decide(state: dict, nlu_result) -> dict:
        """根据 NLU 输出更新意图容器和 active_intent

        Args:
            state: 当前 DialogState（部分字段）
            nlu_result: NLUResult，含 action / target_intent / slots_update

        Returns:
            包含 intents 和 active_intent 的更新字典
        """
        action = nlu_result.action
        target = nlu_result.target_intent
        intents = dict(state.get("intents", {}))
        active_intent = state.get("active_intent", "")

        if action == "continue":
            # 防御：如果 target 与 active_intent 不匹配，降级为 new
            if active_intent and target and target != active_intent:
                logger.warning(
                    f"continue 目标 {target} 与活跃意图 {active_intent} 不匹配，降级为 new"
                )
                action = "new"

        if action == "continue":
            if target in intents:
                _merge_slots(intents, target, nlu_result.slots_update)
            active_intent = target

        elif action == "new":
            # 同名去重
            if target in intents:
                old_status = intents[target].get("status", "")
                if old_status in ("completed", "cancelled"):
                    # 覆盖旧意图
                    intents[target] = _create_intent(target, nlu_result)
                else:
                    # 已存在活跃/挂起的同名意图 → 直接激活
                    intents[target]["status"] = "active"
            else:
                # 挂起当前活跃意图
                _suspend_active(intents)
                # 创建新意图
                intents[target] = _create_intent(target, nlu_result)
            active_intent = target

        elif action == "switch":
            # 挂起当前活跃意图
            _suspend_active(intents)
            # 激活目标意图
            if target in intents:
                intents[target]["status"] = "active"
            else:
                # 目标不存在 → 创建
                intents[target] = _create_intent(target, nlu_result)
            active_intent = target

        elif action == "cancel":
            if target in intents:
                intents[target]["status"] = "cancelled"
            active_intent = _restore_suspended(intents)

        elif action == "complete":
            if target in intents:
                intents[target]["status"] = "completed"
            active_intent = _restore_suspended(intents)

        return {"intents": intents, "active_intent": active_intent}

    # ── 查询 ──────────────────────────────────────────────

    @staticmethod
    def get_active_context(state: dict) -> BusinessContext:
        """从活跃意图构建业务节点所需的 BusinessContext"""
        active_intent = state.get("active_intent", "")
        intents = state.get("intents", {})
        slots = {}

        if active_intent and active_intent in intents:
            slots = intents[active_intent].get("slots", {})

        return BusinessContext(
            session_id=state.get("session_id", ""),
            user_id=state.get("user_id", ""),
            intent=active_intent,
            slots=slots,
        )

    @staticmethod
    def get_active_slots(state: dict) -> dict[str, object]:
        """获取当前活跃意图的槽位"""
        active_intent = state.get("active_intent", "")
        intents = state.get("intents", {})
        if active_intent and active_intent in intents:
            return dict(intents[active_intent].get("slots", {}))
        return {}

    @staticmethod
    def get_missing_slots(state: dict) -> list[str]:
        """动态计算活跃意图的缺失必填槽位"""
        active_intent = state.get("active_intent", "")
        intents = state.get("intents", {})
        if not active_intent or active_intent not in intents:
            return []
        intent_ctx = intents[active_intent]
        required = intent_ctx.get("required_slots", [])
        filled = intent_ctx.get("slots", {}).keys()
        return [s for s in required if s not in filled]

    @staticmethod
    def find_active(intents: dict) -> str:
        """从意图容器中找到 status="active" 的意图名，无则返回 "" """
        for name, ctx in intents.items():
            if ctx.get("status") == "active":
                return name
        return ""

    # ── 序列化 ────────────────────────────────────────────

    @staticmethod
    def to_snapshot(intents: dict) -> dict:
        """将意图容器序列化为纯 dict

        不保存 completed 和 cancelled 的意图（从容器中删除的效果）。
        """
        snapshot = {}
        for name, ctx in intents.items():
            status = ctx.get("status", "")
            if status in ("completed", "cancelled"):
                continue
            snapshot[name] = dict(ctx)
        return snapshot

    @staticmethod
    def from_snapshot(data: dict | None) -> dict[str, dict]:
        """从 DB 快照恢复意图容器"""
        if not data:
            return {}
        result = {}
        for name, ctx in data.items():
            result[name] = {
                "name": ctx.get("name", name),
                "confidence": ctx.get("confidence", 0.0),
                "status": ctx.get("status", "active"),
                "slots": dict(ctx.get("slots", {})),
                "required_slots": list(ctx.get("required_slots", [])),
                "optional_slots": list(ctx.get("optional_slots", [])),
            }
        return result

    # ── 辅助 ──────────────────────────────────────────────

    @staticmethod
    def build_all_intents() -> list[dict]:
        """从 IntentRegistry 构建 all_intents 列表

        每个条目: {name, description, required_slots: [{name, description}],
                    optional_slots: [{name, description}]}
        """
        intents = IntentRegistry.get_all_intents()
        result = []
        for intent in intents:
            result.append({
                "name": intent.name,
                "description": intent.description,
                "required_slots": [
                    {"name": s.name, "description": s.description}
                    for s in intent.required_slots
                ],
                "optional_slots": [
                    {"name": s.name, "description": s.description}
                    for s in intent.optional_slots
                ],
            })
        return result


# ── 模块级辅助函数 ──────────────────────────────────────────

def _merge_slots(intents: dict, target: str, slots_update: dict[str, object]) -> None:
    """将增量槽位合并到目标意图的 slots 中"""
    if target in intents and slots_update:
        existing = dict(intents[target].get("slots", {}))
        existing.update(slots_update)
        intents[target]["slots"] = existing


def _suspend_active(intents: dict) -> None:
    """将所有 active 状态的意图改为 suspended"""
    for ctx in intents.values():
        if ctx.get("status") == "active":
            ctx["status"] = "suspended"


def _create_intent(name: str, nlu_result) -> dict:
    """从 IntentRegistry 获取意图定义，创建新的 IntentContext"""
    intent_def = IntentRegistry.get_intent_by_name(name)
    required_slots = []
    optional_slots = []
    if intent_def:
        required_slots = [s.name for s in intent_def.required_slots]
        optional_slots = [s.name for s in intent_def.optional_slots]

    return {
        "name": name,
        "confidence": nlu_result.confidence,
        "status": "active",
        "slots": dict(nlu_result.slots_update),
        "required_slots": required_slots,
        "optional_slots": optional_slots,
    }


def _restore_suspended(intents: dict) -> str:
    """恢复最近挂起的意图（LIFO），返回恢复后的 active 意图名

    通过找出所有 suspended 意图，按它们在容器中的出现顺序（即创建顺序），
    取最后一个作为"最近挂起"的意图来恢复。
    由于 Python 3.7+ dict 保持插入顺序，suspended 列表中最后的元素即为"最近挂起"。
    """
    suspended_names = [
        name for name, ctx in intents.items()
        if ctx.get("status") == "suspended"
    ]
    if suspended_names:
        # 取最近挂起的（最后出现的）
        target = suspended_names[-1]
        intents[target]["status"] = "active"
        return target
    return ""
```

- [ ] **Step 2d: 运行测试确认通过**

```bash
uv run pytest tests/test_dm/test_intent_controller.py -v 2>&1 | tail -20
```

Expected: ALL PASS (14 tests)

- [ ] **Step 2e: 提交**

```bash
git add app/dm/intent_controller.py tests/test_dm/test_intent_controller.py
git commit -m "feat: 新增 IntentController — 意图生命周期管理器，支持多意图挂起/恢复"
```

---

### Task 3: 更新路由逻辑

**Files:**
- Modify: `app/dm/router.py`
- Modify: `tests/test_dm/test_state_router.py`

**Interfaces:**
- Consumes: `DialogState.active_intent` (str, may be "")
- Produces: `is_platform_intent(state: dict) -> bool`

- [ ] **Step 3a: 修改路由函数**

```python
# app/dm/router.py
def is_platform_intent(state: dict) -> bool:
    """判断当前活跃意图是否为平台意图或空（兜底）

    空 active_intent 也表示无活跃意图，走 fallback 等 NLU 识别新意图。
    """
    active = state.get("active_intent", "")
    if not active:
        return True
    return active in ("unknown", "transfer_human")
```

- [ ] **Step 3b: 更新路由测试**

```python
# tests/test_dm/test_state_router.py — 修改 TestIsPlatformIntent 类

class TestIsPlatformIntent:
    """is_platform_intent 路由函数测试"""

    def test_unknown_is_platform(self):
        assert is_platform_intent({"active_intent": "unknown"}) is True

    def test_transfer_human_is_platform(self):
        assert is_platform_intent({"active_intent": "transfer_human"}) is True

    def test_order_query_is_not_platform(self):
        assert is_platform_intent({"active_intent": "order_query"}) is False

    def test_postsale_return_is_not_platform(self):
        assert is_platform_intent({"active_intent": "postsale_return"}) is False

    def test_empty_intent_is_platform(self):
        """空意图现在走 fallback（变更）"""
        assert is_platform_intent({"active_intent": ""}) is True

    def test_missing_key_is_platform(self):
        """state 中无 active_intent 时视为平台意图（变更）"""
        assert is_platform_intent({}) is True
```

需要同步更新 `tests/test_dm/test_state_router.py` 中的 `TestDialogState` 类 — 移除对 `slots` 和 `missing_slots` 的引用。

```python
# tests/test_dm/test_state_router.py — 更新 TestDialogState

class TestDialogState:
    """DialogState 类型测试"""

    def test_dialog_state_structure(self):
        """验证 DialogState 可构造并包含所有字段"""
        state: DialogState = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "查订单",
            "messages": [],
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "business_result": None,
            "final_response": "",
            "should_fallback": False,
        }
        assert state["session_id"] == "sess-001"
        assert state["user_id"] == "user-001"
        assert state["all_intents"] == []
        assert state["intents"] == {}
        assert state["active_intent"] == ""
        assert state["business_result"] is None
        assert state["final_response"] == ""
        assert state["should_fallback"] is False

    def test_dialog_state_with_data(self):
        """验证 DialogState 包含业务数据"""
        state: DialogState = {
            "session_id": "sess-002",
            "user_id": "user-002",
            "user_input": "ORD-001",
            "messages": [
                {"role": "user", "content": "查订单"},
                {"role": "assistant", "content": "请选择要查询的订单"},
            ],
            "all_intents": [],
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
            "business_result": {"action": "completed", "message": "查询完成"},
            "final_response": "您的订单详情...",
            "should_fallback": False,
        }
        assert state["active_intent"] == "order_query"
        assert state["intents"]["order_query"]["slots"]["order_id"] == "ORD-001"
        assert state["intents"]["order_query"]["status"] == "active"
        assert state["intents"]["order_query"]["confidence"] == 0.9
        assert state["business_result"]["action"] == "completed"

    def test_dialog_state_with_messages(self):
        """验证 messages 字段格式"""
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "您好，有什么可以帮您的？"},
            {"role": "user", "content": "查订单"},
        ]
        state: DialogState = {
            "session_id": "sess-003",
            "user_id": "user-003",
            "user_input": "ORD-001",
            "messages": messages,
            "all_intents": [],
            "intents": {},
            "active_intent": "order_query",
            "business_result": None,
            "final_response": "",
            "should_fallback": False,
        }
        assert len(state["messages"]) == 3
        assert state["messages"][0]["role"] == "user"
```

更新 `TestIntentContext` 以适应扩展字段：

```python
class TestIntentContext:
    """IntentContext 类型测试"""

    def test_intent_context_structure(self):
        ctx: IntentContext = {
            "name": "order_query",
            "confidence": 0.95,
            "status": "active",
            "slots": {"order_id": "ORD-001"},
            "required_slots": ["order_id"],
            "optional_slots": [],
        }
        assert ctx["name"] == "order_query"
        assert ctx["confidence"] == 0.95
        assert ctx["status"] == "active"
        assert ctx["slots"] == {"order_id": "ORD-001"}

    def test_intent_context_empty_slots(self):
        ctx: IntentContext = {
            "name": "unknown",
            "confidence": 0.0,
            "status": "active",
            "slots": {},
            "required_slots": [],
            "optional_slots": [],
        }
        assert ctx["required_slots"] == []
        assert ctx["optional_slots"] == []
```

- [ ] **Step 3c: 运行测试确认通过**

```bash
uv run pytest tests/test_dm/test_state_router.py -v 2>&1 | tail -15
```

Expected: ALL PASS

- [ ] **Step 3d: 提交**

```bash
git add app/dm/router.py tests/test_dm/test_state_router.py
git commit -m "refactor: 路由逻辑适配多意图 — 空 active_intent 走 fallback"
```

---

### Task 4: 更新 IntentClassifier Prompt

**Files:**
- Modify: `app/nlu/classifier.py`
- Modify: `tests/test_nlu/test_classifier.py`

**Interfaces:**
- Consumes: 新 `NLUResult` (Task 1), `all_intents` + `session_intents` (from state), `active_intent`, `messages`
- Produces: `IntentClassifier.classify(user_input, all_intents, session_intents, active_intent, messages) -> NLUResult`

- [ ] **Step 4a: 重写系统 Prompt 构造**

```python
# app/nlu/classifier.py — 替换 _build_system_prompt 方法
def _build_system_prompt(self, all_intents: list[dict] | None = None) -> str:
    """构造包含所有意图定义的系统 prompt"""
    intents = all_intents or []

    intent_descriptions = []
    for intent in intents:
        name = intent.get("name", "")
        desc_text = intent.get("description", "")
        required = intent.get("required_slots", [])
        optional = intent.get("optional_slots", [])

        desc = f"- {name}: {desc_text}"
        if required:
            slot_info = ", ".join(
                f"{s['name']}({s['description']})" for s in required
            )
            desc += f"。必填槽位: {slot_info}"
        if optional:
            slot_info = ", ".join(
                f"{s['name']}({s['description']})" for s in optional
            )
            desc += f"。可选槽位: {slot_info}"
        intent_descriptions.append(desc)

    return f"""你是一个电商智能客服系统的意图识别模块。你的任务是分析用户输入，判断意图变化并提取槽位。

## 可识别的意图

{chr(10).join(intent_descriptions)}

## 输出格式

请严格按以下 JSON 格式输出，不要输出其他内容：
```json
{{
    "action": "new",
    "target_intent": "意图名称",
    "confidence": 0.95,
    "slots_update": {{"槽位名": "槽位值"}}
}}
```

## action 说明

- **new**: 用户表达了新的意图需求，需要创建新意图
- **continue**: 用户在当前的活跃意图上下文中继续填槽位（默认值）
- **switch**: 用户想切回之前挂起的意图
- **cancel**: 用户表达取消当前意图（如"算了"、"不办了"）
- **complete**: 不主动使用此值，由业务节点在完成后使用

## 规则

1. 如果用户输入是在当前活跃意图的上下文中填槽位 → action="continue"，target_intent 设为当前活跃意图名
2. 如果用户表达了新意图需求 → action="new"，target_intent 设为新意图名
3. 如果用户输入无法匹配任何已知意图 → target_intent="unknown"，action="new"
4. 如果用户要求转人工 → target_intent="transfer_human"，action="new"
5. 如果用户说"取消"、"不办了"、"算了" → action="cancel"，target_intent 设为当前活跃意图名
6. **槽位值识别**：如果用户输入是单个值（如订单号），且当前有活跃意图的缺失槽位，则将该值识别为缺失槽位的填充值，action="continue"，target_intent 保持与 active_intent 一致
7. slots_update 只填本次提取到的值，不重复输出已填槽位
8. confidence 取值 0-1，表示你对分类结果的把握程度"""
```

- [ ] **Step 4b: 重写用户 Prompt 构造**

```python
# app/nlu/classifier.py — 替换 _build_user_prompt 方法
def _build_user_prompt(
    self,
    user_input: str,
    session_intents: dict | None = None,
    active_intent: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> str:
    """构造包含会话意图状态和对话历史的用户 prompt"""
    parts = []

    # 对话历史
    if messages:
        history_text = "\n".join(
            f"[{m['role']}]: {m['content']}" for m in messages
        )
        parts.append(f"对话历史:\n{history_text}")

    # 会话意图状态
    if session_intents:
        active_ctx = None
        other_intents = []
        for name, ctx in session_intents.items():
            if ctx.get("status") == "active":
                active_ctx = (name, ctx)
            else:
                other_intents.append((name, ctx))

        if active_ctx:
            name, ctx = active_ctx
            filled = ctx.get("slots", {})
            required = ctx.get("required_slots", [])
            missing = [s for s in required if s not in filled]
            parts.append(
                f"当前活跃意图: {name}（状态: active，"
                f"已填槽位: {filled}，缺失槽位: {missing}）"
            )

        if other_intents:
            other_lines = []
            for name, ctx in other_intents:
                filled = ctx.get("slots", {})
                required = ctx.get("required_slots", [])
                missing = [s for s in required if s not in filled]
                other_lines.append(
                    f"- {name}（状态: {ctx.get('status', '')}，"
                    f"已填槽位: {filled}，缺失槽位: {missing}）"
                )
            parts.append("会话中其他意图:\n" + "\n".join(other_lines))
    elif active_intent:
        parts.append(f"当前活跃意图: {active_intent}")

    parts.append(f"用户输入: {user_input}")
    return "\n".join(parts)
```

- [ ] **Step 4c: 更新 classify() 签名和实现**

```python
# app/nlu/classifier.py — 替换 classify 方法
async def classify(
    self,
    user_input: str,
    all_intents: list[dict] | None = None,
    session_intents: dict | None = None,
    active_intent: str | None = None,
    messages: list[dict[str, str]] | None = None,
) -> NLUResult:
    """对用户输入进行意图变化识别和槽位提取

    Args:
        user_input: 用户原始输入
        all_intents: 所有可用意图定义（从 IntentController.build_all_intents()）
        session_intents: 会话中已产生的意图（含状态+槽位）
        active_intent: 当前活跃意图名
        messages: 对话历史

    Returns:
        NLUResult: 增量式意图变化
    """
    system_prompt = self._build_system_prompt(all_intents)
    user_prompt = self._build_user_prompt(
        user_input,
        session_intents or {},
        active_intent or "",
        messages or [],
    )

    llm_messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]

    try:
        structured_llm = self.llm.with_structured_output(
            schema=NLUResult,
            method="json_mode",
        )
        result = await structured_llm.ainvoke(llm_messages)
        logger.info(
            f"意图分类: action={result.action}, "
            f"target_intent={result.target_intent}, "
            f"confidence={result.confidence}, "
            f"slots_update={result.slots_update}"
        )
        return result
    except Exception as e:
        logger.error(f"意图分类失败: {e}")
        return NLUResult(
            action="new",
            target_intent="unknown",
            confidence=0.0,
            slots_update={},
        )
```

- [ ] **Step 4d: 更新现有 Classifier 测试**

```python
# tests/test_nlu/test_classifier.py — 全部重写

class TestIntentClassifierPromptBuilding:
    """意图分类器 prompt 构造测试"""

    def test_build_system_prompt_from_all_intents(self):
        """验证系统 prompt 从 all_intents 构造"""
        classifier = IntentClassifier()
        all_intents = [
            {
                "name": "order_query",
                "description": "查询订单详情",
                "required_slots": [
                    {"name": "order_id", "description": "订单号"},
                ],
                "optional_slots": [],
            },
            {
                "name": "unknown",
                "description": "未知意图",
                "required_slots": [],
                "optional_slots": [],
            },
        ]
        prompt = classifier._build_system_prompt(all_intents)
        assert "order_query" in prompt
        assert "order_id" in prompt
        assert "查询订单详情" in prompt
        assert "unknown" in prompt
        assert "action" in prompt  # 输出格式说明
        assert "new" in prompt
        assert "continue" in prompt

    def test_build_system_prompt_with_optional_slots(self):
        """验证系统 prompt 包含可选槽位"""
        all_intents = [
            {
                "name": "product_inquiry",
                "description": "商品咨询",
                "required_slots": [],
                "optional_slots": [
                    {"name": "sku_id", "description": "商品SKU"},
                    {"name": "sku_name", "description": "商品名称"},
                ],
            },
        ]
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt(all_intents)
        assert "product_inquiry" in prompt
        assert "可选槽位" in prompt
        assert "sku_id" in prompt

    def test_build_system_prompt_empty_list(self):
        """验证空 all_intents 不报错"""
        classifier = IntentClassifier()
        prompt = classifier._build_system_prompt([])
        assert "可识别的意图" in prompt

    def test_build_user_prompt_basic(self):
        """验证用户 prompt 包含用户输入"""
        classifier = IntentClassifier()
        prompt = classifier._build_user_prompt("你好，帮我查订单")
        assert "你好，帮我查订单" in prompt

    def test_build_user_prompt_with_active_intent(self):
        """验证用户 prompt 包含活跃意图"""
        classifier = IntentClassifier()
        prompt = classifier._build_user_prompt("ORD-001", {}, "order_query")
        assert "order_query" in prompt
        assert "当前活跃意图" in prompt

    def test_build_user_prompt_with_session_intents(self):
        """验证用户 prompt 展示会话意图状态"""
        classifier = IntentClassifier()
        session_intents = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {},
                "required_slots": ["order_id"],
                "optional_slots": [],
            },
            "postsale_return": {
                "name": "postsale_return",
                "confidence": 0.85,
                "status": "suspended",
                "slots": {"order_id": "ORD-001"},
                "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                "optional_slots": [],
            },
        }
        prompt = classifier._build_user_prompt(
            "ORD-003",
            session_intents=session_intents,
            active_intent="order_query",
        )
        assert "order_query" in prompt
        assert "active" in prompt
        assert "postsale_return" in prompt
        assert "suspended" in prompt
        assert "ORD-001" in prompt
        assert "缺失槽位" in prompt


class TestIntentClassifierClassify:
    """意图分类器 classify 方法测试"""

    @staticmethod
    def _make_mock_llm(return_value):
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(return_value=return_value)
        llm = MagicMock()
        llm.with_structured_output.return_value = structured_llm
        return llm

    @staticmethod
    def _make_mock_llm_raising(exception: Exception):
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=exception)
        llm = MagicMock()
        llm.with_structured_output.return_value = structured_llm
        return llm

    @pytest.mark.asyncio
    async def test_classify_returns_nlu_result(self):
        """验证 classify 返回新的 NLUResult"""
        from app.nlu.models import NLUResult
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="order_query",
            confidence=0.95,
            slots_update={"order_id": "ORD-001"},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("查询订单 ORD-001")
        assert isinstance(result, NLUResult)
        assert result.action == "new"
        assert result.target_intent == "order_query"
        assert result.confidence == 0.95
        assert result.slots_update == {"order_id": "ORD-001"}

    @pytest.mark.asyncio
    async def test_classify_unknown_intent(self):
        """验证分类 unknown"""
        from app.nlu.models import NLUResult
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="unknown",
            confidence=0.3,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("asdfasdf???")
        assert result.action == "new"
        assert result.target_intent == "unknown"

    @pytest.mark.asyncio
    async def test_classify_with_continue_action(self):
        """验证 continue action"""
        from app.nlu.models import NLUResult
        mock_llm = self._make_mock_llm(NLUResult(
            action="continue",
            target_intent="order_query",
            confidence=0.9,
            slots_update={"order_id": "ORD-005"},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify(
            "ORD-005",
            session_intents={
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            active_intent="order_query",
        )
        assert result.action == "continue"
        assert result.target_intent == "order_query"

    @pytest.mark.asyncio
    async def test_classify_with_cancel_action(self):
        """验证 cancel action"""
        from app.nlu.models import NLUResult
        mock_llm = self._make_mock_llm(NLUResult(
            action="cancel",
            target_intent="order_query",
            confidence=0.9,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("算了不查了")
        assert result.action == "cancel"

    @pytest.mark.asyncio
    async def test_classify_passes_all_intents(self):
        """验证 classify 将 all_intents 传递给 LLM"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="unknown",
            confidence=0.0,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        await classifier.classify(
            "测试",
            all_intents=[{"name": "order_query", "description": "订单查询"}],
        )
        structured_llm = mock_llm.with_structured_output.return_value
        messages = structured_llm.ainvoke.call_args[0][0]
        system_msg = messages[0]
        assert isinstance(system_msg, SystemMessage)
        assert "order_query" in system_msg.content

    @pytest.mark.asyncio
    async def test_classify_with_transfer_human(self):
        """验证转人工"""
        mock_llm = self._make_mock_llm(NLUResult(
            action="new",
            target_intent="transfer_human",
            confidence=0.9,
            slots_update={},
        ))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("我要找人工客服")
        assert result.target_intent == "transfer_human"

    @pytest.mark.asyncio
    async def test_classify_handles_error(self):
        """验证 LLM 调用异常时降级"""
        mock_llm = self._make_mock_llm_raising(Exception("网络错误"))
        classifier = IntentClassifier(llm=mock_llm)
        result = await classifier.classify("查物流")
        assert result.action == "new"
        assert result.target_intent == "unknown"
        assert result.confidence == 0.0
```

- [ ] **Step 4e: 运行测试确认通过**

```bash
uv run pytest tests/test_nlu/test_classifier.py -v 2>&1 | tail -20
```

Expected: ALL PASS

- [ ] **Step 4f: 提交**

```bash
git add app/nlu/classifier.py tests/test_nlu/test_classifier.py
git commit -m "refactor: IntentClassifier 适配多意图 — 增量式 NLU 输出，all_intents + session_intents 上下文"
```

---

### Task 5: 更新 NLU 节点

**Files:**
- Modify: `app/dm/nodes/nlu_node.py`
- Modify: `tests/test_dm/test_nlu_node.py`

**Interfaces:**
- Consumes: `IntentController.decide()` (Task 2), 新 `IntentClassifier.classify()` (Task 4), 新 `DialogState` (Task 1)
- Produces: state 更新字典（含 `intents`, `active_intent`, `should_fallback`）

- [ ] **Step 5a: 重写 NLU 节点**

```python
# app/dm/nodes/nlu_node.py
"""NLU 节点 — 调用意图分类器进行意图识别和槽位提取"""
from loguru import logger

from app.nlu.classifier import IntentClassifier
from app.dm.intent_controller import IntentController

_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def reset_classifier() -> None:
    global _classifier
    _classifier = None


async def nlu_node(state: dict) -> dict:
    """NLU 节点：对用户输入进行意图变化识别和槽位提取

    将 all_intents、session_intents、active_intent 传递给分类器，
    然后委托 IntentController.decide() 处理意图生命周期。
    """
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
        f"slots_update={result.slots_update}, "
        f"active_intent={update.get('active_intent', '')}"
    )

    # 判断是否兜底
    update["should_fallback"] = (
        result.target_intent in ("unknown", "transfer_human")
    )

    return update
```

- [ ] **Step 5b: 重写 NLU 节点测试**

```python
# tests/test_dm/test_nlu_node.py
"""DM 层 — NLU 节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.nlu_node import nlu_node, get_classifier, reset_classifier


class TestNluNode:
    """nlu_node 函数测试"""

    @staticmethod
    def _make_mock_classifier(return_value):
        classifier = MagicMock()
        classifier.classify = AsyncMock(return_value=return_value)
        return classifier

    def setup_method(self):
        reset_classifier()

    @pytest.mark.asyncio
    async def test_nlu_node_new_intent(self, monkeypatch):
        """验证创建新意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="order_query",
                confidence=0.95,
                slots_update={"order_id": "ORD-001"},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "帮我查订单 ORD-001",
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "order_query"
        assert "order_query" in result["intents"]
        assert result["intents"]["order_query"]["status"] == "active"
        assert result["intents"]["order_query"]["slots"] == {"order_id": "ORD-001"}
        assert result["should_fallback"] is False

    @pytest.mark.asyncio
    async def test_nlu_node_continue_merges_slots(self, monkeypatch):
        """验证 continue action 合并槽位到活跃意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="continue",
                target_intent="postsale_return",
                confidence=0.88,
                slots_update={"postsale_type": "refund_only"},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "仅退款",
            "all_intents": [],
            "intents": {
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                }
            },
            "active_intent": "postsale_return",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "postsale_return"
        assert result["intents"]["postsale_return"]["slots"] == {
            "order_id": "ORD-001",
            "postsale_type": "refund_only",
        }

    @pytest.mark.asyncio
    async def test_nlu_node_new_suspends_active(self, monkeypatch):
        """验证 new action 挂起当前活跃意图"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="order_query",
                confidence=0.92,
                slots_update={"order_id": "ORD-003"},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "user_input": "查订单 ORD-003",
            "all_intents": [],
            "intents": {
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                }
            },
            "active_intent": "postsale_return",
            "messages": [],
        }

        result = await nlu_node(state)

        # 旧意图被挂起
        assert result["intents"]["postsale_return"]["status"] == "suspended"
        # 新意图激活
        assert result["intents"]["order_query"]["status"] == "active"
        assert result["active_intent"] == "order_query"

    @pytest.mark.asyncio
    async def test_nlu_node_unknown_intent(self, monkeypatch):
        """验证 unknown 意图走 fallback"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="unknown",
                confidence=0.1,
                slots_update={},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        state = {
            "user_input": "asdfghjkl",
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "unknown"
        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_nlu_node_transfer_human(self, monkeypatch):
        """验证转人工"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="transfer_human",
                confidence=0.92,
                slots_update={},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        state = {
            "user_input": "我要找人工客服",
            "all_intents": [],
            "intents": {},
            "active_intent": "",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["active_intent"] == "transfer_human"
        assert result["should_fallback"] is True

    @pytest.mark.asyncio
    async def test_nlu_node_passes_context_to_classifier(self, monkeypatch):
        """验证 NLU 节点将 all_intents 和 session_intents 传给分类器"""
        from app.nlu.models import NLUResult
        mock_classifier = MagicMock()
        mock_classifier.classify = AsyncMock(
            return_value=NLUResult(
                action="continue",
                target_intent="order_query",
                confidence=0.9,
                slots_update={"order_id": "999"},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        all_intents = [{"name": "order_query", "description": "订单查询"}]
        session_intents = {
            "order_query": {
                "name": "order_query",
                "confidence": 0.9,
                "status": "active",
                "slots": {},
                "required_slots": ["order_id"],
                "optional_slots": [],
            }
        }
        messages = [
            {"role": "user", "content": "查订单"},
            {"role": "assistant", "content": "请选择要查询的订单"},
        ]

        state = {
            "user_input": "999",
            "all_intents": all_intents,
            "intents": session_intents,
            "active_intent": "order_query",
            "messages": messages,
        }

        await nlu_node(state)

        mock_classifier.classify.assert_called_once_with(
            user_input="999",
            all_intents=all_intents,
            session_intents=session_intents,
            active_intent="order_query",
            messages=messages,
        )

    @pytest.mark.asyncio
    async def test_nlu_node_cancel_intent(self, monkeypatch):
        """验证 cancel action"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="cancel",
                target_intent="order_query",
                confidence=0.9,
                slots_update={},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        state = {
            "user_input": "算了不查了",
            "all_intents": [],
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
            "active_intent": "order_query",
            "messages": [],
        }

        result = await nlu_node(state)

        assert result["intents"]["order_query"]["status"] == "cancelled"
        assert result["active_intent"] == ""

    @pytest.mark.asyncio
    async def test_nlu_node_with_empty_state(self, monkeypatch):
        """验证空 state"""
        from app.nlu.models import NLUResult
        mock_classifier = self._make_mock_classifier(
            NLUResult(
                action="new",
                target_intent="unknown",
                confidence=0.0,
                slots_update={},
            )
        )
        monkeypatch.setattr("app.dm.nodes.nlu_node._classifier", mock_classifier)

        result = await nlu_node({})

        assert result["active_intent"] == "unknown"
        assert result["should_fallback"] is True
```

- [ ] **Step 5c: 运行测试确认通过**

```bash
uv run pytest tests/test_dm/test_nlu_node.py -v 2>&1 | tail -20
```

Expected: ALL PASS (8 tests)

- [ ] **Step 5d: 提交**

```bash
git add app/dm/nodes/nlu_node.py tests/test_dm/test_nlu_node.py
git commit -m "refactor: NLU 节点适配多意图 — 委托 IntentController 处理生命周期"
```

---

### Task 6: 更新业务节点

**Files:**
- Modify: `app/dm/nodes/business_node.py`
- Modify: `tests/test_dm/test_business_node.py`

**Interfaces:**
- Consumes: `IntentController.get_active_context()` (Task 2), `IntentRegistry` (existing)
- Produces: state 更新字典，business 完成后通过 Controller 标记 complete 并恢复挂起意图

- [ ] **Step 6a: 重写业务节点**

```python
# app/dm/nodes/business_node.py
"""业务节点 — 调用业务线的意图处理器"""
from loguru import logger

from app.business.base import BusinessResult
from app.nlu.registry import IntentRegistry
from app.nlu.models import NLUResult
from app.dm.intent_controller import IntentController


async def business_node(state: dict) -> dict:
    """执行业务意图

    通过 IntentController.get_active_context() 构建含独立槽位的上下文，
    业务完成后通过 Controller 标记意图完成并自动恢复挂起意图。
    """
    active_intent = state.get("active_intent", "")

    handler_cls = IntentRegistry.get_handler(active_intent)
    if handler_cls is None:
        logger.warning(f"未找到意图处理器: {active_intent}")
        return {"business_result": BusinessResult.error("该功能暂未开放")}

    # 通过 Controller 构建上下文（含该意图的独立槽位）
    ctx = IntentController.get_active_context(state)

    handler = handler_cls()
    result = await handler.handle(ctx)

    action = ""
    if isinstance(result.data, dict):
        action = result.data.get("action", "")

    logger.info(
        f"业务节点执行: intent={active_intent}, "
        f"action={action}, "
        f"success={result.success}"
    )

    # 业务完成时标记意图为 completed，Controller 自动恢复挂起意图
    if result.success and isinstance(result.data, dict):
        if result.data.get("action") == "completed":
            intent_update = IntentController.decide(
                state,
                NLUResult(
                    action="complete",
                    target_intent=active_intent,
                    confidence=1.0,
                ),
            )
            return {**intent_update, "business_result": result}

    return {"business_result": result}
```

- [ ] **Step 6b: 重写业务节点测试**

```python
# tests/test_dm/test_business_node.py
"""DM 层 — 业务节点测试"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dm.nodes.business_node import business_node
from app.business.base import BusinessResult, OptionItem
from app.nlu.registry import IntentRegistry
from app.nlu.models import IntentDefinition


class TestBusinessNode:
    """business_node 函数测试"""

    def setup_method(self):
        IntentRegistry.clear()

    def _register_mock_intent(self, intent_name: str, handler_cls):
        intent_def = IntentDefinition(
            name=intent_name,
            description="测试意图",
            handler=handler_cls,
        )
        IntentRegistry.register_business("test", [intent_def])

    @pytest.mark.asyncio
    async def test_business_node_completed_updates_intent_status(self):
        """验证业务完成后意图状态变为 completed"""
        mock_result = BusinessResult.completed(
            message="📋 订单 ORD-001 详情已加载",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        assert result["business_result"] is not None
        br = result["business_result"]
        assert br.success is True
        assert br.data["action"] == "completed"
        # Controller 标记完成
        assert result["intents"]["order_query"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_business_node_completed_restores_suspended(self):
        """验证业务完成后自动恢复挂起的意图"""
        mock_result = BusinessResult.completed(
            message="📋 订单 ORD-003 详情已加载",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-003"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                },
                "postsale_return": {
                    "name": "postsale_return",
                    "confidence": 0.85,
                    "status": "suspended",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id", "postsale_type", "postsale_reason"],
                    "optional_slots": [],
                },
            },
        }

        result = await business_node(state)

        assert result["intents"]["order_query"]["status"] == "completed"
        # 挂起的售后意图被恢复
        assert result["intents"]["postsale_return"]["status"] == "active"
        assert result["active_intent"] == "postsale_return"

    @pytest.mark.asyncio
    async def test_business_node_ask_slot(self):
        """验证 ask_slot 行为不变"""
        options = [
            OptionItem(label="ORD-001（已签收）", value="ORD-001"),
            OptionItem(label="ORD-002（已付款）", value="ORD-002"),
        ]
        mock_result = BusinessResult.ask_slot(
            slot_to_fill="order_id",
            options=options,
            message="请选择要查询的订单",
        )
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is True
        assert br.data["action"] == "ask_slot"
        assert br.data["slot_to_fill"] == "order_id"
        # ask_slot 不改变意图状态
        assert "intents" not in result  # business_node 不返回 intents 更新

    @pytest.mark.asyncio
    async def test_business_node_error(self):
        """验证业务错误处理"""
        mock_result = BusinessResult.error("订单不存在")
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(return_value=mock_result)
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "INVALID"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "订单不存在"

    @pytest.mark.asyncio
    async def test_business_node_unregistered_intent(self):
        """验证未注册意图"""
        intent_def = IntentDefinition(
            name="product_inquiry",
            description="商品咨询",
            handler=None,
        )
        IntentRegistry.register_business("test", [intent_def])

        state = {
            "session_id": "sess-001",
            "user_id": "user-001",
            "active_intent": "product_inquiry",
            "intents": {
                "product_inquiry": {
                    "name": "product_inquiry",
                    "confidence": 0.8,
                    "status": "active",
                    "slots": {},
                    "required_slots": ["query"],
                    "optional_slots": [],
                }
            },
        }

        result = await business_node(state)

        br = result["business_result"]
        assert br.success is False
        assert br.error_message == "该功能暂未开放"

    @pytest.mark.asyncio
    async def test_business_node_passes_correct_context(self):
        """验证业务节点传递正确的 BusinessContext（含独立槽位）"""
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock(
            return_value=BusinessResult.completed(message="ok")
        )
        handler_cls = MagicMock(return_value=mock_handler)

        self._register_mock_intent("order_query", handler_cls)

        state = {
            "session_id": "sess-abc",
            "user_id": "user-xyz",
            "active_intent": "order_query",
            "intents": {
                "order_query": {
                    "name": "order_query",
                    "confidence": 0.9,
                    "status": "active",
                    "slots": {"order_id": "ORD-001"},
                    "required_slots": ["order_id"],
                    "optional_slots": [],
                }
            },
        }

        await business_node(state)

        mock_handler.handle.assert_called_once()
        from app.business.base import BusinessContext
        ctx = mock_handler.handle.call_args[0][0]
        assert isinstance(ctx, BusinessContext)
        assert ctx.session_id == "sess-abc"
        assert ctx.user_id == "user-xyz"
        assert ctx.intent == "order_query"
        assert ctx.slots == {"order_id": "ORD-001"}

    @pytest.mark.asyncio
    async def test_business_node_with_real_handler(self):
        """使用真实 Handler 类验证注册中心"""
        from app.business.ecommerce.handlers.order_query import OrderQueryHandler
        from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler

        IntentRegistry.register_business(
            "ecommerce",
            [
                IntentDefinition(
                    name="order_query",
                    description="订单查询",
                    handler=OrderQueryHandler,
                ),
                IntentDefinition(
                    name="postsale_return",
                    description="售后申请",
                    handler=PostsaleReturnHandler,
                ),
            ],
        )

        handler_cls = IntentRegistry.get_handler("order_query")
        assert handler_cls is OrderQueryHandler
```

- [ ] **Step 6c: 运行测试确认通过**

```bash
uv run pytest tests/test_dm/test_business_node.py -v 2>&1 | tail -20
```

Expected: ALL PASS

- [ ] **Step 6d: 提交**

```bash
git add app/dm/nodes/business_node.py tests/test_dm/test_business_node.py
git commit -m "refactor: 业务节点适配多意图 — 通过 IntentController 获取上下文，完成后恢复挂起意图"
```

---

### Task 7: Session 模型 + Alembic 迁移

**Files:**
- Modify: `app/session/models.py`
- Create: `alembic/versions/XXXX_add_intents_json_to_sessions.py`

**Interfaces:**
- Produces: `Session.intents_json: Mapped[dict | None]`

- [ ] **Step 7a: Session 模型新增 intents_json 字段**

```python
# app/session/models.py — 在 Session 类中新增字段
class Session(Base):
    # ... 现有字段保持不变 ...

    intents_json: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="会话意图状态快照: {intent_name: {status, slots, confidence, ...}}"
    )
```

在 `status` 字段后面，`created_at` 之前插入。

- [ ] **Step 7b: 生成 Alembic 迁移**

```bash
cd "D:\work\VIPCourse\codes\claude-code\jd-service" && uv run alembic revision --autogenerate -m "add_intents_json_to_sessions" 2>&1
```

Expected: 生成新迁移文件

- [ ] **Step 7c: 检查并确认迁移文件正确**

检查生成的文件中是否包含：
```python
def upgrade():
    op.add_column('sessions', sa.Column('intents_json', sa.JSON(), nullable=True, comment='会话意图状态快照'))

def downgrade():
    op.drop_column('sessions', 'intents_json')
```

- [ ] **Step 7d: 更新 Session 模型测试**

```python
# tests/test_session/test_models.py — 新增/更新测试
class TestSessionModel:
    def test_intents_json_field_exists(self):
        """验证 Session 模型包含 intents_json 字段"""
        assert hasattr(Session, 'intents_json')
        column = Session.__table__.columns['intents_json']
        assert column.nullable is True
        if column.comment:
            assert '意图' in column.comment or 'intent' in column.comment.lower()
```

- [ ] **Step 7e: 运行 Session 测试**

```bash
uv run pytest tests/test_session/ -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 7f: 提交**

```bash
git add app/session/models.py alembic/versions/ tests/test_session/
git commit -m "feat: Session 新增 intents_json 字段 — 持久化会话意图容器快照"
```

---

### Task 8: SessionService 扩展 + Chat API 更新

**Files:**
- Modify: `app/session/service.py`
- Modify: `app/api/v1/chat.py`

**Interfaces:**
- Consumes: `IntentController.to_snapshot()`, `IntentController.from_snapshot()` (Task 2), `IntentController.build_all_intents()`, `IntentController.find_active()` (Task 2)
- Produces: `SessionService.save_intents_snapshot()`, `SessionService.load_intents_snapshot()`

- [ ] **Step 8a: SessionService 新增方法**

```python
# app/session/service.py — 在 SessionService 类中新增
from sqlalchemy import update

# 在类中添加：
@staticmethod
async def save_intents_snapshot(
    db: AsyncSession, session_id: str, intents: dict
) -> None:
    """保存意图容器快照到 Session.intents_json"""
    from app.dm.intent_controller import IntentController
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
    from app.dm.intent_controller import IntentController
    session = await SessionService.get_session(db, session_id)
    if session and session.intents_json:
        return IntentController.from_snapshot(session.intents_json)
    return None
```

注意：`update` 和 `Session` 可能已经导入，检查现有 import 后添加缺失的。

- [ ] **Step 8b: Chat API 更新 initial_state 构造**

```python
# app/api/v1/chat.py — 修改 send_message 端点中 initial_state 的构造

# 替换原有的 initial_state 构造：
# ── 4.5 从 DB 恢复意图状态 ──────────────────────
from app.dm.intent_controller import IntentController
saved_intents = await SessionService.load_intents_snapshot(db, session_id)
initial_intents = saved_intents if saved_intents else {}

initial_state = {
    "session_id": session_id,
    "user_id": session.user_id,
    "user_input": content,
    "messages": messages_context,
    "all_intents": IntentController.build_all_intents(),
    "intents": initial_intents,
    "active_intent": IntentController.find_active(initial_intents),
    "business_result": None,
    "final_response": "",
    "should_fallback": False,
}
```

- [ ] **Step 8c: Chat API 出口持久化意图快照**

```python
# 替换对话图执行后的保存逻辑：
reply = final_state.get("final_response", "抱歉，我不知道该如何回答。")
active_intent = final_state.get("active_intent", "")

# 持久化意图状态
await SessionService.save_intents_snapshot(
    db, session_id, final_state.get("intents", {})
)
```

`active_intent` 和 `reply` 的提取保持不变，移除旧的 `slots` 相关代码。

- [ ] **Step 8d: 更新图集成测试**

```python
# tests/test_dm/test_graph.py — 更新 _make_initial_state 方法
def _make_initial_state(self, **overrides) -> dict:
    state = {
        "session_id": "sess-test",
        "user_id": "user-test",
        "user_input": "测试输入",
        "messages": [],
        "all_intents": [],
        "intents": {},
        "active_intent": "",
        "business_result": None,
        "final_response": "",
        "should_fallback": False,
    }
    state.update(overrides)
    return state
```

同时更新所有 mock NLUResult 构造 — 将 `intent=`, `slots=`, `missing_slots=` 改为 `action=`, `target_intent=`, `slots_update=`：

```python
# 测试函数示例更新：
NLUResult(
    action="new",
    target_intent="unknown",
    confidence=0.0,
    slots_update={},
)
```

- [ ] **Step 8e: 运行全部测试**

```bash
uv run pytest tests/test_dm/ tests/test_session/ -v 2>&1 | tail -30
```

Expected: ALL PASS（修复后）

- [ ] **Step 8f: 提交**

```bash
git add app/session/service.py app/api/v1/chat.py tests/test_dm/test_graph.py
git commit -m "feat: SessionService + Chat API 支持意图快照持久化与恢复"
```

---

### Task 9: 最终集成测试与回归验证

**Files:**
- Modify: `tests/test_api/test_sessions.py`（如有必要）
- 修复所有未通过的测试文件

**Interfaces:**
- Consumes: All previous tasks
- Produces: All tests passing

- [ ] **Step 9a: 运行全部测试套件**

```bash
uv run pytest -v 2>&1 | tail -50
```

- [ ] **Step 9b: 逐一修复未通过的测试**

检查每个失败的测试，按需调整：
- 旧 `NLUResult(intent=..., slots=..., missing_slots=...)` → 新 `NLUResult(action=..., target_intent=..., slots_update=...)`
- 旧 `state["slots"]` → `IntentController.get_active_slots(state)` 或 `state["intents"][active]["slots"]`
- 旧 `state["missing_slots"]` → `IntentController.get_missing_slots(state)`
- 旧 `_build_user_prompt(user_input, slots, intent)` → `_build_user_prompt(user_input, session_intents, active_intent)`

可能受影响的文件：
- `tests/test_nlu/test_classifier_e2e.py`
- `tests/test_nlg/test_engine.py`
- `tests/test_api/test_sessions.py`

- [ ] **Step 9c: 确认全部测试通过**

```bash
uv run pytest -v 2>&1 | tail -10
```

Expected: ALL PASS, 无 FAIL 或 ERROR

- [ ] **Step 9d: 提交**

```bash
git add -A
git commit -m "test: 修复多意图重构后的所有测试用例"
```

---

### Task 10: NLU 层模型测试更新

**Files:**
- Modify: `tests/test_nlu/test_models.py`

**Interfaces:**
- Consumes: 新 `NLUResult` 模型 (Task 1)

- [ ] **Step 10a: 更新 NLU 模型测试**

```python
# tests/test_nlu/test_models.py
"""NLU 层核心数据模型测试"""
import pytest
from pydantic import ValidationError

from app.nlu.models import NLUResult, IntentDefinition, SlotDef


class TestNLUResult:
    """NLUResult 模型测试"""

    def test_nlu_result_with_action_new(self):
        """验证 NLUResult 支持 new action"""
        result = NLUResult(
            action="new",
            target_intent="order_query",
            confidence=0.95,
            slots_update={"order_id": "ORD-001"},
        )
        assert result.action == "new"
        assert result.target_intent == "order_query"
        assert result.confidence == 0.95
        assert result.slots_update == {"order_id": "ORD-001"}

    def test_nlu_result_defaults(self):
        """验证 NLUResult 默认值"""
        result = NLUResult()
        assert result.action == "continue"
        assert result.target_intent == ""
        assert result.confidence == 0.0
        assert result.slots_update == {}

    def test_nlu_result_with_continue_action(self):
        """验证 continue action"""
        result = NLUResult(
            action="continue",
            target_intent="order_query",
            confidence=0.85,
            slots_update={"order_id": "ORD-005"},
        )
        assert result.action == "continue"

    def test_nlu_result_serialization(self):
        """验证 NLUResult 可序列化为 JSON"""
        result = NLUResult(
            action="new",
            target_intent="order_query",
            confidence=0.9,
            slots_update={"order_id": "ORD-001"},
        )
        data = result.model_dump()
        assert data["action"] == "new"
        assert data["target_intent"] == "order_query"
        assert data["slots_update"] == {"order_id": "ORD-001"}

    def test_nlu_result_deserialization(self):
        """验证从 dict 反序列化"""
        data = {
            "action": "cancel",
            "target_intent": "postsale_return",
            "confidence": 0.9,
            "slots_update": {},
        }
        result = NLUResult(**data)
        assert result.action == "cancel"
        assert result.target_intent == "postsale_return"
```

- [ ] **Step 10b: 运行测试**

```bash
uv run pytest tests/test_nlu/test_models.py -v 2>&1 | tail -10
```

Expected: ALL PASS

- [ ] **Step 10c: 提交**

```bash
git add tests/test_nlu/test_models.py
git commit -m "test: 更新 NLU 模型测试适配新的 NLUResult 增量式输出"
```

---

### 收尾步骤

- [ ] 运行完整测试套件确认全部通过：
```bash
uv run pytest -v 2>&1
```

- [ ] 如果有 E2E 测试（`test_classifier_e2e.py`），检查是否需要手动验证 LLM 调用正常

- [ ] 最终提交（如有遗漏文件）
