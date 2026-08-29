---
title: Define the Scoped Literature Retriever contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 019-define-the-frozen-corpus-contract.md
  - 033-understand-dataset-routing-metadata.md
---

## Question

What frozen-corpus inputs, Reference Content eligibility rules, outputs, invariants, audit proof, empty-result behavior, ranking controls, and fail-closed errors must replace `SearchSemanticScholar` without any global or remote fallback?

## Evidence

- [Scoped Literature Retriever 接口模式研究](../../../research/scoped-literature-retriever-interface-patterns.md)

## Resolution

Robert 批准以下 Scoped Literature Retriever 合同。它以一个 runtime-preflight 绑定的 Approved Target Reference Corpus 为唯一文献边界，用最小、确定、可审计的本地查询替换 `SearchSemanticScholar`；模型不能选择 scope，runtime 不能联网、跨 case、访问全局 paper catalog，任何失败都禁止 remote/global、旧 corpus 或 alternate-ranker fallback。

### Scope binding and model input

- Ideation Run preflight 必须先显式 pin 并验证唯一 `case_id`、canonical corpus hash、bundle manifest、validation report 与兼容 policy versions，再构造绑定到该 corpus 的 retriever。模型、query 和后续 tool call 都不能选择、覆盖或切换 corpus/path/hash。
- Model-visible tool input 是一个 JSON object，且恰好只有非空自然语言 string `query`：

```json
{
  "query": "non-empty natural-language literature question"
}
```

- Unknown field、类型错误、trim 后为空或超过版本化上限都属于 input error；禁止静默丢弃字段、截断、改写或补全 query。Private audit 同时保留 exact raw query、normalization version 与 normalized query。
- `case_id`、corpus/path/hash、paper IDs、`top_k`、filters、sort、pagination、search mode、content type、score threshold、result/segment budget 都不是 model-controlled arguments，而由 preflight pin 的版本化 runtime policy 控制。

### Reference Content eligibility and Retrieval Segments

- 只有当前 `corpus.json` 中 status/type/text/provenance/hash 全部验证通过的 Reference Content 才能成为候选。Validated `publisher_abstract` 直接 eligible；validated `official_full_text` 只能通过确定性、版本化、保持原文且能精确回链 source content/position/hash 的有界 Retrieval Segments 使用，不能整篇塞入 model context 或改称 abstract。
- `derived_text`、模型生成/改写摘要、Target citation `contexts`、`intents`、`isInfluential`、Target/Workshop 隐藏文本以及 evidence 区域中的 alternate content 全部禁止。未来开放新的 content type 必须有独立批准、policy version 和 validation evidence。
- Title 可以参与 matching/ranking，但没有任何 eligible Reference Content 的 record 不能成为 Retrieval Result。若 corpus 仍有 eligible candidates，该 record 只以明确 reason 记入 private audit 并跳过；整个 corpus 没有 eligible candidate 属于 corpus/preflight error，不得伪装成合法 empty。

### Ranking boundary, unit, and stable order

- 每次 retrieval 必须是独立、local、无隐藏 mutable state 的计算。Ranker 只能读取 normalized query、record title、eligible Reference Content/Retrieval Segments；`content_type` 只服务已批准的 eligibility/segmentation policy，`paper_id` 只服务 stable identity 与最终 tie-break。
- Ranker 禁止读取 Target Paper、Target-derived edge/category metadata、Workshop hidden text、previous queries/results、other-run state、citation count、venue、year、publication type、remote API、provider model 或未声明的全局资源。
- Paper 是结果与 ranking 的基本单位：同一 `paper_id` 最多出现一次，允许在该 paper 内携带有界、按相关性排列的 `segments`。Paper 先按 approved ranking score 降序，再按 stable `paper_id` 升序作为最终 tie-break；segments 先按 segment score 降序，再按 canonical content-item order 与 source start position 排序。Filesystem order、raw JSON order、hash-map iteration、wall-clock 或 mutable cache 不能影响结果。
- 相同 pinned corpus bytes、eligibility/normalization/ranking/segmentation versions、runtime controls 与 normalized query，必须产生相同有序 papers、segments、canonical model payload 和 payload SHA-256；不能满足该 observable determinism 的候选 ranker 不得获批。
- 具体 BM25、local embedding 或 hybrid 方案、normalization、content-type handling、paper cap、segments-per-paper、segment/token cap、relevance threshold、dependencies、latency 与 cross-platform behavior 由 [Choose and calibrate local literature ranking](021-choose-and-calibrate-local-ranking.md) 在真实 3–36 篇 corpora 上公平比较后决定。本 ticket 只锁定控制权和不可突破的边界。

### Minimal model-visible Retrieval Result

成功结果使用版本化 typed JSON，`papers[]` 顺序表达 paper relevance，`segments[]` 顺序表达该 paper 内的 evidence order：

```json
{
  "papers": [
    {
      "paper_id": "stable-local-paper-id",
      "title": "Source paper title",
      "segments": [
        {
          "content_type": "publisher_abstract",
          "text": "Source-faithful evidence"
        }
      ]
    }
  ]
}
```

- v1 model payload 只包含 `paper_id`、`title` 和 `segments[{content_type,text}]`。不重复发送 `rank`、query 或 count，也不发送 score/threshold/explanation、case/corpus/path/hash、source offsets/hashes/provenance IDs、candidate/exclusion details、DOI/PMID/URL、authors、venue、publication type、citation count、warnings 或 provider-generated takeaway/summary/highlight。
- `year` 暂不进入 v1；只有后续 idea-quality validation 证明它对 chronology/novelty judgment 有可重复净收益，Robert 再批准新的 output/policy version，才允许加入。

### Empty results, errors, and finalization

- 合法 query 在 approved relevance policy 下没有任何候选达到门槛时，成功返回 `{"papers":[]}`，不返回自然语言伪结果。若后续 approved policy 不设 threshold 且总返回 top candidates，则合法 empty 自然不会发生。
- 模型可以在版本化 call budget 内对合法 empty 重新组织 query；empty 不算完成 literature grounding。一个 Ideation Run 若从未取得非空 Retrieval Result，controller 必须禁止 `FinalizeIdea` 并 fail closed；具体 call budget、finalization gate 和 resume 行为交由 [Define control flow, failures, and resume](025-define-control-flow-failures-and-resume.md) 固化。
- 只有模型可修复的 `INVALID_QUERY` 与 `QUERY_TOO_LONG` 向模型暴露最小、无内部细节的 input error。Boundary proof、corpus/hash/version、eligibility policy、ranking/segmentation、audit persistence、budget 或其他 controller/runtime failures 不生成可继续使用的 Retrieval Result，由 controller 立即终止 run。
- 所有失败都禁止静默重试到不同输入、换 corpus、使用 stale/latest bundle、降低 validation、改用 alternate ranker、读取 evidence content 或联网 fallback。完整错误、stack/path/hash 与 retry diagnostics 只进入 private Evidence Chain，不进入 model context。

### Retrieval Audit Event and release gate

- 每次 invocation 的 success、empty、input error 和 system error 都必须接入 Evidence Chain。Private Retrieval Audit Event 至少关联当前 run/call 与 exact corpus/manifest identity，记录 raw/normalized query、全部 relevant policy/ranking versions、eligible/ineligible candidates 与 reasons、candidate/segment scores、tie-break、returned paper IDs、segment source pointers/hashes、canonical model payload SHA-256、outcome、error、timestamps 与 latency；它不是 model-visible tool response。
- 对 success 和 empty，retriever 必须先生成 canonical payload/hash，再持久化并校验对应 Retrieval Audit Event；只有两者精确连接后才能释放 payload。Audit 写入或校验失败时，即使已有看似合理的 ranking 结果也必须 fail closed，并由外层 failure evidence 尽可能保留该失败，不能声称完整 event 已写入。
- Audit evidence 证明结果来自 exact scope、使用 exact policy、未遗漏边界错误且可以 replay；可审计不等于把 audit metadata 塞进 model context。Event 的最终 physical schema、atomic storage path、run/call identity 与 raw/sanitized layout 由 [Define run identity and evidence layout](023-define-run-identity-and-evidence-layout.md) 决定。

### Versioning and change boundary

Retriever input/output schema、eligibility、normalization、ranking、segmentation、controls 与 error policy 都必须显式 version/pin，并在 audit 中记录。后续 prototype 可以在本合同授权的 mechanism/parameter 空间内选择最简有效方案，但不能改变 corpus scope、model-controlled input、model-visible output、forbidden fields、determinism、audit release gate 或 fail-closed semantics；改变这些内容需要新的证据、Robert 批准和版本升级。

本 ticket 只锁定 mechanism-independent retriever contract；没有实现 retriever、生成 corpus、修改 raw dataset、调用模型或进入 downstream。
