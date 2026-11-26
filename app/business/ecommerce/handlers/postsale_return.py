"""售后申请意图处理器"""
from loguru import logger

from app.business.base import IntentHandler, BusinessContext, BusinessResult
from app.business.ecommerce.repository.order_repo import OrderRepo


class PostsaleReturnHandler(IntentHandler):
    """售后申请处理器

    查询订单状态并返回可申请售后的商品列表。
    支持订单归属校验和售后状态校验。
    """

    def __init__(self):
        self._repo = OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        """处理售后申请 — 查询订单并返回可售后信息"""
        order_id = str(ctx.slots.get("order_id", ""))
        if not order_id:
            return BusinessResult(
                success=False,
                error_message="缺少订单号，无法处理售后",
            )

        try:
            order = await self._repo.get_order_by_id(order_id)
            if order is None:
                return BusinessResult(
                    success=False,
                    error_message=f"订单 {order_id} 不存在，请确认订单号",
                )

            # 校验订单是否属于当前用户
            if order.user_id != ctx.user_id:
                return BusinessResult(
                    success=False,
                    error_message="该订单不属于当前用户",
                )

            if order.order_status not in ("已签收", "已发货"):
                return BusinessResult(
                    success=False,
                    error_message=f"订单状态为「{order.order_status}」，暂不支持申请售后",
                )

            details = await self._repo.get_order_detail_by_order(order_id)

            # 列出售后候选商品
            items = []
            for d in details:
                sku = await self._repo.get_sku_by_id(d.sku_id)
                items.append({
                    "order_detail_id": d.order_detail_id,
                    "sku_id": d.sku_id,
                    "sku_name": d.sku_name,
                    "sku_count": d.sku_count,
                    "final_amount": float(d.final_amount),
                })

            order_data = {
                "order_id": order.order_id,
                "order_status": order.order_status,
                "items": items,
            }

            logger.info(f"售后查询成功: {order_id}, 可售后商品数: {len(items)}")
            return BusinessResult(success=True, data=order_data)

        except Exception as e:
            logger.error(f"售后处理失败: {e}")
            return BusinessResult(
                success=False,
                error_message="处理售后申请时出现错误，请稍后重试",
            )
