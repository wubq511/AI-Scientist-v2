---
title: Define the minimal runtime dependency contract
type: grilling
status: open
assignee: null
blocked_by: []
---

## Question

ideation-only runtime 应声明哪些依赖——裁剪 `requirements.txt` 还是另建独立的最小 requirements 文件？为保证可复现性是否锁定版本？未声明的（`requests`）、未使用的（`token_tracker.py` 里的 `tiktoken` import）和 downstream-only 的包分别如何处理，使环境保持最小且不破坏仓库中保留的代码？
