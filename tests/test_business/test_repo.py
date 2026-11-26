"""OrderRepo 数据仓库测试"""
import pytest
from app.business.ecommerce.repository.order_repo import OrderRepo


class TestOrderRepo:
    """OrderRepo 订单数据仓库测试"""

    def test_order_repo_can_instantiate(self):
        """验证 OrderRepo 可以实例化"""
        repo = OrderRepo()
        assert repo is not None
        assert isinstance(repo, OrderRepo)

    def test_order_repo_has_query_methods(self):
        """验证 OrderRepo 具有必要的查询方法"""
        repo = OrderRepo()
        assert hasattr(repo, "get_orders_by_user")
        assert callable(repo.get_orders_by_user)
        assert hasattr(repo, "get_order_by_id")
        assert callable(repo.get_order_by_id)
        assert hasattr(repo, "get_order_detail_by_order")
        assert callable(repo.get_order_detail_by_order)
        assert hasattr(repo, "get_sku_by_id")
        assert callable(repo.get_sku_by_id)

    def test_order_repo_engine_created(self):
        """验证业务线数据库引擎已创建"""
        from app.business.ecommerce.repository.order_repo import eco_engine
        from sqlalchemy.ext.asyncio import AsyncEngine
        assert eco_engine is not None
        assert isinstance(eco_engine, AsyncEngine)

    def test_order_repo_session_local_created(self):
        """验证业务线 session factory 已创建"""
        from app.business.ecommerce.repository.order_repo import EcoSessionLocal
        assert EcoSessionLocal is not None
        # async_sessionmaker 是一个 sessionmaker 对象
        from sqlalchemy.ext.asyncio import async_sessionmaker
        assert isinstance(EcoSessionLocal, async_sessionmaker)
