#!/bin/bash
# ==============================================================================
# 后端容器启动入口
#
# 职责：
#   1. 等待 MySQL 就绪（TCP 端口可达）
#   2. 执行 Alembic 数据库迁移
#   3. 启动 uvicorn
# ==============================================================================
set -e

MYSQL_HOST="${MYSQL_HOST:-mysql}"
MYSQL_PORT="${MYSQL_PORT:-3306}"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  电商智能客服系统 — 后端容器启动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. 等待 MySQL 就绪 ──────────────────────────────
echo ""
echo "[1/3] 等待 MySQL 就绪（${MYSQL_HOST}:${MYSQL_PORT}）…"

for i in $(seq 1 30); do
    if python -c "
import socket, sys
try:
    s = socket.socket()
    s.settimeout(2)
    s.connect(('${MYSQL_HOST}', ${MYSQL_PORT}))
    s.close()
    print('OK')
    sys.exit(0)
except Exception:
    sys.exit(1)
" 2>/dev/null; then
        echo "  ✓ MySQL 已就绪"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  ✗ MySQL 在 60 秒内未能就绪，退出"
        exit 1
    fi
    echo "  等待中…（${i}/30）"
    sleep 2
done

# ── 2. 执行数据库迁移 ─────────────────────────────
echo ""
echo "[2/3] 执行数据库迁移（alembic upgrade head）…"
uv run alembic upgrade head
echo "  ✓ 迁移完成"

# ── 3. 启动应用 ────────────────────────────────────
echo ""
echo "[3/3] 启动 uvicorn…"
exec uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
