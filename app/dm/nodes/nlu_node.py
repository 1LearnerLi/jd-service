"""NLU 节点 — 调用意图分类器进行意图识别和槽位提取"""
from loguru import logger

from app.nlu.classifier import IntentClassifier

_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    """获取 IntentClassifier 单例（懒加载）"""
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


def reset_classifier() -> None:
    """重置分类器单例（用于测试）"""
    global _classifier
    _classifier = None


async def nlu_node(state: dict) -> dict:
    """NLU 节点：对用户输入进行意图识别和槽位提取

    从 state 中读取 user_input、当前已收集的 slots 和 active_intent，
    调用 IntentClassifier.classify() 后更新 state。

    Returns:
        包含 active_intent、slots（合并）、missing_slots、should_fallback 的更新字典。
    """
    user_input = state.get("user_input", "")
    current_slots = state.get("slots", {})
    active_intent = state.get("active_intent", "")

    classifier = get_classifier()
    result = await classifier.classify(
        user_input=user_input,
        current_slots=current_slots,
        active_intent=active_intent,
    )

    # 合并新提取的槽位到已有槽位
    merged_slots = {**current_slots, **result.slots}

    logger.info(
        f"NLU 节点输出: intent={result.intent}, "
        f"confidence={result.confidence}, "
        f"slots={merged_slots}, "
        f"missing={result.missing_slots}"
    )

    return {
        "active_intent": result.intent,
        "slots": merged_slots,
        "missing_slots": result.missing_slots,
        "should_fallback": result.intent in ("unknown", "transfer_human"),
    }
