"""电商业务线 ORM 模型测试"""
import pytest
from app.business.ecommerce.models.order import (
    EcommerceBase,
    OrderInfo,
    OrderDetail,
    SkuInfo,
)


class TestEcommerceBase:
    """EcommerceBase 基类测试"""

    def test_ecommerce_base_is_declarative(self):
        """验证 EcommerceBase 是 SQLAlchemy 声明式基类"""
        from sqlalchemy.orm import DeclarativeBase
        assert issubclass(EcommerceBase, DeclarativeBase)

    def test_ecommerce_base_distinct_from_platform_base(self):
        """验证业务线 ORM 基类独立于平台库 Base"""
        from app.core.database import Base as PlatformBase
        assert EcommerceBase is not PlatformBase
        # 两个不同的基类，各自的 metadata 独立
        assert EcommerceBase.metadata is not PlatformBase.metadata


class TestOrderInfo:
    """OrderInfo 订单信息表模型测试"""

    def test_order_info_tablename(self):
        """验证表名为 order_info"""
        assert OrderInfo.__tablename__ == "order_info"

    def test_order_info_has_required_columns(self):
        """验证 OrderInfo 包含必要的字段"""
        assert hasattr(OrderInfo, "order_id")
        assert hasattr(OrderInfo, "create_time")
        assert hasattr(OrderInfo, "payment_time")
        assert hasattr(OrderInfo, "delivered_time")
        assert hasattr(OrderInfo, "complete_time")
        assert hasattr(OrderInfo, "user_id")
        assert hasattr(OrderInfo, "receive_id")
        assert hasattr(OrderInfo, "order_status")

    def test_order_info_has_details_relationship(self):
        """验证 OrderInfo 有 details 关联关系"""
        assert hasattr(OrderInfo, "details")


class TestOrderDetail:
    """OrderDetail 订单明细表模型测试"""

    def test_order_detail_tablename(self):
        """验证表名为 order_detail"""
        assert OrderDetail.__tablename__ == "order_detail"

    def test_order_detail_has_required_columns(self):
        """验证 OrderDetail 包含必要字段"""
        assert hasattr(OrderDetail, "order_detail_id")
        assert hasattr(OrderDetail, "order_id")
        assert hasattr(OrderDetail, "sku_id")
        assert hasattr(OrderDetail, "sku_name")
        assert hasattr(OrderDetail, "sku_count")
        assert hasattr(OrderDetail, "total_amount")
        assert hasattr(OrderDetail, "discount_amount")
        assert hasattr(OrderDetail, "final_amount")

    def test_order_detail_has_order_relationship(self):
        """验证 OrderDetail 有 order 关联关系"""
        assert hasattr(OrderDetail, "order")


class TestSkuInfo:
    """SkuInfo 商品信息表模型测试"""

    def test_sku_info_tablename(self):
        """验证表名为 sku_info"""
        assert SkuInfo.__tablename__ == "sku_info"

    def test_sku_info_has_required_columns(self):
        """验证 SkuInfo 包含必要字段"""
        assert hasattr(SkuInfo, "sku_id")
        assert hasattr(SkuInfo, "sku_name")
        assert hasattr(SkuInfo, "sku_price")
        assert hasattr(SkuInfo, "sku_category")
        assert hasattr(SkuInfo, "sku_count")
