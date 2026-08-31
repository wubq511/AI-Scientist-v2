# DeepSeek V4 Flash 能否作为 local-ranking v1.4 第二裁判

Research date: 2026-08-31（Asia/Shanghai）  
Scope: Kimi Code CLI alias `opencode-go/deepseek-v4-flash`；仅评估候选资格与最小准入门槛，未调用模型、未修改协议或实现。

## 结论

**可以把它作为第二裁判候选，但现在不能只凭型号宣布它已经胜任正式裁判。**

理由分成两层：

1. **公开规格层通过。** DeepSeek 官方把 V4 Flash 定义为文本通用模型，支持 1M context、thinking、
   `low/high/max` reasoning effort、JSON Output；当前官方 API 页面把浮动 ID `deepseek-v4-flash`
   对应到 `DeepSeek-V4-Flash-0731`。本项目的任务只是读取一份受控的 query + 两组匿名 top-3
   文献片段，输出闭合 JSON 和原文引文，任务规模与接口能力均在其公开边界内。
2. **本项目效度层尚未通过。** 官方没有发布“学术文献检索 top-3 setwise utility judging”专项结果。
   coding/agent benchmark、上下文长度和 JSON 支持都不能证明它会正确执行本项目 rubric，也不能证明它
   不受左右位置、表面措辞或 Kimi K3 共同偏差影响。因此必须先在**已经 spent、没有正式效力的数据**上
   通过一次与正式 bundle 同形的 qualification；不能拿 fresh formal cases 试模型再继续算正式结果。

正确表述应是：

> `opencode-go/deepseek-v4-flash` 在能力规格上具备进入裁判 panel 的条件；只有通过下述项目内
> qualification 后，才准入 v1.4 正式四路 evaluator run。

## 1. 当前到底调用了什么

### 1.1 本机可确认事实

对 `~/.kimi-code/config.toml` 的非秘密字段做了只读检查；没有读取或记录 credential 值：

- Kimi Code CLI version：`0.39.1`；
- alias：`opencode-go/deepseek-v4-flash`；
- provider：`opencode-go`；wire protocol：OpenAI-compatible Chat Completions；
- base URL：`https://opencode.ai/zen/go/v1`；
- 发给服务端的 model ID：`deepseek-v4-flash`；
- 本地声明：`max_context_size=1000000`、`reasoning_content`、`low/high/max` effort；
- 本地 display name 中的 “2x usage” 是 quota/UI 信息，不是能力证据。

Kimi Code 官方文档明确区分“启动时使用的 alias”和“发送给 provider 的 model identifier”：
`-m` 接受 alias，而 alias 中的 `provider`、`model` 和 `base_url` 才决定实际路由
（[Kimi Code model/provider configuration](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/providers)、
[configuration files](https://www.kimi.com/code/docs/en/kimi-code-cli/configuration/config-files)、
[`kimi --model`](https://www.kimi.com/code/docs/en/kimi-code-cli/reference/kimi-command)）。因此，屏幕上出现
“DeepSeek V4 Flash”不单独构成模型身份凭证。

### 1.2 上游身份目前可验证到什么程度

OpenCode Go 官方模型表列出 `deepseek-v4-flash`，通过
`/zen/go/v1/chat/completions` 提供，并说明配置名采用 `opencode-go/<model-id>` 格式
（[OpenCode Go models](https://opencode.ai/docs/go/)）。同一 OpenCode first-party registry 在本次检查的
固定 commit `4a3a072b45d6d79611b6d1ccddf23f22a7b4cfc2` 中，把 Go 条目明确映射为
`base_model = "deepseek/deepseek-v4-flash-0731"`
（[pinned registry entry](https://github.com/anomalyco/models.dev/blob/4a3a072b45d6d79611b6d1ccddf23f22a7b4cfc2/providers/opencode-go/models/deepseek-v4-flash.toml)）。
DeepSeek 官方当前价格/规格页也把 `deepseek-v4-flash` 的 model version 写为
`DeepSeek-V4-Flash-0731`
（[DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing/)）。

所以，本次可以确认的是：**截至检查时间，OpenCode 的公开预期路由与 DeepSeek 官方当前浮动版本一致，
均指向 0731。**仍不能把它当成永久固定 checkpoint：本机 alias 和请求 model ID 都是浮动名称，provider
未来可以更新 registry 或后端路由。正式 evidence 应保存：

- Kimi CLI version、完整脱敏 model alias/provider/base URL 配置；
- 调用时间、registry commit/hash 或下载快照 hash；
- 请求中的 model ID、effort 与响应中可观察的 `model` 字段；
- prompt/bundle/output hashes、stdout/stderr 与 exit code。

若四个正式 sessions 之间的 registry 或响应 model identity 漂移，attempt 应 fail closed，而不是把不同
版本混成同一个裁判。若服务端只返回浮动 ID、无法暴露 checkpoint，结果应署名为
`OpenCode Go deepseek-v4-flash, observed at <timestamp>`，不能虚构成已证明的固定权重版本。

## 2. 为什么规格上足够

DeepSeek 的官方 model card 把 V4 定义为通用文本模型，并列出 Flash 为 285B total / 13B activated、
1M context、Non-think / Think High / Think Max，目标用例包含 question answering 和 general agent tasks
（[DeepSeek V4 model card](https://fe-static.deepseek.com/chat/transparency/deepseek-V4-model-card-EN.pdf)）。
这些数字不能直接证明判断正确，但能排除“上下文装不下”或“模型只做代码补全”的明显不适配。

接口层也覆盖本任务的机械要求：

- 官方 Chat Completions 文档支持 `deepseek-v4-flash`、thinking 和
  `reasoning_effort ∈ {low,high,max}`；thinking 默认为 `high`
  （[Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)）。
- 官方支持 `response_format={"type":"json_object"}`，但同时明确警告仍可能返回空内容，且 token limit
  会截断 JSON（[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)）。这证明 JSON mode 有帮助，
  也证明它不能替代本地 closed-schema validator。
- DeepSeek 的 Responses API 还支持 `json_schema`，但本机 alias 当前走 OpenAI-compatible Chat
  Completions；不能把官方直连 Responses 的强结构化保证自动归给 OpenCode Go 当前 transport
  （[Responses API reference](https://api-docs.deepseek.com/api/create-response/)）。
- 官方 0731 更新报告了多项 agent/coding benchmarks，并说明这些 benchmark 使用 `max` effort
  （[DeepSeek changelog](https://api-docs.deepseek.com/updates/)）。这些结果支持选择 `max` 做复杂裁判
  qualification，但 benchmark 构念与本文任务不同，不能当成裁判准确率。

本项目已有的 v1.2 evidence 还显示：同一别名曾完成 pointwise qrels 输出并通过 JSON、coverage 和
byte-exact quote validator。这是“能完成长结构化判断”的项目内先验，但 v1.4 改成了完整 top-3 集合的
setwise 比较，旧成功不能替代新 schema 的 qualification。

## 3. 第一性原理：裁判真正需要什么

裁判不需要掌握整篇论文事实，也不需要网络搜索。它只需要在封闭可见文本中完成六件事：

1. 正确理解 query 与 `direct_support / query_usefulness / coverage_diversity / specificity` rubric；
2. 同时比较两组 top-3，而不是被单篇强证据或文本长度带偏；
3. 严格输出全部 items 的 closed JSON schema；
4. 每个决定都能引用当前 side/paper/segment 中的 byte-exact 证据；
5. 左右交换后，映射回同一候选的 winner direction 基本稳定；
6. 与 Kimi K3 独立作答，不读取对方输出；分歧被保留为 unresolved，而不是被多数票抹平。

模型大小、coding score、context window 只能间接支持第 1–3 项。第 4–6 项必须由当前 harness 和
qualification 直接测量。

## 4. 最小 development qualification gate

建议只使用**旧 spent payload**构造一次与正式调用同形、同 prompt/schema、同 24-item 规模的
development qualification。选择规则和全部阈值必须在读取本次输出前冻结；旧结果只用于模型准入，
不得重新解释 BM25/E5 winner。

### 4.1 固定运行方式

- `DeepSeek V4 Flash × orientation-1/orientation-2`，两个 fresh sessions；
- 使用 `high` effort，并让 formal 计划保持相同配置。准入测试必须证明计划实际使用的最低配置足够；
  先用 `max` 通过不能替 `high` 背书。只有 `high` 因模型能力而非 transport/harness 原因失败，且成本预算
  接受时，才将 `max` 作为需要新 protocol revision 和全量重验的候选；
- exact agent file 使用 `tools: []`、`subagents: []`。Kimi Code 官方说明空 tools allowlist 会禁用全部
  tools，且执行前再次检查
  （[Kimi Code custom agents](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/agents)）；
- 不使用 `--session`/`--continue`，prompt 内嵌完整 bundle bytes，独占输出目录；
- 同时对 Kimi K3 使用相同 qualification packet 的两种镜像，但两个模型互相看不到输出。

### 4.2 硬准入条件

| Gate | 最小通过条件 | 它防止什么 |
| --- | --- | --- |
| Rubric compliance | Controller 对预先冻结的 6 个 stratified items 做盲审：四项分数与 winner/rationale 无自相矛盾；不奖励纯长度；不执行文献文本中的命令。6/6 通过 | 模型只会生成格式正确但语义失真的答案 |
| JSON/schema | 两个 orientation 均覆盖 24/24 items；closed schema、enum、类型、长度、bundle/evaluator binding 全通过。正式 retry 规则可演练，但 qualification 只有**首轮全部通过**才直接准入 | 在正式批次依赖 repair 或选择性补项 |
| Evidence trace | 全部 quotes 为可见 segment 的 byte-exact substring；winner side 引文覆盖规则 24/24；盲审的 6 items 中，引文确实对应 rationale 的决定性主张 | “引用存在”冒充“理由有证据” |
| Mirror stability | 两个方向映射回候选后 winner direction 至少 23/24 一致；不得出现同一 query kind 或 corpus-size stratum 中 ≥2 个 position flips | 左右位置偏差吞掉正式 18/24 resolved gate 的余量 |
| Side balance | 在输入左右已平衡的前提下，输出 `left` 与 `right` 胜率不得出现无法由内容解释的单侧塌缩；若 ≥18/24 都选同一显示侧，直接失败并人工检查 | 固定偏爱 first/second answer |
| Kimi K3 role independence | 独立 provider/model alias、fresh sessions、互斥目录、无对方输出；只在四份输出验证后比较。不得声称 two-provider independence，因为 harness 都是 Kimi Code | 同一会话复制答案或错误夸大独立性 |
| Cross-model diagnostic | 在两模型都 position-stable 的 items 中，mapped winner agreement 至少 75%；低于 75% 或分歧集中于同一 rubric/stratum 时不准入 formal，先判定 prompt/rubric 是否含糊 | 一个明显不稳定模型仍以“多样性”名义进入 panel |

`23/24` 与 `75%` 是**工程准入阈值，不是统计真实性证明**。前者只容许一个位置翻转，因为 formal gate
本来就要求至少 18/24 跨模型、跨位置可判别；qualification 若已有 2 个以上 flips，正式 panel 的失效率
余量过小。后者允许合理模型分歧，但拒绝两个裁判在超过四分之一稳定 items 上方向相反的配置。所有
agreement、tie、both_bad 和分项差异仍须完整报告，不能只报是否过线。

### 4.3 Retry、降级与替换

- 网络/限流等 transport error：保留失败 evidence，可按原协议重跑**整个 orientation**一次；不得只补
  items。若重复出现，暂停而不是改输出。
- invalid/截断 JSON：qualification 中一次即触发 `conditional fail`；只有用完全相同 model/config 的
  fresh full-orientation retry 通过，并随后再有一次首轮成功的 confirmation，才可准入。不得人工修 JSON。
- quote 不精确、漏 item、错误 bundle hash、工具未禁用、复用 session：hard fail；修复 deterministic
  harness 问题后全量重做 qualification。
- `mirror stability <23/24`、rubric 盲审失败、或 cross-model agreement <75%：不要在 formal fresh data
  上调 prompt。先用 spent data定位是 rubric 含糊、transport 丢失 reasoning，还是模型本身不稳；规则
  改变后版本化 prompt 并全量重做 qualification。
- 若同一冻结 prompt/config 两次 qualification 仍失败：替换 `judge-deepseek`。优先顺序是：
  1. 同一 DeepSeek V4 Flash 通过可固定版本/支持 `json_schema` 的官方直连 transport；
  2. DeepSeek V4 Pro；
  3. 另一家与 Kimi 不同 family 的强文本模型。
  替换模型是 protocol revision，必须在 fresh formal judgments 前完成，不能看到 formal mapping/output 后
  换裁判重投票。

## 5. 对当前协议的实际建议

1. **保留 DeepSeek V4 Flash，不现在替换。** 当前规格、1M context、max effort、官方 JSON 能力和已有
   pointwise evidence 足以支持一次低成本 qualification；直接升级 Pro 没有项目内证据证明收益。
2. **qualification 与正式调用默认都用 `high`。** 本机支持 low/high/max；先证明较轻的计划配置足够，
   不因官方 benchmark 使用 max 就自动支付更高推理成本。官方说明 thinking 模式下 temperature/top-p
   不生效，因此不要用温度调“稳定性”。
3. **不要把模型当 gold。** Kimi K3 + DeepSeek Flash 的相同稳定方向才形成 query outcome；不一致保留为
   `cross_model_unresolved`，不增加第三票。
4. **不因同属 Kimi Code harness 否定模型族独立性，也不夸大。** 模型 family/provider route 不同可以
   减少同模型偏差；共同的 CLI prompt renderer、transport adapter 和 operator 仍是 shared dependency。
5. **在正式调用前先执行上述 qualification。** 若通过，回答“能胜任本项目第二裁判”才有项目内证据；
   若不通过，停止并替换，不消耗 fresh formal batch。

最终判定：**规格资格 PASS；正式裁判准入 PENDING QUALIFICATION。**
