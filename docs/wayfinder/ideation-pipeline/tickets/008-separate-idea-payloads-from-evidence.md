---
title: Separate idea payloads from evidence
type: grilling
status: closed
assignee: Robert
blocked_by: []
---

## Question

Should provenance and validation fields be inserted into the original idea object?

## Resolution

Keep the original seven-field idea payload for compatibility. Store provenance, validation, run status, and audit information in a separate sidecar or manifest.
