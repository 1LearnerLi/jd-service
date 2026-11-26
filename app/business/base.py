"""业务层基础抽象

定义业务处理的统一接口：上下文、结果和意图处理器抽象基类。
"""
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class BusinessContext(BaseModel):
    """业务处理上下文

    封装一次意图处理所需的全部上下文信息。
    """

    session_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    intent: str = Field(..., description="当前意图名")
    slots: dict[str, object] = Field(
        default_factory=dict,
        description="已填充的槽位值",
    )


class BusinessResult(BaseModel):
    """业务处理结果

    意图处理器执行后返回的统一结果模型。
    """

    success: bool = Field(..., description="是否执行成功")
    data: object = Field(
        default=None,
        description="业务数据，传给 NLG 模板渲染",
    )
    error_message: str = Field(
        default="",
        description="错误描述",
    )


class IntentHandler(ABC):
    """意图处理器抽象基类

    每个业务意图对应一个处理器。处理器内部可以自行查询业务数据库
    来补充槽位、执行业务逻辑。
    """

    @abstractmethod
    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        """执行意图逻辑，返回业务结果"""
        ...
