# acp-studio

把原来的 `git-acp`、`gitee-acp`、`gh-gitee-sync` 三个技能合并成一个本地项目 + 一个可视化界面 + 一个 SKILL：在一个网页里完成 GitHub 提交、Gitee 提交，以及 GitHub ⇄ Gitee 双向同步。

零第三方依赖，仅需 Python 3.9+ 标准库和本机 `git`。

## 参考依赖

本项目合并自以下三个仓库，并保留其核心能力：

- [`gacp-studio`](https://github.com/hpsks416/gacp-studio)：GitHub 提交面板原型（前端结构来源）。
- [`gacpee-studio`](https://github.com/hpsks416/gacpee-studio)：Gitee 提交面板原型（Gitee 推送与凭据逻辑来源）。
- [`gh-gitee-sync`](https://github.com/hpsks416/gh-gitee-sync)：双向同步脚本来源（`scripts/sync_github_gitee.py`）。

## 功能

- 一个界面选择推送目标：GitHub (`origin`) 或 Gitee (`gitee`)。
- Conventional Commits + Gitmoji 提交信息组装与实时预览。
- 一键 `add + commit + push`，或只提交不推送。
- 工作区状态：分支、GitHub/Gitee 远端、领先/落后、暂存/未暂存/未跟踪、最近提交。
- 内置“GitHub ⇄ Gitee 双向同步”按钮，一键运行同步脚本（支持 dry-run）。
- Gitee/GitHub 推送自动走 `http.sslBackend=openssl` 兜底，令牌自动脱敏。
- 仅监听 `127.0.0.1`，不对外暴露。

## 目录结构

```
acp-studio/
├── server.py                    # 零依赖本地 HTTP 服务（静态文件 + JSON API）
├── scripts/sync_github_gitee.py # 双向同步脚本（来自 gh-gitee-sync）
├── SKILL.md                     # Codex 技能
├── agents/openai.yaml           # 界面元数据
├── start.cmd / start.sh         # 启动脚本
├── config.json                  # 端口、远端、凭据配置
└── web/ (index.html, app.js, styles.css)
```

## 环境要求

- Python 3.9+
- git（在 `PATH` 或 `config.json` 的 `git_path`）
- 现代浏览器

## 快速开始

Windows：双击 `start.cmd`，浏览器自动打开 `http://127.0.0.1:8790/`。

macOS / Linux：

```bash
./start.sh
```

或手动：

```bash
python server.py
```

## JSON API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/repo?repo=<abs>` | 工作区状态（含 GitHub/Gitee 远端） |
| POST | `/api/commit` | `{repo_path, message, push, target}` 提交并可选推送 |
| POST | `/api/push` | `{repo_path, target}` 仅推送 |
| POST | `/api/sync` | `{repos, dry_run}` 运行一次双向同步 |
| GET/POST | `/api/state` | UI 状态持久化 |
| GET | `/api/types` | Conventional Commits 类型 |

## 配置

`config.json` 主要字段：`port`（8790）、`github_remote`（origin）、`gitee_remote`（gitee）、`github_user`、`gitee_user`、`gitee_token`、`use_openssl`。凭据优先从环境变量 `GITHUB_TOKEN`、`GITEE_USERNAME`、`GITEE_TOKEN` 读取，令牌绝不写入仓库配置。

## 许可证

[MIT License](LICENSE)

## 免责声明

本工具会执行真实的 `git add / commit / push` 与双向同步，请在执行前确认目标仓库与提交信息无误，并妥善保管私人令牌。
