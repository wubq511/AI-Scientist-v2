# Local-ranking atomic transport smoke protocol v2.0

Protocol date: 2026-09-01（Asia/Shanghai）  
Status: **Frozen before live output**

## 1. 目的与非目的

本 smoke 只回答一个问题：OpenCode Go 的 `deepseek-v4-pro/high` 是否能在当前 adapter 下稳定承载 4 个并发、
single-item、JSON-object SSE calls，并为每个 call 留下可验证且互不复用的 provider receipt。

它不判断文献质量，不选择 BM25/E5，不校准 mirror stability，也不把 synthetic probe answer 计入任何 semantic
gate。Probe exact answer 只是证明 JSON body 没有串题；它不能证明模型具备裁判能力。

## 2. 冻结输入与执行身份

- source commit：`23cb14d95522f9c751bf57418461c4b8d1f6bb6f`
- adapter：`prototypes.local_ranking.atomic_opencode_go`
- endpoint：`POST https://opencode.ai/zen/go/v1/chat/completions`
- provider：`opencode-go`
- model：`deepseek-v4-pro`
- reasoning effort：`high`
- response format：`json_object`
- transport：SSE stream
- `max_tokens` ceiling：`16384`
- call count：4
- max concurrency：4
- 每个 smoke call 在本 attempt 中恰好调用一次；不做单 call retry。
- preparation root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/transport-smoke-001/input`
- output root：
  `artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/transport-smoke-001/output`

Preparation manifest SHA-256：
`89a6d0da77f56e8318041dfd32e8f937345214b65da86041ca0cf73908c0ab51`

| call | prompt SHA-256 | request SHA-256 |
| --- | --- | --- |
| `smoke-001` | `db8d3ec39f74bfb6723b74312a26969095ab312ecd499bb668e730934b84176b` | `92ecbb26f3c8dbab74e0a6c07db048b1f13f6b043b8e46db0c81e3e3da8bd562` |
| `smoke-002` | `1ada2e69a5f16ae26cee681b56d76e8c1bc58111c89090e9dcd0e7768de90741` | `302414c1a944219cf54fc41b9e73bf52aa89a7e9aa8eae318277ed0c6443f0f9` |
| `smoke-003` | `81c00001e19bf44c2868bc2d84f9065660b4b78160a2ad8338432f2e2b8f9bdc` | `14b5de37fa9a5972842bb6a455dc7784b2f7bbe4e8c821e5279c0d37d0cf8e18` |
| `smoke-004` | `085f8c7f0449bfcc2b2eaeaf78341375b65fad4cc729e5a55eab82111dbe4017` | `3ca97f6b469c24cc3ceb3b4677c26efea08b6bde7dfd1e2b7059157c7cf8bee7` |

## 3. 调用前检查

1. 工作树必须 clean，HEAD 必须包含 source commit；
2. 重新计算 preparation manifest 与四个 prompt/request hashes，任何 mismatch 均不调用；
3. 通过 read-only provider usage/quota endpoint 记录调用前 snapshot，不打印或保存 API key；
4. API key 只从 `OPENCODE_GO_API_KEY` 或本机 Kimi config 读取，不进入仓库、artifact 或日志；
5. 当前 provider model list 必须仍包含 `deepseek-v4-pro`。这一项只防止调用已下线模型，不是额外的模型效果门槛。

## 4. PASS / FAIL

Concurrency 4 PASS 当且仅当：

- 4/4 calls 均 HTTP 200、`text/event-stream`、恰好一个 normal terminal chunk 和 `[DONE]`；
- 4/4 content 均为 exact closed JSON：`{"probe_id":"smoke-NNN","status":"ok"}`；
- 4/4 receipts 均 canonical、write-once，绑定 exact preparation/prompt/request/response hashes；
- requested model/effort 与 returned model identity 一致；
- 4 个 provider response IDs 全部非空且唯一；
- usage、cost、timestamps、safe response headers 和 raw SSE 均保留，实际值只报告，不另设无科学必要的阈值。

任何一项不满足，本 attempt 为 transport FAIL，不解释为 DeepSeek 的文献判断失败。不得只补跑失败的一个 probe
然后拼成 PASS。若失败原因支持降低并发，创建全新的 `transport-smoke-002`，保持 model/effort/prompt/token ceiling
不变，把 concurrency 降为 2；仍失败再以新 attempt 降为 1。不得为了得到 PASS 反复运行同一档。

## 5. 执行命令

```bash
python -m prototypes.local_ranking.atomic_opencode_go run-smoke \
  --preparation-root artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/transport-smoke-001/input \
  --output-root artifacts/local-ranking-prototype/atomic-evaluator-v2/attempts/transport-smoke-001/output \
  --kimi-config <local-kimi-config-path>
```

输出目录是 write-once。若命令启动后产生任何文件，不得覆盖原目录；后续尝试必须使用新的 attempt ID。

## 6. 后续边界

Smoke PASS 只把 semantic scheduler 的并发上限冻结为 4。正式 Pro/high calibration 仍需另建 live execution
manifest，明确 144 logical calls、最多 288 physical attempts、实际 quota/call budget、六个 orientation manifests
及早停状态机。Smoke 本身不授权把 144 calls 静默扩大为更多重跑。
