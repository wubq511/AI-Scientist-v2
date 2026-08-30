# Validation Matrix

版本:v1.0(2026-08-30,经 ticket [Define the validation and test matrix](../wayfinder/ideation-pipeline/tickets/027-define-the-validation-and-test-matrix.md) 由 Robert 批准)

本文档是 ideation-only pipeline 的系统级验证矩阵:定义哪些检查存在、各自证明什么、什么证据算通过。它受版本治理——任何修订 = 新版本 + Robert 批准(012);优化类修订必须携带证据并过 promotion gate(029)。

## 定位与边界

- 矩阵对既有 runtime gate(018/019/020/022/023/024/025/026/038 各契约已定的 preflight、finalization gate、audit release gate 等)只做**索引**:引用原契约,不重开决策。矩阵新定义的是**开发期测试层**:用确定性测试证明这些 gate 真的实现了。
- 矩阵只定「检查的存在性与证据标准」,不定「何时运行」:canary 选择与扩量节奏归 028,优化晋升归 029,交付顺序归 030,Evaluation Artifact 字段 schema 归 037。这些 ticket 以行 ID 引用本矩阵。
- 测试归属:每个实现 ticket 交付其触及契约对应的矩阵行测试;每次 commit 必须通过已存在行的验证(AGENTS.md:never bypass failed checks)。

## 结构与读法

九层行分组:unit / contract / integration / replay / leakage / isolation / fault-injection / minimal-environment / qualitative。每行五列:

1. **检查项**:具体验什么;
2. **证明目标**:该行支撑的可信性主张;
3. **契约锚点**:决策来源( ticket 编号),索引行指向原契约;
4. **运行时机与消费者**:dev-time(pytest)/ preflight / runtime / post-seal / gate-time(028/029/030);
5. **通过证据**:什么 artifact 证明该行通过(留存纪律见末节)。

行 ID 稳定:`VM-<层>-<序号>`(contract 层按契约编号,如 `VM-CONTRACT-020-03`);一经分配不重用、不复用。

## 阈值与规则版本治理

018/019/026 委托本矩阵固化的阈值、模式列表与 fixtures,按三类处理:

- **版本化规则集**:每组阈值/模式/fixture 是 versioned tracked file,随实现 ticket 落地(025/034 先例),Run Specification pin 其版本。修订 = 新版本 + Robert 批准;经验性收紧必须携带证据并过 029。「不得在单个 case 上临时调整」对所有规则集成立。
- **契约可推导值(本版直接固化)**:payload hygiene 模式列表从 023/024 的标识符格式推导(`case_id` 形、run root 路径、SHA-256 hex、内部标识符模式);Workshop 泄漏比较源 = 014 审定的 answer-bearing 清单(`abstract_summary`、target identifiers、target-authored `contexts`、methods/designs/results/conclusions)。
- **calibration-pending(保守初始值 + 待校准标记)**:Workshop n-gram overlap 阈值、run 内去重阈值、corpus rule thresholds。本矩阵定义其正负例 fixture 结构,任何修订可在同一 fixture 上回归;初始值宁可偏严(误拒可在 post-seal 证据中显现),收紧走 Evidence Feedback Loop。

## 矩阵

### unit 层

纯确定性模块的 golden/边界测试。全部无网络、无模型、无时钟依赖;模板 = 021 原型现有 19 项测试。

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-UNIT-01 | 文本归一化:golden tokens、重复词保留、非 string 拒绝、fail-closed 错误码 | 归一化行为确定且可回归 | 020, 018 | dev-time;全部 gate | pytest pass |
| VM-UNIT-02 | canonical bytes 构造:UTF-8/NFC/sorted keys/compact/LF/末尾单 newline;duplicate keys/NaN/Infinity 拒绝;timestamp 格式 | 全项目 canonical JSON 契约 | 023 | dev-time | pytest pass |
| VM-UNIT-03 | event hash 计算与 prev 链;断链检测 | Evidence Chain 完整性原语正确 | 023 | dev-time | pytest pass |
| VM-UNIT-04 | 封闭 schema 校验器:unknown type/field、`additionalProperties` 全拒 | schema fail-closed 原语 | 023, 019, 018 | dev-time | pytest pass |
| VM-UNIT-05 | ranking 与 payload 构造:确定性排序、稳定 tie-break、payload allowlist、payload SHA-256 | retrieval 确定性原语 | 020 | dev-time | pytest pass |
| VM-UNIT-06 | versioned 价格表计价:按 attempt 开始时段;缺失/hash 不符 fail closed | 计价确定且不可静默失效 | 024, 022 | dev-time | pytest pass |
| VM-UNIT-07 | failure taxonomy 查表:封闭枚举、suspend/terminal 二值 | 失败分级是查表非临场判断 | 025 | dev-time | pytest pass |

### contract 层

按契约分组的负向「拒绝即通过」测试 + 正向 golden。

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-CONTRACT-018-01 | Workshop validator 正向 golden:合法 Workshop 通过两层 gate | Approved Workshop 准入可实现 | 018 | dev-time | pytest pass + fixture |
| VM-CONTRACT-018-02 | Workshop validator 负向:schema/编码/hash 违规;`paperId`/DOI/URL/exact title 命中;对 014 比较源的 exact/normalized/n-gram 泄漏正例必拒;无静默回退 | 泄漏与畸形输入必被 fail-closed 拦截 | 018, 007, 014 | dev-time;028 | pytest pass + rejected fixture 记录 |
| VM-CONTRACT-019-01 | corpus validator 负向:error 级清单逐条(schema/mapping/membership/identity/title/content 一致性/known-bad 值/provenance 缺口/hash mismatch/quarantined 字段) | corpus 验收覆盖全部 fail-closed 条款 | 019, 016, 033 | dev-time;028 | pytest pass + validation-report fixture |
| VM-CONTRACT-019-02 | corpus validator 正向 golden bundle;validator 不自动改写 canonical corpus | 合法 bundle 可通过且不可被静默改写 | 019 | dev-time | pytest pass + bundle hash |
| VM-CONTRACT-020-01 | retriever input 校验:恰好 `{"query": 非空 string}`;unknown field/类型/trim 空/超长拒绝,无静默改写 | 模型输入边界封闭 | 020 | dev-time | pytest pass |
| VM-CONTRACT-020-02 | scope binding:模型/query/tool call 不能选择、覆盖、切换 corpus | 检索边界不可逾越 | 020 | dev-time;028 | pytest pass |
| VM-CONTRACT-020-03 | eligibility:`derived_text`/`contexts`/`intents`/hidden text 等排除;无 eligible content 的 record 不成结果;全空 ≠ 合法 empty | 模型只见 source-faithful 证据 | 020, 033 | dev-time | pytest pass |
| VM-CONTRACT-020-04 | audit release gate:audit event 未持久化+校验则 payload 不释放;对模型仅暴露 `INVALID_QUERY`/`QUERY_TOO_LONG` | 证据先于释放;失败词汇封闭 | 020 | dev-time | pytest pass |
| VM-CONTRACT-022-01 | adapter allowlist:任意 model/base URL/`extra_body`/未知参数透传拒绝;禁 temperature/top_p/penalties/seed;SDK implicit retries off | provider transport 边界封闭 | 022 | dev-time | pytest pass |
| VM-CONTRACT-022-02 | provider-success 判定:required fields/model 精确匹配/`finish_reason=stop`/content 非空/usage invariants/无意外 tool calls | 假成功不可伪装 | 022, 031 | dev-time | pytest pass |
| VM-CONTRACT-022-03 | 封闭 16 枚举 failure taxonomy 逐条触发(stub transport);retry 规则:≤2 attempts、仅指定枚举重试一次、`timeout_ambiguous` 不重试 | 失败分类与重试行为逐条可证 | 022, 025 | dev-time | pytest pass |
| VM-CONTRACT-023-01 | run root exclusive-create;path 校验拒绝 absolute/`.`/`..`/backslash/symlink/escape | run 状态边界封闭 | 023 | dev-time | pytest pass |
| VM-CONTRACT-023-02 | corrupt 判定清单:缺失/hash mismatch/断链/非法 event;corrupt 禁止 repair/resume/seal/export/replay | 损坏可判定且后果封闭 | 023 | dev-time | pytest pass |
| VM-CONTRACT-023-03 | sanitized release gate:positive allowlist 构造;forbidden key/path/credential-pattern/target-identifier scans;幂等(byte-identical 或失败) | 可提交产物必脱敏 | 023, 010 | dev-time;030 | pytest pass + sanitized fixture |
| VM-CONTRACT-024-01 | 准入清单式导入守卫:传递闭包、双层清单(`ai_scientist.*` 精确清单 + 第三方 top-level 包),新增模块/依赖不更新清单即 fail(024 委托本矩阵的 pytest 占位落地于此) | 最小运行面被显式锁定 | 024, 034 | dev-time;全部 gate | pytest pass |
| VM-CONTRACT-024-02 | preflight 九步逐步 fail-closed fixtures;非交互环境 stdin 非 `yes` 即拒绝 | 入口准逐步可证、无 fallback | 024 | dev-time | pytest pass |
| VM-CONTRACT-024-03 | FinalizeIdea 结构校验:封闭两键 `{"idea","grounding"}`、七字段、类型、非空;违规 = Model-Fixable Error | 提交入口结构封闭 | 024, 038 | dev-time | pytest pass |
| VM-CONTRACT-025-01 | Model-Fixable Error 五类统一回灌(parse/未知 action/参数非法/结构违规/retriever 双码),无静默 break 或 print-only | 可修复错误必然可见可修 | 025 | dev-time | pytest pass |
| VM-CONTRACT-025-02 | finalization gate 固定优先级:hygiene → 结构 → grounding → 去重;每轮只报一个;terminal 条件不被 model-fixable 掩盖 | gate 行为顺序确定 | 025, 038 | dev-time | pytest pass |
| VM-CONTRACT-026-01 | Declared Grounding 三码(`INVALID_GROUNDING`/`EMPTY_GROUNDING`/`UNRETRIEVED_PAPER`)与 per-generation eligibility | 说谎检测确定且可回灌 | 026, 038 | dev-time | pytest pass |
| VM-CONTRACT-026-02 | payload hygiene scan:模式命中即 terminal;run 内去重近重复 = model-fixable | Idea Leakage 防御纵深生效 | 026 | dev-time;028 | pytest pass + 扫描记录 |

### integration 层

deterministic stub model(脚本化 action 序列)驱动完整 run;零网络、零费用。

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-INTEGRATION-01 | happy path:preflight → retrieval → FinalizeIdea → seal;断言 event 序列合法、hash chain 连续、Terminal Outcome = `success` | 各契约组合后整圈可运行 | 011, 023, 024, 025 | dev-time;028, 030 | pytest pass + run evidence fixture |
| VM-INTEGRATION-02 | Model-Fixable 回灌剧本:stub 故意犯错(结构违规、`UNRETRIEVED_PAPER`)再修复;断言回灌计入 reflection 轮次且最终 finalize | 错误回灌在整圈中行为正确 | 025, 038 | dev-time | pytest pass + run evidence fixture |
| VM-INTEGRATION-03 | terminal 剧本:hygiene 命中 → `failed`;run 级 backstop(全程无非空 Retrieval Result)→ `failed` | terminal 路径在整圈中封闭 | 025, 026 | dev-time | pytest pass + run evidence fixture |

### replay 层

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-REPLAY-01 | recorded provider responses 重放 → 相同 canonical artifacts/hashes(transport record/replay stub) | run 结果可复现 | 011, 022 | dev-time;030 | pytest pass + 双侧 hash 比对 |
| VM-REPLAY-02 | corpus 同输入重建 → 相同 bundle SHA-256 | 语料构建确定 | 019 | dev-time;028 | pytest pass + bundle hash |
| VM-REPLAY-03 | 同 pinned corpus + 同 normalized query 重复检索 → 相同有序 payload 与 SHA-256 | 检索确定 | 020 | dev-time | pytest pass + payload hash |
| VM-REPLAY-04 | 中断后 approved resume 继续 → 与无中断 run 的 final Evidence Chain 等价(与 VM-FAULT-02 互补) | resume 不改变可复现性 | 023, 025 | dev-time;030 | pytest pass + chain 比对 |

### leakage 层

横切层,聚合既有泄漏义务;通过证据统一为版本化扫描报告 + rejected cases 记录。

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-LEAKAGE-01 | Workshop 泄漏 gates:对 014 比较源的 exact/normalized substring/substantive n-gram(阈值 calibration-pending,版本化) | Workshop 不暴露 held-out 贡献与身份 | 018, 007, 014 | preflight(workshop 准入);028 | 扫描报告 + rejected drafts 记录 |
| VM-LEAKAGE-02 | payload hygiene scan:模式列表由 023/024 标识符格式推导,版本化;命中即 terminal | Idea Leakage 可机检 | 026, 023, 024 | runtime(finalization gate);028 | 扫描记录 + terminal event |
| VM-LEAKAGE-03 | sanitized release gate scans:forbidden key/path/credential-pattern/target-identifier | 进 Git 的产物无私有信息 | 023, 010 | dev-time;030 | 扫描报告 |
| VM-LEAKAGE-04 | quarantine 校验:`contexts`/`intents` 等辅助字段不进入 corpus model-eligible 区 | 路由元数据不泄漏进检索 | 033, 019 | preflight(corpus 准入);028 | validation report |

### isolation 层

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-ISOLATION-01 | cross-run guards 负向集:跨 run 读/写尝试;他 run 内容即使 hash 匹配也拒绝;exclusive-create 冲突;错 `run_id` resume;`latest`/glob 拒绝 | Run Isolation 不可被绕过 | 023, 011 | dev-time;028 | pytest pass |
| VM-ISOLATION-02 | path/symlink 攻击集:absolute/`..`/backslash/symlink escape 全拒 | 文件系统边界封闭 | 023 | dev-time | pytest pass |
| VM-ISOLATION-03 | 候选隔离惯例(021 模板):隔离 worker、immutable attempt、attempt 重跑失败而非覆盖 | 比较与运行证据互不污染 | 021, 023 | dev-time | pytest pass |

### fault-injection 层

本矩阵新定义的层;全部经 stub/可控环境注入,不动真 provider、不产生费用。

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-FAULT-01 | transport 故障:16 枚举逐条 stub 注入;验证 retry disposition 与 suspend/terminal 分级查表一致 | provider 故障行为逐条可证 | 022, 025 | dev-time | pytest pass + 注入记录 |
| VM-FAULT-02 | 中断注入:SIGINT/SIGTERM 在承诺路径各阶段(staging → fsync → hash → rename → event append);验证无半承诺痕迹 + resume 等价(接 VM-REPLAY-04) | 原子性承诺与 resume 在崩溃下成立 | 025, 023 | dev-time;030 | pytest pass + 注入记录 |
| VM-FAULT-03 | 存储故障:写入失败/磁盘满模拟 → suspend 分级,不判 terminal | 环境类失败不误杀 run | 025 | dev-time | pytest pass |
| VM-FAULT-04 | 模型行为故障整圈:malformed/unknown action、grounding 说谎、hygiene 命中、重复 idea,在完整 control loop 中验证终点行为 | 对抗性/畸形模型行为终点封闭 | 025, 026, 038 | dev-time | pytest pass + run evidence fixture |

### minimal-environment 层

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-ENV-01 | 干净 venv + 034 最小 requirements + Python 3.13 reference:全 pytest + preflight 级 smoke 必过(阻断) | 最小声明依赖即完整运行面 | 034, 017 | dev-time;028, 030 | pytest pass + 环境 lock |
| VM-ENV-02 | Python 3.12/3.14 compatibility candidates:同套验证运行并记录结果,不阻断 | 兼容性有证据但不扩大承诺 | AGENTS.md | dev-time | 记录摘要 |
| VM-ENV-03 | portable CPU FP32 reference path 必需;accelerator 缺席不影响任何行 | 无隐藏硬件依赖 | 013 | dev-time | pytest pass(CPU-only 环境) |
| VM-ENV-04 | 主开发平台(macOS arm64)必过;其余平台候选记录;evidence run 记 exact patch + per-platform dependency lock | 平台声明有证据边界 | AGENTS.md, 021 | dev-time;030 | 平台锁 + 运行摘要 |

### qualitative 层

| 行 ID | 检查项 | 证明目标 | 契约锚点 | 运行时机与消费者 | 通过证据 |
|---|---|---|---|---|---|
| VM-QUAL-01 | canary 阶段每个产生 final idea 的 sealed run 链接 schema 合法的 Evaluation Artifact(机检:链接存在 + schema 合法;schema 归 037) | 定性判断被强制留证 | 032, 037 | post-seal;028 | manifest 链接 + schema 校验 |

判分本身是 Robert 的定性行为,永不机检;LLM judge 属独立决策,另票批准(032)。

## 证据留存纪律

沿用 010:原始测试输出、日志、注入记录、扫描报告本地保留(gitignored,immutable);repo 只提交脱敏摘要——命令、commit SHA、pass/fail、相关 hash。永不记录 secrets。gate-time 消费(028/029/030)引用脱敏摘要 + 本地原始证据路径。
