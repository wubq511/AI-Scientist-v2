# Local-ranking atomic Pro/max calibration protocol v2.1

Protocol date: 2026-09-02（Asia/Shanghai）  
Status: **Frozen before v2.1 Pro/max model output**

## 1. 修正边界

本 protocol 执行 [Atomic rationale contract correction v2.1](local-ranking-atomic-rationale-contract-v2.1.md)。相对
[Pro/max protocol v2.0](local-ranking-atomic-pro-max-calibration-protocol-v2.0.md)，唯一语义 contract 变化是：
`rationale` 由 `1-800 Unicode scalars` 改为 non-empty、grounded、blinded，不再设重复的字符数上限。

`pro-max-calibration-001` 已永久冻结为 `spent_incomplete_contract_v2.0`，其 26 个 responses 全部不得作为本次
vote。v2.1 六个 orientations 都必须使用 fresh provider responses。

以下保持不变：

- 同一批 24 个 spent items 和 exact mirrored evidence；
- `opencode-go/deepseek-v4-pro/max`；
- single-item closed schema、scores、winner、omission 与 evidence-handle 规则；
- `max_tokens=16384`、concurrency 4；
- first-valid、最多两次、exact-prompt、no-error-feedback retry；
- per-replicate `22/24`、pooled `69/72`、directional >0 gates；
- r1 → r2 → r3 的数学 early stop；
- 不复用 Pro/high、Pro/max v2.0 或其他历史 votes。

## 2. Frozen identity and budget

- source commit：`d87e311cb46ce4b3b83dd184c0c05bce0525c95b`
- profile manifest：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-002/input/profile-manifest.json`
- profile manifest SHA-256：
  `61dc61072b0358de75d1a01fb2a3151ffad73ea9ba88369aa050ce0122b61c5f`
- usage snapshot SHA-256：
  `c54601ab0df4044114ad24a8e6bd0f06f6082b7aed5e9eed9babca81be38009a`
- transport smoke result SHA-256：
  `b57460388033dd6ced38f7f45bb7b175bea6e55d74137ae83faa44fb71c44d9e`
- input root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-002/input`
- output root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-002/output`
- profile budget：144 logical、最多 288 physical；执行仍按 replicate early stop，不能把上限当调用目标。

调用前 snapshot：rolling 0%、weekly 28%、monthly 38%，三者均为 `ok`，model endpoint 包含
`deepseek-v4-pro`。v2.0 incomplete run 已消耗 26 calls / 169,211 tokens；这些成本只报告，不换取 vote。

## 3. Six frozen orientation bindings

| replicate | orientation | atomic manifest SHA-256 | transport manifest SHA-256 |
| --- | ---: | --- | --- |
| `r1` | 1 | `38e0ee8d68cb660aff45510abf375fbae62bc43e14dd6c609c14a29ac40eaf5d` | `550997e956d66ddac6ea8c229e61299e5d12845a718c72f52d06495e1e3b8f6d` |
| `r1` | 2 | `336be1a8c23295159d63212981d4bdbf86f63dacfb91e0a173e7a5c377ec3b0c` | `dec08ddbde7569a06466d7c79b9d9fe8f27231abe794c47bf02a7f3997adf4e5` |
| `r2` | 1 | `50d552b3a5170d60d1fc7659acec5bc1d356ba1b9b86b77109a53d31d45b14fd` | `afd92a06e7d9924d001ef024bccb4b98f6d70270a3f61254f5c21623a53fa807` |
| `r2` | 2 | `90f1656dd4dcf76467ab8d79c6b8ae4d3be43811e93d777dd5b58383cd93cc6f` | `841640c7b10799f1b9b3aa640911c536432b730d0e81c37e3ae81f2c908fd869` |
| `r3` | 1 | `b07e944a928149b968274ea8eb19c8fa56ff2d124b2e416fc90fd4b8f3ceff87` | `2877105401af9e21302802b349a45d982fc6496609dcfdc799e78e39048a63a3` |
| `r3` | 2 | `b1db744636494bc530e8a3d72b8fb8db1b305e0a95731f3baf58db2bcc0149d9` | `9787a4ee12643154059b619dc95660cf34ee6f0d397b5b780678b7ea272afe41` |

## 4. 执行与决策规则

1. 先执行 `r1/o1`、再执行 `r1/o2`；任一 logical call 两次仍 invalid，则 run=`incomplete`，不是 semantic
   FAIL。
2. pair validator 计算 mapped mirror stability；r1 stable `<22/24` 或 stable directional 为 0 时，profile
   semantic FAIL，停止且不发 r2/r3。
3. r1 通过才执行 r2；任一 replicate 自身未过 gate 即停止。
4. 前两组后只有 pooled + 24 仍可能达到 69 才执行 r3。
5. 三组都完成后，只有每组 ≥22、pooled ≥69 且每组 directional >0 才 PASS。

不得因当前 winner、分数、mirror mismatch 或“结果看起来不好”重试。不得在本次 FAIL 后追加第四组或重跑
valid r1；若 v2.1 Pro/max 仍未通过，DeepSeek ladder 即在已批准 Atomic contract 下耗尽，应转向 rubric/data
ambiguity 或其他模型族，而不是继续抽样直到 PASS。

