#!/bin/sh
# 容器启动入口: 先跑 alembic migrations, 再起 uvicorn。
# alembic 失败不 block 启动 (保留 best-effort 行为, 生产观察日志)。
set -e

echo "[entrypoint] running alembic upgrade head..."
if alembic upgrade head; then
    echo "[entrypoint] alembic upgrade ok"
else
    echo "[entrypoint] alembic upgrade failed — continuing anyway (legacy schema may be in place)" >&2
fi

echo "[entrypoint] starting uvicorn on 0.0.0.0:${PORT:-8000}"
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2
