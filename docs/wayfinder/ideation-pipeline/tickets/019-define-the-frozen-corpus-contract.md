---
title: Define the frozen corpus contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 016-audit-metadata-gaps-and-enrichment-sources.md
---

## Question

What normalized schema, per-target membership proof, enrichment provenance, versioning, hashes, and validation report make a Target Reference Corpus ready for Ideation Runs?

## Evidence

- [《The Dynamics of Frailty Among Older Adults》abstract 补齐调查](../../../research/missing-frailty-abstract-recovery.md)

## Resolution

Robert 批准以下 frozen corpus 合同。每个 Ideation Case 的最终文献输入必须是一个可按 bytes 和证据精确识别、与其他 case 隔离、在运行前已经完成 enrichment 和 validation 的 `Approved Target Reference Corpus`；Ideation Run 不得再访问全局或远程文献来源。

### Artifact boundary and case identity

- 每个 `case_id` 对应一个 self-contained corpus bundle。Runtime 不依赖 global paper catalog、跨 case join 或按全局表过滤；即使同一 reference 属于多个 targets，也必须在各自 bundle 中形成独立 membership。Build/enrichment evidence 可以按 immutable paper identity 去重，但不得成为 runtime dependency。
- Runtime 只使用不泄漏 Target Paper 身份的 opaque `case_id`。原始 `targetPaperId` 只保存在 private、non-model-visible mapping 和 raw membership evidence 中，不进入 `corpus.json` 或 model context。
- Bundle 至少包含 canonical `corpus.json`、`bundle-manifest.json`、machine-replayable `validation-report.json` 和独立 evidence 区域。Evidence 区域保存 source snapshots、authority responses、official full text、build attempts、conflicts 和 validation pointers；Runtime 禁止读取 evidence 来绕过 `corpus.json`。
- Corpus bundles、Reference Content、official full text、source/build evidence 与 validation artifacts 均允许进入本私有 Git 仓库。密钥、认证信息和其他 secrets 仍然禁止进入 Git；该决定不构成公开发布授权。

### Retrieval-minimal record contract

Canonical `corpus.json` 是 typed deterministic JSON。Top-level 至少包含：

- `schema_version`、`normalization_version`、`enrichment_policy_version`；
- opaque `case_id`；
- source dataset hash、private raw membership hash 和 runtime membership hash 的 references；
- 按 canonical `paper_id` 排序的 `records`。

每条 normalized record 至少表达：

- stable `paper_id` 与经过精确来源核验、规范化的 external identifiers；
- nonempty `title`；
- typed `content_items`，每项明确 `type`、`status`、适用时的 source-faithful text、content hash 与 provenance reference；
- record-level provenance reference；
- 可选的 `year`、`venue` 和 `publication_types`。

`authors`、`citationCount`、完整 bibliography 和旧 Semantic Scholar renderer 的展示兼容性不是 corpus-ready gate。原始 `contexts`、`intents`、`isInfluential` 以及未经批准的 rank、score、query 和其他 dynamic ranking fields 只能作为 non-model-visible evidence，不能进入 frozen runtime corpus。Retrieval eligibility、prompt/run state 也不属于 immutable corpus record。

### Reference Content and missing abstracts

- `Reference Content` 必须按真实来源类型保存；当前允许 `publisher_abstract` 和 `official_full_text`，未来若引入 `derived_text` 必须使用独立类型和 policy version。正文、引用上下文或生成摘要不得写入或冒充 publisher abstract。
- 每个 record 都必须明确 content status；status、source type 与 text 的组合必须一致。Corpus 整体若没有任何 validated Reference Content 则 fail closed。具体哪些 content types 可由 retriever 使用，由 [Define the Scoped Literature Retriever contract](020-define-the-scoped-retriever-contract.md) 和后续 ranking 证据决定，不由 corpus builder 暗中选择。
- 已审计的两条损坏 abstract 只允许按 raw evidence 可证明的精确方式恢复，并保存 transform 与 source provenance；不得通过模型或模糊搜索改写。
- 对 `The Dynamics of Frailty Among Older Adults`，精确 DOI、PMID、PubMed、Europe PMC、Crossref 与 JAMA publisher evidence 一致证明它是没有 publisher abstract 的 Invited Commentary。因此保留 membership，记录 `abstract_status=not_published`，并将 JAMA 官方正文单独保存为 `official_full_text`；原数据中的 `falls,`、target citation context 和正文摘要均不得作为 abstract。该 case 不需要 Robert 再人工寻找 abstract。

### Enrichment and field-level provenance

- Enrichment 只修复 retrieval-readiness blocker，不追求 citation-complete bibliography。允许的 authority path 只包括已有 DOI、PMID、arXiv ID、DBLP identity 等 exact identifier 对应的 Crossref、NCBI/PubMed、Europe PMC、arXiv、DBLP 或 exact official publisher page。
- 禁止 fuzzy title search、global crawling、无精确身份约束的第三方聚合结果，以及以 OpenAlex 或其他来源静默覆盖 raw nonempty fields。
- 每个 canonical 字段必须可追溯到 raw dataset path/hash、row identity/hash 与 field，或 authority、exact identifier、URL、response hash、timestamp、source field path、transform 和 validation。冲突必须显式记录，不得静默选值。
- 缺失 venue 等 optional metadata 可以保留为显式缺失并产生 warning，不得为了填满字段扩大 enrichment scope。

### Canonical bytes, versions, and hashes

- `corpus.json` 固定使用 UTF-8、Unicode NFC、LF、sorted object keys、按 `paper_id` 排序的 records、canonical-sort 的 set-like arrays、正确 JSON integer 类型、显式 null/status 与文件末尾单个 newline。
- `schema_version`、`normalization_version`、`enrichment_policy_version` 和 `validator_version` 独立采用 semantic version；`validator_version` 由 validation report 记录，bundle manifest 必须 pin 并汇总全部四个版本。
- Timestamps 只属于 provenance，不充当内容或 policy version，也不进入 deterministic content identity。相同 source、membership、versions、rules 和 selected content 必须重建出完全相同的 `corpus.json` SHA-256。
- SHA-256 至少覆盖 source dataset、private raw membership（`targetPaperId + paperId`）、runtime membership（`case_id + sorted paper_ids`）、每个 authority response、每项 Reference Content、每条 normalized record、canonical `corpus.json` 和 bundle inventory。Layered hashes 必须足以定位 source、membership、content、record 或 packaging drift。

### Deterministic validation and immutable attempts

- 每个 bundle 必须生成独立的 `validation-report.json`，记录 validator version、corpus/bundle hashes，以及每条 rule 的 stable ID、severity、pass/fail status、evidence pointer 和 error/warning summary。
- 以下至少属于 error，任一出现都 fail closed：schema/canonical bytes 违规；case mapping 不唯一；membership 缺失、额外或重复；identity 无效或 unresolved conflict；title 缺失；content type/status/text 不一致；已知损坏值（例如 `falls,`）进入 runtime；required provenance 缺口；任一 hash mismatch；quarantined field 进入 `corpus.json`；整个 corpus 没有 validated Reference Content。
- Optional year、venue、publication type、authors、citation count 或完整 bibliography 缺失属于 warning。Publisher abstract 被权威确认未发布、但 official full text 已按独立类型保存，也属于可复核的 warning 而非伪造或删除 membership 的理由。
- Validator 可以输出 repair suggestion，但不得自动改写 canonical corpus。具体 rule thresholds、fixtures 和 cross-platform test matrix 由 [Define the validation and test matrix](027-define-the-validation-and-test-matrix.md) 固化。
- 每次 build/retry 都是 immutable attempt，必须保存 inputs、policy versions、authority responses、errors、validation evidence 和 artifact hashes；禁止覆盖失败或成功 attempt。Failed bundle 永远不能进入 Ideation Run。
- 新 build 失败时禁止 silent fallback。旧 passed bundle 只有在 run 显式 pin 其 exact hash 且通过当前 compatibility check 时才可使用，不得以“latest”隐式选择。

### Approval and runtime preflight

只有同时满足以下条件，Target Reference Corpus 才进入 `Approved Target Reference Corpus` 状态：

1. Bundle deterministic validation 为 zero-error；
2. 每项 exceptional Reference Content、source conflict、special transform 和新 authority path 都完成 focused human review；普通 raw abstracts 只需代表性抽查，不要求逐一人工复核全部 records；
3. Robert 批准本轮使用的 schema、normalization、enrichment-policy、validator versions 和 canary evidence，不要求逐一签字全部 237 个 corpus；
4. 当前 scale 符合 [Define canaries and scale gates](028-define-canaries-and-scale-gates.md) 的独立批准，不能因单个 bundle 通过而自动扩量。

Ideation Run preflight 必须显式 pin `case_id`、corpus hash、bundle manifest、validation report 和全部 policy versions；重新计算 corpus 与 membership hashes，确认 validation report 精确对应同一 bundle，并检查版本兼容性。Preflight 不得联网、enrich、repair、读取 alternate bundle 或自动 fallback；任一缺失、不一致、未批准或不兼容都 fail closed。

本 ticket 只锁定 corpus contract；没有生成 corpus、修改 raw dataset、调用模型或进入 downstream。Retriever 的 Reference Content eligibility、query/output contract 与 ranking 行为仍由后续 tickets 通过证据决定。
