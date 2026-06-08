# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 5C，GitHub 发布前最终审计
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 release smoke 目录：`D:\contextgraph-release-smoke\phase5c`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-09

## 当前目标

- 完成 GitHub 发布前最终收口：MIT LICENSE、发布元数据、Git 历史和仓库清洁审计、README / MCP / CI 最终核对、发布清单。

## 当前进度

- Phase 5B checkpoint 已提交：`932fe8f fix(packaging): ship runtime task strategies in distributions`。
- 已新增标准 MIT `LICENSE`。
- 已新增 `RELEASE_CHECKLIST.md`。
- `pyproject.toml` 已补 `license = { file = "LICENSE" }`。

## 下一步

- 重建 wheel / sdist，确认 LICENSE 和 runtime package data 进入产物。
- 跑 Git 历史审计、仓库清洁审计和全量测试。
- 不创建 Phase 5C commit，除非 eugene 明确要求。

## 注意事项

- 本阶段禁止 push、创建远程仓库、发布 PyPI、创建 GitHub Release 或 tag。
- 不要修改 retrieval、parser、Graph、embedding、benchmark 或 MCP 业务逻辑。
- 不要下载 embedding 模型，不要运行 Docker，不要执行 patch，不要跑 target repo tests。
- 不要删除 SWE-bench cache、隔离 DB、第三方 checkout 或 canonical DB。
