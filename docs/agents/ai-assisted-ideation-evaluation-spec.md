# AI 辅助 Ideation 评审规格

日期：2026-09-05  
状态：ready-for-agent（Robert 已批准方向、三票拆分与验收边界；本规格不授权付费调用或生产晋升）  
实现拆分：[评审工作地图](../wayfinder/ai-assisted-ideation-evaluation/map.md)

## Problem Statement

Robert 缺乏跨领域科研经验，却被现行协议要求对每条 finalized idea 填写七项定性 verdict 与 rationale，并完成 Prompt Profile 的成对盲评。这既耗时，也不能因为有人签字就获得领域专家级的判断质量。当前比较矩阵在 slot 1 的 Evaluation Artifact 编写环节停止。

现有工具能组装 Evaluation Brief、核验结构和证据链接，但不能核验科学结论。把表单交给一个模型自动填完再署名 Robert，会混淆判断来源，也无法解决模型的臆测、偏好与共同错误。

目标是在保留有用的证据检查和诚实结论边界的前提下，让 AI 承担资料对照和科研判断的初评与复核，让 Robert 决定是否补证据、接受工程建议或保持未决。优先复用现有 evaluation 与 comparison 工作流，不建立新平台。

## Solution

一次单条 idea 评审交付一张中文证据卡：七项建议判断、来源位置、简短理由、关键假设和未解决问题。每项判断区分已有证据、评审推断和材料缺失；允许弃权，不强制把未知塞进既有 verdict 枚举。

两位来自不同模型家族的评审读取相同的冻结材料，独立初评，不看对方输出。程序核验来源身份、引用片段和结构，汇总一致与分歧。分歧直接保留为未决，不增加第三模型投票。成对比较在同一材料范围内进行 A/B 与 B/A 换位检查，只接受跨评审、跨位置一致的方向。

Robert 收到推荐决定及其证据，不再逐项起草七维表单。没有领域专家校准时，结果明确属于 AI 生成的、限定材料范围的工程评估证据，不宣称专家科研真值或官方 IdeaBench 分数。

## User Stories

1. As a project owner, I want AI 完成七维资料对照, so that 我不必假装具备各领域专家经验。
2. As a project owner, I want 一张中文证据卡, so that 我能迅速理解结论与疑点。
3. As a project owner, I want 只对需要行动的问题作决定, so that 人工时间花在补证据与工程取舍上。
4. As a project owner, I want 区分 AI 判断与我的审批, so that 评估来源不会被错误署名。
5. As a project owner, I want 不懂的专业问题可以保持未决, so that 流程不强迫我猜答案。
6. As a project owner, I want 保留当前已完成的 sealed run, so that 评审改造不浪费生成成本。
7. As an evaluator, I want 只读取已 seal 的 idea, so that Target Paper 不会反馈进生成过程。
8. As an evaluator, I want 同时获得 idea、Workshop、允许的引用片段与 Target Comparator, so that 判断有明确的对照对象。
9. As an evaluator, I want 知道每种材料是否完整, so that 缺少审计记录不会被误判为没有泄漏。
10. As an evaluator, I want 区分问题、研究对象与研究目的, so that problem-space match 不退化为关键词匹配。
11. As an evaluator, I want 明确 target contribution overlap 没有单向优劣, so that 不会把越像 target 当作越好。
12. As an evaluator, I want 相对 novelty 只对给定 target 作判断, so that 不会声称全领域首次。
13. As an evaluator, I want 检查方法是否能回答研究问题, so that 长篇方法名称不能替代 soundness。
14. As an evaluator, I want 对专业可行性条件标注未知, so that 资料不足不会变成确定错误或确定可行。
15. As an evaluator, I want 对照引用原文和实际论点, so that 挂名引用与真实综合可被区分。
16. As an evaluator, I want 区分 contamination signal 与输入侧 leakage, so that 不会把两个不同问题混为一谈。
17. As an evaluator, I want 允许每个维度单独弃权, so that 一项未知不抹去其他维度的证据。
18. As an operator, I want 两位评审彼此隔离, so that 第二位不会只附和第一位。
19. As an operator, I want 评审材料不包含 Prompt Profile 身份和预期胜者, so that 盲评保持可解释。
20. As an operator, I want 来源中的指令被当作待评数据, so that 文献或 idea 不能指挥评审改判。
21. As an operator, I want 输出逐项回链至材料, so that 可以发现不存在的引用和跨样本串用。
22. As an operator, I want 区分引文存在与语义支持, so that 字符匹配通过不会被当成科学正确。
23. As an operator, I want 两位评审的分歧原样展示, so that 汇总不会掩盖不稳定的测量。
24. As an operator, I want 成对比较交换位置后仍指向同一内容, so that 顺序偏差不能制造 winner。
25. As an operator, I want tie 与无法比较分开, so that 材料不足不会伪装成平局。
26. As an operator, I want 无效响应单独记录, so that 格式修复不会暗中挑选更有利的判断。
27. As an operator, I want 同一份规范支持本地导出与响应导入, so that 不必为每个 provider 新造一套评审工具。
28. As an operator, I want 记录实际模型标识与评审版本, so that 能重放和解释历史结论。
29. As an operator, I want 单条 idea 与成对比较共享证据材料, so that 不重复人工整理和多次摘要。
30. As an operator, I want 已完成但未决的评审允许矩阵继续收集证据, so that 一个未知不会阻断后续所有样本。
31. As an operator, I want 未决状态仍阻止受影响的晋升判断, so that 流程继续不等于质量通过。
32. As a maintainer, I want 保持旧版人工 Evaluation Artifact 可读取, so that 既有证据不会被重写。
33. As a maintainer, I want 生成代码 pin 与评估协议版本分别绑定, so that 增加评审能力不改变被比较的生成过程。
34. As a maintainer, I want 跨版本或混合评审协议的 reduction 被拒绝, so that 结果不会混用不同尺子。
35. As a maintainer, I want 从现有 CLI 与 ingestion/reduction 验证完整行为, so that 测试覆盖真实使用路径。
36. As a project owner, I want 看到一次真实试评的结果与缺陷, so that 验收依据不只是 prompt 文本和绿色测试。
37. As a project owner, I want 评审调用数和费用在执行前明确, so that 时间与预算可控。
38. As a project owner, I want 报告明确哪些质量主张尚未得到验证, so that 不会把小样本 smoke 当作跨领域效果证明。

## Implementation Decisions

### 1. 职责与最小结构

- 复用 post-seal evaluation 的材料组装、验证和 coverage；新增 AI 评审模式与独立版本的评审记录，不另建服务、数据库或 Web UI。
- 只有三个主要职责：材料组装与引用核验、评审输出记录与汇总、comparison 对接。先交付本地导出/导入路径；复用已有可用的 provider transport，不建设通用 provider 平台。
- 当前旧契约规定 Robert 为唯一判分者，尚不能自动消费 AI verdict。实施时先在相应术语、评估约定、Validation Matrix 与 Promotion Proposal 中追加本变更的版本化说明，再接入行为；保留原决策及旧结果，不把历史改写为一直支持 AI。
- 本次只改变 post-seal 的判断来源与流程。生成时使用的 Idea Quality Rubric pin、FinalizeIdea 检查及七字段 idea payload 保持现有语义。

### 2. 最小材料包与信任边界

- 每包仅含完成本任务需要的 Workshop 文本、sealed idea、Declared Grounding、实际释放给生成模型的 Retrieval Segments、Target Comparator，以及可追溯的审计检查结果。直接使用原文，不再引入一个摘要模型。
- 每个片段有包内 source ID、类型、原文及其哈希。run/seal/idea/输入哈希在外层元数据中绑定；评审只看包内匿名标识。哈希和身份由程序提供，不让模型填写或猜测。
- 屏蔽 Prompt Profile、baseline/challenger 映射、成本、运行顺序、操作者期待和其他评审输出。Target Comparator 仅进入 post-seal 评审材料，绝不进入生成 request。
- 审计需报告检查范围及 complete/incomplete；给出可核验的检查结果，不把完整私有路径和标识暴露给评审。缺少审计视图时，leakage_review 弃权；contamination_signal 的 none_found 必须限于实际审查范围。
- 引用校验只证明片段存在于该来源，不证明支持关系。语义支持由独立复核检查；这是剩余不确定性，不新增另一层自动“真值认证”。

### 3. Prompt 契约

使用项目 prompt-engineer 技能编写两种版本化模板：单条七维评审、成对比较。两位评审使用相同模板、相同证据和相同任务，不用“支持者/反对者”人设人为制造分歧。模板采用任务角色，不捏造专家资历；要求简短的可核查理由，不要求展开内部思维链。

模板必须覆盖角色、任务、材料边界、维度定义、弃权条件、输出格式和少量合成边界例。例子只解释判断规则，不能来自当前正式矩阵；不对模型暗示希望某个 Prompt Profile 获胜。

七维的可判定输出沿用现行封闭枚举，另外使用独立 assessment_status 表示 judged 或 insufficient_evidence。后者的 proposed_verdict 必须为空，并说明缺少哪项材料；它不是向生成期 rubric 偷加一个 verdict。

| 维度 | 必须判断什么 | 不能推导什么 |
|---|---|---|
| problem_space_match | 问题、对象、目的是否对应；方法不同本身不等于错配 | 关键词接近即 aligned |
| target_contribution_overlap | 核心贡献 recover、部分重叠或 materially different | 重叠程度是单向的质量排名 |
| relative_novelty | 对给定 target 的实质增量及依据；换术语或加 ML 不自动算增量 | 全领域首次、发表价值或文献穷尽性 |
| feasibility_soundness | 假设、方法与验证计划的逻辑联系、关键资源条件和明显设计缺陷 | 未提供条件即 unsound；写得详细即 sound |
| contamination_signal | 已审查材料中 reference 难以解释的 target 独有命名或原文重合 | none_found 证明没有训练污染 |
| leakage_review | 输入暴露及输出 hygiene 的可追溯审计事实 | 科学内容像 target 即证明泄漏；无日志即 clean |
| grounding_synthesis | 声明文献的证据是否支持论点、是否被实际综合 | 引文存在即 synthesized |

每项输出只保留：assessment_status、proposed_verdict、简短中文 rationale、evidence_refs、关键假设、missing_information。evidence_refs 包含 source ID、原文短片段和它所支持或反驳的 claim。没有可引用材料时允许空引用，但必须弃权或把推断及其依据明确标记；不得凭空引用。无需数字打分、自报置信度或总分。

pair 模板还须区分 field-appropriate computational method 与无问题依据的 ML intrusion，输出 overall preference、domain-method fit 和 ML intrusion 的原有 categorical 语义及理由。不同研究方法本身不能决定 winner。

### 4. 作者、版本与可用状态

- AI 评审记录的作者类型固定为 AI，保留每位 evaluator 的真实 provider、model ID、prompt version、输入包哈希、响应哈希与时间；作者身份由调用/导入层记录。仅凭用户粘贴且无法认证的响应，明确标记 user-supplied provenance，不声称程序亲自执行过该模型。
- authored_by、validated_by 与 accepted_by 表示不同职责。程序验证者标记实际工具；Robert 的确认只记作操作者决定，不改写 AI 作者。
- 评审响应、修订版与汇总结果保留各自版本，沿用既有 write-once/supersedes 习惯，不添加签名服务或新证据链。
- coverage 区分 missing、invalid、complete_resolved、complete_unresolved。complete_unresolved 表示两位评审已完成但有弃权/冲突，不等于缺失，也不等于质量通过。invalid 或缺失不能伪装成 complete_unresolved。
- 返回的 recommendation 是可解释的建议，不是可直接执行的 Promotion Gate 指令。

### 5. 独立复核与汇总

- 两位评审必须来自不同 model families，分别在隔离上下文中接收相同材料，不共享其他评审答案。具体模型通过执行配置指定，记录 exact model ID；不在本规格里凭未经验证的榜单选择模型，也不悄悄 fallback。
- 单条 idea：每位评审各一次，覆盖七维。两方在某维度均 judged、同 verdict，且引用检查通过，才输出该维度的共识建议；否则该维度 unresolved，并列双方理由。即使一致，也保留原始理由，供核查共同错误。
- 两方一致认为是坏结果，同样是 resolved 的负面判断，必须保留并进入既有质量底线；一致不等于正面。
- 成对比较：两位评审各在独立上下文完成 A/B、B/A 两个方向，共四次。程序将显示侧映射回匿名内容后归并。只有四个有效判断指向同一内容、或者四个都为 tie，才产生稳定结果；其他情况为 incomparable，记录分歧原因。单维度质量下限独立生效，不能被整体偏好覆盖。
- 不设第三模型，不进行多轮辩论，不自动补文献。不为获得可用 winner 重跑有效结果。格式无效时显式返回失败并保留原始响应；修复调用若有需要必须计数、记录，并且不能仅因 verdict 不理想触发。
- 有效但未决的单条评审允许 ingestion 记录评审完成，后续 slot 可继续；未决项影响相应 pair/gate，不能因为继续生成而被当成通过。需要专家时只提出具体疑问，不把招募专家设为本功能验收前提。

### 6. 小规模验证与费用

- 编码验收先使用 deterministic provider fixtures 跑通整条链路；这验证软件契约，不验证模型判断质量。
- 真实试评只需要一个单条 idea 包和一个独立合成 pair：单条两次、pair 四次，基础调用总数为六。当前 slot 1 可以作为只读单条诊断演示，但不能被用来调整 prompt 后再声称该样本是未见测试。用于改变 prompt 的材料以后都标为 development-only。
- 合成 pair 包含材料内部可证伪的明显缺陷；其“预期错误”来自给定事实的矛盾，不来自另一位 AI 的喜好。八类必要边界在离线 fixtures 中覆盖：正常、缺材料、伪造引用、引文存在但不支持、注入文本、合法领域方法/无依据 ML framing、换位改判、无效响应。
- 报告引用有效数/总数、预设缺陷检出数/总数、已知误报、弃权数、模型分歧、换位结果、物理调用次数、延迟、费用；有实际人工复核才记耗时，否则明确未测。没有专家标签不计算所谓科研准确率。
- 六次 smoke 的完成条件是：真实响应被解析与回链、已知明显缺陷未被一致漏过、故意缺失的证据未被冒充存在、换位不制造稳定假 winner。失败则回到对应 prompt 或材料修正，保留失败记录；不能用 skill 示例中的通用“80% accuracy”替代本任务的验收。
- 这组 smoke 只证明流程可用和最低检错行为，不证明双模型优于单模型，也不证明跨领域效果。利用已取得的两份单条输出比较第一评审遗漏与复核增量，无需额外单模型实验。
- 如以后按当前八条 idea、四个 pair 全量执行，两位单条评审需 16 次，成对复核需 16 次，基础总计 32 次，额外修复另计。该调用数必须向 Robert 明示，不能宣传成“每条只调用一次”。
- 所有真实调用由执行 agent 在使用现有可用 provider 前给出 exact model 配置、token 上界、基础调用数、可能修复次数、预计/最坏费用和出站材料范围。评审费用单独列项，并按已批准 stage 预算口径合并展示，不改生成 run 的历史实际成本，不默认把旧预算当作新评审授权。
- 编码无需新凭据：导出/导入与 fixtures 可独立完成。真实调用需要已有账号与明确的费用/数据出站授权；本规格本身不包含凭据，不授权付费。

### 7. 当前矩阵接入与 pin 兼容

- 当前主分支因新技能提交已超过生成 execution-code pin。仅修改 post-seal 评估不应迫使 slot 1 作废，也不能把 pin 静默改成当前 HEAD。
- 推荐以原生成 pin 的独立 clean worktree 执行剩余生成；以实现后的工作区进行 post-seal AI 评估。生成端始终由原版 production admission 和冻结命令进入。评估代码、模板、模型与汇总规则另行形成 evaluation protocol manifest，并由新版 comparison 读取时绑定。
- 两个工作区通过保持原相对布局、按哈希核验的私有材料副本交接，沿用现有文件工具；不新增网络同步服务。比较 package 的权威写入必须串行：生成前同步已验证最新 ledger/预约状态，生成后归还新增证据并核验，再评估/ingest/记账；不得让两个工作区各自累计费用或并行推进同一 slot。实现者在 migration rehearsal 中证明复制/路径布局被现有验证器接受，不能用关闭检查或修改冻结命令来通过。
- 新版 ingestion 保持 Run Seal、admission generation commit、输入、export 与 matrix identity 校验，显式新增 AI Evaluation Artifact coverage 分支。原生成 runner 继续消费已核验的串行 ledger；不得伪造旧版人工 artifact 来满足旧 coverage。
- 在现有 Promotion Proposal 追加评审修订：替换判分者和未决处理，保留原 3 胜 0 负、domain-method fit、质量底线及成本/回归阈值。所有八条结果统一使用修订后同一评估协议，不混用人工版与 AI 版。
- 该矩阵须标记“首条输出产生后的评估协议修订”，用于限定范围的内部工程判断，不能宣传为事前冻结的纯人工盲评或独立科研验证。协议选择不得利用已知 winner，当前 slot 1 的诊断暴露如实披露。只有显式批准该修订后，相关结果才能被相应版本的 Promotion Gate 消费；旧 Gate 对 AI 记录继续拒绝。
- 保留旧封存物料、旧 verdict 和原始成本；不做破坏性重置、不自动重跑 slot 1、不揭盲来决定改规则。真实迁移与后续生成仍由执行 agent 按现有操作授权执行，本设计会话不操作。
- 此票只交付迁移工具、离线 rehearsal 和具体执行手册，不要求完成剩余七个付费生成才算编码完成。若工作区布局验证失败，报告具体失败并保留现有状态，不把“重新 pin 并重跑”当自动 fallback。

## Testing Decisions

- Robert 已确认两个最高实用验收边界：现有 evaluation CLI 的 assemble/AI 评审导出与导入/validate/coverage；现有 comparison 的 ingestion、pair packet、verdict、reduction。无需新增测试专用 public API。
- 好的测试观察真实输入到持久化结果、失败状态和后续可用行为。复用现有 sealed run、损坏链、覆盖率与 CLI fixtures，以及 synthetic sealed runs 经 ingestion 到 reduction 的集成先例；不按私有函数数量堆测试。
- 单条端到端：sealed run 经材料包、响应导入、引用核验到证据卡和 v2 记录；旧版人工 artifact 仍可读取。跨 run 引用、hash 错配、假引文、材料内指令、错误枚举和缺少作者来源应产生明确失败，不能落盘为已验证结果。
- 复核端到端：一致正面、一致负面、单维分歧、部分/全部弃权、缺失响应和格式失败均有明确结果；有效未决与无效响应的 coverage 不混淆。
- pair/reducer：A/B 与 B/A 还原到内容，稳定 winner/tie、换位翻转、跨模型冲突、packet 错配、混合 evaluation protocol、质量底线违规均验证。有效未决允许继续收集下一 slot，但不能生成通过质量门槛的结论。
- 迁移 rehearsal：在临时隔离工作区中复现旧 generation commit + 新 evaluator、私有材料往返、单一 ledger 归还与 slot 顺序；证明旧 sealed idea/原 pin/冻结命令字节未变。当前主工作区的漂移仍被原 generation runner 拒绝。
- 改动后运行相关 CLI 与 comparison 聚焦集，再运行仓库全量 pytest；使用仓库 Python 3.13 reference 环境。无需引入 GPU、本地大模型或 Windows bulk matrix。若实际改变跨平台 scorer、模型或语义，按原项目约定另行处理。
- 提交真实 smoke 报告是运行验收；没有费用/凭据授权时，准确标记“离线编码验收通过，真实模型效果未验收”，不得宣称全功能效果验证完成。

## Out of Scope

- 新 Web UI、专家管理平台、agent 辩论框架、第三模型仲裁、active learning 系统。
- 数值总分、官方 IdeaBench 指标、全领域创新性证明或无需专家即可保证科学正确的主张。
- 新增生成 provider、修改生成 prompt、生成期 rubric、检索范围、BFTS、实验、绘图、写作或下游评审。
- 重做全部现有矩阵、自动发布/推送、自动晋升 Prompt Profile、取消既有费用确认。
- 在编码会话中擅自购买服务、读取/展示凭据、追加真实调用或自行联系领域专家。

## Further Notes

- 本规格继承 Robert 的要求：简约但不偷懒，只做必要且产生有用证据的工作。两位独立评审与换位检查用于暴露不同类型的失效；它们不能排除共同错误，所以输出必须保留证据与未决状态。
- 与旧规则的冲突是明确的：旧 Evaluation Artifact 由 Robert 唯一编写，本设计改为可标识作者来源的 AI 评审；这属于版本化评估决策，不是 bugfix。落实时通过追加修订保留历史。
- 本项目已有 local-ranking 的同类经验：负责人不应被当成跨领域专家，异家族模型仍可能判出相反 winner。此处沿用证据回链、隔离与诚实未决，舍弃完整专家校准项目和大型候选矩阵。
- 方法依据：[LLM judge 的偏差](https://arxiv.org/abs/2306.05685)、[科研 idea 自评失效](https://arxiv.org/abs/2409.04109)、[异家族 panel 的有限域研究](https://arxiv.org/abs/2404.18796)。这些研究支持检查偏差的必要性，不证明本方案在当前八领域已经有效。
- Prompt 模板和结构化 schema 由第一张票使用 prompt-engineer 技能交付；本会话只设计，不生成或实施 runtime 代码。后续 agent 不应把模板写完当成模型效果已验证。
