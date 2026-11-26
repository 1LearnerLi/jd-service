"""DM 层条件路由

提供给 LangGraph add_conditional_edges 使用的路由函数。
"""


def is_platform_intent(state: dict) -> bool:
    """判断当前活跃意图是否为平台意图（unknown / transfer_human）

    平台意图走 fallback 节点，业务意图走 business 节点。
    """
    active = state.get("active_intent", "")
    return active in ("unknown", "transfer_human")
