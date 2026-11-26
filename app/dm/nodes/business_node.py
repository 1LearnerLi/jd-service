"""业务节点 — 调用业务线的意图处理器

通过 IntentRegistry 动态获取意图对应的 Handler 类，
平台代码不直接导入任何业务线 Handler。
"""
from loguru import logger

from app.business.base import BusinessContext, BusinessResult
from app.nlu.registry import IntentRegistry


async def business_node(state: dict) -> dict:
    """执行业务意图

    根据 active_intent 通过 IntentRegistry 查找对应的 IntentHandler 并执行。
    Handler 内部按 required_slots 顺序逐槽位检查：
    - 槽位缺失 → 返回 BusinessResult.ask_slot()（含 options 列表供前端渲染）
    - 槽位齐全 → 执行并返回 BusinessResult.completed()
    - 执行失败 → 返回 BusinessResult.error()

    Returns:
        包含 business_result 的更新字典。
    """
    active_intent = state.get("active_intent", "")

    handler_cls = IntentRegistry.get_handler(active_intent)
    if handler_cls is None:
        logger.warning(f"未找到意图处理器: {active_intent}")
        return {
            "business_result": BusinessResult.error("该功能暂未开放"),
        }

    ctx = BusinessContext(
        session_id=state.get("session_id", ""),
        user_id=state.get("user_id", ""),
        intent=active_intent,
        slots=state.get("slots", {}),
    )

    handler = handler_cls()
    result = await handler.handle(ctx)

    # 读出 action 用于日志（兼容 ask_slot / completed / error 三种形态）
    action = ""
    if isinstance(result.data, dict):
        action = result.data.get("action", "")

    logger.info(
        f"业务节点执行: intent={active_intent}, "
        f"action={action}, "
        f"success={result.success}"
    )
    return {"business_result": result}
