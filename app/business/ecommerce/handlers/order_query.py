"""订单查询意图处理器"""
from loguru import logger

from app.business.base import IntentHandler, BusinessContext, BusinessResult
from app.business.ecommerce.repository.order_repo import OrderRepo


class OrderQueryHandler(IntentHandler):
    """订单查询处理器

    根据订单号查询订单详情，包含商品明细和金额信息。
    """

    def __init__(self):
        self._repo = OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        """查询订单详情"""
        order_id = str(ctx.slots.get("order_id", ""))
        if not order_id:
            return BusinessResult(
                success=False,
                error_message="缺少订单号，无法查询",
            )

        try:
            order = await self._repo.get_order_by_id(order_id)
            if order is None:
                return BusinessResult(
                    success=False,
                    error_message=f"订单 {order_id} 不存在，请确认订单号是否正确",
                )

            details = await self._repo.get_order_detail_by_order(order_id)

            # 构造返回数据
            detail_list = []
            for d in details:
                # 同时查 SKU 信息补全
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
            return BusinessResult(success=True, data=order_data)

        except Exception as e:
            logger.error(f"订单查询失败: {e}")
            return BusinessResult(
                success=False,
                error_message="查询订单时出现错误，请稍后重试",
            )
