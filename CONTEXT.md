# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 5F，GitHub public baseline 文档收口
- 当前公开仓库：`https://github.com/eugenechoi98/contextgraph`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-09

## 当前目标

- 记录 initial public GitHub baseline 已上线，并确认 Linux GitHub Actions CI 已通过。

## 当前进度

- Initial public GitHub baseline is live.
- Linux GitHub Actions CI passed after cross-platform CLI / MCP test compatibility fixes.
- 最新 CI 修复提交：`0976bd9 fix(ci): make CLI and MCP tests cross-platform`。

## 下一步

- 等待 eugene 检查公开仓库页面，并决定是否进入 tag / release / PyPI 后续流程。

## 注意事项

- 不要创建 tag、GitHub Release 或发布 PyPI，除非 eugene 明确确认。
- 不要修改 retrieval、parser、Graph、embedding、benchmark、MCP 业务逻辑或 CI workflow。
- 不要删除 SWE-bench cache、隔离 DB、第三方 checkout 或 canonical DB。
