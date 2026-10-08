# Agent 协作约定

## GitHub + ECS 必须双端生效

对本仓库完成功能或修复后，**默认必须**同时：

1. 在 `publish` 分支 commit 并 `git push origin publish`
2. 确认 ECS 已部署同一 commit（Actions 成功，或 SSH 手动 `bash scripts/deploy/remote-update.sh`）
3. 向用户汇报：**commit hash**、GitHub push 状态、ECS 验收结果

**不要**只做 scp 不 push，或只 push 不确认 ECS。

### ECS

| 项 | 值 |
|----|-----|
| Host | `39.96.125.66` |
| 路径 | `/opt/ai-cr-lab` |
| SSH | `ssh -i ~/.ssh/ai_cr_lab_deploy root@39.96.125.66` |
| 看板 | http://39.96.125.66:5002/ |
| Webhook | http://39.96.125.66:5001/ |

### 注意

- 勿提交 `conf/.env` 或任何密钥
- MySQL OOM 时 Actions 可能失败；ECS 已配置 swap，失败时用 SSH 补部署
