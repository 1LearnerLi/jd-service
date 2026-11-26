"""售后申请意图处理器

支持多步交互流程：
  步骤 1: 用户提供订单号 → 校验订单，返回可售后商品列表
  步骤 2: 用户选择商品 → 返回售后方式（仅退款/退货退款）和原因选项
  步骤 3: 用户确认方式+原因 → 执行售后，创建售后记录并更新订单状态
"""
from loguru import logger

from app.business.base import IntentHandler, BusinessContext, BusinessResult

# 可售后的订单状态
_REFUNDABLE_STATUSES = frozenset({"已付款", "已发货", "已签收"})

# 售后方式
_POSTSALE_TYPES = {
    "refund_only": "仅退款",
    "return_refund": "退货退款",
}

# 售后原因
_POSTSALE_REASONS = [
    "7天无理由",
    "商品瑕疵/破损",
    "发错货",
    "商品与描述不符",
    "质量问题",
    "不喜欢/不想要了",
]


class PostsaleReturnHandler(IntentHandler):
    """售后申请处理器

    通过 slots 中的 step 字段区分当前所处的售后流程步骤：
    - step 未设置或为 "select_order"：校验订单，返回可售后商品
    - step 为 "select_item"：用户选择了具体商品明细
    - step 为 "confirm"：用户确认了售后方式和原因，执行售后
    """

    def __init__(self, repo=None):
        """初始化处理器

        Args:
            repo: 可选，用于测试时注入 mock repo
        """
        from app.business.ecommerce.repository.order_repo import OrderRepo
        self._repo = repo if repo is not None else OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        """根据当前步骤分发处理"""
        step = str(ctx.slots.get("step", "select_order"))

        if step == "select_item":
            return await self._handle_select_item(ctx)
        elif step == "confirm":
            return await self._handle_confirm(ctx)
        else:
            return await self._handle_select_order(ctx)

    # ── 步骤 1: 校验订单，返回可售后商品 ──────────────────

    async def _handle_select_order(self, ctx: BusinessContext) -> BusinessResult:
        """步骤 1: 验证订单并返回可售后的商品列表"""
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

            if order.user_id != ctx.user_id:
                return BusinessResult(
                    success=False,
                    error_message="该订单不属于当前用户",
                )

            if order.order_status not in _REFUNDABLE_STATUSES:
                return BusinessResult(
                    success=False,
                    error_message=(
                        f"订单状态为「{order.order_status}」，"
                        f"暂不支持申请售后（仅已付款/已发货/已签收可售后）"
                    ),
                )

            details = await self._repo.get_order_detail_by_order(order_id)

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

            logger.info(f"售后步骤1-查询订单: {order_id}, 可售后商品数: {len(items)}")
            return BusinessResult(
                success=True,
                data={
                    "step": "select_item",
                    "order_id": order.order_id,
                    "order_status": order.order_status,
                    "items": items,
                    "hint": "请选择要售后的商品，提供 order_detail_id",
                },
            )

        except Exception as e:
            logger.error(f"售后处理失败: {e}")
            return BusinessResult(
                success=False,
                error_message="处理售后申请时出现错误，请稍后重试",
            )

    # ── 步骤 2: 用户选择了商品，返回方式和原因选项 ─────────

    async def _handle_select_item(self, ctx: BusinessContext) -> BusinessResult:
        """步骤 2: 用户选择了订单明细，返回售后方式和原因选项"""
        order_detail_id = str(ctx.slots.get("order_detail_id", ""))
        if not order_detail_id:
            return BusinessResult(
                success=False,
                error_message="请选择要售后的商品",
            )

        try:
            order_id = str(ctx.slots.get("order_id", ""))
            # 重新获取明细以确认
            details = await self._repo.get_order_detail_by_order(order_id)
            target = next(
                (d for d in details if d.order_detail_id == order_detail_id),
                None,
            )
            if target is None:
                return BusinessResult(
                    success=False,
                    error_message=f"商品明细 {order_detail_id} 不存在于订单 {order_id}",
                )

            # 获取 SKU 信息用于确定类别
            sku = await self._repo.get_sku_by_id(target.sku_id)
            category = sku.sku_category if sku else None

            # 根据类别筛选售后原因
            reasons = self._get_reasons_for_category(category)

            logger.info(
                f"售后步骤2-选择商品: {order_detail_id}, "
                f"类别: {category}, 可选原因数: {len(reasons)}"
            )
            return BusinessResult(
                success=True,
                data={
                    "step": "confirm",
                    "order_id": order_id,
                    "order_detail_id": order_detail_id,
                    "sku_name": target.sku_name,
                    "final_amount": float(target.final_amount),
                    "types": [
                        {"key": "refund_only", "label": "仅退款"},
                        {"key": "return_refund", "label": "退货退款"},
                    ],
                    "reasons": reasons,
                    "hint": "请选择售后方式（refund_only/return_refund）和原因",
                },
            )

        except Exception as e:
            logger.error(f"售后步骤2失败: {e}")
            return BusinessResult(
                success=False,
                error_message="处理售后申请时出现错误，请稍后重试",
            )

    # ── 步骤 3: 确认执行售后 ──────────────────────────────

    async def _handle_confirm(self, ctx: BusinessContext) -> BusinessResult:
        """步骤 3: 用户确认售后方式和原因，执行售后"""
        order_detail_id = str(ctx.slots.get("order_detail_id", ""))
        postsale_type = str(ctx.slots.get("postsale_type", "refund_only"))
        postsale_reason = str(ctx.slots.get("postsale_reason", ""))

        if not order_detail_id:
            return BusinessResult(
                success=False,
                error_message="缺少商品明细信息",
            )
        if not postsale_reason:
            return BusinessResult(
                success=False,
                error_message="请选择售后原因",
            )

        # 校验售后方式
        if postsale_type not in _POSTSALE_TYPES:
            return BusinessResult(
                success=False,
                error_message=f"不支持的售后方式: {postsale_type}",
            )

        try:
            order_id = str(ctx.slots.get("order_id", ""))
            order = await self._repo.get_order_by_id(order_id)
            if order is None:
                return BusinessResult(
                    success=False,
                    error_message=f"订单 {order_id} 不存在",
                )

            details = await self._repo.get_order_detail_by_order(order_id)
            target = next(
                (d for d in details if d.order_detail_id == order_detail_id),
                None,
            )
            if target is None:
                return BusinessResult(
                    success=False,
                    error_message="商品明细不存在",
                )

            refund_amount = float(target.final_amount)
            postsale_type_label = _POSTSALE_TYPES[postsale_type]

            # 写入售后记录
            postsale = await self._repo.create_postsale(
                order_detail_id=order_detail_id,
                refund_amount=refund_amount,
                postsale_type=postsale_type_label,
                postsale_reason=postsale_reason,
                receive_id=order.receive_id,
            )

            logger.info(
                f"售后完成: 订单={order_id}, 商品={order_detail_id}, "
                f"方式={postsale_type_label}, 原因={postsale_reason}"
            )
            return BusinessResult(
                success=True,
                data={
                    "step": "completed",
                    "postsale_id": postsale.postsale_id,
                    "order_id": order_id,
                    "order_detail_id": order_detail_id,
                    "sku_name": target.sku_name,
                    "type": postsale_type_label,
                    "reason": postsale_reason,
                    "refund_amount": refund_amount,
                    "status": "审核中",
                },
            )

        except Exception as e:
            logger.error(f"售后执行失败: {e}")
            return BusinessResult(
                success=False,
                error_message="处理售后申请时出现错误，请稍后重试",
            )

    # ── 辅助方法 ──────────────────────────────────────

    def _get_reasons_for_category(self, category: str | None) -> list[str]:
        """根据商品类别返回适用的售后原因"""
        return _POSTSALE_REASONS
