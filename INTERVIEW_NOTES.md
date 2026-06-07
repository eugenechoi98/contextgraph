# INTERVIEW_NOTES

## 2026-06-08 - 为什么要先恢复 canonical workspace，再继续开发

可以这样说：

> 这轮最重要的不是继续堆功能，而是先把正式工作区、数据库和验证口径收回来。因为如果同一个项目在两个不同目录里分别开发、测试和 index，所有 test count、repo_id、trace 和 eval 结论都会失真。先恢复唯一 canonical workspace，后面的优化才有可信坐标系。

## 2026-06-08 - 为什么 RRF 不能只合分数，还要合并 metadata

可以这样说：

> 在 Hybrid Retrieval 里，同一个 chunk 可能既被 BM25 命中，也被 graph 命中。如果融合层只保留先到的那份 chunk，再把分数加起来，graph 的路径信息就会丢掉。结果是分数看起来对了，但 explainability 变差了。工程里真正稳的做法，是把 score 融合和 metadata 合并都做好。

## 2026-06-08 - 为什么 eval 泄题要在 intake 层解决

可以这样说：

> 如果 fixture、report 或临时调试文件能被索引，那检索系统其实是在偷看答案。这个问题不能靠团队记忆避免，必须在 intake 层直接封死。这样评测结果才值得信。

## 2026-06-08 - 为什么 ablation 不能只看 retrieval_strategy
可以这样说：

> `retrieval_strategy` 只能说明最后哪些路由真的带着结果进入了 ContextPack，但它不能解释某条路由为什么没参与。工程上我们需要至少区分三层：配置请求了什么、代码实际执行了什么、最后哪些路由真的参与了融合。这样看到 `bm25_graph` 最终只剩 `bm25` 时，才能分清是 graph 被关了、没 seed、空 traversal，还是别的降级原因。

## 2026-06-08 - 为什么这轮不急着做 Code Seed Reserve
可以这样说：

> `chunking_001` 这次不是代码候选刚好卡在 seed limit 外面，而是目标文件 `chunker.py` 连 BM25 top 30 都没进，第一次出现已经到 rank 172。这个时候去做 code-seed reserve，本质上是在硬拉很靠后的代码 chunk，容易制造假提升。更稳的做法是先承认它是候选召回问题，再决定要不要做 query expansion 或 chunk text shaping。
