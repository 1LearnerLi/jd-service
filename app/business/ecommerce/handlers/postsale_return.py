"""售后申请意图处理器

槽位驱动的逐槽位填充流程：
  1. 缺少 order_id   → 查询用户最近 5 条订单，返回列表让用户选
  2. 缺少 postsale_type  → 返回 _POSTSALE_TYPES 让用户选
  3. 缺少 postsale_reason → 返回 _POSTSALE_REASONS 让用户选
  4. 三个槽位齐全      → 直接修改订单状态为"售后中"，返回完成信息
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

    每次调用 handle 时检查当前 slots 中缺失哪个槽位，
    按 order_id → postsale_type → postsale_reason 顺序逐项推进。
    """

    def __init__(self, repo=None):
        from app.business.ecommerce.repository.order_repo import OrderRepo
        self._repo = repo if repo is not None else OrderRepo()

    async def handle(self, ctx: BusinessContext) -> BusinessResult:
        """按槽位填充状态分发"""
        slots = ctx.slots

        # 1. 缺少 order_id → 返回最近订单列表
        if not slots.get("order_id"):
            return await self._ask_for_order(ctx)

        # 2. 缺少 postsale_type → 返回售后方式列表
        if not slots.get("postsale_type"):
            # 但先要校验订单是否可售后
            order_check = await self._check_order(ctx)
            if not order_check.success:
                return order_check
            return await self._ask_for_type(ctx)

        # 3. 缺少 postsale_reason → 返回售后原因列表
        if not slots.get("postsale_reason"):
            return await self._ask_for_reason(ctx)

        # 4. 三个槽位齐全 → 执行售后
        return await self._execute(ctx)

    # ── 槽位追问 ──────────────────────────────────────

    async def _ask_for_order(self, ctx: BusinessContext) -> BusinessResult:
        """order_id 缺失：返回用户最近 5 条订单"""
        try:
            orders = await self._repo.get_orders_by_user(ctx.user_id, limit=5)

            if not orders:
                return BusinessResult(
                    success=True,
                    data={
                        "action": "select_order",
                        "message": "您暂无订单记录，请确认后重试",
                        "orders": [],
                    },
                )

            # 只返回可售后的订单
            order_list = []
            for o in orders:
                order_list.append({
                    "order_id": o.order_id,
                    "order_status": o.order_status,
                    "can_apply": o.order_status in _REFUNDABLE_STATUSES,
                })

            logger.info(f"售后-返回订单列表: user={ctx.user_id}, 订单数={len(order_list)}")
            return BusinessResult(
                success=True,
                data={
                    "action": "select_order",
                    "message": "请选择要申请售后的订单",
                    "orders": order_list,
                },
            )
        except Exception as e:
            logger.error(f"查询用户订单失败: {e}")
            return BusinessResult(
                success=False,
                error_message="查询订单时出现错误，请稍后重试",
            )

    async def _ask_for_type(self, ctx: BusinessContext) -> BusinessResult:
        """postsale_type 缺失：返回售后方式"""
        return BusinessResult(
            success=True,
            data={
                "action": "select_type",
                "message": "请选择售后方式",
                "types": [
                    {"key": k, "label": v} for k, v in _POSTSALE_TYPES.items()
                ],
            },
        )

    async def _ask_for_reason(self, ctx: BusinessContext) -> BusinessResult:
        """postsale_reason 缺失：返回售后原因"""
        return BusinessResult(
            success=True,
            data={
                "action": "select_reason",
                "message": "请选择售后原因",
                "reasons": _POSTSALE_REASONS,
            },
        )

    # ── 订单校验 ──────────────────────────────────────

    async def _check_order(self, ctx: BusinessContext) -> BusinessResult:
        """校验订单归属和状态"""
        order_id = str(ctx.slots.get("order_id", ""))
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
                        f"仅已付款/已发货/已签收的订单可申请售后"
                    ),
                )
            return BusinessResult(success=True)
        except Exception as e:
            logger.error(f"校验订单失败: {e}")
            return BusinessResult(
                success=False,
                error_message="查询订单时出现错误，请稍后重试",
            )

    # ── 执行售后 ──────────────────────────────────────

    async def _execute(self, ctx: BusinessContext) -> BusinessResult:
        """三个槽位齐全，直接修改订单状态为售后中"""
        order_id = str(ctx.slots.get("order_id", ""))
        postsale_type = str(ctx.slots.get("postsale_type", "refund_only"))
        postsale_reason = str(ctx.slots.get("postsale_reason", ""))

        # 校验售后方式
        if postsale_type not in _POSTSALE_TYPES:
            return BusinessResult(
                success=False,
                error_message=f"不支持的售后方式: {postsale_type}",
            )

        # 再次校验订单
        order_check = await self._check_order(ctx)
        if not order_check.success:
            return order_check

        try:
            # 简化售后流程：直接修改订单状态为"售后中"
            await self._repo.update_order_status(order_id, "售后中")

            type_label = _POSTSALE_TYPES[postsale_type]
            logger.info(
                f"售后完成: 订单={order_id}, "
                f"方式={type_label}, 原因={postsale_reason}"
            )
            return BusinessResult(
                success=True,
                data={
                    "action": "completed",
                    "order_id": order_id,
                    "type": type_label,
                    "reason": postsale_reason,
                    "new_status": "售后中",
                    "message": (
                        f"售后申请已提交！\n"
                        f"订单号：{order_id}\n"
                        f"售后方式：{type_label}\n"
                        f"售后原因：{postsale_reason}\n"
                        f"当前状态：售后中"
                    ),
                },
            )
        except Exception as e:
            logger.error(f"售后执行失败: {e}")
            return BusinessResult(
                success=False,
                error_message="处理售后申请时出现错误，请稍后重试",
            )
