"""DM 层 DialogState 定义

对话状态的核心数据结构，贯穿整个 LangGraph 图的执行流程。
"""
from typing import Any, TypedDict


class IntentContext(TypedDict):
    """意图上下文 — 记录单个识别到的意图的元信息"""
    name: str
    confidence: float
    required_slots: list[str]
    optional_slots: list[str]


class DialogState(TypedDict):
    """对话状态

    LangGraph StateGraph 的状态字典。每个节点读取并返回部分字段的更新。

    字段说明：
    - session_id / user_id / user_input: 由 API 层在入口注入
    - intents: 所有已识别意图的注册表，key 为意图名
    - active_intent: 当前活跃意图名，由 NLU 节点产出
    - slots: 已填充的槽位键值对，由 NLU 节点累积更新
    - missing_slots: 当前活跃意图的缺失必填槽位列表
    - business_result: 业务节点执行结果（BusinessResult | None）
    - final_response: 最终要返回给用户的回复文本
    - should_fallback: 是否触发兜底流程
    """
    session_id: str
    user_id: str
    user_input: str
    intents: dict[str, IntentContext]
    active_intent: str
    slots: dict[str, object]
    missing_slots: list[str]
    business_result: object      # BusinessResult | None
    final_response: str
    should_fallback: bool
