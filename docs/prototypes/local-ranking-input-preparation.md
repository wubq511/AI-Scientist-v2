# Local ranking 正式输入准备证据

Evidence date: 2026-08-30（Asia/Shanghai）

Status: **Approved inputs / queries and qrels pending**

本记录对应 Wayfinder ticket `Choose and calibrate local literature ranking`。它证明 12-case comparison input proposal 可确定性构建，并记录 Robert 委托 Codex 完成的一手资料研究、逐案语义审计和 immutable approval chain。它没有生成 query、qrels、ranking result 或 winner。

## 当前结论

- 已形成 12 个 private case proposals：development/holdout 各 6 个，每个 split 都有 `small=2`、`medium=2`、`large=2`，reference 数覆盖 3–36，整体覆盖 8 个 broad clusters，包含 4 个 `strategy=2` targets。
- 已机械构建 12 个 private corpus bundles，共 168 条 reference records；12 份 `validation-report.json` 均为 zero-error，且 quarantined `contexts`、`intents`、`isInfluential`、dynamic ranking fields 和 Target identity 未进入 `corpus.json`。
- 已起草 12 份 canonical Workshop Markdown。Derivation author 只读取 private `title + raw abstract` authoring packet，没有打开任何 selected corpus 或 reference evidence；12 份 draft 的 schema/identity/URL/DOI/8-token n-gram deterministic checks 全部通过。
- `input-approval-001` 已批准全部 12 个 cases、Workshop drafts、corpus policy versions 与本轮使用；pending source artifacts 没有被覆盖，而是由新 sidecars 按 hash 标记为 Approved。正式 development/holdout 仍须等待 queries、pinned-tokenizer length preflight 和 blind qrels。

## 选择与输入边界

选择器版本为 `local-ranking-case-selection-v1.1`，split seed 为保持冻结分配而独立 pin 到 `local-ranking-case-selection-v1`：先由 source hashes + opaque target identity 确定 development/holdout bucket，再在每个 bucket 内选择 2 个 small、2 个 medium、2 个 large，以 cluster coverage、reference-count spread、只输出聚合值的 title/content token-overlap spread 和 `strategy=2` coverage 为预注册的 label-free objective；不读取 qrels、ranker output、Target result 或任何后验表现。Reference text 只在隔离的 preparation process 内计算聚合 overlap，不进入 Workshop authoring packet。

准备规则只排除 metadata audit 已点名、尚未完成 authoritative enrichment 的 3 个 reference identities。一次早期 attempt 曾用 `<100 chars` 粗阈值误排 2 条非损坏短摘要；该规则未用于当前 proposal，详见失败记录。

当前 12 个 bundles 全部只包含 validated raw abstract content，每篇一个 source content item。现有 approved source artifacts 中没有 coverage 一致、许可/provenance 已冻结的 official-full-text snapshot；对 PubMed、SPECTER/SPECTER2、Google Scholar、Europe PMC、OpenAlex 和全文检索对照研究的调查支持将 v1.1 明确限定为 abstract-level local paper ranking。没有用 citation contexts、生成摘要或未批准网络内容填补，也不把部分 papers 的全文混入本轮。全文路线的重新打开条件见 [Local ranking 是否需要论文全文](local-ranking-full-text-decision.md)。

结构审计覆盖全部 168 条 records：paper IDs、titles 和 abstracts 均唯一；无空内容、placeholder abstract 或少于 200 characters 的异常短摘要；全部 content type 都是 `publisher_abstract`。按每个 case 最短/最长 abstract 的确定性分层抽查未发现冒充 abstract 的内容。4 篇摘要超过 450 whitespace-delimited words，最长约 865 words；因此 qrels 前必须用 pinned E5 tokenizer 做 exact 512-token preflight，必要时先冻结所有 arms 共用的 source-faithful abstract segmentation。

## Immutable attempts

Private root：`artifacts/local-ranking-prototype/input-preparation-v1/attempts/`（gitignored）。

- `inputs-001`：失败并保留。严格 year parser 遇到 raw `2018.0` 等 integer-valued float 后 fail closed；修复为仅接受 `int` 或 integral `float` 并 canonicalize 为 JSON integer，非整数仍拒绝。
- `inputs-002`：首次 12-case 成功；随后发现 `<100 chars` selection exclusion 过宽，保留但 superseded。
- `inputs-003-replay`：复放 `inputs-002`，52 个 selection/corpus files byte-identical。
- `inputs-004` / `inputs-005-replay`：只排除 3 个 audited-unready identities，52 个 selection/corpus files byte-identical；随后因 validators 和 selection rule 版本号需要显式递增而 superseded。
- `inputs-006`：版本化检查中发现 selection version 不应顺带改变既有 split seed；该成功产物未进入 review，保留为 superseded attempt。
- `inputs-007`：**当前 proposal**；selection rule 为 v1.1，split seed 独立 pin 到原 v1，12-case roster 保持不变；corpus/workshop validators 为 v1.0.1。
- `inputs-008-replay`：复放 `inputs-007`，52 个 selection/corpus files byte-identical。

`inputs-007` 的关键身份：

| Artifact | SHA-256 |
| --- | --- |
| `source-manifest.json` | `54c79f55414856dcb5e3c1f1d9cf4813dd491919e72b4aec684cf88b763c7da4` |
| `selection-manifest.json` | `296514f9a6f46f4242aa0e39b2fd1bdf566ae36e05bf06375b93888c709a9c92` |
| `preparation-manifest.json` | `b8f2e08a983c32e702efecf3c3a94fc85d253b43a03353563e9d4f1abfc8453b` |
| `workshop-authoring.json` | `89792d74f59b5aa9af78d62bde17accab31ee466e4a310269a0e7bf8bac9d973` |
| `workshop-draft-001/workshop-manifest.json` | `f0e9bf9f69e24471a1dc542cc32ecdef4f21e964ba21e20c723c996ce2ca0a93` |
| `workshop-draft-001/semantic-review.md` | `935f0db2dca876bebcc6b435290876ba8fc419867193315e2f1790757dbf94d3` |

## Immutable approval

Robert 明确委托 Codex 从第一性原理研究并决定 input 与全文政策。审批没有改写 pending manifests，而是在 `inputs-007` 下新建 `review-decisions/input-approval-001.json` 与 `approvals/input-approval-001/`：

| Artifact | SHA-256 |
| --- | --- |
| v1.1 protocol | `23d9b6d05d57f015a34f9bc75fa0bf9b0dee0ab2afa01c6b646b5d27a422f91c` |
| `review-decisions/input-approval-001.json` | `4ccc8cdc1c1d28c0a84fa8bfa20902c3b02a031c4c1d6ea9f3c3ecbad21f4358` |
| `approvals/input-approval-001/approval-manifest.json` | `389c5ebcabe5774e2e380d75fc39baa03913b7b9cda82de3087012ca8a22c86e` |
| `approvals/input-approval-001/approved-corpora.json` | `8307a9709e73aacea3bb7ef4c66baddf4f055b2b5feaa93390db34c711c5f570` |
| `approvals/input-approval-001/approved-workshops.json` | `3b14c6fd8429013a9834282c901f45f3c2971fd1030113f4e8d1fb4e2bc74d78` |
| `query-author-packet/manifest.json` | `aca55098a6167840fe7b36bfec3d128f07f4d15477c4869617a5d338ebf51ef8` |

Approval CLI 在写入前重新验证 exact protocol/selection/preparation/Workshop/corpus/report hashes、12 个 semantic approvals、zero-error validators、policy versions 与 168 条 `publisher_abstract` records。再次使用同一 `approval_id` 会返回 `ARTIFACT_EXISTS`；query-author packet 的 12 份 Workshop 与获批 draft bytes 完全一致，且不含 Target authoring input、reference content、qrels 或 ranker output。

## Replay 与验证

准备入口：

```bash
python -m prototypes.local_ranking.input_preparation prepare \
  --output-root artifacts/local-ranking-prototype/input-preparation-v1/attempts/<new-attempt>
```

Workshop deterministic validation：

```bash
python -m prototypes.local_ranking.input_preparation validate-workshops \
  --preparation-root artifacts/local-ranking-prototype/input-preparation-v1/attempts/inputs-007 \
  --draft-set workshop-draft-001
```

Input approval：

```bash
python -m prototypes.local_ranking.input_preparation approve \
  --preparation-root artifacts/local-ranking-prototype/input-preparation-v1/attempts/inputs-007 \
  --draft-set workshop-draft-001 \
  --decision-record artifacts/local-ranking-prototype/input-preparation-v1/attempts/inputs-007/review-decisions/input-approval-001.json \
  --protocol docs/prototypes/local-literature-ranking-comparison-protocol.md \
  --approval-id input-approval-001
```

验证结果：

- Mac ambient Python 3.14.6：36 tests passed；
- Mac Python 3.13.7 reference：36 tests passed；
- Black 26.5.1、Ruff 0.16.5、`compileall`、`git diff --check`：pass；
- `inputs-007` ↔ `inputs-008-replay`：52/52 selection/corpus files SHA-256 相同；
- Workshop deterministic validation：12/12 pass，0 failures；
- Corpus deterministic validation：12/12 pass，0 errors。

这些测试证明 preparation behavior、quarantine、approval binding 和重建确定性；它们不替代 relevance qrels。

## 下一 gate

输入审批已经完成。下一步必须由一个没有读取 Target authoring packet 或 corpus/reference content 的新会话，只读取 `input-approval-001/query-author-packet/` 起草 24 条 broad/focused queries。随后在 qrels 前完成 pinned-tokenizer length preflight，并按需冻结共同 abstract segmentation；再生成 Robert blind qrels form。当前会话已经见过 Target 与 references，不能兼任 query author。
