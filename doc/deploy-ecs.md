# 最低成本部署：GitHub `publish` → 阿里云 ECS

目标：推送到 [`publish`](https://github.com/JerryFish123/ai-cr-lab) 分支后，GitHub Actions 自动 SSH 到 ECS，拉取代码并用 Docker 重建服务。

**不需要再买服务器**（使用已有 ECS）。额外成本 ≈ 0（公开仓库 Actions 免费额度通常够用）。

## 架构

```text
git push origin publish
  → GitHub Actions
  → SSH 登录 ECS
  → git reset --hard origin/publish
  → docker compose up -d --build
  → 服务监听 :5001 / :5002
```

密钥分工：

| 位置 | 内容 |
|------|------|
| GitHub Secrets | ECS 主机、SSH 私钥（仅部署用） |
| ECS 本地 `conf/.env` | LLM / GitHub Token / 钉钉（**永不进 Git**） |

---

## 一、阿里云 ECS（控制台操作）

1. 确认实例已运行，记下 **公网 IP**。
2. **安全组入方向**放行：
   - `22/TCP`：你的办公网 IP（SSH；不要对 `0.0.0.0/0` 长期敞开更稳妥）
   - `5001/TCP`：`0.0.0.0/0`（给 GitHub Webhook 回调）
   - `5002/TCP`：可选，Dashboard；若不需要可不开
3. 登录 ECS（控制台「远程连接」或本地 `ssh root@公网IP`）。

在 ECS 上执行首次初始化（示例）：

```bash
# 若还没有 publish 分支代码，可先 clone main 再 checkout；bootstrap 会拉 publish
sudo apt-get update && sudo apt-get install -y git curl
git clone https://github.com/JerryFish123/ai-cr-lab.git /tmp/ai-cr-lab-src
sudo bash /tmp/ai-cr-lab-src/scripts/deploy/ecs-bootstrap.sh
# 按提示编辑 /opt/ai-cr-lab/conf/.env 后，再执行：
cd /opt/ai-cr-lab && bash scripts/deploy/remote-update.sh
```

验证：

```bash
curl -sS http://127.0.0.1:5001/
# 浏览器：http://<公网IP>:5001
```

---

## 二、为部署准备 SSH 密钥（推荐独立密钥）

在**你自己电脑**上生成仅用于 CI 的密钥（不要用登录密码）：

```bash
ssh-keygen -t ed25519 -C "github-actions-ai-cr-lab" -f ~/.ssh/ai_cr_lab_deploy -N ""
ssh-copy-id -i ~/.ssh/ai_cr_lab_deploy.pub root@<ECS公网IP>
# 测试
ssh -i ~/.ssh/ai_cr_lab_deploy root@<ECS公网IP> 'echo ok'
```

---

## 三、配置 GitHub Secrets

打开：仓库 → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|------|--------|
| `ECS_HOST` | ECS 公网 IP |
| `ECS_USER` | 如 `root` 或 `ecs-user` |
| `ECS_SSH_KEY` | **私钥**全文（`~/.ssh/ai_cr_lab_deploy` 文件内容，含 `BEGIN`/`END`） |
| （部署路径固定） | 服务器目录：`/opt/ai-cr-lab`（与 workflow 一致） |

---

## 四、使用方式（日常）

```bash
# 本地把要上线的改动合到 publish
git checkout publish
git merge main   # 或直接在 publish 上改
git push origin publish
```

然后到 GitHub → **Actions → Deploy publish → ECS** 看是否绿灯。

---

## 五、给「被审查的业务仓库」配 Webhook

在任意要自动 Review 的 GitHub 仓库：

- Payload URL：`http://<ECS公网IP>:5001/review/webhook`
- Content type：`application/json`
- 事件：Pull requests + Pushes

（HTTPS 可后续用 Nginx + 免费证书；最低成本可先用 HTTP。）

---

## 故障排查

| 现象 | 处理 |
|------|------|
| Actions SSH 失败 | 检查安全组 22、公钥是否在 `~/.ssh/authorized_keys`、Secrets 私钥是否完整 |
| 部署报缺少 conf/.env | 在 ECS 上创建并 chmod 600 |
| 页面打不开 | 安全组是否放行 5001；`docker compose ps` / `docker compose logs` |
| Webhook 失败 | ECS 公网是否可达；GitHub 仓库 Settings → Webhooks 看 Deliveries |

---

## 成本说明

- ECS：你已有实例，无新增购机费用  
- GitHub Actions：公开仓通常免费额度足够  
- 流量/LLM：按火山方舟与 GitHub API 实际用量计费  
