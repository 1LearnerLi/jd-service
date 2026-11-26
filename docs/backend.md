# 电商智能客服系统 — 后端实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建基于 LangGraph + FastAPI + SQLAlchemy + MySQL 的可扩展智能客服后端，包含 NLU 意图识别、DM 对话管理、业务处理、NLG 回复生成和会话管理。

**Architecture:** 分层架构 — 通道层(REST+SSE) → NLU层 → DM层(LangGraph StateGraph) → 业务层 → NLG层 → 会话层。平台与业务线分离，通过注册中心和 Pydantic 模型通信。

**Tech Stack:** Python 3.14+, FastAPI, LangGraph, SQLAlchemy 2.x 异步, MySQL 8.0, Alembic, langchain-openai, pydantic-settings, loguru, pytest + httpx

## Global Constraints

- Python 环境使用 **uv** 管理（虚拟环境、依赖安装）
- 平台库 `ecs_platform` 建表通过 **Alembic** 管理，不手动执行 DDL
- 所有代码使用异步（`async def`、`AsyncSession`、`ChatOpenAI.ainvoke`）
- 日志使用 `loguru`
- 变量/文件名使用英文，注释使用中文
- 配置文件为 `.env`，使用 `pydantic-settings` 读取
- 所有层间通信使用 Pydantic 模型
- 业务线数据库连接信息不属于平台配置，由业务线自己的 `config.py` 管理
- 每个任务完成后必须通过测试才能进入下一个任务
- 默认集成分支为 `dev`，不自动合并
- 目标覆盖率 80%+

---

### Task 1: 项目初始化与依赖配置

**Files:**
- Create: `pyproject.toml`
- Create: `.env`
- Create: `app/__init__.py`

**Interfaces:**
- Produces: 项目可被 `uv sync` 安装所有依赖

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "jd-service"
version = "0.1.0"
description = "电商智能客服系统"
requires-python = ">=3.14"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "asyncmy>=0.2.0",
    "alembic>=1.14.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "langgraph>=0.2.0",
    "langchain-openai>=0.3.0",
    "langchain-core>=0.3.0",
    "jinja2>=3.1.0",
    "loguru>=0.7.0",
    "python-dotenv>=1.0.0",
    "sse-starlette>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.25.0",
    "httpx>=0.28.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 创建 .env 模板**

```env
# LLM 配置
OPENAI_API_KEY=sk-your-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# 平台数据库
PLATFORM_DATABASE_URL=mysql+asyncmy://root:123321@localhost:3307/ecs_platform

# 应用
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=INFO
```

- [ ] **Step 3: 创建 app/__init__.py**

```python
"""电商智能客服系统 — 应用包"""
```

- [ ] **Step 4: 安装依赖并验证**

```bash
uv sync --dev
```

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .env app/__init__.py
git commit -m "chore: 初始化项目依赖配置"
```

---

### Task 2: 平台配置与异常处理

**Files:**
- Create: `app/config.py`
- Create: `app/core/__init__.py`
- Create: `app/core/exceptions.py`
- Create: `app/core/response.py`

**Interfaces:**
- Produces:
  - `Settings` (pydantic BaseSettings, 读取 `.env`)
  - `AppException`, `NotFoundException`, `ValidationException`, `BusinessException`
  - `APIResponse[T]` (success, data, error, meta)
  - `success_response(data, meta)`, `error_response(error_msg)`

- [ ] **Step 1: 创建 app/config.py**

```python
"""平台级配置，从 .env 读取"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    # LLM
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    # 平台数据库
    platform_database_url: str = "mysql+asyncmy://root:123321@localhost:3307/ecs_platform"

    # 应用
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 2: 创建 app/core/exceptions.py**

```python
"""统一异常定义"""


class AppException(Exception):
    """应用基础异常"""
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundException(AppException):
    """资源未找到"""
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, status_code=404)


class ValidationException(AppException):
    """校验异常"""
    def __init__(self, message: str = "参数校验失败"):
        super().__init__(message, status_code=422)


class BusinessException(AppException):
    """业务异常"""
    def __init__(self, message: str = "业务处理失败"):
        super().__init__(message, status_code=400)
```

- [ ] **Step 3: 创建 app/core/response.py**

```python
"""统一 API 响应模型"""
from typing import Any, Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """统一响应信封"""
    success: bool = True
    data: T | None = None
    error: str | None = None
    meta: dict[str, Any] | None = None


def success_response(data: Any = None, meta: dict[str, Any] | None = None) -> dict:
    """构造成功响应"""
    return APIResponse(success=True, data=data, error=None, meta=meta).model_dump()


def error_response(error: str, status_code: int = 500) -> dict:
    """构造错误响应"""
    return APIResponse(success=False, data=None, error=error, meta=None).model_dump()
```

- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat: 添加平台配置、异常处理和统一响应模型"
```

---

### Task 3: 平台数据库引擎

**Files:**
- Create: `app/core/database.py`

**Interfaces:**
- Produces:
  - `async_engine`: 平台数据库 AsyncEngine
  - `AsyncSessionLocal`: async_sessionmaker
  - `Base`: SQLAlchemy DeclarativeBase
  - `get_db()`: FastAPI 依赖，yield AsyncSession

- [ ] **Step 1: 创建 app/core/database.py**

```python
"""平台数据库引擎 — ecs_platform"""
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

async_engine = create_async_engine(
    settings.platform_database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""
    pass


async def get_db() -> AsyncSession:
    """FastAPI 依赖：获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
```

- [ ] **Step 2: Commit**

```bash
git add app/core/database.py
git commit -m "feat: 添加平台数据库引擎"
```

---

### Task 4: 会话层 ORM 模型与 CRUD 服务

**Files:**
- Create: `app/session/__init__.py`
- Create: `app/session/models.py`
- Create: `app/session/service.py`

**Interfaces:**
- Consumes: `Base` from `app.core.database`
- Produces:
  - `Session` ORM model (id, user_id, title, status, created_at, updated_at)
  - `Message` ORM model (id, session_id, role, content, intent, slots_json, created_at)
  - `SessionService.create_session(user_id) → Session`
  - `SessionService.list_sessions(user_id, limit=10) → list[Session]`
  - `SessionService.get_session(session_id) → Session | None`
  - `MessageService.add_message(session_id, role, content, intent, slots) → Message`
  - `MessageService.list_messages(session_id) → list[Message]`

- [ ] **Step 1: 编写会话层模型测试**

```python
# tests/test_session/test_models.py
import pytest
from app.session.models import Session, Message


def test_session_model_fields():
    """验证 Session 模型字段定义"""
    assert hasattr(Session, "id")
    assert hasattr(Session, "user_id")
    assert hasattr(Session, "title")
    assert hasattr(Session, "status")
    assert hasattr(Session, "created_at")
    assert hasattr(Session, "updated_at")


def test_message_model_fields():
    """验证 Message 模型字段定义"""
    assert hasattr(Message, "id")
    assert hasattr(Message, "session_id")
    assert hasattr(Message, "role")
    assert hasattr(Message, "content")
    assert hasattr(Message, "intent")
    assert hasattr(Message, "slots_json")
    assert hasattr(Message, "created_at")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_session/test_models.py -v
```

- [ ] **Step 3: 创建 app/session/models.py**

```python
"""会话层 ORM 模型"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Session(Base):
    """会话表"""
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(
        String(50), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(
        Enum("active", "closed", name="session_status"),
        nullable=False,
        default="active",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    messages = relationship("Message", back_populates="session", lazy="selectin")


class Message(Base):
    """消息表"""
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("sessions.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(
        Enum("user", "assistant", name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    slots_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    session = relationship("Session", back_populates="messages")
```

- [ ] **Step 4: 创建 app/session/service.py**

```python
"""会话层 CRUD 服务"""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.session.models import Session, Message
from app.core.exceptions import NotFoundException


class SessionService:
    """会话管理服务"""

    @staticmethod
    async def create_session(db: AsyncSession, user_id: str) -> Session:
        """创建新会话"""
        session = Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            status="active",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        logger.info(f"创建会话: {session.id}, 用户: {user_id}")
        return session

    @staticmethod
    async def list_sessions(
        db: AsyncSession, user_id: str, limit: int = 10
    ) -> list[Session]:
        """获取用户最近会话列表，按更新时间倒序"""
        result = await db.execute(
            select(Session)
            .where(Session.user_id == user_id)
            .order_by(Session.updated_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_session(
        db: AsyncSession, session_id: str
    ) -> Session | None:
        """获取单个会话"""
        result = await db.execute(
            select(Session).where(Session.id == session_id)
        )
        return result.scalar_one_or_none()


class MessageService:
    """消息管理服务"""

    @staticmethod
    async def add_message(
        db: AsyncSession,
        session_id: str,
        role: str,
        content: str,
        intent: str | None = None,
        slots: dict | None = None,
    ) -> Message:
        """添加消息"""
        message = Message(
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
            slots_json=slots,
        )
        db.add(message)
        # 同时更新会话的 updated_at
        await db.execute(
            select(Session).where(Session.id == session_id)
        )
        await db.commit()
        await db.refresh(message)
        logger.info(f"添加消息: session={session_id}, role={role}")
        return message

    @staticmethod
    async def list_messages(
        db: AsyncSession, session_id: str
    ) -> list[Message]:
        """获取会话消息列表，按时间正序"""
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        return list(result.scalars().all())
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_session/test_models.py -v
```

- [ ] **Step 6: Commit**

```bash
git add app/session/
git commit -m "feat: 添加会话层 ORM 模型和 CRUD 服务"
```

---

### Task 5: Alembic 迁移配置

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`

**Interfaces:**
- Consumes: `Base` from `app.core.database`, `Settings` from `app.config`
- Produces: `uv run alembic revision --autogenerate` 可正常生成迁移

- [ ] **Step 1: 初始化 Alembic**

```bash
uv run alembic init alembic
```

- [ ] **Step 2: 修改 alembic.ini — 设置 sqlalchemy.url**

将 `alembic.ini` 中的 `sqlalchemy.url` 行替换为：
```ini
sqlalchemy.url = mysql+asyncmy://root:123321@localhost:3307/ecs_platform
```

- [ ] **Step 3: 修改 alembic/env.py**

```python
"""Alembic 迁移环境配置"""
import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.database import Base
from app.config import settings

# 导入所有模型，确保它们被 Base.metadata 感知
from app.session import models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.platform_database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式运行迁移"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    """在线模式运行迁移"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: 启动 MySQL 并创建平台库**

```bash
docker compose -f docker/docker-compose.yaml up -d mysql
```

- [ ] **Step 5: 生成并运行初始迁移**

```bash
uv run alembic revision --autogenerate -m "init: 创建 sessions 和 messages 表"
uv run alembic upgrade head
```

- [ ] **Step 6: Commit**

```bash
git add alembic.ini alembic/
git commit -m "chore: 配置 Alembic 数据库迁移"
```

---

### Task 6: NLU 层 — 模型与注册中心

**Files:**
- Create: `app/nlu/__init__.py`
- Create: `app/nlu/models.py`
- Create: `app/nlu/platform_intents.py`
- Create: `app/nlu/registry.py`

**Interfaces:**
- Produces:
  - `SlotDef(name, description, ask_prompt)`
  - `IntentDefinition(name, description, required_slots, optional_slots)`
  - `NLUResult(intent, confidence, slots, missing_slots)`
  - `IntentRegistry`: 注册/获取意图
  - `PLATFORM_INTENTS`: 平台预定义意图列表

- [ ] **Step 1: 编写 NLU 模型测试**

```python
# tests/test_nlu/test_models.py
from app.nlu.models import SlotDef, IntentDefinition, NLUResult


def test_slot_def_creation():
    """验证 SlotDef 创建"""
    slot = SlotDef(name="order_id", description="订单号", ask_prompt="请提供您的订单号")
    assert slot.name == "order_id"
    assert slot.ask_prompt == "请提供您的订单号"


def test_intent_definition_with_slots():
    """验证 IntentDefinition 包含槽位"""
    slots = [SlotDef(name="order_id", description="订单号", ask_prompt="请提供您的订单号")]
    intent = IntentDefinition(
        name="order_query",
        description="查询订单详情",
        required_slots=slots,
    )
    assert intent.name == "order_query"
    assert len(intent.required_slots) == 1


def test_nlu_result_serialization():
    """验证 NLUResult 序列化"""
    result = NLUResult(
        intent="order_query",
        confidence=0.95,
        slots={"order_id": "123"},
        missing_slots=[],
    )
    d = result.model_dump()
    assert d["intent"] == "order_query"
    assert d["confidence"] == 0.95
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_nlu/test_models.py -v
```

- [ ] **Step 3: 创建 app/nlu/models.py**

```python
"""NLU 层核心数据模型"""
from pydantic import BaseModel, Field


class SlotDef(BaseModel):
    """槽位定义"""
    name: str = Field(..., description="槽位名称")
    description: str = Field(..., description="槽位描述，用于 LLM 理解")
    ask_prompt: str = Field(..., description="追问提示语，用于向用户追问该槽位值")


class IntentDefinition(BaseModel):
    """意图定义"""
    name: str = Field(..., description="意图唯一名称")
    description: str = Field(..., description="意图描述，用于 LLM 分类")
    required_slots: list[SlotDef] = Field(default_factory=list)
    optional_slots: list[SlotDef] = Field(default_factory=list)


class NLUResult(BaseModel):
    """NLU 层输出"""
    intent: str = Field(..., description="识别的意图名")
    confidence: float = Field(..., description="置信度 0-1")
    slots: dict[str, object] = Field(default_factory=dict, description="已提取的槽位")
    missing_slots: list[str] = Field(default_factory=list, description="缺失的必填槽位")
```

- [ ] **Step 4: 创建 app/nlu/platform_intents.py**

```python
"""平台级意图定义 — 适用于所有业务线"""
from app.nlu.models import IntentDefinition

PLATFORM_INTENTS: list[IntentDefinition] = [
    IntentDefinition(
        name="unknown",
        description="用户输入无法匹配任何已知意图，或者表达混乱、语义不清、超出客服范围",
    ),
    IntentDefinition(
        name="transfer_human",
        description="用户明确要求转接人工客服、投诉、或者表达对AI回复的不满",
    ),
]
```

- [ ] **Step 5: 创建 app/nlu/registry.py**

```python
"""意图注册中心 — 管理所有业务线的意图"""
from app.nlu.models import IntentDefinition
from app.nlu.platform_intents import PLATFORM_INTENTS


class IntentRegistry:
    """意图注册中心（单例模式）"""

    _instance: "IntentRegistry | None" = None
    _business_intents: dict[str, list[IntentDefinition]] = {}

    def __new__(cls) -> "IntentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register_business(cls, business_name: str, intents: list[IntentDefinition]) -> None:
        """注册一个业务线的意图"""
        cls._business_intents[business_name] = intents

    @classmethod
    def get_all_intents(cls) -> list[IntentDefinition]:
        """获取所有意图（平台意图 + 所有已注册业务意图）"""
        all_intents = list(PLATFORM_INTENTS)
        for intents in cls._business_intents.values():
            all_intents.extend(intents)
        return all_intents

    @classmethod
    def get_intent_by_name(cls, name: str) -> IntentDefinition | None:
        """按名称查找意图"""
        for intent in cls.get_all_intents():
            if intent.name == name:
                return intent
        return None

    @classmethod
    def get_required_slot_names(cls, intent_name: str) -> list[str]:
        """获取某个意图的所有必填槽位名称"""
        intent = cls.get_intent_by_name(intent_name)
        if intent is None:
            return []
        return [s.name for s in intent.required_slots]

    @classmethod
    def clear(cls) -> None:
        """清空注册中心（用于测试）"""
        cls._business_intents = {}
```

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_nlu/test_models.py -v
```

- [ ] **Step 7: Commit**

```bash
git add app/nlu/ tests/test_nlu/
git commit -m "feat: 添加 NLU 层模型和意图注册中心"
```

---

### Task 7: NLU 层 — 意图分类器

**Files:**
- Create: `app/nlu/classifier.py`

**Interfaces:**
- Consumes: `IntentRegistry`, `ChatOpenAI` from `app.llm.client`
- Produces: `IntentClassifier.classify(user_input, current_slots, active_intent) → NLUResult`

- [ ] **Step 1: 创建 app/nlu/classifier.py**

```python
"""意图分类器 — 基于 LLM prompt 进行意图识别和槽位提取"""
import json

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from app.nlu.models import NLUResult, IntentDefinition
from app.nlu.registry import IntentRegistry
from app.config import settings


class IntentClassifier:
    """LLM 驱动的意图分类器"""

    def __init__(self, llm: ChatOpenAI | None = None):
        self._llm = llm
        self._registry = IntentRegistry()

    @property
    def llm(self) -> ChatOpenAI:
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

## 规则
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
        context = []
        if active_intent:
            context.append(f"当前活跃意图: {active_intent}")
        if current_slots:
            context.append(f"已收集的槽位: {json.dumps(current_slots, ensure_ascii=False)}")
        context.append(f"用户输入: {user_input}")
        return "\n".join(context)

    async def classify(
        self,
        user_input: str,
        current_slots: dict[str, object] | None = None,
        active_intent: str | None = None,
    ) -> NLUResult:
        """分类用户输入，返回 NLUResult"""
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(user_input, current_slots, active_intent)

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            content = response.content.strip()
            # 去掉可能的 markdown code block 包裹
            if content.startswith("```"):
                content = content.split("\n", 1)
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            data = json.loads(content)
            result = NLUResult(**data)
            logger.info(
                f"意图分类: intent={result.intent}, confidence={result.confidence}, "
                f"slots={result.slots}, missing={result.missing_slots}"
            )
            return result
        except Exception as e:
            logger.error(f"意图分类失败: {e}")
            # 降级返回 unknown
            return NLUResult(intent="unknown", confidence=0.0, slots={}, missing_slots=[])
```

- [ ] **Step 2: Commit**

```bash
git add app/nlu/classifier.py
git commit -m "feat: 添加 LLM 驱动的意图分类器"
```

---

### Task 8: LLM 客户端封装

**Files:**
- Create: `app/llm/__init__.py`
- Create: `app/llm/client.py`

**Interfaces:**
- Produces: `get_llm() → ChatOpenAI` (单例工厂函数)

- [ ] **Step 1: 创建 app/llm/client.py**

```python
"""LLM 客户端封装"""
from langchain_openai import ChatOpenAI

from app.config import settings

_llm_instance: ChatOpenAI | None = None


def get_llm(temperature: float = 0.1) -> ChatOpenAI:
    """获取 ChatOpenAI 实例（单例模式）"""
    global _llm_instance
    if _llm_instance is None:
        _llm_instance = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=temperature,
        )
    return _llm_instance
```

- [ ] **Step 2: Commit**

```bash
git add app/llm/
git commit -m "feat: 添加 LLM 客户端封装"
```

---

### Task 9: 业务层 — 基础抽象

**Files:**
- Create: `app/business/__init__.py`
- Create: `app/business/base.py`

**Interfaces:**
- Produces:
  - `BusinessContext(session_id, user_id, intent, slots)`
  - `BusinessResult(success, data, error_message)` + 三个工厂方法
  - `OptionItem(label, value, disabled=False)` — 统一选项条目
  - `IntentHandler.handle(ctx) → BusinessResult` (抽象类)

**工厂方法（`BusinessResult` 类方法）：**
- `BusinessResult.ask_slot(slot_to_fill, options, message)` — 需要用户选择一个槽位值，返回统一 `ask_slot` 结构
- `BusinessResult.completed(message, **extra)` — 业务处理完成，extra 合并到 data
- `BusinessResult.error(message)` — 业务处理失败

**`ask_slot` 统一 data 结构：**
```json
{
    "action": "ask_slot",
    "message": "提示文字",
    "slot_to_fill": "要填充的槽位名",
    "options": [
        {"label": "展示文字", "value": "回传值", "disabled": false}
    ]
}
```

- [ ] **Step 1: 创建 app/business/base.py**

```python
"""业务层基础抽象"""
from abc import ABC, abstractmethod
from pydantic import BaseModel, Field


class BusinessContext(BaseModel):
    """业务处理上下文"""
    session_id: str = Field(..., description="会话 ID")
    user_id: str = Field(..., description="用户 ID")
    intent: str = Field(..., description="当前意图名")
    slots: dict[str, object] = Field(default_factory=dict, description="已填充的槽位值")


class BusinessResult(BaseModel):
    """业务处理结果"""
    success: bool = Field(..., description="是否执行成功")
    data: object = Field(default=None, description="业务数据，传给 NLG 模板渲染")
    error_message: str = Field(default="", description="错误描述")


class IntentHandler(ABC):
    """意图处理器抽象基类
    
    每个业务意图对应一个处理器。处理器内部可以自行查询业务数据库
    来补充槽位、执行业务逻辑。
    """

    @abstractmethod
    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        """执行意图逻辑，返回业务结果"""
        ...
```

- [ ] **Step 2: Commit**

```bash
git add app/business/
git commit -m "feat: 添加业务层基础抽象"
```

---

### Task 10: 电商业务线 — 配置与 ORM 模型

**Files:**
- Create: `app/business/ecommerce/__init__.py`
- Create: `app/business/ecommerce/config.py`
- Create: `app/business/ecommerce/models/__init__.py`
- Create: `app/business/ecommerce/models/order.py`
- Create: `app/business/ecommerce/repository/__init__.py`
- Create: `app/business/ecommerce/repository/order_repo.py`

**Interfaces:**
- Consumes: `Settings` pattern, SQLAlchemy async
- Produces:
  - `EcommerceSettings(eco_database_url)`
  - `OrderInfo`, `OrderDetail` ORM models (映射已有 `ecs` 库表)
  - `OrderRepo`: 订单相关数据查询

- [ ] **Step 1: 创建 app/business/ecommerce/config.py**

```python
"""电商业务线数据库配置"""
from pydantic_settings import BaseSettings


class EcommerceSettings(BaseSettings):
    """电商业务数据库配置"""
    eco_database_url: str = "mysql+asyncmy://root:123321@localhost:3307/ecs"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


ecommerce_settings = EcommerceSettings()
```

- [ ] **Step 2: 创建 app/business/ecommerce/models/order.py**

```python
"""电商业务 ORM 模型 — 映射已有 ecs 库中的表"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Integer, Numeric, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class EcommerceBase(DeclarativeBase):
    """电商业务线 ORM 基类（独立于平台库 Base）"""
    pass


class OrderInfo(EcommerceBase):
    """订单信息表 — 映射 order_info"""
    __tablename__ = "order_info"

    order_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    create_time: Mapped[datetime] = mapped_column(DateTime)
    payment_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    delivered_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    complete_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("user_info.user_id"))
    receive_id: Mapped[str] = mapped_column(String(50), ForeignKey("receive_info.receive_id"))
    order_status: Mapped[str] = mapped_column(String(20), ForeignKey("order_status.order_status"))

    details = relationship("OrderDetail", back_populates="order", lazy="selectin")


class OrderDetail(EcommerceBase):
    """订单明细表 — 映射 order_detail"""
    __tablename__ = "order_detail"

    order_detail_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(50), ForeignKey("order_info.order_id"))
    sku_id: Mapped[str] = mapped_column(String(50), ForeignKey("sku_info.sku_id"))
    sku_name: Mapped[str] = mapped_column(String(100))
    sku_count: Mapped[int] = mapped_column(Integer)
    total_amount: Mapped[float] = mapped_column(Numeric(10, 2))
    discount_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0.00)
    final_amount: Mapped[float] = mapped_column(Numeric(10, 2))

    order = relationship("OrderInfo", back_populates="details")


class SkuInfo(EcommerceBase):
    """商品信息表 — 映射 sku_info"""
    __tablename__ = "sku_info"

    sku_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    sku_name: Mapped[str] = mapped_column(String(100))
    sku_price: Mapped[float] = mapped_column(Numeric(10, 2))
    sku_category: Mapped[str] = mapped_column(String(20))
    sku_count: Mapped[int] = mapped_column(Integer)
```

- [ ] **Step 3: 创建 app/business/ecommerce/repository/order_repo.py**

```python
"""订单数据访问层"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from loguru import logger

from app.business.ecommerce.config import ecommerce_settings
from app.business.ecommerce.models.order import EcommerceBase, OrderInfo, OrderDetail, SkuInfo

# 电商业务线独立的数据库引擎
eco_engine = create_async_engine(
    ecommerce_settings.eco_database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
)

EcoSessionLocal = async_sessionmaker(
    bind=eco_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class OrderRepo:
    """订单数据仓库"""

    async def get_orders_by_user(
        self, user_id: str, limit: int = 10
    ) -> list[OrderInfo]:
        """查询用户最近的订单"""
        async with EcoSessionLocal() as db:
            result = await db.execute(
                select(OrderInfo)
                .where(OrderInfo.user_id == user_id)
                .order_by(OrderInfo.create_time.desc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def get_order_by_id(self, order_id: str) -> OrderInfo | None:
        """按订单 ID 查询订单（含明细）"""
        async with EcoSessionLocal() as db:
            result = await db.execute(
                select(OrderInfo).where(OrderInfo.order_id == order_id)
            )
            return result.scalar_one_or_none()

    async def get_order_detail_by_order(
        self, order_id: str
    ) -> list[OrderDetail]:
        """查询订单的所有明细"""
        async with EcoSessionLocal() as db:
            result = await db.execute(
                select(OrderDetail).where(OrderDetail.order_id == order_id)
            )
            return list(result.scalars().all())

    async def get_sku_by_id(self, sku_id: str) -> SkuInfo | None:
        """按 SKU ID 查询商品信息"""
        async with EcoSessionLocal() as db:
            result = await db.execute(
                select(SkuInfo).where(SkuInfo.sku_id == sku_id)
            )
            return result.scalar_one_or_none()
```

- [ ] **Step 4: Commit**

```bash
git add app/business/ecommerce/
git commit -m "feat: 添加电商业务线配置、ORM 和数据仓库"
```

---

### Task 11: 电商业务线 — 意图注册与处理器

**Files:**
- Create: `app/business/ecommerce/intents.py`
- Create: `app/business/ecommerce/handlers/__init__.py`
- Create: `app/business/ecommerce/handlers/order_query.py`
- Create: `app/business/ecommerce/handlers/postsale_return.py`

**Interfaces:**
- Consumes: `IntentRegistry`, `IntentHandler`, `BusinessContext`, `BusinessResult`, `OptionItem`, `OrderRepo`
- Produces:
  - `ECOMMERCE_INTENTS`: 电商业务线意图定义（3 个意图，每个意图的 required_slots 逐槽位驱动）
  - `OrderQueryHandler.handle(ctx) → BusinessResult` — 槽位驱动：order_id 缺失时返回 ask_slot（最近 5 条订单列表），齐全后查询并返回 completed
  - `PostsaleReturnHandler.handle(ctx) → BusinessResult` — 三槽位驱动：order_id → postsale_type → postsale_reason 逐项追问，全齐后 update_order_status("售后中") 并返回 completed

**意图定义（最终版本）：**

| 意图 | required_slots | 说明 |
|------|---------------|------|
| `order_query` | `order_id` | order_id 缺失时返回最近 5 条订单让用户选 |
| `postsale_return` | `order_id`, `postsale_type`, `postsale_reason` | 逐槽位追问，可售后状态：已付款/已发货/已签收 |
| `product_inquiry` | `query` | 用户原问题作为槽位值 |

**槽位驱动流程（以 postsale_return 为例）：**

```
handle(ctx)
  ├─ slots 中无 order_id       → ask_slot("order_id", [最近5条订单], "请选择订单")
  ├─ slots 中无 postsale_type  → ask_slot("postsale_type", [{仅退款, 退货退款}], "请选择方式")
  ├─ slots 中无 postsale_reason → ask_slot("postsale_reason", [6个原因], "请选择原因")
  └─ 三槽位齐全                → 校验订单 → update_order_status("售后中") → completed("售后已提交", ...)
```

**order_query 同样采用槽位驱动**：order_id 缺失时不再返回错误，而是返回 `ask_slot` 让用户选择订单。

- [ ] **Step 1: 创建 app/business/ecommerce/intents.py**

```python
"""电商业务线意图定义"""
from app.nlu.models import IntentDefinition, SlotDef

ECOMMERCE_INTENTS: list[IntentDefinition] = [
    IntentDefinition(
        name="order_query",
        description="用户查询自己的订单详情、订单状态或订单信息",
        required_slots=[
            SlotDef(
                name="order_id",
                description="订单号",
                ask_prompt="请选择要查询的订单",
            ),
        ],
    ),
    IntentDefinition(
        name="postsale_return",
        description="用户申请退货退款或售后退款",
        required_slots=[
            SlotDef(
                name="order_id",
                description="订单号",
                ask_prompt="请选择要申请售后的订单",
            ),
            SlotDef(
                name="postsale_type",
                description="售后类型：仅退款或退货退款",
                ask_prompt="请选择售后方式",
            ),
            SlotDef(
                name="postsale_reason",
                description="售后原因",
                ask_prompt="请选择售后原因",
            ),
        ],
    ),
    IntentDefinition(
        name="product_inquiry",
        description="用户咨询商品信息，包括商品价格、规格、库存、使用说明等",
        required_slots=[
            SlotDef(
                name="query",
                description="用户的原始问题",
                ask_prompt="请问您想了解什么商品信息？",
            ),
        ],
    ),
]
```

- [ ] **Step 2: 创建 app/business/ecommerce/handlers/order_query.py**

```python
"""订单查询意图处理器"""
from loguru import logger

from app.business.base import (
    IntentHandler,
    BusinessContext,
    BusinessResult,
    OptionItem,
)


class OrderQueryHandler(IntentHandler):
    """订单查询处理器 — 槽位驱动"""

    def __init__(self, repo=None):
        from app.business.ecommerce.repository.order_repo import OrderRepo
        self._repo = repo if repo is not None else OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        order_id = str(ctx.slots.get("order_id", ""))
        if not order_id:
            return await self._ask_for_order(ctx)
        return await self._query(ctx)

    async def _ask_for_order(self, ctx: BusinessContext) -> BusinessResult:
        """order_id 缺失：返回最近订单列表"""
        try:
            orders = await self._repo.get_orders_by_user(ctx.user_id, limit=5)
            options = [
                OptionItem(
                    label=f"{o.order_id}（{o.order_status}）",
                    value=o.order_id,
                )
                for o in orders
            ]
            return BusinessResult.ask_slot(
                slot_to_fill="order_id",
                options=options,
                message="请选择要查询的订单",
            )
        except Exception as e:
            logger.error(f"查询用户订单失败: {e}")
            return BusinessResult.error("查询订单时出现错误，请稍后重试")

    async def _query(self, ctx: BusinessContext) -> BusinessResult:
        """order_id 齐全：查询订单详情"""
        order_id = str(ctx.slots.get("order_id", ""))
        try:
            order = await self._repo.get_order_by_id(order_id)
            if order is None:
                return BusinessResult.error(
                    f"订单 {order_id} 不存在，请确认订单号是否正确"
                )
            details = await self._repo.get_order_detail_by_order(order_id)
            detail_list = []
            for d in details:
                sku = await self._repo.get_sku_by_id(d.sku_id)
                detail_list.append({
                    "sku_id": d.sku_id,
                    "sku_name": d.sku_name,
                    "sku_count": d.sku_count,
                    "unit_price": float(sku.sku_price) if sku else 0,
                    "total_amount": float(d.total_amount),
                    "discount_amount": float(d.discount_amount),
                    "final_amount": float(d.final_amount),
                })
            order_data = {
                "order_id": order.order_id,
                "order_status": order.order_status,
                "create_time": order.create_time.isoformat() if order.create_time else "",
                "payment_time": order.payment_time.isoformat() if order.payment_time else "",
                "delivered_time": order.delivered_time.isoformat() if order.delivered_time else "",
                "details": detail_list,
            }
            logger.info(f"订单查询成功: {order_id}")
            return BusinessResult.completed(
                message=f"📋 订单 {order_id} 详情已加载",
                **order_data,
            )
        except Exception as e:
            logger.error(f"订单查询失败: {e}")
            return BusinessResult.error("查询订单时出现错误，请稍后重试")
```

- [ ] **Step 3: 创建 app/business/ecommerce/handlers/postsale_return.py**

```python
"""售后申请意图处理器 — 三槽位逐槽位驱动"""
from loguru import logger

from app.business.base import (
    IntentHandler,
    BusinessContext,
    BusinessResult,
    OptionItem,
)

_REFUNDABLE_STATUSES = frozenset({"已付款", "已发货", "已签收"})

_POSTSALE_TYPES = {
    "refund_only": "仅退款",
    "return_refund": "退货退款",
}

_POSTSALE_REASONS = [
    "7天无理由",
    "商品瑕疵/破损",
    "发错货",
    "商品与描述不符",
    "质量问题",
    "不喜欢/不想要了",
]


class PostsaleReturnHandler(IntentHandler):
    """售后申请处理器"""

    def __init__(self, repo=None):
        from app.business.ecommerce.repository.order_repo import OrderRepo
        self._repo = repo if repo is not None else OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        slots = ctx.slots

        if not slots.get("order_id"):
            return await self._ask_for_order(ctx)
        if not slots.get("postsale_type"):
            order_check = await self._check_order(ctx)
            if not order_check.success:
                return order_check
            return self._ask_for_type()
        if not slots.get("postsale_reason"):
            return self._ask_for_reason()

        return await self._execute(ctx)

    async def _ask_for_order(self, ctx: BusinessContext) -> BusinessResult:
        try:
            orders = await self._repo.get_orders_by_user(ctx.user_id, limit=5)
            options = [
                OptionItem(
                    label=f"{o.order_id}（{o.order_status}）",
                    value=o.order_id,
                    disabled=o.order_status not in _REFUNDABLE_STATUSES,
                )
                for o in orders
            ]
            return BusinessResult.ask_slot(
                slot_to_fill="order_id",
                options=options,
                message="请选择要申请售后的订单",
            )
        except Exception as e:
            logger.error(f"查询用户订单失败: {e}")
            return BusinessResult.error("查询订单时出现错误，请稍后重试")

    def _ask_for_type(self) -> BusinessResult:
        options = [OptionItem(label=v, value=k) for k, v in _POSTSALE_TYPES.items()]
        return BusinessResult.ask_slot(
            slot_to_fill="postsale_type",
            options=options,
            message="请选择售后方式",
        )

    def _ask_for_reason(self) -> BusinessResult:
        options = [OptionItem(label=r, value=r) for r in _POSTSALE_REASONS]
        return BusinessResult.ask_slot(
            slot_to_fill="postsale_reason",
            options=options,
            message="请选择售后原因",
        )

    async def _check_order(self, ctx: BusinessContext) -> BusinessResult:
        order_id = str(ctx.slots.get("order_id", ""))
        try:
            order = await self._repo.get_order_by_id(order_id)
            if order is None:
                return BusinessResult.error(f"订单 {order_id} 不存在，请确认订单号")
            if order.user_id != ctx.user_id:
                return BusinessResult.error("该订单不属于当前用户")
            if order.order_status not in _REFUNDABLE_STATUSES:
                return BusinessResult.error(
                    f"订单状态为「{order.order_status}」，"
                    f"仅已付款/已发货/已签收的订单可申请售后"
                )
            return BusinessResult(success=True)
        except Exception as e:
            logger.error(f"校验订单失败: {e}")
            return BusinessResult.error("查询订单时出现错误，请稍后重试")

    async def _execute(self, ctx: BusinessContext) -> BusinessResult:
        order_id = str(ctx.slots.get("order_id", ""))
        postsale_type = str(ctx.slots.get("postsale_type", "refund_only"))
        postsale_reason = str(ctx.slots.get("postsale_reason", ""))

        if postsale_type not in _POSTSALE_TYPES:
            return BusinessResult.error(f"不支持的售后方式: {postsale_type}")

        order_check = await self._check_order(ctx)
        if not order_check.success:
            return order_check

        try:
            await self._repo.update_order_status(order_id, "售后中")
            type_label = _POSTSALE_TYPES[postsale_type]
            logger.info(f"售后完成: 订单={order_id}, 方式={type_label}, 原因={postsale_reason}")
            return BusinessResult.completed(
                message=(
                    f"售后申请已提交！\n"
                    f"订单号：{order_id}\n"
                    f"售后方式：{type_label}\n"
                    f"售后原因：{postsale_reason}\n"
                    f"当前状态：售后中"
                ),
                order_id=order_id,
                postsale_type=type_label,
                postsale_reason=postsale_reason,
                new_status="售后中",
            )
        except Exception as e:
            logger.error(f"售后执行失败: {e}")
            return BusinessResult.error("处理售后申请时出现错误，请稍后重试")
```

- [ ] **Step 4: Commit**

```bash
git add app/business/ecommerce/intents.py app/business/ecommerce/handlers/
git commit -m "feat: 添加电商业务线意图注册和槽位驱动处理器"
```

---

### Task 12: NLG 层 — 模板引擎与 LLM 生成器

**Files:**
- Create: `app/nlg/__init__.py`
- Create: `app/nlg/template_engine.py`
- Create: `app/nlg/llm_generator.py`
- Create: `app/nlg/engine.py`
- Create: `app/business/ecommerce/templates/order_query.j2`
- Create: `app/business/ecommerce/templates/postsale_return.j2`

**设计原则：**
- **槽位追问不使用模板**：`BusinessResult.ask_slot()` 已定义固定数据结构（`action`、`message`、`slot_to_fill`、`options`），前端据此渲染选项按钮，无需 Jinja2 模板。
- **模板归属业务线**：业务相关的模板（如 `order_query.j2`）放在 `business/ecommerce/templates/` 下，不放在平台级 `app/nlg/templates/`。
- **模板引擎输出只作为 message**：所有模板渲染出的文本只能作为 `BusinessResult` 中的 `message` 字段内容，由业务 Handler 负责调用模板引擎渲染；NLGEngine 不直接渲染模板并返回给前端。

**Interfaces:**
- Consumes: `BusinessResult`, `ChatOpenAI`
- Produces:
  - `TemplateEngine(template_dir).render(template_name, context) → str` — 供业务 Handler 调用，渲染 message
  - `LLMGenerator.generate(user_input) → str` — 闲聊/兜底场景
  - `NLGEngine.generate(intent, business_result, context) → str` — 统一入口

- [ ] **Step 1: 创建业务线模板文件**

`app/business/ecommerce/templates/order_query.j2`:
```jinja2
📋 **订单详情**

订单号：{{ data.order_id }}
状态：{{ data.order_status }}
创建时间：{{ data.create_time }}
{% if data.payment_time %}支付时间：{{ data.payment_time }}{% endif %}
{% if data.delivered_time %}签收时间：{{ data.delivered_time }}{% endif %}

{% if data.details %}
**商品明细：**
{% for item in data.details %}
{{ loop.index }}. {{ item.sku_name }} × {{ item.sku_count }}
   单价：¥{{ "%.2f"|format(item.unit_price) }} ｜ 实付：¥{{ "%.2f"|format(item.final_amount) }}
{% endfor %}
{% endif %}
```

`app/business/ecommerce/templates/postsale_return.j2`:
```jinja2
📦 **售后申请 — {{ data.order_id }}**

订单状态：{{ data.order_status }}

可申请售后的商品：
{% for item in data.items %}
{{ loop.index }}. {{ item.sku_name }}（编号：{{ item.sku_id }}）
   数量：{{ item.sku_count }} ｜ 实付：¥{{ "%.2f"|format(item.final_amount) }}
{% endfor %}

请问您想对哪个商品申请售后？请告诉我商品编号。
```

> **注意**：不再需要 `app/nlg/templates/slot_filling.j2`（槽位追问使用 `BusinessResult.ask_slot()` 固定结构）和 `app/nlg/templates/transfer_human.j2`（消息简短，直接硬编码）。

- [ ] **Step 2: 创建 app/nlg/template_engine.py**

```python
"""Jinja2 模板引擎 — 供业务 Handler 渲染 message 使用"""
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from loguru import logger


class TemplateEngine:
    """模板引擎 — 用于需要精确数据的场景（由业务 Handler 调用）"""

    def __init__(self, template_dir: str):
        """初始化模板引擎

        Args:
            template_dir: 模板目录的绝对路径，由调用方（业务 Handler）指定。
                          例如：Path(__file__).parent.parent / "templates"
        """
        self._env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=False,
        )

    async def render(self, template_name: str, context: dict) -> str:
        """渲染模板，返回字符串供业务 Handler 填入 BusinessResult.message"""
        try:
            template = self._env.get_template(template_name)
            result = template.render(**context)
            logger.info(f"模板渲染成功: {template_name}")
            return result
        except TemplateNotFound:
            logger.error(f"模板未找到: {template_name}")
            return "抱歉，系统遇到了一些问题，请稍后重试。"
        except Exception as e:
            logger.error(f"模板渲染失败: {e}")
            return "抱歉，回复生成失败，请稍后重试。"
```

- [ ] **Step 3: 创建 app/nlg/llm_generator.py**

```python
"""LLM 回复生成器"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from loguru import logger

from app.config import settings


class LLMGenerator:
    """LLM 生成器 — 用于闲聊/兜底场景"""

    def __init__(self, llm: ChatOpenAI | None = None):
        self._llm = llm

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                temperature=0.7,
            )
        return self._llm

    async def generate(self, user_input: str) -> str:
        """生成自然语言回复"""
        try:
            messages = [
                SystemMessage(
                    content="你是一个电商客服助手，请用中文回复用户。回复要友好、简洁、有帮助。"
                ),
                HumanMessage(content=user_input),
            ]
            response = await self.llm.ainvoke(messages)
            result = response.content.strip()
            logger.info("LLM 回复生成成功")
            return result
        except Exception as e:
            logger.error(f"LLM 回复生成失败: {e}")
            return "抱歉，我现在无法回答这个问题。请问还有其他可以帮助您的吗？"
```

- [ ] **Step 4: 创建 app/nlg/engine.py**

```python
"""NLG 引擎 — 根据意图和业务结果路由到合适的生成策略"""
from app.nlg.llm_generator import LLMGenerator
from app.business.base import BusinessResult


class NLGEngine:
    """NLG 生成引擎

    职责：根据 intent 和 business_result 决定回复内容。
    - 有 BusinessResult 时直接使用其 message（由业务 Handler 已渲染好）
    - 兜底/unknown 时使用 LLM 生成
    - 转人工时返回固定文案

    注意：模板渲染由业务 Handler 负责，NLGEngine 不直接调用 TemplateEngine。
    """

    def __init__(self):
        self._llm = LLMGenerator()

    async def generate(
        self,
        intent: str,
        business_result: BusinessResult | None = None,
        context: dict | None = None,
    ) -> str:
        """根据意图和业务结果生成回复"""
        context = context or {}

        # 有业务结果 → 直接使用已渲染好的 message（含 ask_slot / completed / error）
        if business_result is not None:
            return business_result.message

        # 转人工 → 固定文案
        if intent == "transfer_human":
            return "正在为您转接人工客服，请稍候..."

        # 兜底 / unknown → LLM 自由生成
        return await self._llm.generate(context.get("user_input", ""))
```

- [ ] **Step 5: Commit**

```bash
git add app/nlg/ app/business/ecommerce/templates/
git commit -m "feat: 添加 NLG 层模板引擎和 LLM 生成器"
```

---

### Task 13: DM 层 — 状态定义与图构建

**设计说明：** 槽位填充由业务 Handler 通过 `BusinessResult.ask_slot()` 处理（Handler 内部检查槽位，缺失时返回选项列表），DM 图无需独立的 `slot_filling` 节点。简化后的节点流程：

```
entry → nlu → [条件路由]
  ├─ 平台意图 (unknown/transfer_human) → fallback → response
  └─ 业务意图 → business → response
```

**Files:**
- Create: `app/dm/__init__.py`
- Create: `app/dm/state.py`
- Create: `app/dm/router.py`
- Create: `app/dm/nodes/__init__.py`
- Create: `app/dm/nodes/nlu_node.py`
- Create: `app/dm/nodes/business_node.py`
- Create: `app/dm/nodes/response_node.py`
- Create: `app/dm/nodes/fallback_node.py`
- Create: `app/dm/graph.py`

**Interfaces:**
- Consumes: `IntentClassifier`, `IntentRegistry`, `NLGEngine`, `IntentHandler` handlers
- Produces: `build_dialog_graph() → CompiledStateGraph`

- [ ] **Step 1: 创建 app/dm/state.py**

```python
"""DM 层 DialogState 定义"""
from typing import Any, TypedDict


class IntentContext(TypedDict):
    """意图上下文"""
    name: str
    confidence: float
    required_slots: list[str]
    optional_slots: list[str]


class DialogState(TypedDict):
    """对话状态"""
    session_id: str
    user_id: str
    user_input: str
    intents: dict[str, IntentContext]
    active_intent: str
    slots: dict[str, object]
    missing_slots: list[str]
    business_result: object      # BusinessResult | None，由业务节点产出
    final_response: str
    should_fallback: bool
```

> **注意**：`missing_slots` 仍由 NLU 节点产出，供业务 Handler 的 `BusinessContext` 使用；回复统一通过 `business_result.message` 返回，不需要单独的 `pending_ask` 字段。

- [ ] **Step 2: 创建 app/dm/router.py**

```python
"""DM 层条件路由"""


def is_platform_intent(state: dict) -> bool:
    """判断当前活跃意图是否为平台意图"""
    active = state.get("active_intent", "")
    return active in ("unknown", "transfer_human")
```

> **注意**：`are_slots_filled` 不再需要——槽位检查由业务 Handler 内部完成，DM 图只做平台/业务意图的二选一路由。

- [ ] **Step 3: 创建 DM 各节点**

`app/dm/nodes/nlu_node.py`:
```python
"""NLU 节点 — 调用意图分类器"""
from loguru import logger

from app.nlu.classifier import IntentClassifier

_classifier: IntentClassifier | None = None


def get_classifier() -> IntentClassifier:
    global _classifier
    if _classifier is None:
        _classifier = IntentClassifier()
    return _classifier


async def nlu_node(state: dict) -> dict:
    """NLU 节点：对用户输入进行意图识别和槽位提取"""
    user_input = state.get("user_input", "")
    current_slots = state.get("slots", {})
    active_intent = state.get("active_intent", "")

    classifier = get_classifier()
    result = await classifier.classify(
        user_input=user_input,
        current_slots=current_slots,
        active_intent=active_intent,
    )

    logger.info(f"NLU 节点输出: intent={result.intent}, confidence={result.confidence}")

    return {
        "active_intent": result.intent,
        "slots": {**current_slots, **result.slots},
        "missing_slots": result.missing_slots,
        "should_fallback": result.intent in ("unknown", "transfer_human"),
    }
```

`app/dm/nodes/business_node.py`:
```python
"""业务节点 — 调用业务线的意图处理器"""
from loguru import logger

from app.business.base import BusinessContext, BusinessResult
from app.business.ecommerce.handlers.order_query import OrderQueryHandler
from app.business.ecommerce.handlers.postsale_return import PostsaleReturnHandler

# 意图 → 处理器映射
_handler_map = {
    "order_query": OrderQueryHandler,
    "postsale_return": PostsaleReturnHandler,
}


async def business_node(state: dict) -> dict:
    """执行业务意图

    Handler 内部按 required_slots 顺序逐槽位检查：
    - 缺失 → 返回 BusinessResult.ask_slot()（含 options 列表供前端渲染）
    - 齐全 → 执行并返回 BusinessResult.completed()
    - 失败 → 返回 BusinessResult.error()
    """
    active_intent = state.get("active_intent", "")

    handler_cls = _handler_map.get(active_intent)
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

    logger.info(f"业务节点执行: intent={active_intent}, action={result.action}")
    return {"business_result": result}
```

`app/dm/nodes/fallback_node.py`:
```python
"""兜底节点 — 处理平台意图"""
from loguru import logger


async def fallback_node(state: dict) -> dict:
    """处理 unknown 和 transfer_human 意图"""
    active_intent = state.get("active_intent", "unknown")

    if active_intent == "transfer_human":
        logger.info("触发转人工")
    else:
        logger.info("触发 unknown 兜底")

    return {"should_fallback": True}
```

`app/dm/nodes/response_node.py`:
```python
"""回复生成节点 — 调用 NLG 引擎"""
from app.nlg.engine import NLGEngine

_engine: NLGEngine | None = None


def get_engine() -> NLGEngine:
    global _engine
    if _engine is None:
        _engine = NLGEngine()
    return _engine


async def response_node(state: dict) -> dict:
    """生成最终回复

    NLGEngine.generate() 逻辑：
    - 有 business_result → 直接使用 business_result.message
    - should_fallback + transfer_human → 硬编码文案
    - 其他兜底 → LLM 自由生成
    """
    intent = state.get("active_intent", "unknown")
    business_result = state.get("business_result")
    should_fallback = state.get("should_fallback", False)
    user_input = state.get("user_input", "")

    engine = get_engine()
    response_text = await engine.generate(
        intent=intent,
        business_result=business_result,
        context={"user_input": user_input} if should_fallback else None,
    )
    return {"final_response": response_text}
```

- [ ] **Step 4: 创建 app/dm/graph.py**

```python
"""LangGraph 对话图构建"""
from langgraph.graph import StateGraph, END

from app.dm.state import DialogState
from app.dm.router import is_platform_intent
from app.dm.nodes.nlu_node import nlu_node
from app.dm.nodes.business_node import business_node
from app.dm.nodes.response_node import response_node
from app.dm.nodes.fallback_node import fallback_node


def build_dialog_graph() -> StateGraph:
    """构建对话状态图

    节点流程：
    entry → nlu → [平台意图 → fallback | 业务意图 → business] → response → END
    """
    workflow = StateGraph(DialogState)

    # 添加节点
    workflow.add_node("nlu", nlu_node)
    workflow.add_node("business", business_node)
    workflow.add_node("response", response_node)
    workflow.add_node("fallback", fallback_node)

    # 设置入口
    workflow.set_entry_point("nlu")

    # NLU 后的条件路由：平台意图走 fallback，业务意图走 business
    workflow.add_conditional_edges(
        "nlu",
        lambda state: "fallback" if is_platform_intent(state) else "business",
        {
            "fallback": "fallback",
            "business": "business",
        },
    )

    # business / fallback 都走向 response
    workflow.add_edge("business", "response")
    workflow.add_edge("fallback", "response")
    workflow.add_edge("response", END)

    return workflow.compile()
```

- [ ] **Step 5: Commit**

```bash
git add app/dm/
git commit -m "feat: 添加 DM 层 LangGraph 对话状态机"
```

---

### Task 14: API 层 — REST 端点

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/v1/__init__.py`
- Create: `app/api/v1/router.py`
- Create: `app/api/v1/chat.py`

**Interfaces:**
- Consumes: `SessionService`, `MessageService`, `build_dialog_graph()`, `get_db()`
- Produces:
  - `POST /api/v1/sessions` — 创建会话
  - `GET /api/v1/sessions` — 会话列表
  - `GET /api/v1/sessions/{session_id}` — 会话详情+消息
  - `POST /api/v1/sessions/{session_id}/messages` — 发送消息（SSE 流式返回）

- [ ] **Step 1: 创建 app/api/v1/chat.py**

```python
"""会话与消息 API 端点"""
import json
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from app.core.database import get_db
from app.core.exceptions import NotFoundException, ValidationException
from app.core.response import success_response, error_response
from app.session.service import SessionService, MessageService
from app.dm.graph import build_dialog_graph

router = APIRouter(prefix="/sessions", tags=["会话管理"])


@router.post("")
async def create_session(
    user_id: str = Query(..., description="用户 ID"),
    db: AsyncSession = Depends(get_db),
):
    """创建新会话"""
    session = await SessionService.create_session(db, user_id)
    return success_response(
        data={
            "id": session.id,
            "user_id": session.user_id,
            "title": session.title,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }
    )


@router.get("")
async def list_sessions(
    user_id: str = Query(..., description="用户 ID"),
    db: AsyncSession = Depends(get_db),
):
    """获取会话列表（最多 10 个）"""
    sessions = await SessionService.list_sessions(db, user_id, limit=10)
    data = [
        {
            "id": s.id,
            "user_id": s.user_id,
            "title": s.title,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
        }
        for s in sessions
    ]
    return success_response(data=data)


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取会话详情及消息列表"""
    session = await SessionService.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    messages = await MessageService.list_messages(db, session_id)

    return success_response(
        data={
            "session": {
                "id": session.id,
                "user_id": session.user_id,
                "title": session.title,
                "status": session.status,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
            },
            "messages": [
                {
                    "id": m.id,
                    "role": m.role,
                    "content": m.content,
                    "intent": m.intent,
                    "slots_json": m.slots_json,
                    "created_at": m.created_at.isoformat(),
                }
                for m in messages
            ],
        }
    )


@router.post("/{session_id}/messages")
async def send_message(
    session_id: str,
    content: str = Query(..., description="消息内容"),
    db: AsyncSession = Depends(get_db),
):
    """发送消息，SSE 流式返回 AI 回复"""
    # 验证会话存在
    session = await SessionService.get_session(db, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")

    # 保存用户消息
    await MessageService.add_message(db, session_id, "user", content)

    # 构建对话图
    graph = build_dialog_graph()

    # 准备初始状态
    initial_state = {
        "session_id": session_id,
        "user_id": session.user_id,
        "user_input": content,
        "intents": {},
        "active_intent": "",
        "slots": {},
        "missing_slots": [],
        "business_result": None,
        "final_response": "",
        "should_fallback": False,
    }

    # 执行对话图
    final_state = await graph.ainvoke(initial_state)
    reply = final_state.get("final_response", "抱歉，我不知道该如何回答。")

    # 保存 AI 回复
    active_intent = final_state.get("active_intent", "")
    slots = final_state.get("slots", {})
    await MessageService.add_message(
        db, session_id, "assistant", reply,
        intent=active_intent if active_intent else None,
        slots=slots if slots else None,
    )

    # SSE 流式返回
    async def event_generator():
        # 逐字符发送（模拟流式效果）
        chunk_size = 5
        for i in range(0, len(reply), chunk_size):
            chunk = reply[i : i + chunk_size]
            yield {"event": "message", "data": chunk}
            await asyncio.sleep(0.02)
        yield {"event": "done", "data": ""}

    return EventSourceResponse(event_generator())
```

- [ ] **Step 2: 创建 app/api/v1/router.py**

```python
"""API v1 路由注册"""
from fastapi import APIRouter
from app.api.v1.chat import router as chat_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(chat_router)
```

- [ ] **Step 3: Commit**

```bash
git add app/api/
git commit -m "feat: 添加 REST API 端点和 SSE 流式回复"
```

---

### Task 15: 应用入口与异常处理

**Files:**
- Create: `app/main.py`

**Interfaces:**
- Consumes: All layers
- Produces: FastAPI app 可启动

- [ ] **Step 1: 创建 app/main.py**

```python
"""FastAPI 应用入口"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.api.v1.router import api_router
from app.core.exceptions import AppException
from app.core.response import error_response
from app.nlu.registry import IntentRegistry
from app.business.ecommerce.intents import ECOMMERCE_INTENTS


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时：注册业务线意图
    IntentRegistry.register_business("ecommerce", ECOMMERCE_INTENTS)
    logger.info("电商业务线意图已注册")
    logger.info(f"已注册意图: {[i.name for i in IntentRegistry.get_all_intents()]}")
    yield
    # 关闭时清理
    logger.info("应用关闭")


app = FastAPI(
    title="电商智能客服系统",
    description="基于 LangGraph + FastAPI 的可扩展智能客服",
    version="0.1.0",
    lifespan=lifespan,
)

# 注册路由
app.include_router(api_router)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """统一业务异常处理"""
    logger.warning(f"业务异常: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(exc.message),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局未知异常处理"""
    logger.error(f"未知异常: {exc}")
    return JSONResponse(
        status_code=500,
        content=error_response("系统繁忙，请稍后重试"),
    )


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "ok"}
```

- [ ] **Step 2: 启动应用验证**

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat: 添加 FastAPI 应用入口和异常处理"
```

---

### Task 16: 集成测试 — 会话 API

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_api/__init__.py`
- Create: `tests/test_api/test_sessions.py`

**Interfaces:**
- Tests: 会话 CRUD API 端到端测试

- [ ] **Step 1: 创建 tests/conftest.py**

```python
"""pytest 全局配置"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    """创建测试 HTTP 客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
```

- [ ] **Step 2: 创建 tests/test_api/test_sessions.py**

```python
"""会话 API 集成测试"""
import pytest


@pytest.mark.asyncio
async def test_create_session(client):
    """测试创建会话"""
    response = await client.post("/api/v1/sessions?user_id=1001")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["user_id"] == "1001"
    assert data["data"]["id"] != ""


@pytest.mark.asyncio
async def test_list_sessions(client):
    """测试获取会话列表"""
    # 先创建几个会话
    for _ in range(3):
        await client.post("/api/v1/sessions?user_id=1001")

    response = await client.get("/api/v1/sessions?user_id=1001")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) <= 10


@pytest.mark.asyncio
async def test_get_session_not_found(client):
    """测试获取不存在的会话"""
    response = await client.get("/api/v1/sessions/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message(client):
    """测试发送消息"""
    # 创建会话
    resp = await client.post("/api/v1/sessions?user_id=1001")
    session_id = resp.json()["data"]["id"]

    # 发送消息
    response = await client.post(
        f"/api/v1/sessions/{session_id}/messages?content=你好"
    )
    assert response.status_code == 200
```

- [ ] **Step 3: 运行集成测试**

```bash
uv run pytest tests/test_api/ -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: 添加会话 API 集成测试"
```

---

### Task 17: 业务线初始化

**Files:**
- Create: `app/business/ecommerce/__init__.py` (如果已存在则更新)
- Modify: `app/main.py` (如果 lifespan 中已注册则 OK)

确保应用启动时电商业务线意图自动注册。

- [ ] **Step 1: 确认 `app/business/ecommerce/__init__.py`**

```python
"""电商业务线"""
```

- [ ] **Step 2: 运行完整测试套件**

```bash
uv run pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add app/business/ecommerce/__init__.py
git commit -m "chore: 确认电商业务线初始化"
```
