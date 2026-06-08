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

## 2026-06-08 - 为什么先加 source-code candidate lane，而不是先改 RRF
可以这样说：

> 这轮证据已经说明问题先发生在候选召回层，而不是融合层。RRF 的职责是整合已经召回到的候选，不负责把完全没进场的代码文件凭空变出来。所以更小、更稳的做法，是保留原始 BM25 lane，再补一个受控的 source-code lane，把相关代码先送进候选池，后面的 graph、RRF 和 token budget 都先不动。
## 2026-06-08 - 为什么这轮不硬跑 nomic，而是先建立 fallback semantic baseline
可以这样说：

> 这轮目标不是“无论代价都把指定模型跑起来”，而是先确认 Vector 到底有没有真实语义信号。如果本机只有 CPU、CUDA 不可用、显存预算只有 2GB，而且还要保护 canonical DB 和 D 盘空间，那直接拉一个 7B 模型做 smoke 风险明显偏高。更稳的工程做法，是先用受控缓存目录和轻量真实模型把语义链路验证起来，再把结论明确标注为 fallback baseline，而不是把一次不安全的实验包装成进展。
## 2026-06-08 - 为什么 adapter 一定要分 query encoding 和 document encoding
可以这样说：

> embedding 适配层最容易犯的错，是为了图省事把 query 和 code chunk 走成同一条编码路径。但像 `nomic-ai/nomic-embed-code` 这种模型，官方用法本来就区分 query prompt 和 code/document 编码。如果索引时也硬套 `prompt_name="query"`，等于把数据分布自己改坏了。工程上更稳的方式，是把职责在接口层拆开，让 indexer 只管 document 侧，retriever 只管 query 侧，fallback 模型再按能力选择是否真正支持 query prompt。
## 2026-06-08 - 为什么这轮要专门给 CodeRankEmbed 加 trust_remote_code 门禁
可以这样说：

> CodeRankEmbed 这个模型能跑，但它不是普通的纯权重模型，它会带自定义 Python 代码一起加载。这个时候最重要的不是“能不能跑起来”，而是“要不要明确知道自己在信任什么代码”。所以这轮做法是先固定 revision，再看自定义代码文件，再要求必须手动开 `trust_remote_code=true`。这样以后谁来接手，都知道这个模型不是默认随便开的。
## 2026-06-08 - 为什么最后推荐 CodeRankEmbed，而不是继续停在 MiniLM
可以这样说：

> MiniLM 已经证明了向量检索是有真实语义效果的，但它不是代码专用模型。CodeRankEmbed 这轮在同一套 13 个 case 上跑出来更好，而且没有看到比 MiniLM 更差的 case，所以现在更适合把它当成本机默认的代码语义模型。这样做不是说 MiniLM 没用，而是说我们已经有了一个更贴近代码检索场景、同时本机也能安全跑的选择。
