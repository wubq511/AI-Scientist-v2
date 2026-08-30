---
title: Define run identity and evidence layout
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

What run identity, directory layout, immutable event schema, raw/sanitized boundary, hashes, and cross-run checks preserve the full Evidence Chain while preventing idea and state contamination?

## Resolution

Robert 批准以下 run identity 与 evidence layout 合同。一个 Ideation Run 是固定 Run Specification 下的一条隔离 Evidence Chain：合法 resume 延续同一 run，rerun/replay 创建新 run；v1 禁止读取任何 prior-run runtime artifact 或 mutable state。

### Minimal identity model

全局 opaque identity 只保留两个：

- `case_id` 稳定标识一个 Ideation Case，不包含或泄漏 Target Paper identity。
- `run_id` 使用 canonical lowercase UUIDv4，标识从 request 创建到 terminal seal 的唯一 Ideation Run。它不编码 `case_id`、时间、输入 hash 或配置。

其余概念使用 run-scoped integer coordinate，不引入额外 UUID：

- `writer_epoch` 是 start/resume writer ownership 的 fencing token；合法 resume 保持 `run_id` 并递增 epoch，旧 writer 的任何写入都必须失败。
- `operation_seq` 标识一次 logical operation，`operation_kind` 使用封闭、版本化枚举。相同 semantic input 与 intended effect 的 transport retry 属于同一 operation；prompt、messages、query 或 config 变化必须创建新 operation。
- `attempt_seq` 标识一个 operation 下的 physical attempt。
- `event_seq` 标识 run 内不可变 Evidence Event；event 的唯一坐标是 `(run_id, event_seq)`。
- `generation_index`、`reflection_index` 和 `idea_index` 只表达 pipeline position，不是 identity。
- Artifact 不使用 `artifact_id`，由 `run_id + run-relative path + SHA-256` 精确引用。

删除并禁止使用含糊的 `invocation_id`、`call_id`、`event_id`、`artifact_id` 和 `parent_run_id`。Paired canary 或 evaluation 在 run 外的 evidence 中显式列出参与比较的 `run_id`，不因此取得读取 raw run 的权限。若未来确需 prior-run artifact import，必须另立 narrow contract，精确 pin source run、artifact path、hash 和 purpose；v1 不保留通用后门。

Run Specification 一旦创建不得修改；变更 Workshop、Corpus、code、model、policy、prompt/config 或 budgets 必须新建 `run_id`。在第一个需要审计的 preflight step 之前创建 run；连 entry request 基本 schema 都未通过的错误仍属于 run 外 entry error。

### Fixed trust roots and per-run layout

v1 使用两个固定、repo-relative trust roots，不接受任意 output root：

```text
artifacts/ideation-runs/<run_id>/          # private, gitignored
├── request.json
├── admission.json                        # only after passed preflight
├── events/
│   ├── 00000001.json
│   └── ...
├── artifacts/
│   ├── operations/<operation_seq>/attempts/<attempt_seq>/
│   ├── ideas/<idea_index>/
│   └── validations/
├── projections/
│   └── resume-state.json                 # derived, non-authoritative
└── seal.json                             # only at terminal outcome

evidence/ideation-runs/<run_id>/           # sanitized, tracked
├── manifest.json
└── events.json
```

`case_id`、日期、idea name、query、model output 和其他用户内容不得进入目录名。Approved Workshop、Corpus bundle 和 Git source 不复制进 run；Run Admission pin clean commit 中 exact repo-relative path 与 hash。实际发送给模型或返回给模型的 exact bytes 必须形成 run-local immutable artifact。

Lifecycle documents 均为 write-once：

- `request.json` 保存 `run_id`、requested `case_id`、Run Specification、command evidence 与 request timestamp，使 preflight rejection 也可审计。
- `admission.json` 只在 preflight 通过后产生，精确 pin Approved Workshop、Approved Target Reference Corpus、Git commit、schemas、policies、model/provider、prompt/config、price snapshot、budgets 与 hashes；它是运行获准消费哪些输入的唯一证据。
- `seal.json` 在 terminal 时产生，固定 terminal outcome、request/admission hashes、final event boundary 与完整 immutable artifact inventory；存在后禁止追加或修改 event/artifact。

`projections/` 只用于性能和 resume convenience，不属于 Evidence Chain。Resume 必须证明 projection 对应当前 event-chain head；否则丢弃并从 canonical evidence 重建。

### Immutable Evidence Event envelope

每个 event 独占 `events/<zero-padded-event_seq>.json`，filename 不含语义或用户内容。所有 producers 共用同一个严格、版本化 envelope：

```json
{
  "schema_version": "1.0.0",
  "run_id": "<canonical-lowercase-uuidv4>",
  "event_seq": 12,
  "writer_epoch": 2,
  "event_type": "provider_attempt.finished",
  "recorded_at": "2026-08-29T14:00:00.000000Z",
  "operation": {
    "operation_seq": 4,
    "operation_kind": "model_inference",
    "attempt_seq": 2
  },
  "pipeline_position": {
    "generation_index": 0,
    "reflection_index": 1,
    "idea_index": null
  },
  "artifact_refs": [
    {
      "role": "provider_response",
      "relative_path": "artifacts/operations/000004/attempts/000002/response.json",
      "media_type": "application/json",
      "byte_length": 1234,
      "sha256": "<hex>"
    }
  ],
  "payload": {},
  "prev_event_hash": "<hex-or-null>",
  "event_hash": "<hex>"
}
```

- `event_seq` 是唯一顺序依据；timestamp 只供诊断。
- `operation` 与 `pipeline_position` 只在语义相关时出现，不使用伪造的空值或默认零填充不适用字段。
- `event_type`、`operation_kind` 和 type-specific payload 使用 tracked、versioned、closed schemas；unknown type/field、非法组合与 `additionalProperties` 全部 fail closed。
- Prompt、response、reasoning、retrieval content、idea body 和 raw error 不内嵌 event，通过 immutable artifact refs 连接。Secret 即使在 private artifact 中也禁止保存。
- 每个 artifact 必须先完整持久化并计算 hash，event 才可引用。Atomic write、staging recovery 与具体 controller transition events 由 [Define control flow, failures, and resume](025-define-control-flow-failures-and-resume.md) 在本 envelope 下固化。

### Canonical bytes and hash graph

项目生成的 lifecycle、event、seal、manifest 与其他 schema-controlled JSON documents 使用同一 canonical bytes contract：UTF-8、无 BOM、所有 strings Unicode NFC、object keys 按 Unicode code point 排序、compact separators、schema-defined array order、LF、文件末尾单个 newline；禁止 duplicate keys、NaN、Infinity 和 schema 外数值类型。Timestamps 固定为 UTC RFC 3339、六位小数与 `Z`。

- 所有 hashes 使用 SHA-256。Captured provider payload 与 model-visible artifact 基于 approved adapter/controller boundary 实际捕获和保存的 representation bytes；即使 media type 是 JSON，也不得在 capture 后为了套用项目 canonical rendering 而重新序列化再 hash。该合同不虚构 SDK 未暴露的 HTTP wire bytes。
- `event_hash = SHA256(canonical event bytes with event_hash omitted)`。
- 首个 event 的 `prev_event_hash` 为 `null`；后续 event 必须精确引用上一 event hash。
- 对应 lifecycle events 引用 `request.json` 与 `admission.json` hashes；`seal.json` 再固定这些 hashes。
- Terminal event 先写入并产生 final event hash；随后 `seal.json` 引用 final event hash 和按 relative path 排序的完整 artifact inventory。Terminal event 不引用 seal，seal 不保存 self-hash，从而避免循环。
- `projections/` 排除在 inventory 与 hash graph 之外。
- Sanitized `events.json` 的每项保留 `source_event_hash`；`manifest.json` 保存 raw request/admission/seal hashes、final event hash、artifact inventory 和 sanitized events hash。

不引入 Merkle tree 或 shared content-addressed store。当前单 run artifact 规模下，sorted inventory 加 linear event hash chain 更容易实现和审计；相同 bytes 在不同 run 中仍分别保存，不能形成隐式跨 run dependency。

### Filesystem and cross-run isolation

- New run root 必须 exclusive-create；若已存在则失败，禁止复用、清空或覆盖。
- Resume 只接受 exact `run_id`；禁止 `latest`、glob、按 `case_id`/Workshop 查找最近 run 或 workshop-adjacent JSON。
- 所有 child names 由 runtime 固定模板生成，只使用 ASCII 固定词、UUID 与 zero-padded integers。
- Artifact refs 必须是 normalized POSIX relative paths；absolute path、`.`、`..`、empty segment、backslash、symlink、path escape、normalization/case collision 全部拒绝。
- 写入前逐层确认目标仍在当前 run root 且无 symlink。Controller、adapter、retriever 与 validator 只能使用绑定到当前 run 的 storage boundary，不能接收 arbitrary output path。
- External input 只能来自 Run Admission allowlist；每次打开重新验证 exact path/hash。任何 `artifacts/ideation-runs/<other-run-id>/` 内容始终不是合法 runtime input，即使 hash 匹配。
- Temporary/staging files 也必须位于当前 run root；禁止 shared mutable idea archive、resume state、cache 或 temp file。
- Sanitized exporter 只能读取一个已 sealed raw run，并写相同 `run_id` 的 sanitized root。目标已存在时，只有 byte-identical output 可视为幂等成功；差异必须失败，禁止覆盖。

### Resume, seal, and corruption gates

Resume 前必须验证 request/run/path identity、run 尚未 sealed、连续的 `1..N` events、完整 hash chain、全部 artifact refs、Run Admission 中 exact commit/inputs/versions、clean worktree、writer ownership 与 projection head。Seal 前还必须证明 terminal event 最后、所有 operations 有 terminal disposition、success run 通过 required validation、failed/rejected run 的失败证据完整、artifact inventory 与文件一一对应。

Dedicated staging subtree 以外不得存在 orphan final artifact。Staging cleanup/archive 行为由 [Define control flow, failures, and resume](025-define-control-flow-failures-and-resume.md) 固化，但 staging bytes 不得伪装为 committed evidence。

任何 canonical file 缺失、hash mismatch、断链、非法 event 或 orphan final artifact 都使 run `corrupt`。Corrupt run 禁止 repair-in-place、resume、seal、export、作为 replay source 或进入 evaluation/promotion；保留原证据，在 work log 记录 incident，并以新 `run_id` 重做。Seal 后可以 best-effort 设置只读权限，但可信度来自 hashes，不依赖 filesystem permissions。

### Raw retention and sanitized release gate

POC 阶段永久本地保留 success、failure 与 preflight-rejected runs 的 private raw evidence；不自动删除、迁移、上传或外部备份。删除或迁移需要 Robert 单独明确批准。Raw evidence 丢失后，sanitized manifest 只剩历史摘要，不再能支撑 replay、evaluation 或 optimization promotion。

Sanitized exporter 从空对象按 positive allowlist 构造，不能复制 raw object 后做字段删除。允许内容限于 opaque run/case IDs、versions、commit/input hashes、event/operation numeric metadata、artifact role/size/hash、provider/model identity、finish disposition、usage/timing/CNY cost、stable error class、terminal outcome、validation results 与 raw chain hashes。

Sanitized evidence 禁止包含 Target Paper identity/title/DOI/URL/private mapping、query、prompt/messages、response、reasoning、Retrieval Segments、idea body、provider response ID、raw error/body/stack、credential/header/environment value、absolute path、username/hostname 或 schema 外 free text。

进入 Git 前必须通过 strict sanitized schema、canonical bytes、raw seal/event/artifact linkage、forbidden key/path/credential-pattern/target-identifier scans，并记录 exporter/validator version 与结果。Hash fields 使用 typed validation 避免 high-entropy false positive。新 schema/allowlist version 需 focused human review；同一批准版本下不要求逐 run 手工复核。任一 gate 失败时不得产生可提交 sanitized root，raw evidence 保持不变。

本 ticket 只锁定 identity、persistence、integrity、privacy 与 isolation contract；没有实现 runtime、创建 run、调用模型或进入 downstream。Generation/tool/reflection/finalization/retry/interruption/resume state machine、atomic write 与 staging recovery 仍由 [Define control flow, failures, and resume](025-define-control-flow-failures-and-resume.md) 决定，但不能放宽本合同。

> 后续修订（2026-08-30）：[Define control flow, failures, and resume](025-define-control-flow-failures-and-resume.md) 修订 orphan final artifact 规则：rename→event 落盘间存在微秒级崩溃窗口，该窗口产生的 orphan 不再直接判 run corrupt；resume 时隔离至 quarantine 区、记录 incident 后继续——event 从未引用这些 bytes，链完整性不受影响。staging cleanup 行为亦由该票固化。
