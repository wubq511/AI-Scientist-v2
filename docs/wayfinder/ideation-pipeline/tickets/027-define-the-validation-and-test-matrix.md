---
title: Define the validation and test matrix
type: grilling
status: closed
assignee: Robert
blocked_by:
  - 018-define-the-workshop-file-contract.md
  - 020-define-the-scoped-retriever-contract.md
  - 022-define-the-deepseek-adapter-contract.md
  - 023-define-run-identity-and-evidence-layout.md
  - 024-define-the-safe-ideation-entry.md
  - 025-define-control-flow-failures-and-resume.md
  - 026-define-the-idea-quality-rubric.md
---

## Question

Which unit, contract, integration, replay, leakage, isolation, fault-injection, minimal-environment, and qualitative checks must pass, and what evidence proves each gate?

## Resolution

2026-08-30 经 grilling 两轮十一题由 Robert 批准。完整矩阵落为独立契约文档 [docs/agents/validation-matrix.md](../../agents/validation-matrix.md)(v1.0),本 Resolution 只记决策摘要。

### 定位与边界

- 矩阵 = 既有 runtime gate 的**索引**(引用原契约,不重开决策)+ **开发期测试层**的新定义(用确定性测试证明各 gate 真的实现)。
- 矩阵只定检查的存在性与证据标准:canary 节奏归 028、优化晋升归 029、交付顺序归 030、Evaluation Artifact schema 归 037;这些 ticket 以稳定行 ID(`VM-<层>-<序号>`)引用矩阵行。
- 测试归属:每个实现 ticket 交付其触及契约的矩阵行测试;每次 commit 必须通过已存在行。

### 结构

九层行分组(unit / contract / integration / replay / leakage / isolation / fault-injection / minimal-environment / qualitative),每行五列:检查项 / 证明目标 / 契约锚点 / 运行时机与消费者 / 通过证据。

### 各层要点

- **unit**:纯确定性模块 golden/边界测试(归一化、canonical bytes、hash chain、schema 校验、ranking/payload、计价、taxonomy 查表),无网络/模型/时钟;模板 = 021 原型现有 19 项测试。
- **contract**:按契约分组的负向「拒绝即通过」+ 正向 golden,覆盖 018/019/020/022/023/024/025/026+038;024 委托的导入守卫 pytest 占位落为 `VM-CONTRACT-024-01`。
- **integration**:deterministic stub model 跑完整 run(happy path / Model-Fixable 回灌剧本 / terminal 剧本),零网络零费用。
- **replay**:recorded transport 重放同 hash;corpus 重建同 SHA-256;同 query 同 payload hash;resume 与无中断 run 的 final chain 等价。
- **leakage**:聚合 018 Workshop 泄漏 gates、026 hygiene 扫描、023 sanitized release scans、033 quarantine 校验;证据 = 版本化扫描报告 + rejected cases。
- **isolation**:023 cross-run 负向测试集 + path/symlink 攻击集 + 021 候选隔离惯例。
- **fault-injection**(本票新定义):四注入面——transport 16 枚举、承诺路径各阶段 SIGINT/SIGTERM、存储故障、完整 loop 模型行为故障;全 stub,不动真 provider。
- **minimal-environment**:干净 venv + 034 最小集 + Python 3.13 reference 必过(阻断);3.12/3.14 记录不阻断;CPU FP32 必需;macOS arm64 主平台必过;evidence run 记 exact patch + 平台锁。
- **qualitative**:索引 032/037;唯一机检行 = canary 阶段 sealed run 的 Evaluation Artifact 链接存在且 schema 合法;判分永不机检。

### 阈值与证据纪律

- 018/019/026 委托的阈值/模式/fixtures 分三类固化:版本化规则集机制(修订 = 新版本 + Robert 批准,经验性收紧过 029);契约可推导值直接固化(hygiene 模式 ← 023/024 标识符格式,leakage 比较源 ← 014 清单);经验性阈值给保守初始值 + calibration-pending 标记 + 正负例 fixture 结构。
- 证据留存沿用 010:原始输出本地保留,repo 只提交脱敏摘要(命令、commit SHA、pass/fail、hash)。

衍生动作:018/019/024/026 追加指向矩阵文档的指针;CONTEXT.md 新增 Validation Matrix 术语。028/029 的 blocked_by 中本票一项随之解除。

本 ticket 只锁定验证矩阵决策;未实现 runtime code、未调用模型、未进入 downstream。
