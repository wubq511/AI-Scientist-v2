# Local literature ranking：runtime 与最小 dense model 调研

Research date: 2026-08-30（Asia/Shanghai）

对应 Wayfinder ticket `Choose and calibrate local literature ranking`。本文回答 runtime、Windows Intel GPU 路线和第一轮 `dense_biencoder` 候选的选型问题；结论已吸收到 comparison protocol 与项目治理文档，但不修改 production retriever。

## 结论

1. **第一轮 dense arm 唯一推荐 `intfloat/e5-small-v2`**，固定到 revision `ffb93f3bd4047442299a41ebb6fa998a38507c52`，只加载 `model.safetensors`。它是四个候选中最贴合“英文短 query → passage/segment”这个 asymmetric retrieval 任务的最小模型：33.4M parameters、384 dimensions、512-token 上限、MIT license，并明确定义 `query: ` / `passage: ` 输入格式。
2. **用 `Transformers` 的官方 `AutoTokenizer`/`AutoModel` 路径直接实现 E5 的 documented average pooling**；第一轮不需要把 `sentence-transformers` 加入 runtime dependency。后者可作为 wheel/support 参考，但不是完成这一项 scorer 所必需的依赖。
3. **CPU FP32 是 mandatory reference path，不是永久 accelerator ban。** Arc 140T 所属的 Arrow Lake-H 已在 PyTorch Intel XPU 的 Windows 11 validated-hardware 范围内，但官方仍把 Intel GPU support 标为 `Prototype`。在每次 exhaustive score 3–36 papers 的条件下，先用 CPU 能最干净地归因 scorer 差异；只有 CPU 违反 latency gate 时，才单独验证 XPU/MPS 是否达到 `>=2x` end-to-end speed、无 fallback、canonical payload 与 CPU 完全一致且新增环境成本可接受。
4. **不采用 `torch-directml`。** 最新公开包仍是 2024 年的 pre-release/Public Preview，固定依赖 PyTorch 2.4.1，只提供到 CPython 3.12 的 Windows wheels；DirectML 官方仓库已经进入 maintenance mode。
5. **runtime policy 采用“一个 normative reference runtime + compatibility matrix”。** Reference minor 改为 Python 3.13，当前 protocol patch 固定为两台机器最短共同路径 3.13.7：Windows 已安装，macOS 可由 `uv` 提供相同 patch；当前 PyTorch 明确支持 Windows/macOS Python 3.10–3.14，而 Python 3.13 仍处于 bugfix support，3.11/3.12 已进入 security-only。每次 evidence run 仍须锁 package/wheel hashes、model revision/artifact hashes；3.12/3.14 只作为独立 compatibility candidates，3.11 只保留历史审计证据。

这些是进入 prototype 前的候选与 runtime 建议，不替 Robert 决定 production ranker。

## 研究边界与判定口径

本项目的相关约束是：每个 case 只有 3–36 篇 approved references，全部 candidates 都 exhaustive score-all；ranker 只能读取 normalized query、title 和 eligible source-faithful segments；runtime 必须 local/offline，保留 Python 3.13 CPU FP32 reference path；Windows/macOS 最终 canonical paper/segment order 必须可重放。

本文把三个经常被混淆的概念分开：

- **声明支持**：项目的官方文档、package metadata 或 classifiers 明确列出 Python/OS；
- **wheel 存在**：特定 release 在官方 package index 上确实有对应 ABI/platform artifact；
- **本项目可支持**：完整 dependency resolution、离线加载、模型 forward 和 observable ranking replay 已在该 cell 实测通过。

前两项不自动推出第三项。特别是纯 Python 的 `Transformers`/`sentence-transformers` wheel 存在，不代表 `torch`、`tokenizers`、`safetensors`、NumPy/SciPy/scikit-learn 的整组 native wheels 一定适配所有旧 OS/architecture。

## 1. Python 3.11–3.14 与 Windows/macOS wheel 现实

### 1.1 截至 2026-08-30 的 release snapshot

| Package | Latest release | 官方 Python metadata | 发布物 | 对本项目的含义 |
| --- | --- | --- | --- | --- |
| PyTorch | `torch 2.13.0` | `Requires-Python >=3.10` | 每个 CPython/OS 单独编译的 native wheel | Python minor、OS、CPU architecture 必须逐格确认 |
| Transformers | `5.16.1` | `>=3.10.0`；classifiers 列到 3.14 | `py3-none-any` wheel，12.1 MB | 包自身跨平台；compiled dependencies 仍需确认 |
| Sentence Transformers | `6.0.0` | `>=3.10`；classifiers 明列 3.10–3.13 | `py3-none-any` wheel，739.6 kB | 包自身支持目标三个 minor；完整栈仍受 PyTorch/科学计算依赖约束 |

来源：[PyTorch 2.13.0 PyPI artifacts](https://pypi.org/project/torch/2.13.0/)、[Transformers 5.16.1 package metadata](https://pypi.org/project/transformers/5.16.1/)、[Sentence Transformers 6.0.0 package metadata](https://pypi.org/project/sentence-transformers/6.0.0/)。这三页是发布仓库的 package metadata，不是第三方兼容表。

Transformers 官方安装文档当前写的是 Python 3.10+、PyTorch 2.4+；5.16.1 的 wheel 是 platform-independent，但它依赖 native `tokenizers` 和 `safetensors`。截至本次核验，`tokenizers 0.23.1` 与 `safetensors 0.8.0` 都发布了 Windows x86-64、macOS x86-64、macOS ARM64 的 `cp310-abi3` wheels，因此可供 CPython 3.11–3.14 使用（[Transformers installation](https://huggingface.co/docs/transformers/installation)、[`tokenizers 0.23.1`](https://pypi.org/project/tokenizers/0.23.1/)、[`safetensors 0.8.0`](https://pypi.org/project/safetensors/0.8.0/)）。

Sentence Transformers 6.0.0 直接依赖 PyTorch、Transformers、NumPy、SciPy 和 scikit-learn。它自己的 universal wheel 和 Python classifiers 只能证明顶层 package 声明支持；真正的 CI/preflight 仍必须让 resolver 选出该 Python minor 可用的 native scientific-stack wheels，并禁止 source build 悄悄替代 binary install（[6.0.0 release metadata](https://pypi.org/pypi/sentence-transformers/6.0.0/json)）。这也是第一轮 E5 直接走 Transformers、避免额外引入 Sentence Transformers 的理由之一。

### 1.2 PyTorch 2.13.0 CPU wheel matrix

| Platform | Python 3.11 | Python 3.12 | Python 3.13 | Python 3.14 | 结论 |
| --- | --- | --- | --- | --- | --- |
| Windows x86-64 | `cp311-win_amd64` | `cp312-win_amd64` | `cp313-win_amd64` | `cp314-win_amd64` | 四格都有官方 wheel |
| macOS 14+ ARM64 | `cp311-macosx_14_0_arm64` | `cp312-macosx_14_0_arm64` | `cp313-macosx_14_0_arm64` | `cp314-macosx_14_0_arm64` | 四格都有官方 wheel |
| macOS Intel x86-64 | 无 | 无 | 无 | 无 | 当前 release 不能列为 binary-supported target |

PyPI 的实际文件名可直接核验，macOS tag 的最低版本是 14.0（[`torch 2.13.0` files](https://pypi.org/project/torch/2.13.0/#files)）。PyTorch `Start Locally` 当前也明确写 latest stable 需要 Python 3.10+，macOS 推荐 3.10–3.14，Windows 支持 3.10–3.14；此前“3.13 只有 wheel、prose 未支持”的判断已经过时（[PyTorch Start Locally](https://pytorch.org/get-started/locally/)）。

Python 官方生命周期给出的更关键差异是：3.13 仍处于 bugfix support 到 2029-10，3.12 和 3.11 分别已进入 security-only 并在 2028-10、2027-10 结束支持；3.14 也在 bugfix support，但 Windows 当前稳定解释器与现有项目代码的最短共同路径是 3.13（[Python active releases](https://www.python.org/downloads/)）。因此选择 3.13 不是因为“版本越新越好”，而是兼顾现有设备、维护寿命与当前 neural wheels。

### 1.3 对 prototype 的实际支持声明

第一轮不应写成宽泛的“支持 Python >=3.10”。建议写成以下可验收状态：

| Cell | 初始状态 | 晋级条件 |
| --- | --- | --- |
| Windows x86-64 / Python 3.13.7 / CPU FP32 | normative | exact lock 安装、offline E5 inference、10 次 fresh-process replay 通过 |
| macOS ARM64 / Python 3.13.7 / CPU FP32 | required replay | exact lock 安装、3 次 replay 与 Windows canonical payload 一致 |
| Windows/macOS ARM64 / Python 3.12 | compatibility candidate | 独立 lock + 同样 fixtures 通过 |
| Windows/macOS ARM64 / Python 3.14 | compatibility candidate | 独立 lock + 同样 fixtures 通过 |
| Python 3.11 | historical evidence only | 不再作为新 prototype target；旧 audit 仍保留为兼容性事实 |
| macOS Intel | unsupported | 只有批准新的依赖/版本策略后才重新评估 |

## 2. Windows Intel Arc 140T：XPU 与 DirectML

### 2.1 `torch.xpu` 是唯一值得保留观察的官方路线

Intel 官方资料把 Arc 140T 列在 Core Ultra Series 2 的 Arrow Lake-H processor graphics 中；PyTorch 的 Intel GPU 页面将 `Intel Core Ultra Processors (Series 2) with Intel Arc Graphics (Arrow Lake-H)` 列为 Windows 11 validated hardware（[Intel Core Ultra comparison chart](https://cdrdv2-public.intel.com/851467/Intel-Core-Ultra-Series1-Series2-Series3-Comparison.pdf)、[PyTorch Intel GPU prerequisites](https://docs.pytorch.org/docs/main/notes/get_start_xpu.html)）。因此，Arc 140T 不是“理论上也许能跑”的未知设备，它落在官方列出的 hardware family 内。

官方 XPU 路线的边界如下：

- PyTorch 2.5 起把 Intel client/data-center GPU 支持并入 upstream `torch.xpu` API，但页面仍明确标为 `Prototype`；
- Windows 使用 stock PyTorch API，不需要旧式 `intel-extension-for-pytorch` 才能调用模型；
- 需要先安装合适的 Intel GPU driver；binary install 使用独立的 `https://download.pytorch.org/whl/xpu` index；
- 官方说明支持 inference/training、eager/`torch.compile`、FP32/BF16/FP16/AMP；
- 当前 XPU index 的 PyTorch 2.13.0 确实提供 Windows `cp311`、`cp312`、`cp313` wheels（[PyTorch XPU guide](https://docs.pytorch.org/docs/main/notes/get_start_xpu.html)、[official XPU wheel index](https://download.pytorch.org/whl/xpu/torch/)）。

额外成本不只是一行 `.to("xpu")`：需要锁 Intel driver、改用特殊 PyTorch wheel/index、记录 XPU runtime dependencies，并为 tokenizer→host→device transfer、supported operators、fallback/error behavior 和 CPU/XPU score drift 增加 fixtures。若从 source build，官方还要求 Intel GPU driver 与 Deep Learning Essentials/oneAPI toolchain；binary wheel 虽免去编译工具链，driver 与专用 runtime 仍存在（[PyTorch XPU software prerequisites](https://docs.pytorch.org/docs/main/notes/get_start_xpu.html)、[Intel GPU dependency notes](https://www.intel.com/content/www/us/en/developer/articles/release-notes/gpu-dependencies-for-pytorch-release-notes.html)）。

### 2.2 DirectML 不应进入候选

DirectML API 本身覆盖 DirectX 12-capable Intel/AMD/NVIDIA/Qualcomm GPUs，但 PyTorch integration 是独立的 `torch-directml` plugin。当前公开事实是：

- Microsoft 把 `torch-directml` 标为 Public Preview，PyPI classifier 是 Alpha；
- 最新版本仍为 `0.2.5.dev240914`，发布于 2024-09-15，依赖 `torch==2.4.1` 和 `torchvision==0.19.1`；
- Windows wheels 只有 CPython 3.8–3.12，没有 3.13；
- 官方 operator roadmap 不是完整覆盖保证；
- DirectML GitHub repository 已明确进入 maintenance mode，不再计划新功能更新，并建议 Windows 11 24H2+ 用户考虑 Windows ML（[`torch-directml` release](https://pypi.org/project/torch-directml/)、[DirectML repository](https://github.com/microsoft/DirectML)、[operator roadmap](https://github.com/microsoft/DirectML/wiki/PyTorch-DirectML-Operator-Roadmap)）。

它会迫使 prototype 从当前 PyTorch/Transformers 版本线退回旧栈，同时仍保留 preview backend 和 operator coverage 风险。即使 Arc 140T 能通过 DirectX 12 被识别，也没有理由为了最多 36 papers 接受这组退化。

ONNX Runtime DirectML/Windows ML 是另一条 inference runtime，不是 `torch-directml` 的透明替代；采用它还需冻结 export graph、opset、execution provider、模型转换和数值 parity。当前 ticket 比较的是 scorer，而不是 deployment runtime，故也不进入第一轮（[Microsoft DirectML overview](https://github.com/microsoft/DirectML#onnx-runtime-on-directml)）。

### 2.3 Determinism 与投入产出判断

PyTorch 官方明确声明：不能保证不同 release、commit、platform 之间完全可重复，CPU 与 GPU 即使 seed 相同也可能不同；`torch.use_deterministic_algorithms(True)` 只会在已有 deterministic implementation 时选用它，否则报错，并不承诺跨 backend bitwise identity（[PyTorch reproducibility](https://docs.pytorch.org/docs/main/notes/randomness.html)）。

对本项目，风险不在随机训练——所有模型只做 `eval()` inference——而在不同 backend 的 floating-point accumulation、kernel/operator coverage 和 near-tie score 顺序。项目最终要求 observable order/payload 一致，因此 CPU 与 XPU 都必须另做 near-tie/canonical-payload 验证，不能因相同 model weights 就假定等价。

**判断：XPU 不进入 scorer relevance comparison，DirectML 完全排除；XPU/MPS 只保留 evidence-gated performance cell。** 这是由项目规模与可归因性反推的结论：

- N=3–36，不需要 GPU 解决 candidate-volume 问题；
- E5-small-v2 仅 33.4M parameters，CPU inference 在 complexity gate 内是否合格可直接实测；
- CPU FP32 提供两个平台都能运行的 reference path，避免按 GPU/iGPU availability 改变 relevance execution path；
- 加速器会把一次 scorer comparison 变成 driver/backend comparison。

只有 CPU warm p95、cold-start 或 corpus-build 实测超过已批准 gate，且优化 batching/threading 后仍失败，才比较 `torch.xpu` 或 macOS MPS。Accelerator 只有在 end-to-end 至少快 2 倍、无 unsupported/fallback operator、canonical paper/segment payload 与 CPU 完全一致且新增环境不超过 1 GiB 时，才可作为可选 deployment backend；CPU correctness path 仍必须保留。DirectML 不因 CPU 失败而复活。

## 3. 四个 dense bi-encoder 候选

### 3.1 可比信息

下表中的 parameter count 和 artifact bytes 来自官方 Hugging Face model metadata/file trees；“任务适配”是基于各自 model card 声明的训练/usage format 对本项目输入合同所作判断。

| Model | 任务与固定 input format | Parameters / official weight artifact | Max length / dimension | License | 本项目判断 |
| --- | --- | --- | --- | --- | --- |
| `intfloat/e5-small-v2` | asymmetric passage retrieval；query=`query: …`，segment=`passage: …`；mean pooling + L2 normalize + dot/cosine | 33.4M；`model.safetensors` 133,466,304 B | 512 tokens / 384 | MIT | **唯一推荐**；最贴合 query-to-segment，CPU 足够小，格式完全显式 |
| `BAAI/bge-small-en-v1.5` | retrieval；query 加 `Represent this sentence for searching relevant passages: `，passage 不加 instruction；CLS pooling + normalize | 33.4M；`model.safetensors` 133,466,304 B | 512 / 384 | MIT | 最接近的替代；但与 E5 同成本、没有对本项目 scientific segments 的已知独立优势，不应同时扩大第一轮 |
| `sentence-transformers/all-MiniLM-L6-v2` | generic sentence/short-paragraph similarity/search；两侧 raw text，mean pooling + normalize | 22.7M；`model.safetensors` 90,868,376 B | 默认截断 256 word pieces / 384 | Apache-2.0 | 最轻，但目标更泛、上下文更短；不如明确的 asymmetric retrieval model 适配 |
| SPECTER2 (`base` + ad-hoc-query + proximity adapters) | scientific ad-hoc search；short query 用 query adapter，candidate 用 proximity adapter；官方 candidate 是 `title [SEP] abstract`，CLS vector + L2 distance | BERT-base class，约 110M；base `pytorch_model.bin` 439,740,465 B，两个 adapter 各 3,593,365 B | 512 / 768 | Apache-2.0 | scientific domain 最直接，但输入单位是 paper title+abstract，不是 arbitrary full-text segment；依赖和模型约 3.3× 更重 |

Sources: [E5-small-v2 model card](https://huggingface.co/intfloat/e5-small-v2)、[E5 official artifact metadata](https://huggingface.co/api/models/intfloat/e5-small-v2?blobs=true)、[BGE-small-en-v1.5 model card](https://huggingface.co/BAAI/bge-small-en-v1.5)、[BGE artifact metadata](https://huggingface.co/api/models/BAAI/bge-small-en-v1.5?blobs=true)、[all-MiniLM-L6-v2 model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)、[MiniLM artifact metadata](https://huggingface.co/api/models/sentence-transformers/all-MiniLM-L6-v2?blobs=true)、[SPECTER2 ad-hoc query card](https://huggingface.co/allenai/specter2_adhoc_query)、[SPECTER2 base files](https://huggingface.co/allenai/specter2_base/tree/main)、[SPECTER2 proximity files](https://huggingface.co/allenai/specter2/tree/main)。

四个模型都可做 CPU inference；“CPU feasible”在这里表示模型大小和官方 PyTorch/Transformers usage 不要求 GPU，不表示已经满足本项目的 cold/warm latency gate。latency、RSS 和 artifact/environment bytes 仍必须由同一 Windows CPU harness 实测。

### 3.2 唯一推荐：`intfloat/e5-small-v2`

推荐 identity：

```text
model_id: intfloat/e5-small-v2
revision: ffb93f3bd4047442299a41ebb6fa998a38507c52
weight_file: model.safetensors
weight_bytes: 133466304
weight_sha256: 45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1
license: MIT
query_prefix: "query: "
passage_prefix: "passage: "
max_length: 512
embedding_dimension: 384
dtype: float32
reference_device: cpu
```

这里的 revision、bytes 和 SHA-256 来自 Hugging Face 官方 model API 的 LFS metadata；`5036950ec9dc58628f01c5286ef743ee1fd9ab2c` 是 Git blob ID，不是 weight SHA-256。正式准备 artifacts 时仍应对实际下载 bytes 重新计算 SHA-256，并把 tokenizer/config/weight 的全部 artifact hashes 写入 manifest，而不是只信 remote metadata（[pinned E5 tree](https://huggingface.co/intfloat/e5-small-v2/tree/ffb93f3bd4047442299a41ebb6fa998a38507c52)、[official metadata](https://huggingface.co/api/models/intfloat/e5-small-v2?blobs=true)）。

选择依据：

1. **任务方向一致。** E5 model card 明确把短 query 与 passage 分开编码，正好对应 normalized scientific query → source-faithful Retrieval Segment，而不是对称的 sentence similarity。
2. **policy 可审计。** `query: ` / `passage: ` 是固定、版本化 preprocessing，不依赖 runtime prompt guessing；缺 prefix 会导致官方明确警告的性能下降，因此 fixture 也能直接检查。
3. **最小依赖路径。** 官方 card 给出了 `AutoTokenizer` + `AutoModel` + attention-mask-aware average pooling 的完整路径，可以不安装 Sentence Transformers。
4. **长度与资源适中。** 512 tokens 比 MiniLM 默认 256 更能容纳批准的 segments，同时 33.4M/133.5 MB 远小于 SPECTER2 base。
5. **输入公平。** 它以 passage/segment 为 candidate，不需要强迫 dense arm 只看 abstract，也不需要读取 citation graph 或额外 metadata。

Prototype 中的 normative scorer comparison 使用 `model.eval()`、`torch.inference_mode()`、CPU FP32、固定 tokenizer no-truncation policy 和 normalized embeddings；所有 eligible segments exact score-all。title field 与 paper-level aggregation 继续遵守 comparison protocol，不能由 dense model 私自改成 `title + abstract`。

### 3.3 其余模型的拒绝理由

#### `BAAI/bge-small-en-v1.5`：拒绝第一轮，保留为替补

BGE-small-v1.5 不是差模型。官方 model card 显示它与 E5-small-v2 同为 33.4M/384d/512 tokens，且其自报 MTEB table 上 general retrieval average 高于 E5-small-v2；v1.5 也改善了不加 instruction 时的 similarity distribution（[BGE card evaluation/usage](https://huggingface.co/BAAI/bge-small-en-v1.5)）。

但这不是项目 frozen scientific queries 的直接证据。它与 E5 资源成本相同，新增的长 query instruction 只是另一种固定格式，并没有针对 arbitrary scientific full-text segments 的官方专门保证。把 E5 和 BGE 同时加入只有 24 条 query 的第一轮，会扩大多重比较而不回答新的 mechanism hypothesis。若 E5 在 development split 暴露稳定 dense failure，可在不打开 holdout 的前提下用同样 protocol **替换**为 BGE，而不是把两者都推进正式比较。

#### `all-MiniLM-L6-v2`：拒绝，因为“更小”不足以补偿任务错位

MiniLM 的优势是 22.7M、约 90.9 MB，四者最轻。官方 card 将它定位为 sentences/short paragraphs 的通用 semantic search/similarity encoder，默认超过 256 word pieces 截断；训练语料虽包含 MS MARCO、S2ORC 和 SPECTER pairs，也混合了大量 Reddit、QA、duplicate/similarity datasets（[all-MiniLM-L6-v2 card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)）。

当前 dense arm 的首要作用是公平挑战 lexical scorer 的 query-to-passage vocabulary mismatch，不是最小化几十 MB。E5 只多约 42.6 MB，却有明确 asymmetric prefixes 和 512-token policy，因此 MiniLM 不应成为唯一 dense representative。

#### SPECTER2：拒绝第一轮，因为 scientific 不等于 segment retrieval

SPECTER2 是四者中 scientific-domain supervision 最强的路线：base 从超过 6M citation triplets 学习，ad-hoc query adapter 专门编码 short textual query，proximity adapter 编码 candidates（[SPECTER2 paper](https://aclanthology.org/2023.emnlp-main.338/)、[official model card](https://huggingface.co/allenai/specter2_adhoc_query)）。

问题是官方 candidate recipe 把 `title [SEP] abstract` 作为 paper input，而当前 contract 需要同一 scorer 公平处理 approved abstract 与 official-full-text segments。把 segment 塞进 abstract 位置是未经官方验证的迁移；只给 SPECTER2 title+abstract 又违反“dense/fusion 不能看到与 lexical 不同正文”的公平条件。此外，它需要 base + query adapter + proximity adapter 和额外 `adapters` package，官方 artifacts 仍是 PyTorch `.bin`，约 447 MB 合计。它适合作为未来“paper-level scientific representation”研究，不是当前最小 segment scorer。

## 4. 推荐 runtime policy

### 4.1 选择 reference runtime + compatibility matrix

建议 policy 分成两层：

**Normative evidence runtime**

- Python 3.13.7；它已存在于 Windows，Mac 可由 `uv` 安装相同 patch，从而减少设备改动并消除 patch 差异；
- Windows x86-64 CPU 是 full comparison executor；macOS ARM64 CPU 对 finalists replay；
- exact resolved dependencies + wheel hashes；
- E5 exact revision + tokenizer/config/weight hashes；
- relevance comparison 禁止 GPU/MPS/XPU/DirectML 自动选择；
- offline flags 与 network-denied fixture；
- canonical order/payload 必须跨平台一致。

**Compatibility matrix**

- `Windows x86-64 × Python 3.12/3.14`；
- `macOS ARM64 × Python 3.12/3.14`；
- Python 3.11 只记录现有 ideation import audit，不要求 neural stack；
- 每个 Python minor/platform 独立 resolution/lock，因为 native wheel filenames 和 hashes天然不同；
- 只把 install + offline load + inference + deterministic fixtures 全通过的 cell 标成 supported；其余状态只能是 provisional/unsupported。

### 4.2 为什么不采用单一“所有东西硬锁死”的语言政策

硬锁一个 Python patch 对重放一次 evidence run 是必要的，但不能回答“下一台 Windows/macOS 是否可安装”。反过来，只写 `Python >=3.10` 又无法重放。reference + matrix 同时保留两种证据：

- **实验归因**：所有横向 candidate comparison 在一个 exact environment 完成；
- **可移植性**：不同 runtime cell 不比较 latency，只验证安装与 observable result；
- **可升级性**：升级某个 cell 不会悄悄改变 normative result；
- **诚实支持**：wheel/docs 声明只是候选资格；只有项目 lock、offline inference 与 replay 实测通过才标 supported。

Package policy 仍然必须 hard pin。不要用 floating `torch>=…`、`transformers>=…` 或 model `main/latest` 生成正式证据。建议先把 `torch 2.13.0 + transformers 5.16.1` 当作待 preflight 的 2026-08-30 reference snapshot；它们通过 resolver、model forward、offline、latency 和 replay gates 后才冻结，不因“latest”身份自动批准。Sentence Transformers 6.0.0 不进入 E5 minimal runtime；若 harness 后续确实使用其 API，再作为新依赖单独 preflight。

## 5. Prototype 前必须验证的最小清单

这份研究不能替代以下实测：

1. Windows/Python 3.13.7 从空环境只安装预批准 wheels，不允许 source build；记录完整 lock 与 hashes。
2. 下载 pinned E5 artifacts 后断网，验证 `local_files_only=True` 且 cache 缺失/损坏时 fail closed。
3. 对 512-token boundary、Unicode、empty/OOV、single segment、near-tie 和 36-paper fixtures 做 CPU inference。
4. Windows fresh process 重放 10 次；macOS ARM64 重放 finalists 3 次；比较 canonical payload SHA-256，而不是要求 embedding float bitwise 相同。
5. 记录 cold start、warm p50/p95、peak RSS、model bytes 和完整 environment bytes；只有 E5 通过已批准 gate，dense arm 才能进入正式 relevance comparison。
6. 单独验证 `query: ` / `passage: ` prefixes、truncation count、pooling、normalization、score direction 和 stable tie-break 均进入 audit/config。

## 来源核验与不确定性

本轮只使用：PyTorch/Intel/Microsoft/Hugging Face/BAAI/AllenAI 的官方文档、官方 package/model registries、官方 repositories/model cards，以及原始论文。没有使用博客、论坛答案或第三方 compatibility table。

已用官方 registry API 机械核验 latest versions、wheel filenames、model revisions、parameter metadata 和 artifact byte sizes；关键 wheel/model URLs 在本文逐项链接。仍需保留以下不确定性：

- package index 有 wheel 不等于项目完整 lock 可解；Python 3.13 仍需 fresh-environment preflight；
- Arc 140T 落在 validated Arrow Lake-H family 内，但本文没有在 Robert 的具体 driver/OEM configuration 上运行 `torch.xpu.is_available()`；
- E5、BGE、MiniLM、SPECTER2 的公开 benchmark 目标都不等同于当前 frozen qrels；唯一推荐是对“最小而公平的第一轮 dense representative”的选择，不是相关性胜者声明；
- CPU latency、RSS、cross-platform near-tie stability 和实际 segment truncation rate只能由批准后的 prototype 给出。

因此，本文已把 runtime 和唯一 dense candidate 收敛到可执行输入，但没有提前宣称 E5 会击败 lexical scorer，也没有改变当前 protocol 的最终决策权。
