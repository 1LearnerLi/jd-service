# ── 后端服务 Dockerfile ─────────────────────────────────
# 基于 python:3.14-slim，使用 uv 管理依赖
#
# 注意：国内构建时 ghcr.io 可能很慢，可取消注释 pip install uv 替代方案

FROM python:3.14-slim

# 安装系统编译依赖（asyncmy 等包需要 gcc）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 安装 uv
# 方式一：从 ghcr.io 拉取静态二进制（推荐，速度快）
# COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
# 方式二：国内备选 — 通过 pip 安装（使用阿里云镜像更快）
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

# ── 先复制依赖文件，利用 Docker 层缓存 ──
COPY pyproject.toml uv.lock ./

# 安装 Python 依赖（uv 自动使用 pyproject.toml 中配置的阿里云镜像）
RUN uv sync --no-dev

# ── 复制项目源码 ──
COPY . .

# 确保入口脚本可执行
RUN chmod +x docker/backend/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["docker/backend/entrypoint.sh"]
