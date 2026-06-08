# CONTEXT

- 当前正式工作区：`D:\contextgraph-studio`
- 禁止继续开发路径：`C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph`
- 当前阶段：Phase 5A，Open-source Readiness Audit + CI + Clean Install Smoke
- 当前 canonical DB：`D:\contextgraph-studio\.data\contextgraph.db`
- 当前 SWE-bench cache：`D:\contextgraph-swebench-cache`
- 当前虚拟环境：`D:\contextgraph-studio\.venv`
- 最后更新时间：2026-06-08

## 当前目标

- 功能冻结，把当前可运行项目收敛成可以安全放到 GitHub 的开源基线。
- 只做 README / MCP 示例 / CI / clean install smoke / 仓库清洁检查。

## 当前进度

- Phase 4E-D.1 checkpoint 已提交：`e6d1d5e feat(parser): index Python module-level assignments`。
- 旧 `HANDOFF_2026-06-08_Phase4B.md` 已确认为过期中途草稿并删除。
- README 已改为 GitHub 用户入口。
- 已新增 MCP 客户端配置样例和 GitHub Actions CI。

## 下一步

- 跑定向测试、全量测试、clean install smoke。
- 做仓库清洁、路径和密钥扫描。
- 不创建 Phase 5A commit，除非 eugene 明确要求。

## 注意事项

- 本阶段禁止继续开发 retrieval、parser、Graph、embedding 或 benchmark 功能。
- 不要下载 embedding 模型，不要跑第 4 个 SWE-bench 实例，不要跑完整 300-case benchmark。
- 不要删除 SWE-bench cache、隔离 DB、第三方 checkout 或 canonical DB。
- 默认模式必须保持 no-model-download：`VECTOR_INDEX_ENABLED=false`，`HYBRID_VECTOR_ENABLED=false`。
