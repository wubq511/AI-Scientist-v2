# Local-ranking atomic Pro/max calibration protocol v2.0

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Frozen before Pro/max model output**

## 1. Escalation reason and fixed boundary

Pro/high r1 mirror stability was `20/24`, below the frozen `22/24` minimum, with 48/48 first-valid calls. The approved
ladder therefore permits one fresh `opencode-go/deepseek-v4-pro/max` calibration.

Relative to [Pro/high protocol v2.0](local-ranking-atomic-pro-high-calibration-protocol-v2.0.md), the only semantic execution
profile change is `reasoning_effort: high → max`. The following remain exact:

- same 24 spent items and mirrored left/right evidence;
- same single-item prompts, rubric and response schema;
- same `max_tokens=16384` ceiling and concurrency 4;
- same first-valid, max-two-attempt, no-error-feedback retry policy;
- same per-replicate `22/24`, pooled `69/72`, and directional >0 gates;
- same r1 → r2 → r3 mathematical early stop;
- all provider responses are fresh; no Pro/high vote or response is reused.

## 2. Frozen identity and budget

- source commit：`b1634a752dace243241a23dae5dd9077843b8032`
- profile manifest：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-001/input/profile-manifest.json`
- profile manifest SHA-256：
  `64075d27eb9bd557abaf59918496976f87a24fb48cf0b70f0bc55855e0a4a503`
- usage snapshot SHA-256：
  `e34924c8bceef06fa7b8049bdc9c6ec88c9b95fea71b300e086e4b29b470e298`
- transport smoke result SHA-256：
  `b57460388033dd6ced38f7f45bb7b175bea6e55d74137ae83faa44fb71c44d9e`
- total budget：144 logical，最多 288 physical；但只先授权执行 r1 的 48 logical calls；
- input root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-001/input`
- output root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/pro-max-calibration-001/output`

调用前 usage snapshot：rolling 16%、weekly 25%、monthly 36%，全部 `ok`。Pro/high 证明 receipt cost 可以为 0
但 quota percentage 仍会上升，因此本次继续逐 call 记录 token/cost，并严格执行 r1 早停以避免无信息调用。

## 3. Six frozen orientation bindings

| replicate | orientation | atomic manifest SHA-256 | transport manifest SHA-256 |
| --- | ---: | --- | --- |
| `r1` | 1 | `b6e1d4a79501f1f08939b8445173146159f21ec79075107372ec722d857c4bb8` | `70f0ccb5bbd36ce2c924738081a333d7a6dbdf94a41905627353f86bbe4727c3` |
| `r1` | 2 | `2c15f94773555da1dd6e531f82ce55b8d6ed9e12108be1fd5a11efe1315a6312` | `1df9aefb6d01c4a944d372f21247e6979c26f184924b4ffb7caa9e489896c4d7` |
| `r2` | 1 | `8cb4ec68286da5afa5d6bf63dd1f3dedcd9af29a84c987b8085901de3a99e64e` | `d0659494fe9f34c7e9737ea236c61554edd1332b7633e02d65810bb8e203c201` |
| `r2` | 2 | `ec405848fe290b1bf944e9c4927ab884dc55518b92cb28ef022c681572f079c6` | `c7d336dd2107c9497ca3f683cf71a941781f9cd5d12f0baf3f4c4e4662d65fdb` |
| `r3` | 1 | `786cf8e75a378b31952697b9fc3652a06201cda25f9a1bb502c72585cfb3988e` | `445d8d0b1484dc7adb2f28d79565c113f6bed3c59fe8eb4ddf0b70457fb62924` |
| `r3` | 2 | `e4a3649f3d2801f6428f741c55434f395034bb1d8ca0e1fa78d6698361aa96b8` | `30aee3846bb950f2a7fe093cbce1af590ffd08bb0f2c355cd4252884798abe5c` |

## 4. Decision rule

Execute `r1/o1` then `r1/o2`, validate the pair with `atomic_pair`, and stop immediately if stable `<22/24` or stable
directional count is zero. Only a passing r1 permits r2; only a still-mathematically-possible pooled result permits r3.

If Pro/max qualifies, it is the DeepSeek profile allowed to proceed to a separate fresh Kimi K3 panel qualification. If
Pro/max fails, the DeepSeek ladder is exhausted under this atomic contract; do not add extra replicates or repeat r1. The next
decision must examine rubric/data ambiguity or another model family, not keep sampling until PASS.
