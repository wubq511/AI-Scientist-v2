# 本地文献排序比较协议 v1.3：Windows CPU 线程数执行补充

状态：2026-08-31 approved overlay。Robert 明确授权充分利用 Windows 设备的 CPU
算力；Codex 依据冻结 development input 上的隔离比较选择后续执行参数。本文件只覆盖
[v1.1 主协议](local-literature-ranking-comparison-protocol.md)的 Windows CPU `thread_count`
执行参数，不改变 scorer、字段、qrels、metrics、promotion margin、resource gate、output budget
或 holdout sealing；[v1.2](local-literature-ranking-comparison-protocol-v1.2.md) 与
[v1.2.1](local-literature-ranking-comparison-protocol-v1.2.1.md) 的 AI-qrels 约束继续生效。

## 1. 要解决的问题

Stage A 的 1-thread reference run 表明，E5 的真正瓶颈是 corpus embedding，而不是 SSH、文件
传输或 model cold start。每套 comparison 为同一个 E5 candidate 做 5 次 cold preflight 和 1 次
score，1-thread 下 corpus build 总时长约 61 秒，最大单 case 约 26.7 秒。后续 Stage B、budget
calibration 和 finalist replay 若继续固定单线程，会浪费 Windows 的 16 logical CPUs，但不会增加
relevance 证据质量。

## 2. 冻结比较

比较只改变 `runtime.thread_count ∈ {1, 4, 8, 16}`；以下内容完全相同：

- clean commit `2c1b332aafba13a43b921902f3413a8e9ae641dc`；
- Python 3.13.7、Windows x86_64 dependency lock、CPU FP32、offline/network deny；
- development input、judge-A qrels、pinned `intfloat/e5-small-v2` model bytes；
- 5 次 fresh-process cold、每 query 30 次 warm、同一 output budget；
- 12 条 development queries 的 canonical paper/segment payload。

| Threads | Cold p95 | Corpus build total | Max case build | Warm p95 | Peak RSS | Gate |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 5.546 s | 60.948 s | 26.746 s | 58.4 ms | 474,853,376 B | pass |
| 4 | 5.499 s | 16.539 s | 7.322 s | 22.8 ms | 489,861,120 B | pass |
| 8 | 5.241 s | 9.331 s | 4.065 s | 17.5 ms | 501,432,320 B | pass |
| 16 | 5.253 s | 7.863 s | 3.162 s | 23.8 ms | 509,685,760 B | pass |

四档的 12/12 canonical payload hashes 完全相同。相对 1-thread，16-thread 将 corpus build
total 缩短 `7.75x`、最大 case build 缩短 `8.46x`；8-thread 的 warm p95 最低，但 16-thread
仍只有 23.8 ms，远低于 1 秒 gate，而本轮 formal evidence 的墙钟主要由重复 corpus build
决定。

## 3. 决策

1. Stage B、development output-budget calibration 与 Windows finalist replay 使用
   `thread_count=16`，并在每个 `environment.json` 中记录；所有横向 relevance arms 必须使用
   同一值。
2. 1-thread CPU FP32 路径继续保留并已经通过全部 complexity gates；它是 portability/fallback
   evidence，不要求为已完成的 Stage A relevance 重新计算。
3. 8-thread 结果保留为 latency-sensitive deployment 候选，但本 ticket 不据 development probe
   锁定 production serving 参数。Production implementation 仍需单独授权。
4. 不引入 GPU、XPU、MPS、DirectML、新依赖或近似检索；本补充仍是 portable CPU FP32 路线。
5. 本轮不新增“score once, evaluate three qrels”的 replay 语义。虽然 worker 不读取 qrels，Stage A
   也已证明三套 payload 相同，但 16-thread 已把剩余重复成本降到可接受范围；为一次性 prototype
   增加新 evidence schema/validator 的维护和错误风险高于节省的几分钟。三套 qrels 继续独立运行，
   以保留最直接的 sensitivity evidence。

## 4. Fail-closed 条件

- 任一 16-thread arm 出现 canonical payload drift、非确定性、resource gate failure、fallback 或
  环境差异，立即停止该 attempt；不得自动降线程后继续写进同一 evidence root。
- 新 attempt 必须来自包含本 overlay 和当前 harness 的 clean commit；不得热补丁旧 Windows checkout。
- Holdout 在 Stage B、budget、finalists 和参数冻结前继续 sealed。

原始 thread probe 位于 gitignored private evidence；tracked 结论和 hashes 见
[development comparison result](local-literature-ranking-comparison-result.md)。
