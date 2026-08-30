# Local ranking Windows dense smoke

Run date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本次只验证 frozen dense runtime 能否在 Windows CPU reference environment 中安装、离线加载、确定性打分并满足已批准的 complexity gates；输入是 tracked diagnostic fixture，不是正式 relevance evidence，不能据此选择 ranker。

## 结论

Pinned `intfloat/e5-small-v2` Windows CPU FP32 preflight 通过。三个独立 attempt 中，BM25、E5 dense 与 BM25+E5 RRF 的全部 canonical payload SHA-256 完全一致；E5 的 worst observed cold/warm/build/RSS、model bytes 与 isolated-environment bytes 均低于 protocol v1.0 gate。第三个 attempt 使用 evidence-hardening harness，三条 candidate 的 direct/conservative resource verdict 均为 `pass`。

这不解除正式比较的输入 gate。第三个 attempt 使用 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`local_files_only=True` 与 Python socket deny guard；独立 probe 已得到 typed `NETWORK_ACCESS_DENIED`。该组合覆盖当前 Python/Transformers transport surface，但不是 Windows Firewall 级隔离。RRF 的 gate 使用两个 source metrics 加 fusion timing 的 conservative composition，并明确记录 measurement mode，不冒充同进程实测。

## Frozen identity

- Source commit: `fdffb46c5acd8151b33fe3ed1c1abc2aea5dd8e9`
- Source ZIP SHA-256: `0e38584fa8dcefece134f66b80ec302c82542cac853fe642029ffa4bb9491936`
- Windows lock SHA-256: `6ad4e9f0a5aa690345edf349fc6d983dd31dd452220c10e80b39e6a269a302dd`
- Python: `3.13.7`; platform: Windows AMD64; CPU execution only; one thread; FP32
- Model revision: `ffb93f3bd4047442299a41ebb6fa998a38507c52`
- Weight SHA-256: `45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1`
- Six-file model manifest SHA-256: `a0459c80016d083d853c3c3d44c46754b793b005a8a84cca5e1fc2eb3f03bb04`
- Attempt 01 protocol/summary SHA-256: `c34fc4de8cb5cd37e9ec070d26ec606a18a2c8269c9d0bf8f21f14e421399280` / `cbcede1bb226c6c95167e40ef53554b3e08cc1c8cc704753faaff6c8f80c1053`
- Attempt 02 protocol/summary SHA-256: `f23f5b0f65f380d8d788812723112caa39ce3990f77c9e66ee76bf8a7f0b7969` / `f933d929766129cfe66921de3b2bb8759dfa9e9895704b6ffe6ab3c229cd1d85`
- Evidence-hardening source commit / ZIP SHA-256: `d0650023c4c06084e04761036ad3f40616dc6e24` / `56ef8dc79ca32dd7d7b2abee41112717d20cf696cdd1018aeb944d42b60487b4`
- Attempt 03 protocol/environment/summary SHA-256: `b6238c1737d436635bb8a043fdbccb7bf96abe6d043c87aba545704882bdb6ce` / `f49e0edfe16c9820fd375e34b76603464efaddd7a7a8c38458810a870ce8f314` / `f580491491d14ec896e2f13f53f0a4cfa4af4894fa218c4300c85c01fe40375d`

Diagnostic runs 的 working root 不是 Git worktree，因此 raw summary 的 `git.commit/clean` 为 `null`；source identity 由 commit archive 与 ZIP hash 共同锚定。正式 development/holdout 仍由 harness 强制 clean Git worktree，不能沿用此诊断例外。

## Gate evidence

下表取两次 attempt 的 worst observed E5 数值：

| Gate | Observed | Limit | Verdict |
| --- | ---: | ---: | --- |
| Cold-start p95 | 8.786 s | 15 s | pass |
| Warm-query p95 | 29.641 ms | 1 s | pass |
| Corpus representation build | 0.193 s | 60 s | pass |
| Peak RSS | 422,768,640 bytes | 4 GiB | pass |
| Pinned model files | 134,410,262 bytes | 256 MiB | pass |
| Isolated environment | 836,643,909 bytes | 3 GiB | pass |

Windows host 在运行时记录为 16 physical / 16 logical CPUs、33,820,106,752 bytes RAM；没有记录 hostname、用户名、IP 或 SSH identity。两次 attempt 都运行 5 个 fresh-process cold preflights 与每 query 30 个 warm repetitions。

## Determinism evidence

三个独立 attempt 的 payload hashes 逐 candidate、逐 query 完全一致：

| Candidate | `fixture-broad` | `fixture-focused` |
| --- | --- | --- |
| `bm25-v1` | `be2c4411573e32c76110507346b745b2861fe766ad24a688889f252c2b2f50be` | `eb931979954e89e626eaadb7bdbc239da4d54a76ea1bd6dac09a6449d935db42` |
| `dense-e5-v1` | `be2c4411573e32c76110507346b745b2861fe766ad24a688889f252c2b2f50be` | `330203a278acadb3c2c3e3bf5ea19c30755ebfa6a5c9badbec95e4917c236999` |
| `rrf-bm25-dense-v1` | `be2c4411573e32c76110507346b745b2861fe766ad24a688889f252c2b2f50be` | `eb931979954e89e626eaadb7bdbc239da4d54a76ea1bd6dac09a6449d935db42` |

第三个 attempt 与前两个 attempt 的全部 hashes 也一致。Fixture 中 E5 的 relevance 指标略高于 BM25，但样本只有一个人工构造 case、两条 query；这只是 loader/scorer smoke，不满足 blind qrels、strata 或 promotion rule，必须忽略其 winner 含义。

Attempt 03 直接记录了 Windows lock SHA-256 `6ad4e9f0a5aa690345edf349fc6d983dd31dd452220c10e80b39e6a269a302dd`、40 个 installed distributions、environment/model bytes 与 network policy。E5 direct gate 为 cold p95 5.298 s、warm p95 28.195 ms、build 0.180 s、peak RSS 423,174,144 bytes；RRF conservative composition 为 cold p95 5.487 s、warm p95 28.290 ms、build 0.180 s、peak RSS 449,605,632 bytes，均为 `pass`。

## Remaining gates

1. 上游先生成至少 12 个合法的 Approved Workshop + Approved Target Reference Corpus case bundles，随后才能冻结 24 queries 与 blind qrels。
2. Formal split 必须在 clean Git worktree 运行；诊断 workspace 的 archive identity 不能替代该 hard gate。
3. Finalists 冻结后执行 Windows 10 次 fresh-process replay；只有 dense 进入 finalists 时，才在 Mac 安装 neural stack并做三次 cross-platform observable replay，当前不把计算负担移回 Mac。
