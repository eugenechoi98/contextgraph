# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：外部用户 onboarding 与 README demo 收口
- 当前公开仓库：`https://github.com/eugenechoi98/contextgraph`
- 当前 clean-room smoke 目录：`D:\contextgraph-external-user-smoke`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-09

## 当前目标

- 证据化验证 Quick Start 行为，并让 README 更适合第一次 clone 的外部用户。

## 当前进度

- 已确认 `cgstudio index .` 输出 `repo_id`。
- 已确认 `cgstudio retrieve` 未传 `repo_id` 时会使用最近一次成功 scan。
- 已使用独立 venv 和独立 DB 完成外部用户 clean-room smoke。

## 下一步

- 等待 eugene 决定是否添加 README 截图或继续进入 tag / release / PyPI 后续流程。

## 注意事项

- 本轮只提交并 push README / CONTEXT / TIMELINE 文档改动。
- 不要修改 retrieval、parser、Graph、embedding、benchmark、MCP 业务逻辑或 CI workflow。
- 不要删除 SWE-bench cache、隔离 DB、第三方 checkout、clean-room smoke 目录或 canonical DB。
