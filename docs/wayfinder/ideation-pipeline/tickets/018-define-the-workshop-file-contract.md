---
title: Define the Workshop File contract
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 014-understand-target-to-workshop-semantics.md
  - 016-audit-metadata-gaps-and-enrichment-sources.md
  - 033-understand-dataset-routing-metadata.md
---

## Question

Which source fields, transformation rules, leakage checks, schema, filenames, and provenance must every Target Paper's Workshop File satisfy?

## Evidence

- [原始 AI Scientist-v2 Workshop File：证据、边界与本项目输入原则](../../../research/original-workshop-file-contract.md)

## Resolution

Robert 批准以下 Workshop File 合同。官方 AI Scientist-v2 的四段 Markdown 只是文档惯例，本项目把它收紧为可验证的 README-compatible baseline；它负责限定搜索空间，不负责提供 Target Paper 的答案。

### Derivation source boundary

- 每个 Workshop 只对应一个 Target Paper。私有 derivation input 仅允许该 target 原始记录中的 `title` 与 raw `abstract`。
- Target Reference Corpus 的 abstracts 只供 ideation 阶段的 Scoped Literature Retriever 使用，不参与 Workshop derivation。
- `abstract_summary` 和 target-authored reference `contexts` 不得作为 derivation source。它们可以由私有 validator 用来发现泄漏，但不能进入生成上下文。
- Model-visible Workshop 必须重新表述，不得复制 Target Paper 的 exact title、raw abstract 或可识别其身份和贡献的内容。具体 derivation mechanism 不在本 ticket 锁定，但任何实现都必须服从同一 source allowlist、内容合同和验证门。

### Model-visible schema and semantics

Workshop 是英文 UTF-8 Markdown，采用以下唯一 canonical rendering；四个值全部非空，不允许 frontmatter、额外 section、注释或附加指令：

```markdown
# Title: <identity-free problem-area label>

## Keywords
<established comma-separated terms>

## TL;DR
<one open question or tension>

## Abstract
<background, object, significance, and neutral scope>
```

- `Title` 是 identity-free 的问题领域标签，不得使用 exact Target Paper title、target-created method name 或 target-created acronym。
- `Keywords` 只包含既有的领域、研究对象、现象、任务和通用约束术语，不得编码 target-created name 或结果方向。
- `TL;DR` 表达一个开放问题或张力，不得写成“使用 X 实现 Y”的 target hypothesis 或 solution recipe。
- `Abstract` 描述背景、研究对象、重要性与中性范围，不得包含 Target Paper 的方法、机制、实验设计、target-specific dataset recipe、结果或结论。Workshop Abstract 不是 Target Paper abstract 的摘要栏。
- 初始 baseline 不从唯一官方样例外推硬 word-count。每段与全文长度必须记录在 Workshop Manifest 中，供 canary 分析；任何后续长度门必须由验证证据决定。

Canonical bytes 使用 Unicode NFC、LF 换行、图示的固定空行和文件末尾单个 newline；Workshop hash 基于这些 bytes。科学专名只有在它是既有领域术语且不会识别 Target Paper 时才可保留。

### Identity and provenance boundary

- Model-visible 文件名使用稳定且不泄漏论文身份的 `<case_id>.md`；`case_id` 不得包含 exact title、DOI、URL、`paperId` 或其他可反查标识符。
- Target Paper identity 与 `case_id` 的映射只存在 private、non-model-visible Workshop Manifest 中。具体目录和 run-level evidence layout 由 [Define run identity and evidence layout](023-define-run-identity-and-evidence-layout.md) 决定。
- Workshop Manifest 至少记录：`case_id`、private target identity、source dataset path/hash、canonical target-row hash、source allowlist、Workshop contract version、derivation mechanism/version，以及适用的 provider/model/config/prompt hash 或 manual author。
- Manifest 还必须记录 Workshop path/hash、section/full lengths、全部 derivation attempts、validation rule versions/results、independent reviewer、timestamps、失败原因与最终 approval status。除审计所必需的 hash 和定位信息外，不重复保存原始论文正文。

### Leakage validation and approval

只有通过两层验证的文件才是 `Approved Workshop`，才允许进入 Ideation Run：

1. Deterministic validation 必须验证 canonical schema、顺序、非空值、UTF-8/NFC/LF、无额外内容和 canonical hash；扫描 `paperId`、DOI、URL、exact Target Paper title；并对 raw abstract、`abstract_summary`、reference `contexts` 等私有比较源执行可重放的 exact、normalized substring 与 substantive n-gram overlap 检查。具体阈值和规则版本由 [Define the validation and test matrix](027-define-the-validation-and-test-matrix.md) 固化，不得在单个 case 上临时调整。
2. Independent semantic review 必须与 derivation attempt 分离，不能以生成器的自我声明代替；它检查近义改写后的 target answer 泄漏、是否仍允许多个实质不同的 method families 作答，以及是否仍与 target problem 相关。

任一 deterministic 或 semantic gate 失败，candidate 只能保留为 rejected draft，不得进入 ideation。

### Failure, retry, and rollout

- Retry 只能在相同冻结 source、source allowlist 和 contract version 下创建新的 derivation attempt；每次 attempt、artifact hash、validation 结果和失败原因都必须保留。
- 禁止静默回退到 raw abstract、exact title、cluster-only text、旧 Workshop 或其他 target 的 Workshop。若没有 attempt 通过，两层 gate 后该 case fail closed，不能启动 Ideation Run。
- 首轮只在少量跨领域 canary targets 上建立 baseline，不直接生成全部 237 个 Workshops。canary 选择与扩量门由 [Define canaries and scale gates](028-define-canaries-and-scale-gates.md) 决定。
- README-compatible 四段格式是初始 baseline，不是永久最优结构。problem-envelope specificity、字段删改和 rendering 变体必须在 [Compare Workshop specificity and rendering](036-compare-workshop-specificity-and-rendering.md) 中经过冻结 canary 与 optimization promotion gate 的公平比较，并再次获得 Robert 批准后才能替换 baseline。

本 ticket 未生成 Workshop、未调用模型，也未进入任何 downstream 阶段。

> 后续指针（2026-08-30）：[Define the validation and test matrix](027-define-the-validation-and-test-matrix.md) 已关闭；本票委托固化的泄漏检测阈值与规则版本落为 `docs/agents/validation-matrix.md` 的 calibration-pending 规则集（VM-LEAKAGE-01），fixture 结构与版本治理见该文档「阈值与规则版本治理」。
