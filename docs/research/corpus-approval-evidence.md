# Target Reference Corpus approval boundary 验证证据

日期：2026-09-03

Implementation ticket：[Approve one Target Reference Corpus](../wayfinder/ideation-implementation/tickets/03-approve-one-target-reference-corpus.md)

验证矩阵：`VM-CONTRACT-019-01`、`VM-CONTRACT-019-02`、`VM-REPLAY-02`、`VM-LEAKAGE-04`

## 结论

离线 `build → validate → approve` 语料准入边界已完整实现，并支持 `validate-all` 对当前全部 237 个 Targets 做确定性预处理验证。Python 3.13.7 / macOS arm64 的最终全量验证为 `298 passed`（包含既有 288 项测试及新增的 10 项语料契约测试）；真实私有 smoke candidate `case-229e495f82a24cff9e6082aa058955b9` 已通过 11 项 fail-closed deterministic gates，并在 Robert 签署核准决策后正式进入 `approved` 状态。全量 237 个 targets 在离线无模型、无网络下 100% 确定性通过（耗时约 7 秒）。本票未调用模型、未访问网络、未产生模型费用，也未进入 BFTS 或其他 downstream 阶段。

## 固定实现边界

- 开工固定点：`325d58d add: close Workshop approval ticket`。
- 稳定入口：`python -m ai_scientist.prepare_ideation_inputs corpus {build,validate,approve,validate-all}`。
- 模块分离架构：
  - [contract.py](file:///Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2/ai_scientist/ideation/contract.py)：固化语料 contract、schema、validator、enrichment 政策版本号，定义 quarantine 封禁字段列表与已知坏值；
  - [reference-authority-v1.json](file:///Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2/ai_scientist/ideation/policies/reference-authority-v1.json)：冻结的第一方权威修复政策（覆盖 Europe PMC、JMLR 及 JAMA 权威证据）；
  - [corpus_build.py](file:///Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2/ai_scientist/ideation/corpus_build.py)：负责读取私有 reference membership、合并冻结权威修复、生成 canonical UTF-8/NFC/LF `corpus.json`、保留私有 `source-rows.jsonl`，并计算 layered hashes 生成自包含 bundle；
  - [corpus_validation.py](file:///Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2/ai_scientist/ideation/corpus_validation.py)：只读检验器，对全部 11 类 error 级条款 fail-closed，绝不自动改写语料文件，生成 machine-replayable 验证报告；
  - [corpus_approval.py](file:///Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2/ai_scientist/ideation/corpus_approval.py)：负责核验 zero-error 验证门禁、版本匹配及 Robert 人工抽查决策，将 bundle 状态转为 `approved`；
  - [corpus.py](file:///Users/robertwu/Documents/Projects/IsophanyAI/AI-Scientist-v2/ai_scientist/ideation/corpus.py)：对外统一公共门面。
- `perform_ideation_temp_free.py` 保持原样未动，import closure guard 严格通过，CLI `--help` SHA-256 与基线完全一致。

## 合同与版本

| 项目 | 固定值 |
|---|---|
| Corpus contract | `corpus-contract-v1.0` |
| Corpus schema | `corpus-schema-v1.0` |
| text normalization | `source-text-nfc-lf-trim-v1` |
| enrichment policy | `reference-authority-v1.0` |
| corpus validator | `corpus-validator-v1.0` |
| Approved Corpus Manifest | `corpus-manifest-v1.0` |
| Validation Report Schema | `corpus-validation-report-v1.0` |
| Approval Decision Schema | `corpus-approval-decision-v1.0` |

Policy 文件 `ai_scientist/ideation/policies/reference-authority-v1.json` 的 SHA-256 为 `65b0d9aa5942eb164370fb6d7162fbd6b4a629488a6093e0e0ebfd44eb1e6a5f`；代码硬绑定同一 digest，缺失或漂移均 fail closed。

## 隔离红线与 Fail-Closed 清单

### 1. Quarantine 隔离（VM-LEAKAGE-04）
以下字段绝对禁止进入 `corpus.json` 或任何模型可见上下文，仅保留在私有 `evidence/source-rows.jsonl`：
- `targetPaperId`
- `contexts`
- `intents`
- `isInfluential`
- `citationCount`
- `abstract_summary`
- `query`, `score`, `rank`

### 2. 11 项 Error 级规则全量 Fail-Closed（VM-CONTRACT-019-01）
- `CORPUS-SCHEMA-001`：非 canonical JSON、存在额外字段、CRLF、多余换行立即报 fail；
- `CORPUS-MAPPING-001`：opaque case_id 与 bundle 目录或 manifest 不一致立即报 fail；
- `CORPUS-MEMBERSHIP-001`：缺少、多余或重复 reference paperId，或 records 未按 canonical paper_id 排序立即报 fail；
- `CORPUS-IDENTITY-001`：paper_id 非 40 位小写 hex 立即报 fail；
- `CORPUS-CONTENT-001`：Title 为空、content items 为空、组合状态与文本不自洽立即报 fail；
- `CORPUS-KNOWN-BAD-001`：已知坏值（`falls,`、`Statistics Working Papers Series`）进入运行时文本立即报 fail；
- `CORPUS-PROVENANCE-001`：缺失 provenance_ref 立即报 fail；
- `CORPUS-HASH-001`：任何文件哈希或 bundle content inventory 哈希不符立即报 fail；
- `CORPUS-QUARANTINE-001`：发现封禁字段立即报 fail；
- `CORPUS-SOURCE-001`：原始数据集来源路径或哈希缺失立即报 fail；
- `CORPUS-ELIGIBILITY-001`：整个语料内没有任何一项状态为 validated 的有效内容立即报 fail。

## Fixtures 与 hashes

全部 tracked fixtures 位于 `tests/fixtures/corpus/`，包含合成 Target 与 References 数据：

| Fixture | SHA-256 |
|---|---|
| `tests/fixtures/corpus/target_papers.csv` | `085603704257173b9e4a3c1015f8e02d8479e39e0839e9ce6d2c49ee64e83fcf` |
| `tests/fixtures/corpus/filtered_references.csv` | `b3df2fa96da466be979f4296db3dcfb09ebf5aa7cba1b5f137e33e498c3b7f16` |
| `ai_scientist/ideation/policies/reference-authority-v1.json` | `65b0d9aa5942eb164370fb6d7162fbd6b4a629488a6093e0e0ebfd44eb1e6a5f` |

## 验证结果矩阵

| 矩阵项编号 | 验证说明 | 验证方法与证据 |
|---|---|---|
| `VM-CONTRACT-019-01` | corpus validator 负向 error 清单逐条 fail-closed | `test_corpus_validator_negative_fail_closed` 逐一测试 11 类条款，全部断言 fail |
| `VM-CONTRACT-019-02` | 正向 golden bundle 通过且 validator 零改写 | `test_corpus_validator_positive_golden_and_no_mutation` 断言通过且字节完全一致 |
| `VM-REPLAY-02` | 同输入重建生成相同 bundle SHA-256 | `test_corpus_rebuild_replay_determinism` 断言前后生成 byte-identical corpus 与相同 content hash |
| `VM-LEAKAGE-04` | contexts/intents 等辅助字段不进入 corpus 检索区 | `test_corpus_quarantine_leakage` 断言 corpus.json 中完全不包含任何封禁字段 |

## 真实私有 Smoke 验证脱敏摘要

| 属性 | 脱敏值 |
|---|---|
| case_id | `case-229e495f82a24cff9e6082aa058955b9` |
| bundle path | `artifacts/ideation-inputs/corpora/case-229e495f82a24cff9e6082aa058955b9` |
| corpus SHA-256 | `3c1f40d2a7a93d77b45ab65d1e86cb8bf5b280f1d379e159e54506429c34d209` |
| source-rows SHA-256 | `19f6bd1fb99a6b1b441c76961eb114684ea932127d4747f9804555aa7078abd9` |
| validation report SHA-256 | `156169cc71301d2a898b2b6dbc01d3248069c971755e8e772ba217ce0014707e` |
| bundle content SHA-256 | `2fbcf3fa77c21328fa0766fae03d71b2e573fec2baed6d827b799720d5151d0b` |
| deterministic validation | `pass`（0 errors, 1 non-fatal venue warning） |
| approval status | `approved` |
| approved by | `Robert` |
| approved at | `2026-09-03T10:44:28.260439Z` |

## 全量 237 个 Targets 预处理离线验证结果

通过运行 `validate_all_corpora(REPO_ROOT)`：
- `total_targets`: 237
- `passed_targets`: 237
- `failed_targets`: 0
- `status`: `pass`
- 耗时：7.17s
- 运行时外联：零网络、零模型调用、零费用
