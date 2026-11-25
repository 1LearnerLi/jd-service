"""意图分类器 — 基于 LLM prompt 进行意图识别和槽位提取"""
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from app.nlu.models import NLUResult
from app.nlu.registry import IntentRegistry
from app.config import settings


class IntentClassifier:
    """LLM 驱动的意图分类器

    通过构造包含所有已注册意图的系统 prompt，
    让 LLM 对用户输入进行意图分类和槽位提取。
    """

    def __init__(self, llm: ChatOpenAI | None = None):
        """初始化分类器

        Args:
            llm: 可选的 ChatOpenAI 实例，用于测试时注入 mock
        """
        self._llm = llm
        self._registry = IntentRegistry()

    @property
    def llm(self) -> ChatOpenAI:
        """懒加载 LLM 实例"""
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                temperature=0.1,
            )
        return self._llm

    def _build_system_prompt(self) -> str:
        """构造包含所有意图定义的系统 prompt"""
        intents = self._registry.get_all_intents()
        intent_descriptions = []
        for intent in intents:
            desc = f"- {intent.name}: {intent.description}"
            if intent.required_slots:
                slot_info = ", ".join(
                    f"{s.name}({s.description})" for s in intent.required_slots
                )
                desc += f"。必填槽位: {slot_info}"
            if intent.optional_slots:
                slot_info = ", ".join(
                    f"{s.name}({s.description})" for s in intent.optional_slots
                )
                desc += f"。可选槽位: {slot_info}"
            intent_descriptions.append(desc)

        return f"""你是一个电商智能客服系统的意图识别模块。你的任务是分析用户输入，判断意图并提取槽位。

## 可识别的意图

{chr(10).join(intent_descriptions)}

## 输出格式

请严格按以下 JSON 格式输出，不要输出其他内容：
```json
{{
    "intent": "意图名称",
    "confidence": 0.95,
    "slots": {{"槽位名": "槽位值"}},
    "missing_slots": ["缺失的必填槽位名"]
}}
```

#### 规则
1. 如果用户输入无法匹配任何已知意图，intent 设为 "unknown"
2. 如果用户要求转人工，intent 设为 "transfer_human"
3. 从用户输入中尽可能提取所有槽位值
4. missing_slots 只列出必填槽位中缺失的部分
5. confidence 取值 0-1，表示你对分类结果的把握程度"""

    def _build_user_prompt(
        self,
        user_input: str,
        current_slots: dict[str, object] | None = None,
        active_intent: str | None = None,
    ) -> str:
        """构造包含当前上下文的用户 prompt"""
        context_parts = []
        if active_intent:
            context_parts.append(f"当前活跃意图: {active_intent}")
        if current_slots:
            context_parts.append(f"已收集的槽位: {json.dumps(current_slots, ensure_ascii=False)}")
        context_parts.append(f"用户输入: {user_input}")
        return "\n".join(context_parts)

    async def classify(
        self,
        user_input: str,
        current_slots: dict[str, object] | None = None,
        active_intent: str | None = None,
    ) -> NLUResult:
        """对用户输入进行意图分类和槽位提取

        Args:
            user_input: 用户原始输入
            current_slots: 当前已收集的槽位（用于上下文继承）
            active_intent: 当前活跃意图（用于意图延续判断）

        Returns:
            NLUResult: 包含意图名、置信度、已提取槽位和缺失必填槽位
        """
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(
            user_input,
            current_slots or {},
            active_intent or "",
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            structured_llm = self.llm.with_structured_output(
                output_schema=NLUResult,
                # 不使用严格模式，避免 LLM 输出不符合 JSON 格式时抛出异常
                strict=False,
            )
            result = await structured_llm.ainvoke(messages)
            logger.info(
                f"意图分类: intent={result.intent}, confidence={result.confidence}, "
                f"slots={result.slots}, missing={result.missing_slots}"
            )
            return result
        except Exception as e:
            logger.error(f"意图分类失败: {e}")
            # 降级返回 unknown
            return NLUResult(
                intent="unknown",
                confidence=0.0,
                slots={},
                missing_slots=[],
            )
