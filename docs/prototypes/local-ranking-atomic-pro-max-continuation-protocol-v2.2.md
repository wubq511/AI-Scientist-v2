# Local-ranking atomic Pro/max mechanical continuation protocol v2.2

Protocol date: 2026-09-02（Asia/Shanghai）  
Status: **Frozen before `call-021` attempt 3**

## 1. Authorized scope

This protocol applies the [bounded-retry correction v2.2](local-ranking-atomic-bounded-retry-contract-v2.2.md) to the
incomplete `pro-max-calibration-002/r1/o1`. It authorizes exactly:

1. preserve and revalidate the 23 existing first-valid calls;
2. preserve `call-021` attempts 1/2 as invalid;
3. execute only `call-021` attempt 3 with identical request bytes;
4. stop immediately if attempt 3 is valid; otherwise execute attempt 4 once;
5. if attempt 4 is also invalid, stop as `incomplete` and do not raise the ceiling again;
6. if valid, resolve one combined orientation trace from all old and new attempts.

No other r1/o1 call may be re-executed. The controller must not use winner, scores, private reasoning, or future mirror
agreement to decide retry. Orientation 2 has not run, so no mirror outcome exists at amendment time.

## 2. Frozen old evidence

- original profile manifest SHA-256：
  `61dc61072b0358de75d1a01fb2a3151ffad73ea9ba88369aa050ce0122b61c5f`
- r1/o1 atomic manifest SHA-256：
  `38e0ee8d68cb660aff45510abf375fbae62bc43e14dd6c609c14a29ac40eaf5d`
- original run-result SHA-256：
  `73b08939d22a602762f697332638874fb49d2aa8e6ce745df555536576b5ac85`
- original round-1 SHA-256：
  `1f69326a43a869cec50890bc0b605d80b958c6f22d4e148dfbf5d52fad9a746f`
- original round-2 SHA-256：
  `774cfde214ba6d65ef8563ad4424d56698b1420d602270fd87fd546e7d97a383`
- `call-021` attempt-1 SHA-256：
  `1eecb472d9d19a244a2cb451188dbc180b3ed1e6240cb8cd3cc36d095649fc90`
- `call-021` attempt-2 SHA-256：
  `a6375e28a5dd24c545e719c5ef4109354c3c0c17d67cf602a682bf28b4c20879`
- both attempts request SHA-256：
  `0916cfca6f3fca8a00c48c9b728af82e9395a98187cf673d511bc0b204998cdb`
- provider response IDs：attempt 1 `chatcmpl-RcRvEOYKJzo40IbwYWcQu7zO`；attempt 2
  `chatcmpl-RCrOMjl96Mf47vCQjUOG1GWI`。

Old run-result and rounds remain immutable. The combined v2.2 resolver reads their attempt artifacts; it does not replace
the v2.1 run-result.

## 3. Frozen amended execution identity

- correction source commit：`510f6c2a73b88b749dd422fc48fc388f6d5b085e`
- amended profile manifest：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-002/input/continuation-v2.2/profile-manifest.json`
- amended profile manifest SHA-256：
  `e69acf34a7214c3f763780a6d67b90bbd99f116fa3977d3aed3cb9a4128b8b7f`
- amended usage snapshot SHA-256：
  `960d1600220860282bbaa65ae43ec6db88e0500eac5714efc0b4c3ca5c6baaf9`
- amended r1/o1 transport manifest SHA-256：
  `f819b9248dc1b2404bbdf950025bd2b45e553438397eb5c3dc3dc5672f8716d4`
- amended request SHA-256 for `call-021`：
  `0916cfca6f3fca8a00c48c9b728af82e9395a98187cf673d511bc0b204998cdb`，与旧 request exact identical；
- model/profile：`opencode-go/deepseek-v4-pro/max`；
- `max_tokens=16384`，no error feedback；
- usage before continuation：rolling 9%、weekly 32%、monthly 40%，均为 `ok`。

The amended profile binds all future orientations to max four attempts and a theoretical 576-call ceiling. For this
continuation, only one or two new physical calls are authorized.

## 4. Remaining transport bindings

The atomic manifests stay unchanged; only transport manifests encode the amended retry policy.

| replicate | orientation | atomic manifest SHA-256 | amended transport manifest SHA-256 |
| --- | ---: | --- | --- |
| `r1` | 1 | `38e0ee8d68cb660aff45510abf375fbae62bc43e14dd6c609c14a29ac40eaf5d` | `f819b9248dc1b2404bbdf950025bd2b45e553438397eb5c3dc3dc5672f8716d4` |
| `r1` | 2 | `336be1a8c23295159d63212981d4bdbf86f63dacfb91e0a173e7a5c377ec3b0c` | `b14d880aa5cc52facce38504cc52f3d5fe0ec3c01a99623d247e9352b6dae0e1` |
| `r2` | 1 | `50d552b3a5170d60d1fc7659acec5bc1d356ba1b9b86b77109a53d31d45b14fd` | `d3c68c472021939d8f1982bc38a3f7622b5e466e1539cc54644dbfce4a2b0446` |
| `r2` | 2 | `90f1656dd4dcf76467ab8d79c6b8ae4d3be43811e93d777dd5b58383cd93cc6f` | `342422f821d0ebc1ebd53dc6d0a498f2c5d83807255dd8b34102f1cedea4a4be` |
| `r3` | 1 | `b07e944a928149b968274ea8eb19c8fa56ff2d124b2e416fc90fd4b8f3ceff87` | `38b2900b5709102f213bf89787e39575d04ab0ad315b8400568a26d4bf81ca91` |
| `r3` | 2 | `b1db744636494bc530e8a3d72b8fb8db1b305e0a95731f3baf58db2bcc0149d9` | `c572aae8fa425e386e1e23cffb1d3f560f6d2f5c8c71b04600e0a607d2162f5c` |

## 5. Acceptance and next step

The combined resolver must prove consecutive attempts 1..N, first-valid selection, no retry after valid, exact manifest /
prompt / request / response / receipt bindings, and globally unique provider response IDs. A valid combined trace then permits
fresh r1/o2. Only the mirror pair result may decide whether r2 is allowed.

