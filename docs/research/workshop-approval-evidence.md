# Workshop approval boundary 验证证据

日期：2026-09-03

Implementation ticket：[Approve one Workshop File](../wayfinder/ideation-implementation/tickets/02-approve-one-workshop-file.md)

验证矩阵：`VM-UNIT-01`、`VM-UNIT-04`、`VM-CONTRACT-018-01`、`VM-CONTRACT-018-02`、`VM-LEAKAGE-01`

## 结论

离线 `prepare → validate → approve` 边界已实现。Python 3.13.7 / macOS arm64 的最终全量验证为 `288 passed`；真实私有 smoke candidate 已通过 deterministic gate，并停在 `pending_independent_review`。由于该 candidate 的 derivation actor 是 `codex`，在独立 reviewer 提交 hash-bound semantic decision 前，不产生真实 `Approved Workshop`。本票未调用模型、未访问网络、未产生模型费用，也未进入 BFTS 或其他 downstream 阶段。

## 固定实现边界

- 开工固定点：`9ec43b5 fix: backfill foundation closure commit`。
- 实现 commits：`c51d68b add: implement Workshop approval boundary`、`c7c8367 fix: harden Workshop approval contract`、`11e5cb6 fix: enforce frozen Workshop preparation`。
- 稳定入口：`python -m ai_scientist.prepare_ideation_inputs workshop {prepare,validate,approve}`。
- `preparation.py` 只负责 source ingestion、允许字段投影、preparation schema 与 case-level frozen binding；`validation.py` 负责 canonical/leakage gate、attempt 持久化与重放；`approval.py` 负责独立 semantic decision、完整 attempt history 与最终 resolution；`workshop.py` 只保留 public facade。
- `perform_ideation_temp_free.py` 未修改；本票没有将 approval 接入 Ideation Run，该准入集成仍属于后续 ticket。

## 合同与版本

| 项目 | 固定值 |
|---|---|
| Workshop contract | `workshop-contract-v1.0` |
| validator | `workshop-validator-v1.1` |
| normalization | `ideation-text-normalization-v1.0` |
| leakage policy | `workshop-leakage-rules-v1.0` |
| semantic packet / decision | `workshop-semantic-packet-v1.1` / `workshop-semantic-decision-v1.1` |
| Approved Manifest | `approved-workshop-manifest-v1.1` |
| substantive overlap | 8 stable tokens；`calibration_status=pending` |

Policy 文件 `ai_scientist/ideation/policies/workshop-leakage-v1.json` 的 SHA-256 为 `5147d6b1d951e2de0f50fb132955e053e638ffd3daa6292c08a047f8fdc21f61`；代码硬绑定同一 digest，缺失或漂移均 fail closed。经验性阈值没有按单 case 调整。

`prepare` 输出的 authoring source 封闭为 `case_id`、`title`、raw `abstract`、schema version 与 source allowlist；`abstract_summary`、Target identifiers 与 target-authored reference `contexts` 只进入私有 validator/reviewer packet。相同 `case_id` 的所有 preparations 与 attempts 必须共享完全相同的 Target identity、dataset path/hash、canonical target-row hash、authoring-source hash、allowlist、contract 与 rule versions；正常 retry、恢复/注入冲突 preparation、validation replay 和 approval 都执行该约束。

Deterministic gate 验证严格四段 rendering、UTF-8/NFC/LF/末尾单 newline、非空值、无额外内容、opaque identity、`paperId`/DOI/URL/exact title，以及 raw abstract、`abstract_summary`、reference `contexts` 的 exact、normalized substring 与 8-token overlap。Semantic decision 封闭要求以下九项均为 `true` 才能批准：English、Title/Keywords/TL;DR/Abstract 各段语义、target relevance、multiple method families、answer leakage 与 identity leakage。reviewer 必须与 derivation actor 不同，且 review timestamp 必须晚于 derivation。

## Fixtures 与 hashes

全部 tracked fixtures 为人工合成数据，不含真实 Target 内容：

| Fixture | SHA-256 |
|---|---|
| `tests/fixtures/workshop/target_papers.csv` | `fbc987410d540651e81c5df4891bc74f2aaa2d471d0046fac089b0d0aa8d11a8` |
| `tests/fixtures/workshop/filtered_references.csv` | `fea6b908300a7af07e4fa41003f42b2a217a78ecc37346618001a35c7790dda2` |
| `tests/fixtures/workshop/valid.md` | `bee3534cc63cd1d43ec4d624d68bbc3ebb0673ce1fef8f8bacfcada91f7bd638` |
| `tests/fixtures/workshop/leaked.md` | `951a4fe042fa08945033e55b6b1e3f7c1387ab6a46ca0bc219fc2b14bf35040e` |

正向 fixture 经两层 gate 产生 Approved Workshop；负向与动态 fixtures 覆盖 invalid UTF-8、non-NFC、CRLF、extra section、`paperId`、DOI、URL、exact title、三类私有比较源 × 三类匹配、candidate/preparation/report/semantic-packet hash tamper、source drift、self-review、semantic rejection、跨 Target preparation 绕过与 rejected-attempt history。失败只留下 immutable rejected attempt；没有 fallback artifact 或 Approved Workshop。

## TDD 与验证结果

主要 RED 证据：初始测试因 `ai_scientist.ideation` 不存在而 collection fail；实现后新增 tampered semantic packet 用例先暴露 approval 可错误成功，deterministic reject 状态用例先暴露 `semantic_status=pending`，第一轮 code review 的 English/section semantic 与跨 Target retry 用例在旧实现失败；最终对抗复现“移走 preparation A → 创建 Target B preparation → 恢复 A → validate B”先证明读取阶段可绕过 frozen binding。对应实现均在保留测试后转绿。

最终可复现命令（`<venv>` 是既有 Python 3.13.7 clean environment；依赖未变化，精确环境继续引用 [ideation foundation lock](ideation-foundation-macos-arm64-py313.lock.txt)，SHA-256 `8b43ebd5480a02a1613a44f65a6bd27ba94e8aa24b9e9eb8fa48cc82d75e26f0`）：

```bash
<venv>/bin/python -m pytest -q \
  tests/test_workshop_approval.py \
  tests/test_dependency_contract.py \
  tests/test_ideation_import_contract.py \
  tests/test_ideation_cli_baseline.py
<venv>/bin/python -m black --check \
  ai_scientist/ideation ai_scientist/prepare_ideation_inputs.py \
  tests/test_workshop_approval.py
<venv>/bin/python -m compileall -q ai_scientist
<venv>/bin/python -m pytest -q
```

结果：

- Workshop + foundation 定向验证：`33 passed in 2.72s`，其中 Workshop 文件为 30 tests。
- Black：本票触及范围 12 files 全部 unchanged。
- compileall：exit `0`。
- 全量 pytest：`288 passed in 11.53s`。
- `git diff --check`：通过。
- `requirements.txt` / `requirements-dev.txt` 未修改，SHA-256 仍分别为 `3b031a68c7bd8c4f498b8182183b10b866a2aac46fd8c77bda85a3200b0637ac` / `68528a63263d3edc209368d0c63f3512c9ade0e568b82c6350361911c9653391`。

## 真实私有 smoke 的脱敏摘要

真实 source、authoring packet、candidate、review packet 与完整 attempts 保留在 gitignored `artifacts/ideation-inputs/`，不进入 Git。本摘要只记录 opaque identity、状态与 hashes：

| Artifact / result | Sanitized value |
|---|---|
| case | `case-229e495f82a24cff9e6082aa058955b9` |
| preparation manifest | `47a2f1579df3a48d36058a15782ea33479b54d88037e6e95fb05c318d6a12294` |
| candidate canonical bytes | `c30836c059dc81d4804c44a83890c9894d30f882fb15cdf73dcbb5e93aef24dc` |
| attempt manifest | `78e1ec2c3759e5438812f4695e1caa3c88d1883b22336b31658a362fcb00bed6` |
| validation report | `ebc2532232b739d23fd8ee6a373ddec8bb617a454032d5e039ea41bce915726e` |
| semantic review packet | `70837770bea3ad717d6d6e36a5f64ae3ab69b587515d3c9a7f70d6ff36db8ffa` |
| deterministic gate | `pass`；failures `[]` |
| semantic gate | `pending_independent_review` |
| Approved Workshop | 未产生 |

Private paths 由 opaque `case_id` 和 canonical stage IDs 组成；已用 `git check-ignore -v` 确认 candidate 与 semantic review packet 命中 `.gitignore` 的 `artifacts/ideation-inputs/` 规则。

## Code review

固定点 `9ec43b5` 的第一轮并行 review：Standards 轴 1 个硬性违规与 3 个判断项，Spec 轴 2 个 P1 与 3 个 P2。修复包括删除无依据的 `type: ignore`、按生命周期拆分 1,596 行模块、引入具名 `LoadedAttempt`、补全全部 attempt provenance、扩展 semantic contract 和 VM fixtures、冻结 case→Target/source binding。

最终候选复核又各发现 1 项：Standards 指出 preparation manifest 先验 hash 后重读形成 TOCTOU；Spec 通过恢复冲突 preparation 复现 validation/approval 绕过。前者改为在同一次 read 的 bytes 上验 hash 后解析，后者在 validate 与 approval/replay 两个入口扫描完整 case inventory。两项回归转绿后的双轴复核均为 0 findings：无剩余 Standards 违规、Spec 缺口或 scope creep。

## Trust boundary

所有自动化验证均为 offline、zero-model、zero-cost；没有访问 provider、Semantic Scholar 或其他远端服务。Tracked fixtures 和本文不含真实 Target identity/title/DOI/URL、论文正文、prompt、response、credential、绝对路径、username 或 hostname。真实 smoke 尚不是 Approved Workshop；只有独立 reviewer 对 hash-bound packet 作出九项全通过 decision 后，`approve` 才能原子生成 model-visible `<case_id>.md` 与 private manifest。
