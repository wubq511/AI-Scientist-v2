# 证据链验证与脱敏导出证据 (Ticket 11)

## 验证背景与范围

本证据文档对应 implementation ticket [11: Validate and export a trustworthy Evidence Chain](../wayfinder/ideation-implementation/tickets/11-validate-and-export-a-trustworthy-evidence-chain.md)，证明：

1. **确定性证据损坏判定 (`RUN_CORRUPT`) 与不可修复性 (VM-CONTRACT-023-02)**：
   - 静态校验器 `validate_evidence_chain` 全面核验链条完整性：`request.json`、`admission.json`、`events/` 单调哈希链（`event_hash = sha256(canonical(event - hash))` 且 `parent_event_hash` 紧密闭合）、`seal.json` 终态封印（final event 指针一致、artifact_inventory 逐项匹配并升序排列）、所有引用 artifact 存在且 byte_length / sha256 吻合、无未清空的 `staging/` 残留、无任何符号链接（symlink）；
   - 损坏的 run 保留原始不可变证据，但绝不尝试「自动修复」，并在 resume、seal、export、replay、evaluation 或 promotion 路径中坚决 fail closed。
2. **正向白名单脱敏导出与原子提交 (VM-CONTRACT-023-03)**：
   - 脱敏导出器 `export_sanitized_evidence` 从空对象出发，仅按正向白名单字段提取信息构造 `evidence/ideation-runs/<run_id>/manifest.json` 与 `events.json`；
   - 导出过程经过严格的发布门禁扫描（release gate scanner），验证 schema、规范化 JSON 字节格式、哈希闭环，并以临时暂存目录加原子重命名（atomic rename）提交，失败绝不在导出目录留下半成品；
   - 导出具备幂等性：重复导出已存在的完全相同内容返回成功且字节完全一致，若目标已存在且字节有偏差则 fail closed 报错拒绝。
3. **禁止泄漏项释放门禁扫描 (VM-LEAKAGE-03)**：
   - 严格拦截模型提示词与中间推理私有字段（如 `prompt`, `messages`, `response`, `reasoning`, `idea` 等）；
   - 严格扫描禁止路径（如私有工作区路径、`data/raw/`、`artifacts/ideation-runs/`）；
   - 深度扫描凭证模式（API Key、Bearer 令牌及环境中活动的 `DEEPSEEK_API_KEY` / `S2_API_KEY` 等）；
   - 针对非公开 Target Paper 身份标识（Title、DOI、arXiv ID、PMCID、PubMed ID）进行敏感词泄露排查。
4. **跨 Run 与路径安全隔离 (VM-ISOLATION-01, VM-ISOLATION-02)**：
   - RunStore 强制拒绝跨 Run 读写，排他性创建冲突（`RUN_ID_COLLISION`），拒绝 `latest`、通配符（glob）或非法 Run ID；
   - Admission 阶段显式拒绝将前序 Run 的私有证据（`artifacts/ideation-runs/`）作为新 Run 的 runtime input 或父关系输入（`CROSS_RUN_INPUT_FORBIDDEN`）；
   - 路径防穿透：全面防御绝对路径、`..` 父目录穿越、反斜杠 `\` 注入，并在路径各级严查并拒绝符号链接（symlink）。
5. **候选与尝试写一次性及离线重放决定论 (VM-ISOLATION-03)**：
   - Attempt 具备不可变 Write-once 语义：重跑或重试绝不能覆盖已存在的 Attempt 文件（`ARTIFACT_EXISTS`）；
   - 离线验证器 `replay_recorded_run` 从已记录证据完整重放事件序列，证明决定论。

验证全程确定性：使用 `StubTransport`，无任何外部网络访问，**零网络调用、零真实费用**，未进入下游 BFTS、实验、写论文或评审阶段。

---

## 验证矩阵映射

| 行 ID | 检查项 | 结果 | 证据 |
|---|---|---|---|
| **VM-CONTRACT-023-02** | 损坏的 Run（缺核心文件、坏事件链、哈希篡改、伪造 artifact、未清空 staging、包含 symlink）被确定性识别为 `RUN_CORRUPT`，且不可修复/恢复/封印/导出/重放 | **PASS** (`tests/test_evidence_chain_validation.py`) | 覆盖缺失 `request.json`、缺失 `admission.json`、broken parent hash、tampered event hash、tampered artifact bytes、orphan 未登记 artifact、staging 残留、symlink 植入等 8 种破坏性测试，均确定性判定 `RUN_CORRUPT`，原始文件完全保留 |
| **VM-CONTRACT-023-03** | 仅 sealed run 允许导出；基于正向白名单构建 `manifest.json` 与 `events.json`；校验器/导出器版本记录；发布门禁全面放行；幂等逐字节一致；原子提交 | **PASS** (同上) | 未 sealed 的 run 导出报错 `RUN_NOT_SEALED`；导出产物字段逐一断言且仅含白名单字段；多次导出相同 run 产生 byte-identical 产物；篡改后重复导出报错 `EXPORT_CONFLICT` |
| **VM-LEAKAGE-03** | 发布门禁扫描拦截敏感信息（提示词/中间字段、私有路径、API Key/Bearer/环境变量、Target Paper 私有身份） | **PASS** (同上) | 门禁深度扫描 `_scan_for_forbidden_keys`、`_scan_for_forbidden_paths`、`_scan_for_credentials`、`_scan_for_target_identities`，任何越界数据均直接拦截中断导出并清理临时目录 |
| **VM-ISOLATION-01** | 跨 Run 隔离保护：拒绝跨 run 读写、排他创建冲突、拒绝 `latest`/glob、禁止将历史 run 证据作为运行时输入 | **PASS** (同上) | 跨 Run artifact 读写抛出 `CROSS_RUN_ACCESS_DENIED`；复用已有 run_id 抛出 `RUN_ID_COLLISION`；非法 run_id 抛出 `INVALID_RUN_ID`；Admission 传入历史证据目录报错 `CROSS_RUN_INPUT_FORBIDDEN` |
| **VM-ISOLATION-02** | 路径攻击集全面防御：绝对路径、`..` 父目录穿越、反斜杠转移、各级路径中的符号链接攻击 | **PASS** (同上) | 针对 `read_artifact`、`write_artifact`、`build_artifact_inventory` 及 Run root 的路径越界与 symlink 注入，均抛出 `INVALID_ARTIFACT_PATH` 或 `SYMLINK_NOT_ALLOWED` |
| **VM-ISOLATION-03** | Attempt 不可变写一次保证，离线验证器从已记录证据证明决定论 | **PASS** (同上) | 已存在的 attempt 重复写入触发 `ARTIFACT_EXISTS`；`replay_recorded_run` 离线验证通过事件序列与 artifact inventory 证明事件与状态推演的完全决定论 |

---

## 核心架构与设计落实

### 1. 证据链校验器 (`ai_scientist/ideation/evidence.py`)
- `validate_evidence_chain(workspace_root, run_id, check_sealed=True)`：
  - 静态检查 Run 目录规范及 `request.json`、`admission.json`；
  - 遍历读取 `events/` 下有序事件，核验 `event_seq` 单调递增、`parent_event_hash` 紧邻、`sha256(canonical_json(event - event_hash))` 强校验；
  - 检查 `seal.json`（若要求 sealed）：核验 `final_event` 对应链条末尾、`artifact_inventory` 完整性与字典序升序排列、终态类型与 payload 声明一致；
  - 全量核验 inventory 中每一个 artifact 文件的物理存在、字节长度与 SHA-256 校验和；
  - 扫描禁止符号链接及未清理的 `staging/` 临时文件。
  - 任何违规统一判定并抛出 `RUN_CORRUPT`。

### 2. 正向白名单脱敏导出器 (`export_sanitized_evidence`)
- 仅从未受污染的空字典构建脱敏对象（Positive Allowlist Construction），绝不在原始对象上进行黑名单剔除（No in-place deletion）；
- `sanitized_events` 仅保留 `event_seq`、`event_type`、`operation_seq`、`pipeline_position` 等合规调度元数据，payload 内仅保留安全数字/字符串/布尔状态，严禁透传自由文本提示词与中间推理输出；
- `sanitized_manifest` 记录 Run 元数据、Admission 绑定承诺、事件摘要哈希、产物清单与版本戳（`validator_version`, `exporter_version`）；
- 提交机制：先在 `evidence/ideation-runs/.staging_<run_id>_<uuid>` 写入、fsync 并通过发布门禁扫描，确认无误后以 `os.rename` 原子转正；若目标已存在且字节一致则成功，若内容不一致则阻断报错。

### 3. 跨 Run 与路径防御网
- **路径与符号链接拦截** (`run_store.py`)：`_validate_run_relative_path` 禁止以 `/` 起始、禁止 `\` 路径分隔符、禁止含 `..` 路径分量；`read_artifact` 与 `write_artifact` 沿路径各层通过 `os.path.islink` 排查软链接；Run 根目录与产物清点拒绝任何软链接；
- **历史证据输入阻断** (`admission.py`)：在 `NewRunRequest.validate` 与 `_read_pinned_input` 中严密校验 workshop/corpus 输入路径，凡命中或指向 `artifacts/ideation-runs` 者，统一报错 `CROSS_RUN_INPUT_FORBIDDEN`，杜绝旧 run 证据污染新 run。

### 4. CLI 命令扩展 (`perform_ideation_temp_free.py`)
- `validate` 子命令：`python perform_ideation_temp_free.py validate --run-id <UUID>`，校验成功输出结构化结果并 exit 0；损坏或未 seal 输出错误并 exit 1；
- `export` 子命令：`python perform_ideation_temp_free.py export --run-id <UUID>`，导出成功输出结构化脱敏路径并 exit 0；失败输出错误并 exit 1。

---

## 验证执行记录

```bash
# 1. 证据链验证与脱敏导出专用测试集 (21 项全量通过)
$ python -m pytest tests/test_evidence_chain_validation.py -v
======================== 21 passed, 6 warnings in 8.03s ========================

# 2. 全量回归测试 (565 项全量通过，无任何回归损坏)
$ python -m pytest -q
565 passed, 6 warnings in 74.43s (0:01:14)

# 3. 语法与字节码编译检查
$ python -m compileall ai_scientist
(exit code 0)

# 4. 代码风格与格式检查
$ python -m black --check ai_scientist/ideation/evidence.py tests/test_evidence_chain_validation.py ai_scientist/ideation/run_store.py ai_scientist/ideation/admission.py ai_scientist/perform_ideation_temp_free.py
All done! ✨ 🍰 ✨
5 files would be left unchanged.
```

所有新增规范均与既有体系无缝协同，Ticket 11 验收标准全部达成。
