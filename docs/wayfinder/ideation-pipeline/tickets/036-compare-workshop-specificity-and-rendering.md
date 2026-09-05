---
title: Compare Workshop specificity and rendering
type: prototype
status: open
assignee: null
blocked_by:
  - 029-define-the-optimization-promotion-gate.md
---

## Question

在相同的跨领域 canary、冻结的 Target Paper 与 Target Reference Corpus、derivation source boundary、ideation 配置、validation 和 idea-quality rubric 下，README-compatible 的 `Title`、`Keywords`、`TL;DR`、`Abstract` baseline 与 `B-guarded` problem-envelope 或其他字段变体相比，哪一种能提高 target-problem relevance 和 idea quality，同时不增加 answer leakage、不缩窄 multiple-answer breadth，也不降低可复现性？比较必须记录输入、Workshop、private provenance、validation、idea outputs、成本与失败；任何改进只有通过 optimization promotion gate 并取得 Robert 批准后才能替换兼容基线。

## Notes

- 2026-08-30 [Define canaries and scale gates](028-define-canaries-and-scale-gates.md) 已定：本票的变体比较裁剪为 **3 case 子集的变体臂**（baseline 臂复用 035 胜方的既有 run），计入 canary 阶段 ¥30 硬上限，位于执行优先队列队尾、预算紧张时最先被截断（见 `docs/agents/canary-and-scale-gates.md` v1.0）。

- 2026-09-06：Robert 已直接指定 `reasoning_effort=max`，035 不再产生 high/max 胜方。本票若后续执行，基线来自相同新 prompt + max 配置下的 Canary 结果；旧 high 结果不自动视为可比基线。本票仍在执行队尾，本决定不启动 Workshop 变体比较。
