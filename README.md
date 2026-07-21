# ai-cr-lab

基于大模型的 **AI Code Review** 实验项目。  
当仓库发生 Push / Pull Request（或 Merge Request）时，自动拉取变更、调用 LLM 审查，并把结果回写到 PR/Commit 评论；可选推送到钉钉等 IM。

> 远程仓库：[JerryFish123/ai-cr-lab](https://github.com/JerryFish123/ai-cr-lab)

## 能做什么

- 接入 **GitHub / GitLab / Gitea** Webhook
- 多模型：OpenAI 兼容接口（如火山方舟）、DeepSeek、Anthropic、通义、Ollama 等
- 审查策略：
  - `diff_only`：只审 diff（默认，成本低）
  - `agentic`：克隆仓库后工具探索（`read_file` / 沙箱命令），失败自动降级
- 审查风格：专业 / 讽刺 / 绅士 / 幽默
- IM 通知：钉钉 / 企业微信 / 飞书
- Dashboard：审查记录与简单统计（Streamlit）

## 原理

```text
Git 平台事件（Push / PR / MR）
  → Webhook POST /review/webhook
  → 异步 Worker 拉 diff
  → LLM 生成审查报告（含总分）
  → 回写评论 +（可选）IM 通知 + 落库
```

## 本地快速启动

1. 准备 `conf/.env`（可从 `conf/.env.dist` 复制）
2. Python **3.10+**，建议虚拟环境：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python api.py
```

3. 浏览器打开 API：`http://127.0.0.1:5001`  
4. 将 GitHub Webhook 指向公网可达地址：`https://<你的域名或隧道>/review/webhook`  
   （本机演示需隧道或云服务器；GitHub 无法直接访问 `127.0.0.1`）

## 配置要点

| 配置项 | 说明 |
|--------|------|
| `LLM_PROVIDER` | 如 `openai`（可接火山方舟 OpenAI 兼容 Base URL） |
| `GITHUB_ACCESS_TOKEN` / `GITLAB_ACCESS_TOKEN` | 读 diff、写评论 |
| `REVIEW_STRATEGY` | `diff_only` 或 `agentic` |
| `DINGTALK_*` | 可选，群机器人通知 |

密钥只放在本地 `conf/.env`，**不要提交到 Git**。

## 部署到阿里云 ECS（`publish` 一键更新）

推送到 **`publish`** 分支后，GitHub Actions 会 SSH 到已有 ECS，自动 `git pull` + `docker compose up -d --build`。

完整步骤见：[doc/deploy-ecs.md](doc/deploy-ecs.md)

## 项目定位

本仓库用于作品集与工程实验：验证「变更进入仓库 → AI 审查生效」的完整闭环。  
企业平台化叙事（如百炼工作流）与本仓库演示职责区分，避免混为一谈。

## 致谢

实现参考并演进自开源项目 [AI-Codereview-Gitlab](https://github.com/sunmh207/AI-Codereview-Gitlab)。
