# Post-Seal 定性评估证据 (Ticket 12)

## 验证背景与范围

本证据文档对应 implementation ticket [12: Evaluate every finalized idea after seal](../wayfinder/ideation-implementation/tickets/12-evaluate-every-finalized-idea-after-seal.md)，落地契约锚点 [032（IdeaBench 评估保真度）](../wayfinder/ideation-pipeline/tickets/032-choose-ideabench-evaluation-fidelity.md)、[026（Idea Quality Rubric）](../wayfinder/ideation-pipeline/tickets/026-define-the-idea-quality-rubric.md) 与 [037（post-seal Evaluation Artifact 合同）](../wayfinder/ideation-pipeline/tickets/037-define-the-post-seal-evaluation-artifact-contract.md)，证明：

1. **Assemble（合同 037.6 前半）**：`assemble_evaluation_brief` 只对 sealed 且 non-corrupt 的 run 工作（先跑 `validate_evidence_chain(check_sealed=True)`，corrupt 判定 `RUN_CORRUPT`、未 seal 判定 `RUN_NOT_SEALED`，fail closed）；从 seal inventory 取 finalized idea 七字段 payload、Declared Grounding 与 sidecar，经事件链定位 retrieval `model_payload` 引用并逐字节核验 hash，摘出每个 declared paper 的 segment 摘录；Target Paper comparator 经 Workshop Manifest 绑定推导（`approval_status`/`case_id`/workshop hash 复核）并对 `data/raw/target_papers.csv` 做 dataset 级与 target-row 级 SHA-256 校验，任何漂移 fail closed。产出确定性 `brief.md`（无时间戳，重 assemble 字节一致、直接覆盖）与预填 linkage 的 `draft.json` skeleton（已存在则保留，绝不覆盖 Robert 在填工作）。
2. **Validate（合同 037.8）**：`validate_evaluation_artifact` 执行全确定性 fail-closed 校验——canonical JSON 值（NFC/无重复键/无 float）、封闭 schema（未知字段即拒）、linkage 完整性（run_id、`seal.json` hash、idea 在 seal inventory 且 path+hash 匹配、run 非 corrupt）、`case_id` 与 `request.json` 一致、target 引用与 Workshop Manifest 记录一致、`rubric_version` 属于已批准版本（pinned policy 文件 `idea-quality-rubric-v1.json`，hash 锁定于 `contract.py`，篡改即 `POLICY_DRIFT`）、`schema_version` 为当前支持版本、七项 criterion 齐全且 verdict 在封闭 enum 内、rationale 非空（纯空白亦拒）、authoring audit 字段齐全且格式合法、draft 审计的 `brief_sha256` 必须等于磁盘当前 brief（防 stale brief 定稿）、`supersedes` 线性链（目标存在、同 run/idea、尚未被 superseded）。任一失败不产生定稿、draft 原样保留、无 Git 侧输出；通过则追加 `validated_by`/`validated_at`/`validation_result="passed"` 并以 O_EXCL write-once 提交 `v%04d.json`。
3. **粒度与红线（037.5 + 032）**：每个 finalized idea 独立计一份 artifact，terminal `failed` run 中已 committed 的 idea 同样可评估（已有测试覆盖）；全程不产生 numeric score、overall score、LLM judgment 或 sanitized stub；Evaluation Artifact 不进该 run 的 Evidence Chain。
4. **Read-only coverage（037.9 + VM-QUAL-01）**：`list_evaluation_coverage` 只读扫描全部 seal inventory × `artifacts/evaluations/`，按 idea 输出 `covered`（supersedes 链 head 通过同一套确定性校验：链接存在 + schema 合法）/`draft_only`/`missing`；head 存在但非法时附 `head_error` 不计 covered；corrupt run 单列 `status: "corrupt"`；case 级 comparator 输入（Workshop Manifest/target 数据源）缺失的 sealed run 单列 `status: "unevaluable"`（其自身 Evidence Chain 完整，与 corrupt 区分）；未 seal run 不属于 seal inventory，不计入。coverage 不改写任何 run evidence 或 evaluation artifacts（有树级 hash 前后比对测试）。

判分本身（七项 verdict 与 rationale 的内容）是 Robert 的定性行为，永不机检；未引入任何 LLM judge。

---

## 验证矩阵映射

| 行 ID | 检查项 | 结果 | 证据 |
|---|---|---|---|
| **VM-QUAL-01** | canary 阶段每个产生 final idea 的 sealed run 可链接 schema 合法的 Evaluation Artifact（机检：链接存在 + schema 合法；判分内容不机检） | **PASS** (`tests/test_post_seal_evaluation.py`) | `list_evaluation_coverage` 对 seal inventory 逐 idea 核算 `covered`/`draft_only`/`missing`；`covered` 要求 head artifact 通过与 validate 同源的封闭 schema + hash linkage + 七项 enum + supersedes 链校验；head 非法（如注入未知字段）确定性降级并附 `head_error`；assemble→validate 全链路 golden 测试证明链接可建立 |

---

## 核心架构与设计落实

### 1. 评估模块 (`ai_scientist/ideation/evaluation.py`)
- `assemble_evaluation_brief(workspace_root, run_id, idea_index, *, assembled_by)`：
  - 先静态校验整条 Evidence Chain（sealed + non-corrupt 是进入评估的硬前提，合同 023/037.8）；
  - idea/grounding/sidecar 三件按 seal inventory 的 path+SHA-256 逐字节核验后读取；retrieval 摘录严格沿事件链（sidecar `retrieval_operation_seqs` → `operation.finished`/`literature_retrieval` 事件 → `model_payload` artifact ref）取回模型实际所见 payload；事件 `artifact_refs`、payload ref 字段、payload `papers`/`segments` 的每层形状均 fail-closed 校验（畸形即 `RUN_CORRUPT`，缺失 ref 即 `EVALUATION_LINKAGE_INCONSISTENT`，绝不抛裸 traceback）；declared paper 不在任何 retrieval payload 中即 `EVALUATION_LINKAGE_INCONSISTENT` fail closed；
  - Target Paper comparator：Workshop Manifest 绑定复核（approved/case/workshop hash）→ `source_provenance.target_dataset` 的 path/dataset hash/row hash 逐项核验 → 明文 title/DOI（DOI 恰好一条，缺失即 fail closed）；
  - `brief.md` 内容完全由证据推导、无时间戳，重复 assemble 字节一致（可重建）；`draft.json` skeleton 预填全部 linkage + `supersedes`（取当前最新定稿）+ rubric/schema 版本 + `assembled_*`/`brief_sha256` 审计字段，七项 judgment 留 `null` 待填；已存在 draft 绝不覆盖（`draft_status: "existing_kept"`）。
- `validate_evaluation_artifact(workspace_root, run_id, idea_index, *, validated_by)`：
  - 重验 run 链（assemble 后 run 被篡改即 `RUN_CORRUPT` 拒验）；draft 缺失即 `EVALUATION_DRAFT_NOT_FOUND`；
  - 校验核 `_check_artifact_document`：封闭 schema（draft 禁止携带 `validated_*` 三字段，定稿必须携带且 `validation_result="passed"`）、schema/rubric 版本、run/case 身份、seal/idea/target 全 hash linkage、七项 verdict 封闭 enum + rationale 非空（去空白）、audit 字段存在性与时间戳格式、draft 的 `brief_sha256` 必须匹配磁盘当前 brief、`supersedes` 线性链（null ⟺ 无定稿；否则必须等于当前最高版本文件名，目标须存在、同 run/idea）；
  - 通过 → 构造定稿（draft 字段 + validated 三字段），canonical bytes 后 O_EXCL write-once 提交 `v%04d.json`（`v0001.json`、`v0002.json`…），序号 = 现有最高版本 + 1；冲突即 `ARTIFACT_EXISTS`；
  - 失败 → 无定稿、draft 字节不动（测试逐字节断言）。
- `list_evaluation_coverage(workspace_root)`：
  - 只读：扫描 `artifacts/ideation-runs/` 下合法 run_id 目录，未 seal 跳过；每 run 先过完整证据链校验（corrupt 单列且不计 idea）；再推导 comparator（case 级输入缺失单列 `unevaluable`）；逐 finalized idea（seal inventory 中 `artifacts/ideas/<idx>/idea.json`）判定三态；
  - `covered` 的判据 = 链上最新定稿通过与 validate 同源的 `mode="final"` 校验（链接存在 + schema 合法，VM-QUAL-01）；head 非法附 `head_error`（code+message）并按 draft 存在性报 `draft_only`/`missing`；
  - 输出仅 stdout（private，不进 Git），含逐 run 明细与 summary 计数；summary 单列 `corrupt_runs` 与 `unevaluable_runs`，这两类 run 的 ideas 不进入三态统计，消费方不会高估覆盖率；版本化 `evaluation-coverage-v1.0.0` 输出 schema。

### 2. 版本化 rubric 策略 (`ai_scientist/ideation/policies/idea-quality-rubric-v1.json`)
- 七项 criterion id 与各自封闭 verdict enum 固化为 canonical JSON 单文件（`idea-quality-rubric-v1.0.0`）；SHA-256 pin 进 `contract.py`（`EVALUATION_RUBRIC_POLICY_PATH`/`EVALUATION_RUBRIC_POLICY_SHA256`），加载即验 hash，漂移 `POLICY_DRIFT`；criteria 增删改 = 新版本文件 + Robert 批准（026.6 治理）。

### 3. 存储布局与隐私（037.2/037.7）
- 私有根 `artifacts/evaluations/<run_id>/ideas/<zero-padded idea_index>/`，下含 `brief.md`（阅读材料，可覆盖重建）、`draft.json`（填写中工作文件，不计入任何链）、`v<zero-padded seq>.json`（write-once 定稿，supersedes 线性链）；`.gitignore` 已补 `artifacts/evaluations/` 条目（与 `artifacts/ideation-runs/` 同级处理，有测试钉住）；路径逐级符号链接防护与 run root 同级。

### 4. CLI 扩展 (`perform_ideation_temp_free.py`)
- `evaluation assemble --run-id <UUID> --idea-index <N> --assembled-by <NAME>`：成功 exit 0（stdout 结构化 JSON）；失败 exit 1（stderr 结构化错误，`assemble_rejected`）；
- `evaluation validate --run-id <UUID> --idea-index <N> --validated-by <NAME>`：成功 exit 0；失败 exit 1（`validation_rejected`，draft 保留）；
- `evaluation list-coverage`：只读报告 exit 0；workspace 级失败（如 rubric policy 缺失/漂移）exit 1；
- 顶层 `--help` baseline hash 与准入导入闭包清单（新增 `evaluation`/`preparation`/`text` 模块）按既有门禁机制同步更新。

---

## 验证执行记录

```bash
# 1. post-seal 评估专用测试集（59 项全量通过；含 21 项负向 draft 参数化拒绝、
#    supersedes 线性链、coverage 三态/异常 run、read-only 证明、CLI seam、
#    retrieval 摘录畸形形状 fail-closed 参数化守卫）
$ python -m pytest tests/test_post_seal_evaluation.py -q
59 passed

# 2. 全量回归测试（628 项全量通过，无任何回归损坏）
$ python -m pytest -q
628 passed, 6 warnings in 96.11s (0:01:36)

# 3. 语法与字节码编译检查
$ python -m compileall ai_scientist
(exit code 0)

# 4. 代码风格检查（触及文件全部通过；ai_scientist 全树 black 的 14 处既存
#    upstream 漂移与本票无关，stash 验证为基线既有状态，按最小改动纪律不动）
$ python -m black --check ai_scientist/ideation/evaluation.py ai_scientist/ideation/contract.py ai_scientist/perform_ideation_temp_free.py tests/test_post_seal_evaluation.py tests/test_ideation_import_contract.py tests/test_ideation_cli_baseline.py
6 files would be left unchanged.
```

TDD 红灯证据：`tests/test_post_seal_evaluation.py` 首跑因 `ai_scientist.ideation.evaluation` 模块不存在 collection fail；golden assemble 首跑因断言语句按 fixture corpus 第一 record 假设摘录文本而红（实际 declared paper 为 enrichment 后的另一 record），改为直接断言 run 内 payload 的逐段原文摘录后转绿。

双轴 code-review（Standards + Spec）后的修复轮：Spec 轴指出 `_collect_retrieval_excerpts` 对畸形 `artifact_refs`/`payload_ref`/`payload` 形状的未防护 dict 访问可能抛 `KeyError`/`TypeError` 裸 traceback，违反 037.8 全确定性 fail-closed——已修复为逐层形状守卫（`RUN_CORRUPT`/`EVALUATION_LINKAGE_INCONSISTENT`），并补 13 项参数化负向与 2 项边界单元测试钉住；同轮将 `_load_run_context` 的 `assert isinstance` 改为 `fail("RUN_CORRUPT")` 与邻近代码一致、rubric schema 版本常量归入 `contract.py`（`EVALUATION_RUBRIC_SCHEMA_VERSION`）与 policy path/hash 同位、coverage summary 补 `unevaluable_runs` 计数防高估覆盖率。修复后专用测试集 59 passed、全量 628 passed。

验证全程确定性：`StubTransport` 驱动完整 run（含 terminal `failed` run 中已 committed idea 的场景），无任何外部网络访问、零真实费用，未进入下游 BFTS、实验、写论文或评审阶段；七项 verdict/rationale 的填写内容在测试中仅为占位文本，不构成任何真实判分。
