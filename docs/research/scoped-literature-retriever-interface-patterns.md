# Scoped Literature Retriever 接口模式研究

Research date: 2026-08-29 (Asia/Shanghai)

对应 Wayfinder ticket `Define the Scoped Literature Retriever contract` 的 Q4（query/control）与 Q6（最小 model-visible output）。本报告只研究合同模式，不选择最终 ranking 算法，也不改变 ticket、`CONTEXT.md` 或 runtime。

## 结论

主流学术 API 和 AI/MCP 文献工具解决的是“从持续更新的全球索引中发现论文”：调用方通常可以选择 corpus、搜索模式、filters、sort、page size、pagination 和输出字段。这个宽控制面是开放探索的产品能力，不是本项目应照搬的默认值。

本项目的问题更窄：在 runtime preflight 已绑定的、仅含 3–36 篇论文的唯一 Approved Target Reference Corpus 中，为 ideation model 返回有限、source-faithful evidence。由此导出的候选合同是：

1. 模型只提交一个非空自然语言 `query`；未知字段一律拒绝。`case_id`、corpus/path/hash、paper IDs、`top_k`、filters、sort、pagination、search mode、content type 均不是 model-controlled input。
2. query 不得静默截断。runtime policy 固定最大长度、normalization、返回论文数、每篇 segment 数/长度、ranking version 和稳定 tie-break；私有审计同时保留 raw query 与 normalized query。
3. model-visible success payload 的不可约核心只有：本地 `paper_id`、`title`、按相关性排好序的 source-faithful `segments[{content_type,text}]`。数组顺序已表达 rank；不重复发送 `rank`。`year` 可能对时间/novelty 判断有用，但尚需后续 rubric/ranking validation 证明；其余 metadata 默认留在私有审计。
4. 不向模型发送 score、candidate set、corpus/hash/path、source offsets/hashes、query echo、total count、排除原因、ranking explanation、external identifiers、URL、citation count 或 provider-generated takeaway。它们要么重复、不可操作，要么会把动态/派生信号伪装成论文证据。
5. 私有 Retrieval Audit Event 必须比 model-visible payload 丰富：记录 corpus identity、全部 policy/ranking versions、eligible/ineligible candidates、scores、tie-break、source pointers/hashes、最终 payload hash、错误与时间信息。可审计不等于把审计细节塞进模型上下文。

这是一组带入 grilling 的证据化建议，不替 Robert 锁定最终合同。`year` 是否进入模型、query 最大长度和返回/segment 上限必须在后续最小实证中确定。

## 研究边界与方法

只使用系统所有者发布的 primary sources：官方 API 文档、官方 API 规格、官方项目仓库。覆盖：

- Semantic Scholar Academic Graph API；
- OpenAlex API；
- Crossref REST API；
- NCBI PubMed E-utilities；
- Elicit API 与官方 MCP；
- Consensus API 与官方 MCP。

Scite 有官方 MCP 产品页，但本轮未在公开页面找到可核验的 tool input/output schema；因此只记录为“存在”，不拿其能力描述推断接口合同（[Scite MCP 官方页](https://scite.ai/mcp)）。本轮也未找到可核验的 Google Scholar 官方公开检索 API，因而没有用第三方 wrapper 代替官方证据。Europe PMC 与 PubMed 在生命科学覆盖上有重叠；本轮选择文档更完整、明确分离 search 与 fetch 的 NCBI E-utilities 作为代表。

比较重点是 query schema、filters/limit/pagination/sort、结果字段、score/snippet/provenance、empty/error/rate-limit，以及 determinism/replay implications。外部产品的全局检索能力不等于本项目的 runtime 授权。

## 接口对照

### Query 与控制面

| 系统 | 搜索范围 | 调用方可控输入 | 结果规模与顺序 |
| --- | --- | --- | --- |
| Semantic Scholar Academic Graph | 持续更新的全局学术图谱 | bulk search 要求 `query`；可传 `fields`、`sort`、publication type、OA PDF、minimum citation count、date/year、venue、field of study 等 filters | relevance search 用 `limit`/`offset`；bulk search 用 continuation `token`，并允许按 `paperId`、publication date 或 citation count 排序。官方 tutorial 说明两种搜索使用 custom-trained ranker（[Semantic Scholar API tutorial](https://www.semanticscholar.org/product/api/tutorial)） |
| OpenAlex | 持续更新的全局 OpenAlex dataset | `search`、`search.exact` 或 `search.semantic` 三选一；可叠加 filters、`select`、`sort` | `page`/`per_page` 或 cursor；普通 search 默认按 `relevance_score` 降序，score 同时结合 text similarity 与 citation count。semantic search 最多使用 2,000 characters，超出部分会被截断，最多返回 50 篇（[search](https://help.openalex.org/api/searching/)、[semantic search](https://help.openalex.org/api/semantic-search/)、[paging](https://help.openalex.org/api/paging/)） |
| Crossref REST | 持续更新的全局 Crossref metadata | 通用 `query`、`query.bibliographic` 等 field queries；大量 metadata filters；`select`、`sort`/`order` | `rows` 默认 20、最高 1,000；支持 offset/cursor。官方 Swagger 将 query、filter、select、sorting 和 large result sets 分开定义（[Crossref Swagger](https://api.crossref.org/)、[REST tips](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)） |
| NCBI PubMed E-utilities | PubMed/Entrez 全局数据库 | ESearch 要求 `db` 与 `term`；可传 field/date constraints、`sort`、`retstart`/`retmax`、`usehistory`、`WebEnv`/`query_key` | ESearch 返回 UID set；`retmax` 默认 20，PubMed 最多直接取前 10,000；PubMed sort 支持 publication date、author、journal 和 relevance。随后按 UID 用 ESummary/EFetch 取 metadata 或 abstract/full record（[E-utilities ESearch/ESummary/EFetch](https://www.ncbi.nlm.nih.gov/books/NBK25499/)） |
| Elicit API/MCP | Elicit 全局索引或 PubMed | `query` 加可选 `corpus`、semantic/keyword `searchMode`、`maxResults`、year/date、keywords、PDF、journal quartile、study type、retraction 等 filters；keyword mode 与 filters 互斥 | `maxResults` 默认 10，plan 决定上限；官方 MCP 把同一组 controls 暴露成 `search_papers` tool（[Elicit API](https://docs.elicit.com/)、[Elicit MCP tool reference](https://github.com/elicit/api-examples/tree/main/integrations/mcp)） |
| Consensus API/MCP | Consensus 全局索引 | MCP `search` 接受 `query`，并可选 year、study type、SJR quartile、human、sample size、medical mode、preprint 和 duration filters；REST 还暴露 citation、OA、domain、country、journal、`page`/`page_size` 等 | MCP 每次返回数受 plan 控制；REST 有 page/page size。REST 可请求 semantic score 和 query-relevant full-text chunks（[Consensus MCP](https://docs.consensus.app/docs/mcp)、[Consensus search API](https://docs.consensus.app/reference/v1_search)） |

### 返回值、score、snippet 与错误

| 系统 | 成功结果 | Score / snippet | Empty、error 与 rate-limit |
| --- | --- | --- | --- |
| Semantic Scholar | bulk response 是 estimated `total`、continuation `token` 和 `data[]`；paper field 可由 `fields` 投影 | 官方 search contract 没有承诺向 client 返回可校准 relevance score；abstract 等 paper metadata 可按需请求 | tutorial 列出 400/401/403/404/429/500；API key 的 introductory rate 是 1 RPS，未认证请求共享公共配额（[tutorial](https://www.semanticscholar.org/product/api/tutorial)、[API overview](https://www.semanticscholar.org/product/api)） |
| OpenAlex | 所有 list endpoints 使用 `meta{count,page,per_page,cost_usd}`、`results[]`、`group_by[]` envelope；`select` 可裁剪 root-level fields | 普通与 semantic search 可返回 `relevance_score`；官方 search 文档没有定义 query-highlight/snippet | 标准 400/403/404/429/500 与 `{error,message}`；429 可能来自 rate 或 daily budget，并提供 rate-limit headers（[response/select](https://help.openalex.org/api/)、[errors](https://help.openalex.org/api/errors/)） |
| Crossref | JSON metadata records；works query 结果可含 `score`，`select` 可裁剪 DOI/title 等字段 | score 是全局 metadata match signal；接口不提供 source-faithful query excerpt contract | 429 时 backoff；limit/concurrency 来自 response headers。官方说明分页期间 reindex 可能使 items 加入/移出结果集，并建议 cache 与固定 index-date window（[access and rate limits](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)、[REST tips](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/)） |
| NCBI PubMed | ESearch 先返回 Count/UIDs，可选 History Server handles；ESummary/EFetch 再返回 structured metadata、abstract 或完整 XML/text | ESearch 不返回可供模型解释的 relevance score 或 source excerpt。其 search→UID→fetch 分层避免把“发现顺序”冒充“论文证据” | 请求应带 `tool`/`email`；超过 3 requests/s 应使用 API key，标准 key 支持 10 requests/s。文档要求调用方处理服务错误；无命中可由 Count/空 UID set 表达（[E-utilities reference](https://www.ncbi.nlm.nih.gov/books/NBK25499/)、[usage policy](https://www.ncbi.nlm.nih.gov/books/NBK25497/)） |
| Elicit API/MCP | `papers[]` 包含 title、authors、year、abstract、DOI/PMID/internal ID、venue、citation count、URLs；另有 non-fatal `warnings[]` | search response schema不返回 score、highlight 或 query snippet | 400 validation、401 auth、402 quota、403 plan、429 rate、500 server error；统一错误通常为 `{error:{code,message}}`。超过 100 requests/min/IP 会返回 429 并封锁 5 分钟（[Elicit API](https://docs.elicit.com/)） |
| Consensus API/MCP | MCP 返回 `papers[]`、`total_results`、原 query；paper 有 title、authors、abstract、journal、year、citation count、URL，plan 较高时增加 study type/takeaway，Enterprise 可有 DOI | MCP search schema不返回 score/chunks；REST 可选择 `include_semantic_score`（仅 top 50）和 `include_full_text_chunks`。`takeaway` 是产品派生内容，不是 source-faithful paper text | 官方 MCP docs 将“no results”与 429 分开：无结果建议调整 query/filter，429 要 backoff；REST 明确 422 response。输出字段和数量随 plan 变化（[Consensus MCP](https://docs.consensus.app/docs/mcp)、[Consensus search API](https://docs.consensus.app/reference/v1_search)） |

## 从这些工具可以借鉴什么

### 1. 将“模型意图”与“runtime policy”分离

所有系统都需要 query，但 `top_k`、filters、sort、corpus 和 pagination 是产品控制面，不是检索本质。对开放全球发现，调用方需要这些旋钮缩小数亿条记录；对本项目 3–36 篇固定 candidates，runtime 可以每次完整检查 eligibility、完整 ranking，再按固定 policy 裁剪。模型再控制 `top_k` 或 filters 不会增加可用证据，只会制造：

- 同一 query 因模型临时参数不同而不可比较；
- 通过 year/content type/paper ID 过滤掉相反证据的路径；
- corpus substitution 或跨 case 的攻击面；
- prompt 中额外参数与审计状态。

Elicit/Consensus MCP 证明“把丰富 filters 暴露给 agent”是成熟产品采用的模式；它们也同时证明这是一项面向全球 discovery 的产品选择，而不是 MCP 的硬性要求。Consensus MCP 相比其 REST API 已经隐藏 semantic score/full-text-chunk switches，说明 purpose-specific tool surface 可以比底层 API 更窄（[Consensus MCP](https://docs.consensus.app/docs/mcp)、[Consensus REST search](https://docs.consensus.app/reference/v1_search)）。

### 2. 搜索顺序与论文证据必须分层

PubMed 最清楚地把 ESearch 的 UID selection 与 EFetch 的 paper record retrieval 分成两步。Semantic Scholar/OpenAlex/Crossref 允许 field projection；这三类模式共同支持一个边界：ranking 的内部状态与 model-visible source text 不应混成一块。

本项目的 Retrieval Segment 应只包含验证过的 source-faithful Reference Content。ranking score、citation count、provider-generated summary/takeaway 和“为什么相关”的生成式 explanation 都不是论文文本。Consensus 的 `takeaway`、REST semantic score 和 optional chunks 是产品方便项；其中只有能够回链到冻结 source offsets、保持原文且经过本项目验证的 excerpt 才有资格成为 Retrieval Segment。

### 3. 字段裁剪是正确方向，但应由 server 固定

Semantic Scholar 的 `fields`、OpenAlex/Crossref 的 `select` 都承认“只返回消费方需要的字段”能减少成本与噪声。然而这些 API 让 client 自选字段，是因为它们服务不同应用。本项目只有一个受控 consumer，因此 response schema 应由版本化 retriever 固定，模型不需要 `fields`/`select`。

### 4. 结构化区分成功空集与失败

全球 API 普遍将合法无命中表示为空集合/zero count，将 malformed input、auth/quota/rate/server failures 表示为不同 HTTP/error codes。Scoped retriever 同样不能把空 query、boundary proof failure、corpus invalid、ranking failure 伪装成 `papers: []`；反过来，一个合法 query 在 eligible corpus 中没有匹配可以成功返回空数组。最终 error taxonomy 属于后续 grilling 决策，但至少应有 machine-readable code 与 `retryable`，同时禁止把私有路径/hash/stack trace 暴露给模型。

### 5. Replay 不能只靠 query

仅保存 query 无法 replay 上述全球工具：

- Semantic Scholar/OpenAlex/Crossref corpus 持续更新；
- OpenAlex relevance score 引入动态 citation count；
- Crossref 明确提醒分页期间 reindex 会改变 result set；
- Elicit/Consensus 未在 search response 中给出 ranking model/version，且结果数量/字段受 plan 影响；
- semantic/AI ranking 的实现和版本通常不在单次结果中固定。

Semantic Scholar 官方建议高吞吐场景下载带 release date 的 datasets 并本地查询，这最接近本项目的 frozen-corpus 原则（[Semantic Scholar datasets](https://www.semanticscholar.org/product/api/tutorial)）。但本项目已经有更小、更强的边界：canonical corpus hash + local deterministic retrieval + versioned policy + 完整 audit event，不需要把任何全球 snapshot 带入 Ideation Run。

## Q4：候选 query/control contract

### Model-visible tool input

```json
{
  "query": "non-empty natural-language literature question"
}
```

候选规则：

- input 必须是 JSON object，且恰好只有 `query`；unknown fields fail closed，避免模型“试探”隐藏参数。
- `query` 必须是 string；trim 后不能为空。
- 最大长度由版本化 runtime policy 固定，并在 ranking prototype 中以真实 ideation queries 校准。超过上限返回 input error，不像 OpenAlex semantic search 那样静默截断。
- 私有 audit 同时保留 exact raw query、normalization version 和 normalized query；normalization 只服务 matching，不改写审计原文。
- 模型不能传 `case_id`、corpus/path/hash、paper ID、`top_k`/limit、filter、sort、page/cursor、search mode、content type、score threshold 或 segment budget。

### Private runtime controls

以下不是 tool arguments，而是 preflight 绑定并进入 audit 的版本化 policy：

- exact Approved Target Reference Corpus identity；
- eligible content types/statuses；
- query validation/normalization version；
- ranking implementation/model/dependency version；
- paper result cap、segments-per-paper cap、segment/token cap；
- score combination、threshold 和 stable `paper_id` tie-break；
- maximum calls/query budget 与 error policy。

是否需要 score threshold、是否允许合法 zero-result、具体 caps 都需要后续实证；控制权归 runtime，而不是模型。

## Q6：候选 minimal model-visible output

### Success payload 的不可约核心

```json
{
  "papers": [
    {
      "paper_id": "opaque-local-paper-id",
      "title": "Source paper title",
      "segments": [
        {
          "content_type": "publisher_abstract",
          "text": "Source-faithful text ..."
        }
      ]
    }
  ]
}
```

- `paper_id`：让模型在 idea/reflection 中稳定指向论文，不需要知道 corpus 或 Target Paper identity。
- `title`：用来辨认论文并解释 segment 上下文。
- `segments[].content_type`：防止 official full text 片段被误认作 publisher abstract。
- `segments[].text`：模型实际需要的 source-faithful evidence。
- `papers[]` 顺序就是 paper rank，`segments[]` 顺序就是 evidence order；额外 `rank` 字段重复同一信息。

合法 zero-result 是 `{"papers":[]}`；不是带解释性自然语言的伪结果。模型已知自己发出的 query，因此不回显 query；数组长度已给出返回数，因此不发送 `count`。

### 默认不进入模型上下文

| 字段 | 原因 |
| --- | --- |
| score / threshold / ranking explanation | 未校准、算法相关；会诱导模型把内部相关性信号当成论文质量或事实 |
| `case_id`、corpus/path/hash、manifest/version | 模型不能操作，且暴露私有 scope implementation |
| eligible/ineligible candidates 与排除原因 | 仅用于审计；模型不能修复 corpus |
| source offsets/hashes/provenance record IDs | 由 audit event 连接；对生成想法无直接作用 |
| DOI/PMID/external IDs/URL | runtime 禁止联网；本地 `paper_id` 已足够 grounding |
| citation count、venue、publication type、authors | 不属于 source evidence；是否提高 idea quality 需单独证明，不能因常见就默认加入 |
| provider takeaway/summary/highlight | 派生文本可能改写原义；只有可证明 source-faithful、可回链 offset 的原文 segment 才合格 |
| raw/normalized query echo、total result count、warnings | 重复或不可操作；留在 audit/error channel |

`year` 是唯一值得单独验证的 metadata 候选：它可能支持 chronology/novelty reasoning，但也可能给模型不必要的 recency bias。建议先以无 `year` 的不可约 payload 为 baseline，再在后续 idea-quality validation 中比较加入 validated `year` 是否产生可重复收益；未证明前不进入核心合同。

### Private Retrieval Audit Event

审计记录至少应包含：

```json
{
  "case_id": "...",
  "corpus_hash": "...",
  "raw_query": "...",
  "normalized_query": "...",
  "policy_versions": {},
  "eligible_candidates": [],
  "ineligible_candidates": [],
  "candidate_scores": [],
  "tie_break": [],
  "returned_paper_ids": [],
  "segment_source_pointers": [],
  "segment_hashes": [],
  "model_payload_sha256": "...",
  "outcome": "success|empty|error",
  "error": null
}
```

这不是建议的最终 physical schema，只列出 Evidence Chain 不能丢失的信息。具体 canonicalization、timestamps、latency、error taxonomy 和 payload version 字段应由 ticket 继续决定。

## 应拒绝直接照搬的模式

- 运行时访问任何全球/远程 API，或在本地无结果时 fallback 到 Semantic Scholar/OpenAlex/Crossref/PubMed/Elicit/Consensus。
- 让模型选择 corpus、case、paper IDs、provider、keyword/semantic mode、filters、sort、page 或 `top_k`。
- 按 citation count、journal quartile、provider study-type/takeaway 等动态 metadata 默认为模型排序或证据。
- 静默截断 query、静默降低 result count、静默跳到下页或自动改写 query。
- 把 empty、invalid input、boundary failure、no eligible content、ranking exception 混成同一个空数组。
- 将 proprietary score、AI takeaway 或无法回链 source offsets 的“相关段落”呈现为论文原文。

## 仍需本项目实证的问题

1. query 最大长度：应从真实 ideation tool calls 分布确定，而不是照搬 Elicit/Consensus 的 2,000 characters 或 OpenAlex 的截断行为。
2. query normalization：Unicode/whitespace/case/punctuation/stemming 对真实查询的收益与 replay 影响。
3. paper cap、segments-per-paper、segment length/token budget：比较 evidence coverage、idea quality、latency 和 context cost。
4. `year` 是否进入 model-visible payload；如果进入，缺失值如何表达。
5. ranker 及 score threshold：BM25、embedding 或 hybrid 必须在 3–36 篇真实冻结 corpus 上公平比较，不从全球 API 的做法类推。
6. legal zero-result 与 error taxonomy；模型是否需要 sanitized `error.code/message/retryable`，以及哪些错误必须直接终止 Ideation Run。
7. model output 是否要求引用 `paper_id`；若未来要求精确 segment-level citation，再评估增加 opaque `segment_id`，不提前把 source pointer/hash 暴露给模型。

## Sources

- [Semantic Scholar Academic Graph API overview](https://www.semanticscholar.org/product/api)
- [Semantic Scholar Academic Graph API tutorial](https://www.semanticscholar.org/product/api/tutorial)
- [OpenAlex API reference](https://help.openalex.org/api/)
- [OpenAlex search](https://help.openalex.org/api/searching/), [semantic search](https://help.openalex.org/api/semantic-search/), [sorting](https://help.openalex.org/api/sorting/), [paging](https://help.openalex.org/api/paging/), [field selection](https://help.openalex.org/api/selecting-fields/), [errors](https://help.openalex.org/api/errors/)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), [Swagger](https://api.crossref.org/), [filters](https://www.crossref.org/documentation/retrieve-metadata/rest-api/rest-api-filters/), [tips](https://www.crossref.org/documentation/retrieve-metadata/rest-api/tips-for-using-the-crossref-rest-api/), [access and rate limits](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
- [NCBI E-utilities reference](https://www.ncbi.nlm.nih.gov/books/NBK25499/), [general introduction and usage policy](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- [Elicit API reference](https://docs.elicit.com/), [official Elicit MCP tool reference](https://github.com/elicit/api-examples/tree/main/integrations/mcp)
- [Consensus MCP reference](https://docs.consensus.app/docs/mcp), [Consensus search API reference](https://docs.consensus.app/reference/v1_search)
- [Scite MCP official page](https://scite.ai/mcp) — inspected but excluded from interface comparison because no public tool schema was found
