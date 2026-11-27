#!/usr/bin/env bash
# ==============================================================================
# 服务器首次初始化脚本（Docker 部署版）
#
# 通过 GitHub Actions workflow_dispatch 手动触发，SSH 远程执行。
#
# 功能：
#   - 配置 SSH 认证，拉取项目代码
#   - 从 docker/.env.template 创建 docker/.env，并注入环境变量
#   - 启动 docker compose（MySQL + Neo4j + backend + nginx）
#
# 通过环境变量注入（由 GitHub Actions workflow 的 envs 传入）：
#   REPO_URL           - 仓库 SSH 地址（必填，如 git@github.com:owner/repo.git）
#   GH_SSH_PRIVATE_KEY - SSH 私钥（用于 git clone）
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

# 加载 OS 信息（后续步骤需要 $ID 判断发行版）
if [ -f /etc/os-release ]; then
    source /etc/os-release
fi

# ---------- 转义 sed RHS 中的特殊字符 ----------
# 避免 API Key 中包含 & \ | 等字符时 sed 替换出错
escape_sed_rhs() {
    local val="$1"
    # 先转义反斜杠，再转义 &，最后转义分隔符
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

# ---------- 配置 SSH 认证 ----------
# 将环境变量 GH_SSH_PRIVATE_KEY 写入 ~/.ssh/，用于 git clone/pull
# 参数: $1 = git host（如 github.com）
setup_ssh() {
    local git_host="${1:-}"
    if [ -z "${GH_SSH_PRIVATE_KEY:-}" ]; then
        echo "  ⚠ GH_SSH_PRIVATE_KEY 未设置，将尝试使用已有的 SSH 配置"
        return 0
    fi

    mkdir -p ~/.ssh
    chmod 700 ~/.ssh

    # 写入 SSH 私钥
    echo "$GH_SSH_PRIVATE_KEY" > ~/.ssh/id_git_deploy
    chmod 600 ~/.ssh/id_git_deploy

    # 配置 SSH Host（幂等，只追加一次）
    if ! grep -q "Host ${git_host}" ~/.ssh/config 2>/dev/null; then
        cat >> ~/.ssh/config << SSHEOF
Host ${git_host}
    IdentityFile ~/.ssh/id_git_deploy
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
SSHEOF
        chmod 600 ~/.ssh/config
    fi

    export GIT_SSH_COMMAND="ssh -i ~/.ssh/id_git_deploy -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

    echo "  ✓ SSH 私钥已配置（目标: ${git_host}）"
}

# 验证 SSH 连接（通用，兼容 GitHub / Gitee 等平台）
verify_ssh() {
    local git_host="${1:-}"
    if [ -z "$git_host" ]; then
        echo "  ✗ 未指定 git host，无法验证 SSH"
        return 1
    fi
    local result
    result=$(ssh -i ~/.ssh/id_git_deploy -T -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "git@${git_host}" 2>&1) || true
    # GitHub 返回 "successfully authenticated"，Gitee 返回 "Welcome to Gitee"
    if echo "$result" | grep -qiE "successfully authenticated|Welcome to"; then
        echo "  ✓ SSH 连接 ${git_host} 成功"
        return 0
    else
        echo "  ✗ SSH 连接 ${git_host} 失败: $result"
        return 1
    fi
}

# ---------- 加载配置 ----------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/deploy.conf" ]; then
    source "$SCRIPT_DIR/deploy.conf"
fi

PROJECT_DIR="${MAIN_PROJECT_DIR:-/opt/jd-service}"
BRANCH="${BRANCH:-dev}"

# 仓库地址从环境变量获取（CI 传入），不再硬编码
REPO_URL="${REPO_URL:-}"

echo "============================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 服务器初始化开始"
echo "  当前用户: $(whoami)"
echo "  项目目录: $PROJECT_DIR"
echo "  仓库地址: ${REPO_URL:-（未设置）}"
echo "============================================"

# ---------- 1. 安装 git ----------
echo "[1/4] 检查 git…"
if ! command -v git &> /dev/null; then
    if [ "$ID" = "ubuntu" ] || [ "$ID" = "debian" ]; then
        $SUDO apt-get install -y git
    elif [ "$ID" = "alinux" ] || [ "$ID" = "centos" ] || [ "$ID" = "rhel" ]; then
        $SUDO yum install -y git
    fi
    echo "  ✓ git 已安装"
else
    echo "  ✓ git 已存在: $(git --version)"
fi

# ---------- 2. 克隆项目 ----------
echo "[2/4] 配置 SSH 并拉取项目代码…"

# 如果在 CI 环境中运行（shell executor 已 checkout），跳过 SSH 和 clone
if [ "${CI_MODE:-}" = "true" ] || [ "${CI:-}" = "true" ]; then
    echo "  检测到 CI 环境，跳过 SSH 配置和 git clone（Runner 已 checkout）"
    # 确保我们在项目目录中（shell executor 已 checkout）
    if [ -d "$PROJECT_DIR" ] && [ -d "$PROJECT_DIR/.git" ]; then
        cd "$PROJECT_DIR"
    fi
else
    # 必须在 CI 环境变量中设置 REPO_URL
    if [ -z "$REPO_URL" ]; then
        echo "  ✗ REPO_URL 未设置，请在 CI variables 中配置仓库 SSH 地址"
        echo "    示例: git@github.com:owner/repo.git"
        exit 1
    fi

    # 从 REPO_URL 提取 git host
    GIT_HOST=$(extract_git_host "$REPO_URL")
    if [ -z "$GIT_HOST" ]; then
        echo "  ✗ 无法从 REPO_URL 解析 git host: $REPO_URL"
        exit 1
    fi

    # 配置 SSH 认证
    setup_ssh "$GIT_HOST"

    # 验证 SSH 连接
    if ! verify_ssh "$GIT_HOST"; then
        echo "  ✗ SSH 认证失败，请检查 GH_SSH_PRIVATE_KEY 是否正确"
        echo "    确保该 SSH 公钥已添加到 ${GIT_HOST} 仓库的 Deploy Keys 中"
        exit 1
    fi

    # 尝试 clone（带超时检测，60s 内无响应视为失败）
    try_clone() {
        local src_url="$1"
        local target_dir="$2"
        echo "  尝试 clone: $src_url"
        if timeout 60 git clone --depth 1 --single-branch --branch "$BRANCH" "$src_url" "$target_dir" 2>&1; then
            return 0
        fi
        rm -rf "$target_dir" 2>/dev/null || true
        return 1
    }

    try_fetch() {
        local src_url="$1"
        echo "  尝试 fetch: $src_url"
        git remote set-url origin "$src_url"
        # 使用显式 refspec 确保创建 remote tracking 分支（--depth 1 默认只写 FETCH_HEAD）
        if timeout 60 git fetch origin --depth 1 "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}" 2>&1; then
            # -B: 如果本地分支不存在则创建，已存在则强制重置到远程分支
            git checkout -B "$BRANCH" "origin/$BRANCH"
            echo "  ✓ 已切换到分支 $BRANCH"
            return 0
        fi
        return 1
    }

    if [ -d "$PROJECT_DIR/.git" ]; then
        echo "  项目已存在，更新代码…"
        cd "$PROJECT_DIR"

        if try_fetch "$REPO_URL"; then
            echo "  ✓ 代码更新成功"
        else
            echo "  ✗ 更新失败，请检查 SSH 认证是否有效："
            echo "    ssh -T git@${GIT_HOST}"
            exit 1
        fi
    else
        echo "  克隆项目到 $PROJECT_DIR…"
        $SUDO mkdir -p "$(dirname "$PROJECT_DIR")"
        $SUDO chown "$(whoami):$(whoami)" "$(dirname "$PROJECT_DIR")"

        if try_clone "$REPO_URL" "$PROJECT_DIR"; then
            echo "  ✓ 克隆成功"
            cd "$PROJECT_DIR"
        else
            echo "  ✗ 克隆失败，请检查 SSH 认证是否有效："
            echo "    ssh -T git@${GIT_HOST}"
            exit 1
        fi
    fi
fi

# ---------- 3. 创建 docker/.env 并注入密钥 ----------
echo "[3/4] 创建 docker/.env 配置文件…"
if [ ! -f "$PROJECT_DIR/docker/.env" ]; then
    if [ -f "$PROJECT_DIR/docker/.env.template" ]; then
        cp "$PROJECT_DIR/docker/.env.template" "$PROJECT_DIR/docker/.env"
        echo "  docker/.env 已从模板创建"
    else
        echo "  ⚠ docker/.env.template 不存在，请手动创建 docker/.env"
    fi
fi
# 无论文件是新创建还是已存在，都注入环境变量中的非空值
write_docker_env "$PROJECT_DIR/docker/.env"

# ---------- 4. 启动 Docker Compose ----------
echo "[4/4] 构建并启动所有 Docker 服务…"
cd "$PROJECT_DIR/docker"

# 确保 Neo4j 初始化脚本有可执行权限（防止 SCP 上传后丢失）
chmod +x "$PROJECT_DIR/docker/neo4j/docker-entrypoint-init.sh"

# 首次启动：构建镜像并启动
$SUDO docker compose up -d --build

echo ""
echo "============================================"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 初始化完成"
echo "============================================"
echo ""
echo "各服务状态："
$SUDO docker compose ps
echo ""
echo "访问地址："
echo "  前端页面:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')"
echo "  后端 API:  http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo '服务器IP')/health"
echo ""
echo "后续运维："
echo "  查看日志:    cd $PROJECT_DIR/docker && $SUDO docker compose logs -f"
echo "  停止服务:    cd $PROJECT_DIR/docker && $SUDO docker compose down"
echo "  重启服务:    cd $PROJECT_DIR/docker && $SUDO docker compose restart"
echo "  更新部署:    提交代码后触发 deploy workflow，或手动执行 scripts/deploy.sh"
echo ""