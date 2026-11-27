"""业务节点 — 调用业务线的意图处理器

通过 IntentRegistry 动态获取意图对应的 Handler 类，
平台代码不直接导入任何业务线 Handler。
"""
from loguru import logger

from app.business.base import BusinessResult
from app.nlu.registry import IntentRegistry
from app.nlu.models import NLUResult
from app.dm.intent_controller import IntentController


async def business_node(state: dict) -> dict:
    """执行业务意图

    通过 IntentController.get_active_context() 构建含独立槽位的上下文，
    业务完成后通过 Controller 标记意图完成并自动恢复挂起意图。

    Returns:
        包含 business_result 和可能 intents 更新的字典。
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

    # 读出 action 用于日志（兼容 ask_slot / completed / error 三种形态）
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
