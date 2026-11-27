# ── 前端 + nginx 多阶段构建 ──────────────────────────
#
# 阶段 1：Node.js 编译 Vue/Vite 前端
# 阶段 2：nginx 提供静态文件 + 反向代理

# ============================================================
# 阶段 1：编译前端
# ============================================================
FROM node:22-alpine AS frontend-builder

WORKDIR /build

# 利用 Docker 层缓存：先装依赖，再拷源码
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# 容器化后 API 使用相对路径（前后端由同一 nginx 服务）
ENV VITE_API_BASE_URL=/api/v1

RUN npm run build

# ============================================================
# 阶段 2：nginx 服务
# ============================================================
FROM nginx:alpine

# 移除默认配置
RUN rm /etc/nginx/conf.d/default.conf

# 使用自定义 nginx 配置
COPY docker/nginx/nginx.conf /etc/nginx/conf.d/default.conf

# 从阶段 1 复制前端构建产物
COPY --from=frontend-builder /build/dist /var/www/jd-cs

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
