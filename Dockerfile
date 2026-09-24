# 多阶段构建：前端产物 + 后端运行时合一镜像（D2 一体化部署）
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
# 境内构建固定走清华 PyPI 镜像（uv sync 网络超时是部署主要失败源）
ENV UV_DEFAULT_INDEX=https://pypi.tuna.tsinghua.edu.cn/simple
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ .
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
EXPOSE 8100
# 运行期 --no-sync：依赖在构建层已 uv sync 装好，容器启动不做任何网络安装
# （uv run 默认会重新同步依赖组，境内网络拉 PyPI 超时会导致启动失败）
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8100"]
