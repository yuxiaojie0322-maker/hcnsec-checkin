# 🛡️ hcnsec.cn 每日签到工作流

公开运行 GitHub Actions 工作流，核心运行脚本存放于统一私有仓库 `my-private-scripts/hcnsec` 中。
自动登录并完成每日签到、额度统计与 Telegram 结果推送。

## 配置说明

需要在本仓库的 **Settings -> Secrets and variables -> Actions** 中配置以下 Secrets：

| Secret 名称 | 说明 | 是否必填 |
| :--- | :--- | :--- |
| `CORE_SCRIPT_TOKEN` 或 `REPO_TOKEN` | 具备读取私有仓库 `my-private-scripts` 权限的 GitHub Personal Access Token (PAT) | 必填 |
| `HCN_ACCOUNTS` | 账号密码，格式：`user1:pass1\|user2:pass2` 或 JSON 数组 | 必填 |
| `TG_BOT_TOKEN` | Telegram Bot Token，用于发送签到通知 | 选填 |
| `TG_CHAT_ID` | Telegram 接收通知的 Chat ID | 选填 |

## 手动触发测试

1. 打开本仓库的 **Actions** 页面。
2. 选择 **hcnsec 每日签到** 工作流。
3. 点击 **Run workflow** 手动触发测试。
4. 之后每天 UTC 22:30（北京时间 6:30）自动定时执行。
