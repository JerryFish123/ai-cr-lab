#!/usr/bin/env bash
# 在 ECS 上执行：拉取 publish 并重建容器（不触碰 conf/.env）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BRANCH="${DEPLOY_BRANCH:-publish}"
REMOTE="${DEPLOY_REMOTE:-origin}"

echo "[deploy] cwd=$ROOT_DIR branch=$BRANCH"

if [ ! -f conf/.env ]; then
  echo "[deploy] ERROR: 缺少 conf/.env（密钥仅存服务器本地，不从 Git 拉取）"
  echo "[deploy] 请从 conf/.env.dist 复制并填写后重试"
  exit 1
fi

git fetch --prune "$REMOTE" "$BRANCH"
git checkout "$BRANCH"
git reset --hard "$REMOTE/$BRANCH"

echo "[deploy] HEAD=$(git rev-parse --short HEAD)"

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    echo "[deploy] ERROR: 未找到 docker compose"
    exit 1
  fi
  "${COMPOSE[@]}" up -d --build --remove-orphans
  "${COMPOSE[@]}" ps
else
  echo "[deploy] ERROR: 未安装 docker，请先跑 ecs-bootstrap.sh"
  exit 1
fi

echo "[deploy] done"
