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