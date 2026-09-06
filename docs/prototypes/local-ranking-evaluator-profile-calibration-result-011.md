# Local-ranking evaluator profile calibration result 011

Run date: 2026-09-01（Asia/Shanghai）
Status: **FAIL — Flash/high SSE is mechanically reliable but mirror stability is below the frozen gates**

适用协议：
[profile calibration v1.1](local-ranking-evaluator-profile-calibration-protocol-v1.1.md)。本 attempt 使用
`opencode-go/deepseek-v4-flash` / `high`，每组两个 orientations 并行、最大并发 2，三个 replicates 依次执行。

## 1. Mechanical execution

六路 SSE 均为 HTTP 200、normal `stop`、收到 `[DONE]` 与 billing sidecar，并各自通过原
`operational_judge finalize` 的 24/24 closed-schema、coverage、bundle binding 和 visible-evidence 校验。
六个 provider response IDs 全部不同；没有 retry、repair 或复用旧 output。

| replicate | orientation | provider response ID | total tokens | trace SHA-256 |
| --- | ---: | --- | ---: | --- |
| 1 | 1 | `router-c1fc7ab1a8760970cf41a98e89d2ff18` | 83,016 | `434f69112b1bc0667cb59aa26970f5612cb0c09718073bb4a7e1de234b439e64` |
| 1 | 2 | `router-a43eb996c137ab1745ac4a6190aa0611` | 88,495 | `6321cfadcdcf35ffd905753255d1034ccac8117d61d27cb6b2fc5801cb831a37` |
| 2 | 1 | `router-f9f0810284249faa3508e59bd3f292fa` | 95,527 | `30a7d6bdacc24c44e9222882a9b63462ce3b5e8a96aeb2da580907c6490abb87` |
| 2 | 2 | `router-dac3f58ba5ce23a49ab7413f10d338d9` | 85,982 | `20404808a1d266d6c7b64630c0435e1c830e34813a70c56f6c23c6cfdbf9b320` |
| 3 | 1 | `router-858eb38774b00e73867ddb7391eb92f2` | 105,753 | `9cae15bd44004a170b786e7987497b7729b7f879480cc816f83bc47586f6c369` |
| 3 | 2 | `router-76b08fb23bed9bd2b9942b258733ca8d` | 91,914 | `2c2bd395647c5cc240edccbab41fcfa5a71b421f15f72d5cd61ae52f02d38c69` |

Aggregate result SHA-256：
`4524b8887c53e29245e970c9cf8b03cb4c1f64fe85395f61be4a524e4e444a37`。

## 2. Frozen aggregate decision

| replicate | mirror stable | minimum 22/24 | original 23/24 gate |
| --- | ---: | --- | --- |
| 1 | 22/24 | PASS | FAIL |
| 2 | 20/24 | FAIL | FAIL |
| 3 | 22/24 | PASS | FAIL |

Pooled mirror stability 为 `64/72`，低于 `69/72`；达到 `23/24` 的组数为 `0/3`，低于要求的 `2/3`。
因此三个 aggregate gates 全部失败，聚合器给出 `status=fail`、`decision=escalate_profile`。

## 3. Interpretation and next step

这次把 transport failure 与 evaluator semantic instability 分开了：SSE transport 和本地 validator 六路全过，
但同一匿名任务在左右镜像交换后不能稳定复现 judgment。重复三次并没有把 qualification-007 的 22/24 解释成
一次偶然波动，反而得到 22、20、22。因此 `Flash/high` 不批准为正式双模型 panel evaluator。

按已批准的顺序，下一步是 `deepseek-v4-flash/max` 的独立 SSE synthetic qualification；只有 synthetic 的
profile identity、stream receipt 和 1/1 semantic validator 全部 PASS，才允许为该 profile 生成新的 full-size
bundles/requests 并开始三组校准。不得把本 attempt 的六份 output 复用为 panel votes。

本 attempt 没有打开 private mapping、没有运行 candidate reducer、没有计算 BM25/E5 winner，也没有进入
Downstream Experiment。
