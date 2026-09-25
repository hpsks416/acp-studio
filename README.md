> ⚠️ **本仓库已废弃**：内容已并入 [agent-deploy](https://github.com/hpsks416/agent-deploy) 的 skills/acp-studio/ 子目录，请以 agent-deploy 为准。本仓库保留仅供历史归档。

# acp-studio

本地统一的 GitHub/Gitee 提交与双向同步面板：合并了 git-acp / gitee-acp / gh-gitee-sync 三个 skill，一键提交、推送并做双向同步。

## 环境依赖

- 操作系统：Windows
- 运行时：Python 3（标准库）
- 第三方软件：git

## 目录结构

    acp-studio/
    ├── SKILL.md    技能入口与工作流
    ├── evals.yaml
    ├── agents\openai.yaml
    ├── scripts\sync_github_gitee.py

## 安装

    # GitHub
    git clone https://github.com/hpsks416/acp-studio.git "$env:USERPROFILE\.dsh\skills\acp-studio"
    # 或 Gitee（国内直连）
    git clone https://gitee.com/hpsks416/acp-studio.git "$env:USERPROFILE\.dsh\skills\acp-studio"

克隆后 DSH 自动重新发现，无需构建。

## License

MIT License. See [LICENSE](LICENSE).

