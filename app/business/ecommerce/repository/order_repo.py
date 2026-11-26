"""订单数据访问层

使用电商业务线独立的数据库引擎和 session。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from loguru import logger

from app.business.ecommerce.config import ecommerce_settings
from app.business.ecommerce.models.order import OrderInfo, OrderDetail, SkuInfo

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
    """订单数据仓库

    提供订单、订单明细、商品信息的查询能力。
    """

    async def get_orders_by_user(
        self, user_id: str, limit: int = 10
    ) -> list[OrderInfo]:
        """查询用户最近的订单，按创建时间倒序"""
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
