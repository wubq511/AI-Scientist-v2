---
title: Define the minimal runtime dependency contract
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

ideation-only runtime 应声明哪些依赖——裁剪 `requirements.txt` 还是另建独立的最小 requirements 文件？为保证可复现性是否锁定版本？未声明的（`requests`）、未使用的（`token_tracker.py` 里的 `tiktoken` import）和 downstream-only 的包分别如何处理，使环境保持最小且不破坏仓库中保留的代码？

## Resolution

Robert 批准以下 runtime dependency contract。本 ticket 只定规则与流程；确切包清单由实现 ticket 随代码落地生成，任何新增依赖须指出其使用方代码并经 Robert 批准（021 的 dense 结果走自己的 evidence gate 追加）。

### 三文件结构

- `requirements.txt` 是本 fork 的 canonical runtime 契约，只含最小集；现有 29 包全量清单改名 `requirements-upstream.txt` 保留，文件头注明其仅服务仓库中保留的 legacy/downstream 代码、非本 fork runtime 契约。
- `black`、`pytest` 等开发验证工具独立为 `requirements-dev.txt`，不进 runtime 文件，也不归入 upstream 文件。

### 锁定策略

三个文件均精确 pin（`==`）。hash 级防篡改不由声明层承担；evidence run 按 `AGENTS.md` 现行规定记录 per-platform dependency lock。

### 收录规则

最小集 = 新 ideation 路径的实际 import 闭包。每个包必须能指出使用方代码；使用方消失，依赖即删。现存三个包按此规则处置：

- `requests`：声明进最小集并标注 transitional，随 Semantic Scholar 调用被 Scoped Literature Retriever 替换时与代码一同移除。
- `tiktoken`：不声明；后续实现删除 `token_tracker.py` 中的未使用 import。token 记账以 provider usage 为准，不做本地 tokenizer 估算。
- downstream-only 包：整体留在 `requirements-upstream.txt`，永不进入最小集；边界由已决的准入清单式导入守卫 fail-closed 执行（见 [Define the safe ideation entry](024-define-the-safe-ideation-entry.md)）。

本 ticket 只形成决策；未修改 `requirements.txt` 或任何 runtime code。
