# DM 层优化设计 — messages 上下文、槽位值识别、Handler 注册解耦

## 概述

对 DM 层进行三项优化，增强上下文能力、NLU 识别精度和平台-业务线解耦。

## 1. DialogState 新增 messages 属性

**问题**：当前 DialogState 没有对话历史，NLU 和业务处理缺乏上下文。

**方案**：在 `DialogState` 中新增 `messages` 字段：

```python
messages: list[dict[str, str]]  # [{"role": "user"|"assistant", "content": "..."}]
```

- API 层在入口注入从数据库加载的历史消息
- 每个回合结束后，将本轮的 user 消息和 assistant 回复追加到 messages
- NLU 节点将 messages 传给 IntentClassifier 作为上下文

## 2. IntentClassifier 增强

### 2.1 classify() 新增 messages 参数

```python
async def classify(
    self,
    user_input: str,
    current_slots: dict[str, object] | None = None,
    active_intent: str | None = None,
    messages: list[dict[str, str]] | None = None,  # 新增
) -> NLUResult:
```

### 2.2 系统 prompt 调整

在原有 prompt 基础上增加两条规则：

1. **对话历史上下文**：将 messages 拼入用户 prompt，让 LLM 理解完整对话背景
2. **槽位值识别**：当用户输入是单个值（如 "ORD-001"、"仅退款"），且当前有活跃意图的缺失槽位时，将该值识别为缺失槽位的填充值，意图保持与 active_intent 一致，不做意图重新分类

### 2.3 nlu_node 传递 messages

```python
result = await classifier.classify(
    user_input=user_input,
    current_slots=current_slots,
    active_intent=active_intent,
    messages=state.get("messages", []),
)
```

## 3. IntentDefinition 新增 handler 字段

```python
class IntentDefinition(BaseModel):
    name: str
    description: str
    required_slots: list[SlotDef] = []
    optional_slots: list[SlotDef] = []
    handler: type | None = None  # 新增：对应的 IntentHandler 子类
```

## 4. 业务线约定：统一使用 INTENTS 常量

每个业务线的 `intents.py` 必须导出名为 `INTENTS` 的列表变量，意图定义中直接绑定 handler：

```python
# business/ecommerce/intents.py
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler

INTENTS: list[IntentDefinition] = [
    IntentDefinition(
        name="order_query",
        description="用户查询自己的订单详情...",
        required_slots=[SlotDef(name="order_id", ...)],
        handler=OrderQueryHandler,
    ),
    IntentDefinition(
        name="postsale_return",
        description="用户申请退货退款...",
        required_slots=[...],
        handler=PostsaleReturnHandler,
    ),
    IntentDefinition(
        name="product_inquiry",
        description="用户咨询商品信息...",
        required_slots=[SlotDef(name="query", ...)],
        handler=None,  # 暂未实现
    ),
]
```

## 5. IntentRegistry 改进

新增方法 `get_handler(intent_name) -> type | None`：

```python
@classmethod
def get_handler(cls, intent_name: str) -> type | None:
    """按意图名获取对应的 Handler 类"""
    intent = cls.get_intent_by_name(intent_name)
    if intent is None:
        return None
    return intent.handler
```

`register_business()` 无需改动——因为 `IntentDefinition` 已自带 handler，注册意图的同时 handler 映射就自然建立了。

## 6. business_node 解耦

删除硬编码的 `_handler_map` 字典和业务线 import：

```python
# 旧代码（删除）
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler
_handler_map: dict[str, type] = {
    "order_query": OrderQueryHandler,
    "postsale_return": PostsaleReturnHandler,
}

# 新代码
from app.nlu.registry import IntentRegistry

async def business_node(state: dict) -> dict:
    active_intent = state.get("active_intent", "")
    handler_cls = IntentRegistry.get_handler(active_intent)
    # ...
```

## 涉及文件

| 文件 | 动作 |
|------|------|
| `app/dm/state.py` | 新增 `messages` 字段 |
| `app/nlu/models.py` | `IntentDefinition` 新增 `handler` 字段 |
| `app/nlu/classifier.py` | `classify()` 新增 `messages` 参数，调整 prompt |
| `app/nlu/registry.py` | 新增 `get_handler()` 方法 |
| `app/business/ecommerce/intents.py` | 变量名改为 `INTENTS`，增加 `handler` 绑定 |
| `app/dm/nodes/nlu_node.py` | 传递 `messages` 给 classifier |
| `app/dm/nodes/business_node.py` | 删除硬编码 `_handler_map`，改用 registry |
| `app/main.py` | 注册时使用 `ECOMMERCE_INTENTS` → `INTENTS`（变量名更新） |
| 各测试文件 | 同步更新 |

## 测试策略

- 更新现有 DM 层测试以适配新接口
- 新增 `IntentDefinition.handler` 测试
- 新增 `IntentRegistry.get_handler()` 测试
- 新增 `IntentClassifier` 带 messages 参数和槽位值识别的测试
- 更新 `business_node` 测试，mock `IntentRegistry.get_handler`
