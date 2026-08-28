---
title: Define the minimal runtime dependency contract
type: grilling
status: open
assignee: null
blocked_by: []
---

## Question

Which dependencies does the ideation-only runtime declare — a pruned `requirements.txt` or a separate minimal requirements file — are versions pinned for reproducibility, and how are the undeclared (`requests`), unused (`tiktoken` import in `token_tracker.py`), and downstream-only packages handled so the environment stays minimal without breaking the code that remains in the repo?
