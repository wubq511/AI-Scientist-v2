# Local ranking 正式输入准备证据

Evidence date: 2026-08-30（Asia/Shanghai）

Status: **Prepared / pending HITL approval**

本记录对应 Wayfinder ticket `Choose and calibrate local literature ranking`。它只证明 12-case comparison input proposal 可确定性构建并已到达 Robert 审批点；不把 draft 叫作 Approved Workshop，不把 pending bundle 叫作 Approved Target Reference Corpus，也没有生成 query、qrels、ranking result 或 winner。

## 当前结论

- 已形成 12 个 private case proposals：development/holdout 各 6 个，每个 split 都有 `small=2`、`medium=2`、`large=2`，reference 数覆盖 3–36，整体覆盖 8 个 broad clusters，包含 4 个 `strategy=2` targets。
- 已机械构建 12 个 private corpus bundles，共 168 条 reference records；12 份 `validation-report.json` 均为 zero-error，且 quarantined `contexts`、`intents`、`isInfluential`、dynamic ranking fields 和 Target identity 未进入 `corpus.json`。
- 已起草 12 份 canonical Workshop Markdown。Derivation author 只读取 private `title + raw abstract` authoring packet，没有打开任何 selected corpus 或 reference evidence；12 份 draft 的 schema/identity/URL/DOI/8-token n-gram deterministic checks 全部通过。
- 当前 approval count 仍为 0：corpus manifests 是 `pending_robert_approval`，Workshop manifest 是 `pending_independent_semantic_review`。正式 development/holdout 仍不能运行。

## 选择与输入边界

选择器版本为 `local-ranking-case-selection-v1.1`，split seed 为保持冻结分配而独立 pin 到 `local-ranking-case-selection-v1`：先由 source hashes + opaque target identity 确定 development/holdout bucket，再在每个 bucket 内选择 2 个 small、2 个 medium、2 个 large，以 cluster coverage、reference-count spread、只输出聚合值的 title/content token-overlap spread 和 `strategy=2` coverage 为预注册的 label-free objective；不读取 qrels、ranker output、Target result 或任何后验表现。Reference text 只在隔离的 preparation process 内计算聚合 overlap，不进入 Workshop authoring packet。

准备规则只排除 metadata audit 已点名、尚未完成 authoritative enrichment 的 3 个 reference identities。一次早期 attempt 曾用 `<100 chars` 粗阈值误排 2 条非损坏短摘要；该规则未用于当前 proposal，详见失败记录。

当前 12 个 bundles 全部只包含 validated raw abstract content，每篇一个 segment。现有 approved source artifacts 中没有可直接纳入的 official-full-text snapshot，因此 protocol 的 full-text 与 segment-count-imbalance 可选覆盖项本轮未实现；没有用 citation contexts、生成摘要或未批准网络内容填补。该限制不改变 scorer 间输入公平性，但最终结论只能直接支持 abstract-only corpora。

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

验证结果：

- Mac ambient Python 3.14.6：31 tests passed；
- Mac Python 3.13.7 reference：31 tests passed；
- Black 26.5.1、Ruff 0.16.5、`compileall`、`git diff --check`：pass；
- `inputs-007` ↔ `inputs-008-replay`：52/52 selection/corpus files SHA-256 相同；
- Workshop deterministic validation：12/12 pass，0 failures；
- Corpus deterministic validation：12/12 pass，0 errors。

这些测试证明 preparation behavior、quarantine 和重建确定性，不替代 Robert 的语义判断或 relevance qrels。

## 下一 HITL gate

Robert 需要在 private semantic-review packet 中逐 case 判断：

1. Workshop 是否仍与 Target problem 相关；
2. 是否允许多个实质不同的 method families；
3. 是否泄漏 Target method、mechanism、design、result 或 conclusion；
4. 是否存在近身份化措辞；
5. 是否批准当前 corpus schema/normalization/enrichment-policy/validator versions 与本轮 12-case 使用。

只有上述审批通过后，才能新写 immutable approval sidecar 与 final approved manifests，引用当前 draft/bundle hashes；不得覆盖 pending artifacts。Query author 必须在一个没有读取 Target authoring packet 或 corpus/reference content 的新会话中，只看 Approved Workshops 起草 24 条 broad/focused queries；随后才生成 Robert blind qrels form。
