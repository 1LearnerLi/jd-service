#!/usr/bin/env bash
# ==============================================================================
# 服务端部署脚本（Docker 全容器化版）
#
# 用法（在 CI 或手动执行）：
#   bash deploy.sh
#
# 部署流程：
#   1. 从本地 git remote 获取仓库地址，git pull 拉取目标分支最新代码
#   2. 更新 docker/.env 中的密钥（从环境变量注入）
#   3. docker compose up -d --build（重新构建镜像并重启容器）
#
# 通过环境变量注入密钥（由 CI variables 或环境变量传入）：
#   OPENAI_API_KEY     - LLM API Key
#   OPENAI_BASE_URL    - LLM 接口地址（可选）
#   LLM_MODEL          - LLM 模型名称（可选）
#   DASHSCOPE_API_KEY  - DashScope API Key（可选）
#   LOG_LEVEL          - 日志级别（可选）
# ==============================================================================

set -euo pipefail

# 如果是 root，sudo 为空；否则前缀 sudo
if [ "$(id -u)" = "0" ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# 获取真实 HOME 目录
HOME_DIR="$(eval echo ~"$(whoami)")"

# ---------- 转义 sed RHS 中的特殊字符 ----------
escape_sed_rhs() {
    local val="$1"
    val="${val//\\/\\\\}"
    val="${val//&/\\&}"
    val="${val//|/\\|}"
    echo "$val"
}

# ---------- 将环境变量写入 docker/.env ----------
write_docker_env() {
    local env_file="$1"
    echo "  注入密钥到 $(basename "$env_file")…"

    if [ -n "${OPENAI_API_KEY:-}" ]; then
        sed -i "s|^OPENAI_API_KEY=.*|OPENAI_API_KEY=$(escape_sed_rhs "$OPENAI_API_KEY")|" "$env_file"
        echo "    ✓ OPENAI_API_KEY 已注入"
    fi
    if [ -n "${OPENAI_BASE_URL:-}" ]; then
        sed -i "s|^OPENAI_BASE_URL=.*|OPENAI_BASE_URL=$(escape_sed_rhs "$OPENAI_BASE_URL")|" "$env_file"
        echo "    ✓ OPENAI_BASE_URL 已注入"
    fi
    if [ -n "${LLM_MODEL:-}" ]; then
        sed -i "s|^LLM_MODEL=.*|LLM_MODEL=$(escape_sed_rhs "$LLM_MODEL")|" "$env_file"
        echo "    ✓ LLM_MODEL 已注入"
    fi
    if [ -n "${DASHSCOPE_API_KEY:-}" ]; then
        sed -i "s|^DASHSCOPE_API_KEY=.*|DASHSCOPE_API_KEY=$(escape_sed_rhs "$DASHSCOPE_API_KEY")|" "$env_file"
        echo "    ✓ DASHSCOPE_API_KEY 已注入"
    fi
    if [ -n "${LOG_LEVEL:-}" ]; then
        sed -i "s|^LOG_LEVEL=.*|LOG_LEVEL=$(escape_sed_rhs "$LOG_LEVEL")|" "$env_file"
        echo "    ✓ LOG_LEVEL 已注入"
    fi
}

# ---------- 从远程 URL 提取 git host ----------
# git@github.com:owner/repo.git → github.com
# https://github.com/owner/repo.git → github.com
extract_git_host() {
    local url="$1"
    local host
    # SSH 格式: git@host:path
    host=$(echo "$url" | sed -n 's|^git@\([^:]*\):.*|\1|p')
    if [ -n "$host" ]; then
        echo "$host"
        return 0
    fi
    # HTTPS 格式: https://host/path
    host=$(echo "$url" | sed -n 's|^https://\([^/]*\)/.*|\1|p')
    if [ -n "$host" ]; then
        echo "$host"
        return 0
    fi
    return 1
}

# ---------- 探测并验证 SSH 认证 ----------
# 自动探测服务器上可用的 SSH 密钥文件，验证 git 平台认证
# 参数: $1 = git host（如 github.com / gitee.com）
# 成功后设置 GIT_SSH_KEY_FILE 供后续 git fetch/pull 使用
find_and_verify_ssh() {
    local git_host="${1:-}"
    if [ -z "$git_host" ]; then
        echo "  ✗ 未指定 git host，无法验证 SSH"
        return 1
    fi
    echo "  探测服务器 SSH 密钥文件（目标: git@${git_host}）…"

    # 按优先级探测常见密钥文件
    local candidates=(
        "$HOME_DIR/.ssh/id_ed25519"
        "$HOME_DIR/.ssh/id_rsa"
        "$HOME_DIR/.ssh/id_ecdsa"
        "$HOME_DIR/.ssh/id_ed25519_sk"
        "$HOME_DIR/.ssh/id_dsa"
    )

    local found_key=""
    for key in "${candidates[@]}"; do
        if [ -f "$key" ]; then
            echo "  发现密钥: $key"
            local result
            result=$(ssh -i "$key" -T -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "git@${git_host}" 2>&1) || true
            # GitHub 返回 "successfully authenticated"，Gitee 返回 "Welcome to Gitee"
            if echo "$result" | grep -qiE "successfully authenticated|Welcome to"; then
                echo "  ✓ 密钥 $key 认证 ${git_host} 成功"
                found_key="$key"
                break
            else
                echo "  ⚠ 密钥 $key 认证失败: $result"
            fi
        fi
    done

    if [ -z "$found_key" ]; then
        echo ""
        echo "  ✗ 未找到能认证 ${git_host} 的 SSH 密钥"
        echo "  请在服务器上手动配置："
        echo "    1. ssh-keygen -t ed25519 -C \"your-email@example.com\" -f ~/.ssh/id_ed25519 -N \"\""
        echo "    2. cat ~/.ssh/id_ed25519.pub"
        echo "    3. 将公钥添加到 ${git_host} → 设置 → SSH 公钥"
        echo "    4. ssh -T git@${git_host}  验证连接"
        return 1
    fi

    GIT_SSH_KEY_FILE="$found_key"
    return 0
}

# ---------- 加载配置 ----------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/deploy.conf" ]; then
    source "$SCRIPT_DIR/deploy.conf"
fi

PROJECT_DIR="${MAIN_PROJECT_DIR:-/opt/jd-service}"
BRANCH="${BRANCH:-dev}"

echo "============================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始部署（Docker 全容器化）"
echo "  HOME 目录: $HOME_DIR"
echo "  项目目录: $PROJECT_DIR"
echo "============================================"

cd "$PROJECT_DIR"

# ---------- 1. 拉取最新代码 ----------
echo "[1/4] 拉取 $BRANCH 分支最新代码…"

# 如果在 CI 环境中运行，跳过 SSH 验证和 git pull（Runner 已 checkout）
if [ "${CI:-}" = "true" ] || [ "${CI_MODE:-}" = "true" ]; then
    echo "  检测到 CI 环境，跳过 SSH 验证和 git pull（Runner 已 checkout）"
else
    # 从本地仓库动态获取远程 URL
    REMOTE_URL=$(git remote get-url origin 2>/dev/null || true)
    if [ -z "$REMOTE_URL" ]; then
        echo "  ✗ 无法获取远程仓库地址（git remote get-url origin 返回空）"
        echo "    请确认已正确配置 git remote"
        exit 1
    fi
    echo "  远程仓库: $REMOTE_URL"

    # 从远程 URL 提取 git host，用于 SSH 验证
    GIT_HOST=$(extract_git_host "$REMOTE_URL")
    if [ -z "$GIT_HOST" ]; then
        echo "  ✗ 无法解析远程仓库地址中的 host: $REMOTE_URL"
        exit 1
    fi

    # 探测并验证 SSH 密钥，设置 GIT_SSH_KEY_FILE
    find_and_verify_ssh "$GIT_HOST"

    # 用 -i 显式指定 SSH 密钥文件
    export GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY_FILE -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
    echo "  GIT_SSH_COMMAND=$GIT_SSH_COMMAND"

    # 使用显式 refspec 确保创建 remote tracking 分支（--depth 1 默认只写 FETCH_HEAD）
    if git fetch origin --depth 1 "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"; then
        # -B: 如果本地分支不存在则创建，已存在则强制重置到远程分支
        git checkout -B "$BRANCH" "origin/$BRANCH"
        echo "  ✓ 代码更新成功"
    else
        echo "  ✗ 更新失败，请检查 SSH 认证是否有效："
        echo "    ssh -T git@${GIT_HOST}"
        exit 1
    fi
fi

# ---------- 2. 更新 docker/.env 并注入密钥 ----------
echo "[2/4] 检查并更新 docker/.env 配置…"
if [ ! -f "$PROJECT_DIR/docker/.env" ]; then
    if [ -f "$PROJECT_DIR/docker/.env.template" ]; then
        echo "  docker/.env 不存在，从模板创建…"
        cp "$PROJECT_DIR/docker/.env.template" "$PROJECT_DIR/docker/.env"
    else
        echo "  ✗ docker/.env 和 docker/.env.template 均不存在"
        exit 1
    fi
fi
write_docker_env "$PROJECT_DIR/docker/.env"

# ---------- 3. 重新构建并启动 Docker 服务 ----------
echo "[3/4] 重新构建 Docker 镜像并重启服务…"
cd "$PROJECT_DIR/docker"
$SUDO docker compose up -d --build

# ---------- 4. 清理旧镜像 ----------
echo "[4/4] 清理旧 Docker 镜像…"
$SUDO docker image prune -f

echo ""
echo "============================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 部署完成"
echo "============================================"
echo ""
echo "各服务状态："
$SUDO docker compose ps
echo ""
