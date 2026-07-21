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

# 国内 ECS 直连 GitHub 偶发 Empty reply：带重试；失败则尝试 ghproxy 镜像拉取
fetch_ok=0
for attempt in 1 2 3; do
  if git fetch --prune "$REMOTE" "$BRANCH"; then
    fetch_ok=1
    break
  fi
  echo "[deploy] git fetch 失败 (attempt=$attempt)，3s 后重试…"
  sleep 3
done

if [ "$fetch_ok" -ne 1 ]; then
  ORIGIN_URL="$(git remote get-url "$REMOTE")"
  case "$ORIGIN_URL" in
    https://github.com/*)
      MIRROR_URL="https://ghproxy.net/${ORIGIN_URL}"
      echo "[deploy] 改用镜像拉取: $MIRROR_URL"
      git fetch --prune "$MIRROR_URL" "+refs/heads/${BRANCH}:refs/remotes/${REMOTE}/${BRANCH}"
      ;;
    *)
      echo "[deploy] ERROR: git fetch 失败且无法推断镜像 URL: $ORIGIN_URL"
      exit 1
      ;;
  esac
fi

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
