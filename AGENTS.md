# AGENTS.md

## 称呼
- 每次回复先称呼我 `eugene`

## 输出规则
- 每次最终回复都附上“面试知识点”
- 面试知识点要围绕本轮真实工程决策来写，不写空泛定义

## Canonical Workspace

本项目唯一正式工作区为：

D:\contextgraph-studio

每轮开始前必须执行：

Get-Location
git rev-parse --show-toplevel

只有当两者都指向 D:\contextgraph-studio 时，才允许修改文件、运行写型验证、执行 index、eval、serve 或 mcp。

如果当前目录不是 D:\contextgraph-studio：
- 立即停止修改
- 不在其他目录继续开发
- 不复制或覆盖文件
- 先切回正式工作区

C:\Users\Administrator.DESKTOP-5G2BKSD\Documents\contextgraph
仅作为迁移来源快照保留，不得继续开发。

## Python 环境
- 优先使用项目本地虚拟环境
- Windows 使用 `.venv\Scripts\python.exe`
- 不直接使用系统 `python`

## 文档读取顺序
1. `AGENTS.md`
2. `CONTEXT.md`
3. `DECISIONS.md`
4. `TIMELINE.md`
5. `VALIDATION_SPEED_POLICY.md`
6. `README.md`
7. `ARCHITECTURE.md`
8. `DEPLOYMENT.md`

## 文档维护
- `CONTEXT.md` 只保留当前现场
- `TIMELINE.md` 记录阶段性变化
- `DECISIONS.md` 记录关键设计取舍
- `DEPLOYMENT.md` 记录本地运行、验证与工作区约束

## 验证原则
- 当前项目仍处于 0->1 早期阶段
- 默认采用 Early-stage Lightweight Review
- 发现明显 bug 直接修复并重跑相关验证
- 不在错误工作区上继续开发或验证