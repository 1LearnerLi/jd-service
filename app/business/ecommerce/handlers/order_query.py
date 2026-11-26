"""订单查询意图处理器"""
from loguru import logger

from app.business.base import (
    IntentHandler,
    BusinessContext,
    BusinessResult,
    OptionItem,
)


class OrderQueryHandler(IntentHandler):
    """订单查询处理器

    槽位驱动：order_id 缺失时返回用户最近订单列表让用户选。
    """

    def __init__(self, repo=None):
        from app.business.ecommerce.repository.order_repo import OrderRepo
        self._repo = repo if repo is not None else OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        order_id = str(ctx.slots.get("order_id", ""))
        if not order_id:
            return await self._ask_for_order(ctx)
        return await self._query(ctx)

    async def _ask_for_order(self, ctx: BusinessContext) -> BusinessResult:
        """order_id 缺失：返回用户最近订单"""
        try:
            orders = await self._repo.get_orders_by_user(ctx.user_id, limit=5)
            options = [
                OptionItem(
                    label=f"{o.order_id}（{o.order_status}）",
                    value=o.order_id,
                )
                for o in orders
            ]
            logger.info(f"订单查询-返回订单列表: user={ctx.user_id}, 订单数={len(options)}")
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
