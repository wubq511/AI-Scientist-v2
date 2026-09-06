# 最终 Idea 与检索质量：高价值优化审查

日期：2026-09-06。审查基线：`e27c1da`。状态：已记录、暂缓；本次交付不实施优化，不启动对照运行。

Robert 本轮明确限定：优化必须直接改善最终 idea 或检索结果，基础设施问题暂不处理。本文只讨论这个目标。

## 当前决定（2026-09-06）

Robert 明确表示当前没有时间优化，只记录问题。以下内容保留为后续参考，不是当前执行计划，也不重开已关闭的交付票。

**待办：小语料中的潜在有用摘要被固定 top-3 截断遗漏。**

- 已确认现象：音乐案例的 Approved Target Reference Corpus 只有 4 篇合格摘要，两次 Retrieval Result 都只返回同样的 3 篇；音乐干预与焦虑差异研究未被模型看到。
- 潜在影响：模型可能缺少用于完善假设、识别替代解释或设计验证的证据。尚未证明本次遗漏使最终 idea 变差，也未证明完整阅读一定更好。
- 后续候选：有时间重新启动时，比较现行 top-3 与输入预算内的完整小语料阅读；具体方案尚未选定。
- 当前处理：仅留存现象、证据和未知项；保留现行检索与生成行为。其余建议同样暂缓，待 Robert 明确重新启动。

## 判断

**优先改善模型实际看到的证据，再改善它如何从证据提出、检验研究问题。现在没有充分理由先换 BM25、继续增加 reasoning effort，或扩大生成样本。**

现有 idea 已经能提出具体机制、跨领域方法和验证计划，不能简单评价为“空泛”。主要机会是：小语料仍漏掉有用证据；query 没有追踪最终假设的方法需求；部分贡献与新颖性断言超出了已检索文献能够支持的范围。

这里的“更好”指相关证据更完整、核心论点有支持、能够区分替代解释、验证方案更聚焦，不是更像 target，也不是提高 AI 共识率。

## 审查依据与边界

- 阅读 035 的 12 份最终 idea、21 次检索 audit/payload、各 run 实际绑定 corpus，以及相关评审理由。以 `request.json` 的 corpus 绑定为准。
- 12 条 sealed Evidence Chain 重新验证为 `valid`，AI coverage 经现有只读完整性校验可解析；这证明本轮分析消费的是可回链产物，不证明科学结论正确。
- 阅读现行 prompt、BM25 实现、020/021 检索决策。分析现有排名，没有重新计算候选排序、运行本地 scorer 矩阵或调用模型。
- 下文的文献用途判断来自本次人工式阅读，是诊断假设；尚无优化后 idea 的对照结果，不能宣称改进幅度。
- 这些 12 个案例已被查看，适合诊断和开发验证，不能再当作未接触的 holdout。

## 1. 最高优先级：让小语料中的关键证据进入模型上下文

### 现象

现行 [`retrieval.py`](../../ai_scientist/ideation/retrieval.py) 固定 `paper_cap=3`、`total_segment_cap=3`。12 个实际 corpus 中，10 个只有 3–8 篇 eligible abstracts。它们全部摘要的总长度约 3,792–10,678 字符；这只是字符量，不是 tokenizer 实测，也尚未证明全量输入的净收益。

**音乐案例（slot 8）提供最清楚的漏检证据：**

- corpus 只有 4 篇，两次不同 query 都返回同样的 3 篇。
- 结果包含音乐流派分类与 sentiment 系统，却一直漏掉 *The analgesic effect of music on cold pressor pain responses: The influence of anxiety and attitude toward pain*。
- 遗漏摘要讨论音乐干预、对照条件，以及一般焦虑和疼痛相关焦虑对效果的差异。最终 idea 正要研究主观感受与生理反应的分离，还提出 cold pressor 备选设计；因此它提供了一个应考虑的个体差异与替代解释。它不直接证明 idea 的假设，也不等同于生理 stress-recovery 实验。
- 两次排名中，第 3/4 名分数分别为 `0.306224` / `0.306182`。不能把跨语料 raw score 当阈值，但此处确实是很小的分差决定模型是否看见整篇证据。

**照护者主观年龄案例（slot 12）：**只有 6 篇 eligible abstracts，最终方案依赖 within-person 动态与纵向中介，首轮 top-3 全是主题背景；corpus 内 *A critique of the cross-lagged panel model* 没有进入结果。其摘要直接讨论 within-person 过程与稳定 between-person 差异的分离，是值得阅读的方法边界材料。最终 idea 已有 multilevel 设计，不能仅凭漏检就认定它方法错误。

### 推荐方向

先比较**有界完整阅读小语料摘要**与现行 top-3。全部内容仍限于该 run 已批准的 eligible reference abstracts，不加入 target 内容、全文、联网搜索或生成摘要。是否全量阅读应受实际输入预算约束，不能只按篇数硬编码。

最小备选是 top-3 → top-5：从现有排名可知它能补上音乐案例的第 4 篇，但仍拿不到主观年龄案例的第 6 篇方法文献。它可以作为低成本对照，不能预设为最终方案。

32 篇大 corpus 不宜据此直接全塞；小语料收益成立之后，再处理超出阅读预算的情况。

### 怎样判断值得采用

保持同一生成模型、prompt、任务和输出预算，仅改变可见证据集合。先在上述两个诊断案例对照 top-3 / top-5 / 完整小语料，观察：关键证据是否被正确用于假设、替代解释或验证设计；是否增加无关引用、淹没有效材料；最终方案是否实质变化。再用未查看的新案例确认。

不能以“多返回了文献”判成功。最脆弱的假设是：额外材料会被有效使用；若只是增加引用长度而 idea 不变，就不应采用全量阅读。

## 2. 高优先级：第二次检索应回答具体缺口，而不是重复主题词

### 现象

数字孪生案例（slot 9）的最终 idea 聚焦**网络架构是否改变疫情干预的排序**。两次实际 query 却主要由 `digital twin healthcare ... validation calibration ...` 构成，没有 `epidemic`、传播动力学或具体干预机制。

corpus 内两篇 source-faithful 文献未被返回：

- *Epidemic spreading in scale-free networks*：两次排名第 4、第 6；摘要讨论网络结构与传播阈值。
- *The effect of network topology on the spread of epidemics*：两次排名第 10、第 9，score 都为 0；摘要讨论拓扑性质如何决定传播持续性。

两篇主要研究计算机网络传播，不能充当临床干预证据；但对这个 idea 的合成网络仿真和机制设定，比只看到一般图特征更直接。这里既有 top-3 截断，也有 query 与最终机制没有对齐的问题。单纯增加 top-k 无法解释或解决第二篇的零词面匹配。

21 次检索中，有 3 个案例第二次没有新增 paper。其内 2 个 corpus 本来只有 3 篇，重复返回不等于 ranker 错误；它提示生成侧应识别材料已经读完，而非再次改写同义主题词。

### 推荐方向

把第二次 query 的用途改为：针对初步假设指出一项仍缺少的证据，再围绕**机制、方法或最强替代解释**检索。query 使用生成侧已经可见的 Workshop、idea 和 reference 词汇；不能借用 sealed target。

例如数字孪生方向应围绕 network topology、epidemic spreading、intervention ranking 提问；纵向主观年龄方向应围绕 within-person、between-person、cross-lagged 或 mediation 提问。这些是待验证的 query 方向，不是已证明有效的新 query。

最小改动候选在 [`profiles.py`](../../ai_scientist/ideation/profiles.py) 的 reflection/tool 使用指导，不必一开始改 ranker 或新增工具接口。先不增加固定轮数：有新问题才搜索，材料已覆盖时转向检验假设。

验证时固定检索输出策略，独立比较现行 query 与缺口驱动 query，避免把第 1 项和本项同时修改后无法归因。指标是新增的**有用证据**及其对最终设计的贡献；新 paper 数只是辅助观察。

## 3. 高优先级：定稿前检查“核心主张—依据—替代解释—最小判别研究”

### 现象

最终 idea 不缺细节，但部分细节是缺乏已见证据支持的确信：

- ECV 案例（slot 4）把 `620EA9D3` 用来支持“directional technique ... have also been examined”。实际释放摘要涉及族群、产次和胎盘位置，并没有方向技术证据。这是具体的 claim–source 错配，不只是文风问题；primary reviewer 也指出了它。
- 7 个案例（slots 2、4、6、7、8、9、12）的 hypothesis/related work 出现未经所见材料充分支持的全领域新颖性或普遍性断言，如“从未测量”“没有研究”“首次”。本轮没有证明这些断言在现实中为假；结论是仅靠这几个摘要无法证明它们为真。
- 主观年龄案例给出约 1,700–1,800 person-days 可获得 `>80% power` 的确定表述，却未给出效应量、相关结构或计算依据。它使计划显得精确，但不足以支撑该精度。
- 音乐案例展开成约 120 段刺激、300 人主观评定、64 人生理研究、另 30 人确认研究。复杂不必然错误，但应先说明哪个最小对照就能区分“声学因素分离”与“焦虑/熟悉度等个体差异”的解释，后续扩展才有依据。

### 推荐方向

加强生成阶段的实质性自我检验：

1. 对核心事实检查已见 reference 是否真能支持；不支持则删除事实断言、补检索，或明确改为待检验假设。
2. 明确最接近的已知研究做了什么、proposal 新增哪一个可检验贡献；不能靠“换对象 + 多指标”或“首次”字样完成 novelty 论证。
3. 给出最强的替代解释，以及区分两者的最小研究。核心检验与可选扩展分开；样本量、资源和效果数字没有依据时不能装成已验证事实。

这不是给最终文案加免责声明。ECV 应纠正引用后重新论证研究缺口；音乐方案应吸收被遗漏的焦虑差异证据，检查原来的 double-dissociation 解释是否仍成立；纵向方案应把方法前提写清楚。若检查改变了核心假设，就允许重构 idea，而非受“stick to the spirit of the original idea”约束只润色。

最小候选先作用于当前 reflection 和七字段内的生成要求，不急于新增 claim schema、额外 judge 或另一套系统。最终质量评判关注已纠正的实质错误、新贡献和可区分性，不能只统计更少的绝对化词语。

## 执行顺序与暂缓事项

1. **先验证第 1 项**：机会最具体，音乐案例有明确漏文献，且大部分 corpus 本来很小。
2. 第 2 项单独比较，主要解决多主题或方法需求未进入 query 的情况。
3. 第 3 项在固定证据条件下比较生成指导，判断究竟是否改善 idea，而非仅改善措辞。

不推荐立即换 E5/hybrid：021 已记录 formal holdout 方向不稳定、E5 未达到 promotion margin。历史结论不证明 BM25 最好，但足以反对在没有新问题证据时重跑旧路线。也不推荐先做多 agent brainstorm/best-of-N：同一个证据盲区可能被复制多次；当前更应解决缺失的关键输入和未检查的主张。

上述步骤是候选验证顺序，不是已批准的实施计划。生产 retrieval/prompt 变化与后续生成对照分别需要批准；本轮没有修改它们。新增排序候选批量计算按既有 Windows 拓扑执行；本轮只是读取现有排名。

## 可复核索引

- 035 最终 idea：`artifacts/ideation-runs/<run_id>/artifacts/ideas/000000/idea.json`。
- 每次 query、完整候选排名与释放结果：同 run 的 `artifacts/operations/*/attempts/*/{audit,payload}.json`。
- 语料来源：同 run `request.json` 指向的 approved corpus；未从 target 或其 citation contexts 构造优化建议。
- slot 4：`6561a348-7f82-4fd2-b323-911aaca48d16`。
- slot 8：`46b4b22a-1a30-43d1-98e6-ca0f164c9d57`。
- slot 9：`875f41ac-d7bd-46b7-ab5c-24bcbd91a124`。
- slot 12：`5dc54c4b-4fe2-47f3-8b20-3bebac096c32`。
- 历史排序裁决：[ticket 021](../wayfinder/ideation-pipeline/tickets/021-choose-and-calibrate-local-ranking.md) 的 Resolution。

只读核对和源码检查能支持“问题存在、值得验证”，不能证明新策略会更优。优化后实证结果留待另行批准的对照。
