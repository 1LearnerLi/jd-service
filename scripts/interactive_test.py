"""智能客服交互式测试工具

用法:
    uv run python scripts/interactive_test.py

前置条件:
    - Docker MySQL 运行中（docker compose up -d）
    - ecs / ecs_platform 库已初始化（ecs.sql 由 Docker 自动导入）
    - .env 中已配置 OPENAI_API_KEY

命令:
    /help     显示帮助
    /data     显示可用的测试数据
    /user <id> 切换用户（默认 1001）
    /new      开始新会话
    /history  查看当前会话消息历史
    /quit     退出
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

# Windows GBK 终端兼容：强制 stdout 用 UTF-8
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── 测试数据说明 ──────────────────────────────────────────
# 数据来源：docker/mysql/ecs.sql（Docker 启动时自动导入，无需手动插入）

TEST_DATA_INFO = """
+=====================================================================+
                        可用测试数据（ecs.sql 真实数据）
+---------------------------------------------------------------------+
  [用户]
    1001 (张三) -- 2 个订单
    1002 (李四) -- 2 个订单
    1003 (王五) -- 3 个订单（含售后中）
    1004 (赵六) -- 2 个订单
    1005 (孙七) -- 2 个订单
    1006 (周八) -- 2 个订单（含已取消）
    1007 (吴九) -- 1 个订单
    1008 (郑十) -- 1 个订单
    1009~1010     -- 无订单

  [订单（部分展示）]
    ORD-20240701-001  已完成  -- 智能手机X1 + 耳机 + 移动电源
    ORD-20240705-001  已发货  -- 男士T恤 + 女士牛仔裤
    ORD-20240702-001  已完成  -- 实木餐桌 + 床头柜
    ORD-20240706-001  待支付  -- 保湿面霜 + 口红套装
    ORD-20240703-001  已完成  -- 巧克力礼盒 + 咖啡 + 大米
    ORD-20240707-001  售后中  -- 儿童绘本 + 编程教程
    ORD-20240710-001  待发货  -- 婴儿奶瓶 + 推车 + 湿巾
    ORD-20240704-001  已完成  -- 轻薄笔记本电脑
    ORD-20240708-001  已发货  -- 卫衣 + 运动鞋 + 短裤
    ORD-20240706-002  待支付  -- 智能手表 + 路由器
    ORD-20240630-001  已完成  -- 燕麦片 + 红酒 + 蜂蜜
    ORD-20240709-001  售后中  -- 办公椅
    ORD-20240703-002  已取消  -- 数码相机
    ORD-20240711-001  待发货  -- 眼影盘 + 防晒霜 + 卸妆水
    ORD-20240708-002  已完成  -- 婴儿奶粉 + 沐浴露

  [商品] 共 60 个 SKU，覆盖服装/数码/美妆/食品/家具/图书/母婴 7 个品类

  [意图说明]
    order_query      查询订单详情（需 order_id）
    postsale_return  售后申请（需 order_id -> 售后方式 -> 售后原因）
    product_inquiry  商品咨询（暂未实现 Handler）
    transfer_human   转人工客服
    unknown          无法识别 -> 兜底回复
+---------------------------------------------------------------------+
  [推荐测试输入]
    1. "帮我查一下我的订单"     -> 订单列表 -> 回复订单号查详情
    2. "我要申请售后"           -> 售后流程（多轮）
    3. "转人工"                 -> 平台意图
    4. "asdfghjkl"             -> unknown 兜底
    5. "这个手机有什么功能"     -> product_inquiry（暂未实现）
+=====================================================================+
"""

HELP_TEXT = """
+=====================================================================+
  [命令]
    /help      -- 显示此帮助
    /data      -- 显示可用的测试数据
    /user <id> -- 切换用户 ID（如 /user 1002）
    /new       -- 开始新会话
    /history   -- 查看当前会话消息历史
    /quit      -- 退出
+---------------------------------------------------------------------+
  [提示]
    - 直接输入文字即可发送消息，AI 将流式回复
    - 多轮对话中系统会保持上下文和意图状态
    - 响应中会显示本轮意图和槽位信息
+=====================================================================+
"""


# ── API 客户端 ────────────────────────────────────────────


async def create_session(client: httpx.AsyncClient, user_id: str) -> str:
    """创建会话，返回 session_id"""
    resp = await client.post(f"http://127.0.0.1:8000/api/v1/sessions?user_id={user_id}")
    if resp.status_code != 200:
        print(f"[ERROR] 创建会话失败: {resp.status_code} {resp.text}")
        return ""
    body = resp.json()
    session_id = body["data"]["id"]
    print(f"[OK] 会话已创建: {session_id[:8]}...  用户: {user_id}")
    return session_id


async def send_message(
    client: httpx.AsyncClient, session_id: str, content: str
) -> dict:
    """发送消息并消费 SSE 流，返回 {"reply": str, "events": list}"""
    resp = await client.post(
        f"http://127.0.0.1:8000/api/v1/sessions/{session_id}/messages?content={content}"
    )
    if resp.status_code != 200:
        print(f"[ERROR] 发送失败: {resp.status_code}")
        return {"reply": "", "events": []}

    full_text = ""
    events = []
    async for line in resp.aiter_lines():
        if line.startswith("event:"):
            events.append(line[6:].strip())
        elif line.startswith("data:"):
            chunk = line[5:].strip()
            if chunk:
                full_text += chunk
    return {"reply": full_text, "events": events}


async def get_session_info(client: httpx.AsyncClient, session_id: str) -> dict | None:
    """获取会话详情"""
    resp = await client.get(f"http://127.0.0.1:8000/api/v1/sessions/{session_id}")
    if resp.status_code != 200:
        return None
    return resp.json()["data"]


# ── 主循环 ────────────────────────────────────────────────


async def main():
    # 注册电商业务线意图
    from app.nlu.registry import IntentRegistry
    from app.business.ecommerce.intents import INTENTS

    IntentRegistry.clear()
    IntentRegistry.register_business("ecommerce", INTENTS)

    print("=" * 62)
    print("   电商智能客服 -- 交互式测试工具")
    print("=" * 62)
    print("输入 /help 查看帮助，/quit 退出")
    print("服务地址: http://127.0.0.1:8000")
    print("数据来源: docker/mysql/ecs.sql（Docker 启动时自动导入）")
    print()

    user_id = "1001"
    session_id = ""

    async with httpx.AsyncClient(timeout=120.0) as client:
        # 检查服务
        try:
            resp = await client.get("http://127.0.0.1:8000/health")
            if resp.status_code != 200:
                print("[!!] 服务未就绪，请先启动: uv run uvicorn app.main:app --reload")
                return
        except Exception:
            print("[ERROR] 无法连接到 http://127.0.0.1:8000，请先启动服务")
            return

        # 创建初始会话
        session_id = await create_session(client, user_id)
        if not session_id:
            return

        print()
        print(TEST_DATA_INFO)

        while True:
            try:
                user_input = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if not user_input:
                continue

            # ── 处理命令 ──
            if user_input.startswith("/"):
                parts = user_input.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                if cmd == "/quit":
                    print("再见！")
                    break

                elif cmd == "/help":
                    print(HELP_TEXT)

                elif cmd == "/data":
                    print(TEST_DATA_INFO)

                elif cmd == "/user":
                    if arg:
                        user_id = arg
                        session_id = await create_session(client, user_id)
                        if not session_id:
                            continue
                    else:
                        print("[!!] 用法: /user <用户ID>  如 /user 1002")

                elif cmd == "/new":
                    session_id = await create_session(client, user_id)
                    if not session_id:
                        continue

                elif cmd == "/history":
                    if session_id:
                        info = await get_session_info(client, session_id)
                        if info:
                            msgs = info.get("messages", [])
                            print(f"\n-- 会话 {session_id[:8]}... 消息历史 ({len(msgs)} 条) --")
                            for m in msgs:
                                role = "USER" if m["role"] == "user" else "AI"
                                intent_str = f" [{m.get('intent', '')}]" if m.get("intent") else ""
                                print(f"  [{role}] {m['content'][:100]}{intent_str}")
                            print("-- 结束 --\n")
                        else:
                            print("[!!] 无法获取会话信息")
                    else:
                        print("[!!] 没有活跃会话，请先创建")

                else:
                    print(f"[!!] 未知命令: {cmd}，输入 /help 查看帮助")
                continue

            # ── 发送消息 ──
            if not session_id:
                session_id = await create_session(client, user_id)
                if not session_id:
                    continue

            print("AI: ", end="", flush=True)
            result = await send_message(client, session_id, user_input)
            reply = result["reply"]

            if reply:
                print(reply)
            else:
                print("(空回复)")

            # 显示上下文信息
            if session_id:
                info = await get_session_info(client, session_id)
                if info:
                    msgs = info.get("messages", [])
                    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
                    if assistant_msgs:
                        last = assistant_msgs[-1]
                        intent = last.get("intent", "")
                        slots = last.get("slots_json", {})
                        if intent:
                            print(f"   [意图: {intent}]", end="")
                            if slots:
                                print(f"  [槽位: {slots}]", end="")
                            print()

            print()


if __name__ == "__main__":
    asyncio.run(main())
