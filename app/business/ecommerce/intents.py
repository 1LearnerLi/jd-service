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
                ask_prompt="请提供您的订单号，我帮您查询详情",
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
                ask_prompt="请提供您要申请售后的订单号",
            ),
        ],
    ),
    IntentDefinition(
        name="product_inquiry",
        description="用户咨询商品信息，包括商品价格、规格、库存、使用说明等",
        optional_slots=[
            SlotDef(
                name="sku_id",
                description="商品 SKU ID",
                ask_prompt="请提供商品编号",
            ),
            SlotDef(
                name="sku_name",
                description="商品名称",
                ask_prompt="请问您想了解哪款商品？",
            ),
        ],
    ),
]
