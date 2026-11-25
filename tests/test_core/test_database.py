"""平台数据库引擎测试"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, AsyncEngine

from app.core.database import async_engine, AsyncSessionLocal, Base, get_db


class TestDatabaseEngine:
    """数据库引擎测试"""

    def test_async_engine_created(self):
        """验证 AsyncEngine 已创建"""
        assert async_engine is not None
        assert isinstance(async_engine, AsyncEngine)

    def test_async_session_local_created(self):
        """验证 async_sessionmaker 已创建"""
        assert AsyncSessionLocal is not None
        assert isinstance(AsyncSessionLocal, async_sessionmaker)

    def test_base_is_declarative(self):
        """验证 Base 为 DeclarativeBase 子类"""
        from sqlalchemy.orm import DeclarativeBase as DB
        assert issubclass(Base, DB)

    def test_get_db_is_async_generator(self):
        """验证 get_db 为异步生成器函数"""
        import inspect
        assert inspect.isasyncgenfunction(get_db)


class TestPlatformDatabaseUrl:
    """平台数据库连接 URL 测试"""

    def test_database_url_format(self):
        """验证数据库 URL 格式"""
        from app.config import settings
        url = settings.platform_database_url
        # 应为异步 MySQL URL
        assert "mysql+asyncmy://" in url
        assert "ecs_platform" in url

    def test_database_url_not_empty(self):
        """验证数据库 URL 非空"""
        from app.config import settings
        assert len(settings.platform_database_url) > 0
