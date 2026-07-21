#!/usr/bin/env bash
# ECS 首次初始化（只需跑一次）。在服务器上以有 sudo 权限的用户执行。
# 用法：
#   curl -fsSL ... | bash   # 不推荐直接 curl 生产脚本
#   或：git clone 后 bash scripts/deploy/ecs-bootstrap.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/JerryFish123/ai-cr-lab.git}"
DEPLOY_PATH="${DEPLOY_PATH:-/opt/ai-cr-lab}"
BRANCH="${DEPLOY_BRANCH:-publish}"

echo "[bootstrap] install docker if needed"
if ! command -v docker >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y ca-certificates curl git
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y curl git ca-certificates
  elif command -v yum >/dev/null 2>&1; then
    sudo yum install -y curl git ca-certificates
  else
    echo "[bootstrap] 未识别包管理器，请手动安装 Docker 后重试"
    exit 1
  fi
  if command -v dnf >/dev/null 2>&1 || command -v yum >/dev/null 2>&1; then
    # 国内 ECS：优先阿里云 Docker CE 源（get.docker.com 常不可达）
    sudo dnf config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo 2>/dev/null \
      || sudo yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo
    sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin \
      || sudo yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin \
      || curl -fsSL https://get.docker.com | sudo sh
  else
    curl -fsSL https://get.docker.com | sudo sh
  fi
  sudo mkdir -p /etc/docker
  if [ ! -f /etc/docker/daemon.json ]; then
    sudo tee /etc/docker/daemon.json >/dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://mirror.ccs.tencentyun.com"
  ]
}
EOF
  fi
  sudo systemctl enable --now docker || true
  sudo usermod -aG docker "$USER" || true
fi

echo "[bootstrap] clone/update repo → $DEPLOY_PATH"
if [ -d "$DEPLOY_PATH/.git" ]; then
  sudo git -C "$DEPLOY_PATH" fetch --prune origin
  sudo git -C "$DEPLOY_PATH" checkout "$BRANCH"
  sudo git -C "$DEPLOY_PATH" reset --hard "origin/$BRANCH"
else
  sudo mkdir -p "$(dirname "$DEPLOY_PATH")"
  sudo git clone --branch "$BRANCH" "$REPO_URL" "$DEPLOY_PATH" \
    || sudo git clone "$REPO_URL" "$DEPLOY_PATH"
  sudo git -C "$DEPLOY_PATH" checkout "$BRANCH" || true
fi

sudo chown -R "$USER":"$USER" "$DEPLOY_PATH"
cd "$DEPLOY_PATH"

if [ ! -f conf/.env ]; then
  cp conf/.env.dist conf/.env
  chmod 600 conf/.env
  echo "[bootstrap] 已生成 conf/.env，请立刻编辑填入 LLM / GitHub Token / 钉钉等配置："
  echo "  nano $DEPLOY_PATH/conf/.env"
  echo "填好后再执行：bash scripts/deploy/remote-update.sh"
  exit 0
fi

bash scripts/deploy/remote-update.sh
echo "[bootstrap] 完成。请确认安全组放行 5001/5002，并访问 http://<公网IP>:5001"
