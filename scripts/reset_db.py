"""清空旧表并执行 Alembic 迁移 — 一次性操作脚本"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def main():
    engine = create_async_engine(settings.platform_database_url)
    async with engine.begin() as conn:
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        await conn.execute(text("DROP TABLE IF EXISTS messages"))
        await conn.execute(text("DROP TABLE IF EXISTS conversation_sessions"))
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        print("[OK] 旧表已删除")
        result = await conn.execute(text("SHOW TABLES"))
        tables = result.fetchall()
        print(f"[OK] 剩余表: {[t[0] for t in tables]}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
