# 原始 AI Scientist-v2 Workshop File：证据、边界与本项目输入原则

研究日期：2026-08-29

研究范围：只研究 ideation 输入语义与公开实现，不调用模型，不进入 BFTS、实验、绘图、写作或评审阶段。

## 结论

1. **[Confirmed] 官方不存在机器可执行的 Workshop schema。** 官方 README 把输入称为 high-level topic description，建议使用 `Title`、`Keywords`、`TL;DR`、`Abstract` 等 section；运行时代码却不解析、不校验这些字段，而是把整个 Markdown 原样读入 prompt。因此这四段是 **de facto 文档格式惯例**，不是 formal schema。([README at `96bd516`](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/README.md#L97-L121); [runtime at `96bd516`](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/perform_ideation_temp_free.py#L98-L108); 本地镜像：`README.md:97-121`、`ai_scientist/perform_ideation_temp_free.py:98-108,303-315`)
2. **[Confirmed] 官方公开代码历史中只有一个 Workshop Markdown 样例，而且只有一个内容版本。** 它是 10 个物理行、331 个 whitespace-delimited words、2,304 个 Unicode characters；四段依次是 `Title`、`Keywords`、`TL;DR`、`Abstract`，其中 Abstract 占 282 words。样例于 commit `be512772...` 加入，此后未改；当前 blob 是 `714db6b...`。([fixed sample](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/ideas/i_cant_believe_its_not_better.md#L1-L10); [adding commit](https://github.com/SakanaAI/AI-Scientist-v2/commit/be512772df68a095e109aef746295b2420fc4f93); 本地镜像：`ai_scientist/ideas/i_cant_believe_its_not_better.md:1-10`)
3. **[Confirmed] 原始 Workshop 输入的粒度是一个能产生许多不同论文方向的 broad theme，不是一篇 paper 的 gap、hypothesis 或技术路线。** Nature version of record 称其为 “broad theme of the workshop”，并把一般 ideation 范围描述为 user-specified ML research subfield；Sakana 官方页面也称为 broad research direction/topic。([Nature, Generating manuscripts and Human evaluation](https://www.nature.com/articles/s41586-026-10265-5); [official Nature announcement](https://sakana.ai/ai-scientist-nature/); [official 2025 experiment post](https://sakana.ai/ai-scientist-first-publication/))
4. **[Confirmed] Workshop 全文在每个 idea 的首轮作为 user prompt 的第一部分出现。** `Title`、`Keywords` 等没有单独权重；额外正文、标识符乃至指令也会同样进入模型。随后 reflection prompt 不再显式重复 Workshop，但首轮 user/assistant 消息由 `msg_history` 继续带入同一个 proposal 的对话。([ideation prompt and loop](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/perform_ideation_temp_free.py#L98-L179); [message history](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/llm.py#L267-L449); 本地镜像：`ai_scientist/perform_ideation_temp_free.py:98-179`、`ai_scientist/llm.py:267-449`)
5. **[Inference] 本项目不应复制“ICBINB 征稿页”，而应复制它的功能。** 最低充分输入是一个 target-derived、identity-free 的 **problem envelope**：研究对象/现象、尚未解决的张力或问题、为何重要、必要的中性边界。它应足以让不同 targets 的 ideation 分布不同，同时仍容纳多个实质不同的答案；它不应包含 Target Paper 的方法、机制、实验配方、结果、结论或可反查标识符。
6. **[Inference, medium confidence] Q1 应选择经过收紧的 B，而不是 A 或 C。** 建议把 B 改写为：给出 target 对应的 problem neighborhood，但不复述 target 独有的 gap-to-solution framing，并要求至少存在多个不同 method families 可以合理作答。A 可作为 pilot control；C 与官方 broad-theme 证据直接冲突，也会把 held-out answer 带入输入。
7. **[Unknown] 官方资料没有回答 per-target 最优粒度、最佳字数、四个 section 是否优于其他结构，或 Target Paper → Workshop 的安全转换算法。** 这些不能从唯一的 broad-workshop 样例外推，必须按 Robert 提议先做少量 target canary，再决定是否全量生成。

## 证据标签

- **Confirmed**：由官方源码、Git 历史、官方论文或 Sakana 官方页面直接陈述或可机械复现。
- **Inference**：由 confirmed facts 和本项目目标推出的最窄设计判断，不宣称是官方协议。
- **Unknown**：公开的一手资料没有给出答案，或证据不足以建立精确对应关系。

## 1. 研究对象与固定版本

本报告只使用以下一手来源：

| 来源 | 固定版本 | 本报告用它回答什么 |
|---|---|---|
| [SakanaAI/AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2/tree/96bd51617cfdbb494a9fc283af00fe090edfae48) | `96bd51617cfdbb494a9fc283af00fe090edfae48`，2025-12-19 | Workshop 文件、README 约定、prompt 与 message-history 数据流、完整 Git 历史 |
| [Workshop file adding commit](https://github.com/SakanaAI/AI-Scientist-v2/commit/be512772df68a095e109aef746295b2420fc4f93) | `be512772df68a095e109aef746295b2420fc4f93`，2025-04-16 | 样例首次公开及默认路径变化 |
| [SakanaAI/AI-Scientist-ICLR2025-Workshop-Experiment](https://github.com/SakanaAI/AI-Scientist-ICLR2025-Workshop-Experiment/tree/c05036b2e0dcc17056abfba398184f51a93087ca) | `c05036b2e0dcc17056abfba398184f51a93087ca`，2025-04-18 | 公开的三份 workshop submission 及仓库中是否保存真实 input |
| [AI Scientist-v2 technical report](https://pub.sakana.ai/ai-scientist-v2/paper/paper.pdf) | 下载文件 SHA-256 `c902bdf96ff2519189049cacf12114d63e310d58471f61dd156b16d4baa7f2fa` | §3.1、§4.2 与 Appendix B 的 ideation 角色、约 20 ideas 和 prompt 模板 |
| [Nature version of record](https://doi.org/10.1038/s41586-026-10265-5) | 2026-03-25 version of record | 高层系统语义、user-specified subfield、broad workshop theme |
| [Sakana official Nature announcement](https://sakana.ai/ai-scientist-nature/) 与 [2025 experiment post](https://sakana.ai/ai-scientist-first-publication/) | 2026-03-26；2025-03-12 | “broad research direction/topic”的官方公开解释 |

对官方仓库的历史检查覆盖 clone 中的所有公开 refs：`origin/main`、`origin/revert-68-main`；对 Workshop Experiment 仓库覆盖 `origin/master`。在这些 refs 的全部 reachable commits 中，唯一的 `ai_scientist/ideas/*.md` 是 `i_cant_believe_its_not_better.md`。

## 2. 官方 Workshop File 究竟是什么

### 2.1 不是 formal schema，而是自由 Markdown 的惯例形态

**[Confirmed] 文档层面：** README 要求用户创建一个描述 research area/theme 的 Markdown，并说它 “should contain sections like” `Title`、`Keywords`、`TL;DR`、`Abstract`；同时把样例称为 expected structure and content format。这里的 “like” 给出推荐形态，不给出字段类型、长度、required/optional、version、escaping 或 extra-section 规则。([README lines 97–117](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/README.md#L97-L117))

**[Confirmed] 运行时层面：**

- `open(args.workshop_file).read()` 读取全文；
- 没有 Markdown parser、header lookup、JSON Schema、frontmatter parser 或 validation；
- 整段字符串直接替换 `{workshop_description}`；
- 文件名仅通过字符串替换 `.md → .json` 决定 idea archive 路径。

证据见 [`perform_ideation_temp_free.py` lines 98–108, 158–179, 287–315](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/perform_ideation_temp_free.py#L98-L179)；本地镜像为 `ai_scientist/perform_ideation_temp_free.py:98-108,158-179,287-315`。

因此，准确表述是：

> 官方有一个推荐的四段 Markdown **format convention**，没有一个机器执行的 **formal schema**。

这也意味着 section 标题并不构成安全边界。若文件中混入 Target Paper identifier、answer-bearing paragraph 或 prompt instruction，当前 runtime 会原样发送。

### 2.2 唯一公开样例的形态与内容功能

官方样例：[`ai_scientist/ideas/i_cant_believe_its_not_better.md`](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/ideas/i_cant_believe_its_not_better.md#L1-L10)，本地镜像 `ai_scientist/ideas/i_cant_believe_its_not_better.md:1-10`。

| Section | 实测长度 | 直接内容 | 对 ideation 的功能解释 |
|---|---:|---|---|
| `Title` | 11 words；68 characters | ICBINB workshop 名称与 applied-DL challenges | 给搜索空间一个易识别的总标签；不包含技术答案 |
| `Keywords` | 6 words；46 characters | negative results、deep learning、failure modes | 提供三个高显著性主题锚点 |
| `TL;DR` | 24 words；149 characters | benchmark/现实效果张力，以及探索 pitfalls/challenges 的动词 | 把主题压缩成开放问题和行动方向 |
| `Abstract` | 282 words；1,992 characters | 价值观、背景、现实部署张力、跨领域范围、failure categories、共同模式与期望价值 | 定义广度、相关性标准和“什么算切题”，但不指定答案 |
| 全文 | 331 words；2,304 characters；10 physical lines | 四段自由 Markdown | 作为一个完整字符串进入首轮 prompt |

Abstract 虽然只有一个物理行，但语义上完成了七个任务：

1. 说明价值取向：negative/surprising results、transparency、shared learning；
2. 给出背景：benchmark success 推动 real-world deployment；
3. 给出核心张力：dynamic real world 暴露 benchmark 忽略的 limitations；
4. 给出探索对象：challenges、unexpected outcomes、shared failure patterns；
5. 给出覆盖面：healthcare、scientific discovery、robotics、education、fairness、social sciences；
6. 给出可接受的 failure categories：performance、safety、reliability、ethics、society；
7. 给出价值函数：跨领域迁移经验，推动 robust/reliable/applicable AI。

**[Confirmed] 它没有提供**某个候选 idea 的 named method、模型架构、dataset、实验分组、数值结果或结论。它约束的是“去哪片问题空间搜索”与“什么方向算 aligned”，不是“实现哪一个答案”。

**[Inference] 四个 section 的功能有重叠，真正必要的是上述语义，不是 Markdown 标题本身。** 例如 `Keywords` 和 `TL;DR` 可以帮助 LLM 建立显著性，但源码没有给它们独立通道或权重。

### 2.3 历史版本与缺失的原始实验 input

Git 历史揭示了一个重要区别：**公开样例**不等于已证明的**原始内部实验输入**。

- **[Confirmed]** initial commit `f85bb035...`（2025-04-08）已经包含若干 idea JSON 与实验代码，但没有任何 Workshop `.md`；当时 ideation CLI 默认指向未随仓库提交的 `experimental/workshops/i_cant_believe_its_not_better.md`。([initial tree](https://github.com/SakanaAI/AI-Scientist-v2/tree/f85bb0355cacb600e020f3de0e7e6f59503058e2/ai_scientist/ideas); [initial ideation script](https://github.com/SakanaAI/AI-Scientist-v2/blob/f85bb0355cacb600e020f3de0e7e6f59503058e2/ai_scientist/perform_ideation_temp_free.py#L267-L315))
- **[Confirmed]** commit `be512772...`（2025-04-16）新增当前 10-line Markdown，并把默认路径改到 `ideas/i_cant_believe_its_not_better.md`。([commit diff](https://github.com/SakanaAI/AI-Scientist-v2/commit/be512772df68a095e109aef746295b2420fc4f93))
- **[Confirmed]** 约 18 分钟后的 commit `d1c359c7...` 才把 `Title`、`Keywords`、`TL;DR`、`Abstract` 写入 README 作为 expected structure；这进一步表明 schema 来自文档惯例，而不是 parser。([README-documentation commit](https://github.com/SakanaAI/AI-Scientist-v2/commit/d1c359c7e41d963f68c67f7820ace23137630eb7))
- **[Confirmed]** 当前 Markdown 从新增后没有任何内容 commit；所以公开 Git 历史只有这一个内容版本。
- **[Confirmed]** official Workshop Experiment repo 在固定 commit `c05036b...` 只公开三份 submitted paper、AI reviews、human reviews 与 review tooling；其全部 Git 历史没有 ideation Workshop input、约 20 个 initial ideas 的 archive 或 ideation interaction log。([repo tree](https://github.com/SakanaAI/AI-Scientist-ICLR2025-Workshop-Experiment/tree/c05036b2e0dcc17056abfba398184f51a93087ca); [README lines 12–26](https://github.com/SakanaAI/AI-Scientist-ICLR2025-Workshop-Experiment/blob/c05036b2e0dcc17056abfba398184f51a93087ca/README.md#L12-L26))
- **[Confirmed]** 该 experiment repo 确实有一个变量也叫 `ws_description`，但它位于 `ai-reviewing/reviews_workshop.ipynb:52-80`，内容是四项投稿要求与五项评审维度；随后作为 `reviewer_system_prompt` 送给三份已完成 paper 的 reviewer（notebook lines 97–146）。它是 **review rubric**，不是 ideation input，不能算第二个 Workshop File 样例。([fixed notebook](https://github.com/SakanaAI/AI-Scientist-ICLR2025-Workshop-Experiment/blob/c05036b2e0dcc17056abfba398184f51a93087ca/ai-reviewing/reviews_workshop.ipynb))
- **[Confirmed]** technical report §4.2 只说 theme 从 workshop official website 提取，并生成 approximately twenty ideas；Appendix B 公开的是 `{workshop_description}` placeholder，不是填充后的真实文本。([technical report](https://pub.sakana.ai/ai-scientist-v2/paper/paper.pdf), pp. 9, 20–21)

所以：

- **[Inference]** 当前公开 `.md` 很可能是官方为复现而补充的 workshop-description 样例，并与论文描述的 theme 相符。
- **[Unknown]** 它是否与 2025 submission experiment 使用的内部 prompt 字节级相同；公开证据不能建立这一点。
- **[Unknown]** 约 20 个候选 idea 的完整分布，以及 Workshop 文本中各 section 的独立因果效果。

## 3. Workshop text 如何进入 prompt，以及什么实际影响 ideation

### 3.1 精确数据流

对每次 proposal generation：

```text
Markdown full text
    ↓ read() without parsing
{workshop_description}
    + previous idea archive
    ↓ first user message
LLM action: literature search or finalize
    + tool result / reflection instruction
    ↓ same msg_history
refined/final idea JSON
```

具体行为：

1. **[Confirmed]** 每个新 idea 开始时，`msg_history = []`。`ai_scientist/perform_ideation_temp_free.py:154-164`
2. **[Confirmed]** 首轮 user prompt 的顺序是完整 Workshop、已生成 proposals、再要求生成一个不同的新 proposal。`ai_scientist/perform_ideation_temp_free.py:98-108,158-164`
3. **[Confirmed]** 第二轮起的新 prompt 只包含 reflection round、quality/novelty/feasibility 指令和上次工具结果；但是 `get_response_from_llm` 把新 user message追加到旧 `msg_history`，所以首轮 Workshop 仍在对话历史。`ai_scientist/perform_ideation_temp_free.py:165-179`、`ai_scientist/llm.py:267-449`
4. **[Confirmed]** 下一个 proposal 会重置对话历史，但重新注入同一个 Workshop；同时把 archive 中的全部旧 ideas 作为 `prev_ideas_string` 注入，推动 diversity。`ai_scientist/perform_ideation_temp_free.py:137-164`
5. **[Confirmed]** 默认 `reload_ideas=True`；若 sibling JSON 已存在，旧 ideas 在首次新 generation 前就进入 archive。`ai_scientist/perform_ideation_temp_free.py:128-146`

### 3.2 实际有影响的内容，不止 Workshop

**[Confirmed]** ideation 的条件输入至少包括：

- system prompt：high-impact、novel、creative、simple/elegant question、与 literature 区分、academic-lab feasibility、top-ML publishability；
- Workshop 全文：主题与 scope；
- previous ideas：要求当前 proposal 与 archive 不同；
- Semantic Scholar tool results：在 reflection 中吸收相关工作；
- reflection prompt：quality、novelty、feasibility、clarity、simplicity。

证据见 [`perform_ideation_temp_free.py` lines 23–125](https://github.com/SakanaAI/AI-Scientist-v2/blob/96bd51617cfdbb494a9fc283af00fe090edfae48/ai_scientist/perform_ideation_temp_free.py#L23-L125)。

这带来三个关键判断：

- **[Confirmed]** runtime 不知道 `Title` 与 `Abstract` 的字段身份，只有 LLM 根据 Markdown 语义理解它们。
- **[Inference]** Workshop 的任务是提供 search prior 和 alignment criterion；novelty、feasibility、output shape 已由系统 prompt 与 tools 负责，不需要在每个 Workshop 重复。
- **[Inference]** Workshop 中任何 answer-bearing 细节都会影响整个 proposal trajectory：它不仅影响首轮想法，还通过 message history 影响 literature query、reflection 与最终 JSON。

**[Unknown]** 各 section 对最终 idea 的边际因果贡献。官方没有做 title-only、keywords-only、abstract-only 等 ablation。

## 4. Nature 论文中的 workshop/theme 角色

Nature version of record 给出两层粒度：

1. **[Confirmed] 一般系统角色：** ideation 在一个 user-specified machine-learning research subfield 内迭代生长 high-level research directions and hypotheses，并为每个方向形成 title、reasoning 和 experimental plan。([Nature, “Generating manuscripts”](https://www.nature.com/articles/s41586-026-10265-5))
2. **[Confirmed] ICBINB 适配角色：** template-free system 只需用 workshop 的 broad theme 提示；论文对该 theme 的括号解释是研究 deep-learning limitations，包括此前改善思路未奏效的情形。([Nature, “Human evaluation results”](https://www.nature.com/articles/s41586-026-10265-5))

官方配套资料进一步确认：

- **[Confirmed]** Sakana 的 Nature 公告说，系统在 broad research direction 之后自行生成 ideas、查阅 literature、设计和执行 experiments、写 paper。([official announcement, lines 21–24](https://sakana.ai/ai-scientist-nature/))
- **[Confirmed]** 2025 官方实验页面说 humans “merely gave it the broad topic”，而选择 ICBINB 是因为它 scope 较宽，能容纳 practical limitations of DL 下的 diverse topics。([official experiment post, Evaluation Process](https://sakana.ai/ai-scientist-first-publication/))
- **[Confirmed]** technical report §3.1 把 v2 的变化定义为从 existing-code incremental modification 上移到更高抽象层：先开放思考 research directions、hypotheses 和 experiment designs，类似先写 abstract/grant proposal，再承诺具体 implementation。([technical report](https://pub.sakana.ai/ai-scientist-v2/paper/paper.pdf), pp. 3–4)

**结论：[Confirmed] Workshop/theme 是搜索空间的高层边界，不是 proposal 本身；proposal 的 hypothesis、method 和 experiments 应由 ideation 阶段产生。**

## 5. 从第一性原理推导本项目的最低充分输入

### 5.1 先定义这个输入必须完成的工作

本项目的 Workshop 同时面对两项相反要求：

1. **区分性：** 不同 Target Paper 对应的 ideation 不应退化成同一个 broad-cluster prompt；否则 Target → Workshop 映射没有提供 target-level conditioning。
2. **非答案性：** Workshop 不能让 ideation 模型直接得到 Target Paper 的贡献；否则生成结果与 target 相似不能再说明 ideation 能力。

因此需要的不是“尽可能多的信息”，而是**刚好能识别问题空间、不能识别 held-out answer 的信息**。

### 5.2 最低充分语义

以下是 **[Inference]**，不是官方 schema：

| 必要语义 | 为什么需要 | 安全边界 |
|---|---|---|
| `problem_area` | 让模型知道在哪个学科/子领域搜索 | 使用通行领域名，不用 Target Paper title 或 target-created name |
| `research_object_or_phenomenon` | 把问题落到对象、群体、任务或现象，而不是八类 cluster | 不包含 target 特有干预、architecture、material、instrument 或 dataset recipe |
| `open_tension_or_question` | 给 ideation 一个要解释/改善/测量的开放问题 | 只陈述问题，不写 “use X to achieve Y” 或 target hypothesis 的 mechanism |
| `significance` | 定义为何值得研究，帮助模型评价方向 | 不夹带 target result、effect direction 或 claimed application |
| `neutral_scope_or_constraints`（按需） | 防止 proposal 完全偏离 case；控制 feasibility | 只保留不指向唯一答案的 context、population、resource/evaluation dimension |

四段 Markdown 可作为 model-visible rendering：

- `Title`：identity-free problem-area label；
- `Keywords`：少量 established terms；
- `TL;DR`：一句开放问题/张力；
- `Abstract`：背景、重要性、中性 scope，以及仍允许的探索宽度。

但这只是建议的 rendering；真正 contract 应先定义允许/禁止语义，再定义 Markdown section。

### 5.3 最低充分性的四个反事实测试

这些测试是 **[Inference]**：

1. **Removal test：** 删除某句话后，模型是否仍知道“研究什么、为什么、边界在哪”？若是，该句不是最低必要信息。
2. **Distinctness test：** 两个科学问题明显不同的 targets 是否会得到实质相同的 Workshop？若是，输入太宽。
3. **Multiple-answer test：** 至少多个不同 method families 能否合理回答这个 Workshop？若否，输入太窄或已编码答案。
4. **Answer prediction test：** 只看 Workshop，审计者能否高置信预测 target 的具体 method、experiment 或 result？若能，输入泄漏。

### 5.4 不应从官方样例机械复制的内容

以下判断均为 **[Inference]**：

- 不复制 331-word 长度。唯一官方样例是跨领域 workshop CFP，per-target problem envelope 所需长度未知，可能明显更短。
- 不复制 workshop 品牌、community building、submission culture、venue invitation 等行政语义；它们在 ICBINB 中定义 relevance，在本项目中通常不是科学问题。
- 不默认复制 negative-result framing。它属于 ICBINB 的 value function；除非当前 target problem 本身需要该方向，否则会给所有 ideas 人为加同一种结果偏好。
- 不把领域举例列表当 target scope。原样例列出 healthcare、robotics 等是为了扩大征稿面，而 per-target input 应缩到问题 neighborhood。
- 不复制 Target Paper 的 exact title、authors、DOI、paperId、venue、URL 或 target-created acronym；这些不是 ideation 必需信息，却提高反查与记忆泄漏风险。
- 不复制 Target Paper 的 abstract、solution-bearing hypothesis、method、architecture、experimental design、result、mechanism、conclusion；这些本应由 ideation 产生或事后评估。
- 不在 model-visible Markdown 写 provenance、source spans、hash 或 leakage diagnostics；它们应进入 private sidecar。

## 6. 对 Q1 specificity 的证据分级建议

### 建议：选择 `B-guarded`

建议把现有 B 改成：

> 给出与 target 对应的 **problem neighborhood**：研究对象/现象、已存在的开放问题或张力、意义和必要的中性约束；不得复述 target 独有的 gap-to-solution framing，并且必须能容纳多个实质不同的 method families。

### 证据强度

| 判断 | 结论 | 证据强度 | 理由 |
|---|---|---:|---|
| 不选 C | 高置信 | High | 官方明确使用 broad theme/subfield；官方样例不含具体 hypothesis、method、experiment 或 result。C 还把应由 ideation 产生的内容提前给出。 |
| A 可作 control | 高置信 | High | 官方 ICBINB 证明 broad theme 能产生 diverse directions；所以 cluster-level prompt 是合理 baseline。 |
| A 不应直接定为 per-target production contract | 中高置信 | Medium–High | 本项目要求每个 Target 对应 Workshop；仅八个 cluster 会让许多 targets 得到同一 topic，弱化 target-level mapping。这个结论来自本项目目标，不是官方实验结论。 |
| B-guarded 是当前最佳 production hypothesis | 中等置信 | Medium | 它同时满足 target-level 区分和 broad-theme 非答案性；但官方没有研究 Target Paper → Workshop，因此仍需 canary evidence。 |
| 四段 section 与具体字数 | 暂不锁定 | Unknown | 只有一个样例，无 ablation、无 parser、无 per-target 数据。 |

### 为什么不是原 B 的无条件版本

“已有问题”或“gap”也可能是 target answer 的一部分。许多论文用非常独特的 gap formulation 几乎唯一指向其 proposed method。安全条件不应是句子在论文里被作者标成 background，而应是：

- 它是否在 target contribution 之前独立成立；
- 它是否兼容多个不同答案；
- 它是否不能用于反查或重建 target contribution。

所以应把 B 的核心从“可以包含 gap”改成“可以包含 non-answer-bearing open tension”。

## 7. 少量 target pilot：先验证，再全量

这是 **[Inference]** 的建议实验设计；本 ticket 只定义和批准设计，不在本报告中调用模型。

### 最小公平比较

选择少量跨领域 canaries，而不是随机挑同一 cluster：

- 至少覆盖多个 cluster；
- 同时包含容易抽取 background 的 target 与 gap/method 强耦合的高泄漏 target；
- 包含不同问题粒度和不同 abstract 写法；
- 先冻结选择理由与 target hashes，避免看结果后换样本。

对每个 target 至少比较：

1. `A-control`：只给 cluster/broad-area theme；
2. `B-guarded`：target-derived problem envelope；
3. 可选 `B-overfit canary`：故意靠近 target-specific gap，仅用于验证 leakage gate 是否能拒绝，不能进入正式 ideation。

### 比较指标

| 指标 | 问题 |
|---|---|
| `target_problem_relevance` | ideas 是否真正围绕该 target 的问题，而不是 cluster 泛题？ |
| `multiple_answer_breadth` | Workshop 是否允许多个不同方法族，而非暗示一个答案？ |
| `answer_leakage` | 是否出现 target method/result/identifying phrase 的复制或近义重建？ |
| `idea_diversity` | 同一 Workshop 下 ideas 是否实质不同？ |
| `reference_grounding` | ideas 是否利用 target-scoped references，而不是 Workshop 偷带答案？ |
| `reproducibility_and_cost` | 同一输入能否重放，生成/审计成本是否可接受？ |

### Promotion gate

只有当 `B-guarded` 相对 `A-control` 明显提高 target-problem relevance，同时不恶化 answer leakage、multiple-answer breadth 和 reproducibility，才值得全量生成。若没有提升，应保留更宽的输入；若泄漏增加，应收窄 derivation source 或加强人工语义 gate，而不是用更多自动生成掩盖问题。

## 8. 明确未知项与下一步决策

1. **[Unknown]** 最优 Workshop word count 与每段长度。
2. **[Unknown]** `Keywords`/`TL;DR` 是否独立提升 ideation，还是只是重复 Abstract。
3. **[Unknown]** target-derived problem envelope 的最可靠生成机制：人工、规则、受约束 LLM 或混合方案。
4. **[Unknown]** paraphrase-level leakage 的可靠自动阈值；exact match 或 n-gram 只能覆盖一部分风险。
5. **[Unknown]** DeepSeek 对 2024 targets 的参数记忆；安全 Workshop 不能消除训练数据 contamination。
6. **[Unknown]** 当前公开 Workshop `.md` 是否与 2025 internal experiment prompt 完全一致。

这些未知项支持当前顺序：先批准 mechanism-independent 的语义合同，再用少量 canaries 比较生成机制与 specificity；不要先全量生成 237 份再发现输入边界错误。

## 最终建议陈述

**[Inference] Workshop File 应定义为 target-derived、identity-free、model-visible 的 problem envelope，而不是 Target Paper 摘要。官方四段 Markdown 可保留为可读 rendering，但项目必须自行增加 strict schema、private provenance 和 fail-closed leakage checks。Q1 采用 `B-guarded` 作为待验证 hypothesis；A 作为 broad baseline；C 拒绝。先用少量跨领域 targets 做公平 canary 比较，证据达标后再全量。**
