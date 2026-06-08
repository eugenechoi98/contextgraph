# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 5B，Packaging Artifact + uvx Local Install Validation
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 release smoke 目录：`D:\contextgraph-release-smoke\phase5b`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-09

## 当前目标

- 验证 wheel / sdist 构建、安装包内容、仓库外安装、MCP stdio、uvx 本地 wheel 启动。
- 不发布 PyPI，不 push，不创建 GitHub Release。

## 当前进度

- Phase 5A checkpoint 已提交：`3ff8951 chore(open-source): establish GitHub readiness baseline`。
- 已做最小 packaging 修复：默认 `task_strategies.yaml` 改为包内 resource，并随 wheel/sdist 分发。
- wheel / sdist 已构建到仓库外 release smoke 目录。
- wheel、sdist、MCP stdio wheel smoke、uvx 本地 wheel smoke 均已通过。

## 下一步

- 跑定向测试和全量测试。
- 做 repository hygiene、路径和密钥扫描。
- 不创建 Phase 5B commit，除非 eugene 明确要求。

## 注意事项

- 本阶段禁止继续开发 retrieval、parser、Graph、embedding、benchmark、MCP 业务逻辑或前端功能。
- 不要下载 embedding 模型，不要运行 Docker，不要执行 patch，不要跑 target repo tests。
- 不要删除 SWE-bench cache、隔离 DB、第三方 checkout 或 canonical DB。
- 构建产物、release smoke DB、uvx cache 均在仓库外。
