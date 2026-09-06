# `e5-small-v2` 512-token 边界与摘要长度政策研究

Research date: 2026-08-30（Asia/Shanghai）

Status: **一手资料研究结论；不修改已批准协议，不代表 ranker 选择结果**

## 结论

`512` **有必要保留，但必须把它放在正确的层级**：它是 pinned `intfloat/e5-small-v2` 单次编码输入的受支持上限，计算对象是加入 `query: ` / `passage: ` prefix 和 tokenizer special tokens 后的完整 token sequence；它不是 publisher abstract 的语义长度标准，也不应成为原始 corpus 的破坏性截断上限。

对当前“每篇只有题名 + publisher abstract、每个 case 3–36 篇、目标是公平比较 lexical/dense scorer”的实验，最合理的政策是：

1. 原始题名和 publisher abstract 完整、不可变地保留，不设 512-token corpus cap；
2. 用 pinned tokenizer 对实际会送入 E5 的完整字符串做 exact、non-truncating preflight；
3. 未超限摘要保持一个 segment；只对超限摘要做所有 arms 共用的 deterministic、source-faithful、sentence-aware、zero-overlap、full-coverage segmentation；
4. 每个 segment 加上 `passage: ` 和 special tokens 后必须 `<=512`，否则 fail closed；dense 不得私自截断；
5. lexical/dense 面对完全相同的 segment 文本和 paper aggregation，才能把差异主要归因于 scorer；
6. 不因少量超长摘要直接换成长上下文模型。换模型同时改变模型架构、训练数据、tokenizer、pooling、依赖和成本，回答的是另一个问题，应作为以后独立预注册的 challenger。

因此，对“我们的上限设定有必要吗、合理吗”的直接回答是：

- **作为 E5 model-input safety invariant：必要且合理。**
- **作为 raw abstract/corpus 上限或统一前截断规则：不合理。**
- **作为所有 scorer 共用 retrieval segment 的最大可编码长度：合理，前提是完整原文通过多个可回链 segments 保留，而不是删除 512 之后的内容。**

## 1. `512` 究竟是哪一种边界

### 1.1 Checkpoint 的位置表示边界

Pinned revision `ffb93f3bd4047442299a41ebb6fa998a38507c52` 的 [`config.json`](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/config.json) 明确给出：

- `architectures: ["BertModel"]`；
- `position_embedding_type: "absolute"`；
- `max_position_embeddings: 512`。

Transformers 官方 [`BertEmbeddings` 源码](https://github.com/huggingface/transformers/blob/main/src/transformers/models/bert/modeling_bert.py) 据 `config.max_position_embeddings` 创建 position embedding table 和 `position_ids` buffer，并在 forward 时按 `seq_length` 切片。对这一 pinned checkpoint 的标准 `AutoModel` 路径，512 因而不是建议性的 UI 默认值，而是 checkpoint 已学习并由实现提供的 position 范围。

理论上可以改代码、扩展/替换 position embeddings 或手工制造 position ids；但那会改变模型表示且新增未经该 checkpoint 验证的参数/位置语义，不能继续声称是同一个 pinned `e5-small-v2` arm。因此，**在本实验冻结的模型身份下，512 是硬的受支持输入边界**。

### 1.2 Tokenizer 的模型长度元数据

同一 pinned revision 的 [`tokenizer_config.json`](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/tokenizer_config.json) 设置 `model_max_length: 512`；[`sentence_bert_config.json`](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/sentence_bert_config.json) 也设置 `max_seq_length: 512`。

但 `model_max_length` 本身不是无条件的安全闸。Transformers 官方文档说明：

- [`model_max_length`](https://huggingface.co/docs/transformers/main_classes/tokenizer) 是与模型关联的最大 input-token 数；
- [padding/truncation 文档](https://huggingface.co/docs/transformers/main/en/pad_truncation) 明确 `truncation=False` 是“不截断”，`truncation=True` 才按模型或显式 `max_length` 截断；
- tokenizer API 甚至允许在不截断时产生超过模型 admissible size 的序列。

所以不能把“tokenizer 知道 512”误解为“所有调用都会安全且显式地处理超长文本”。正式输入应先在 `truncation=False` 下计数并断言长度，而不是依赖 `truncation=True` 帮忙悄悄删掉尾部。

### 1.3 官方推理合同

Pinned [`e5-small-v2` model card](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/README.md) 的官方示例：

- 为 asymmetric retrieval 使用 `query: ` 和 `passage: ` prefix；FAQ 说明这与训练方式一致，缺少 prefix 会降低性能；
- 调用 `tokenizer(..., max_length=512, truncation=True, ...)`；
- limitations 写明长文本最多截到 512 tokens。

这里的“512”是**整个编码序列**，不是 prefix 之前的 abstract token 数。BERT 单序列还会加入 `[CLS]`、`[SEP]`；Transformers 提供 [`num_special_tokens_to_add(pair=False)`](https://huggingface.co/docs/transformers/main_classes/tokenizer#transformers.PreTrainedTokenizer.num_special_tokens_to_add) 来精确计算 special-token 开销。因此正确 gate 是：

```text
len(tokenizer("passage: " + segment,
              add_special_tokens=True,
              truncation=False)["input_ids"]) <= 512
```

不应把 abstract 的裸 token 数粗略写成 512，也不应按字符数、单词数或经验上的“约 510”替代 pinned tokenizer 的实际结果。

### 1.4 训练长度与模型输入上限不是一回事

Model card 的 Training Details 直接指向 E5 原论文。论文 [*Text Embeddings by Weakly-Supervised Contrastive Pre-training*](https://arxiv.org/pdf/2212.03533) Appendix B / Table 11 报告：

- weakly supervised pre-training 的 `max length` 是 128；
- supervised fine-tuning 的 `max length` 是 192；
- 因部分 evaluation datasets 有长文本，作者冻结 position embeddings，并把 evaluation 最大文本长度设为 512。

这给出三个不同概念：

| 层级 | 一手证据值 | 它回答什么 |
| --- | ---: | --- |
| E5 recipe pre-training input | 128 | 对比预训练时一次看到多长的序列 |
| E5 recipe fine-tuning input | 192 | 有监督检索微调时一次看到多长的序列 |
| E5 evaluation / checkpoint supported input | 512 | 作者评估和发布模型允许编码到多长 |

所以“模型能接收 512”不等于“模型在 512-token 对比样本上训练过”。论文证明作者有意在 evaluation 使用 512，但更长输入相对 128/192 的训练分布更远，不能把 512 内所有位置的检索质量视为当然相同。

证据边界也要如实说明：`e5-small-v2` model card 把 Training Details 指向这篇论文，但公开的一手资料没有给出一个独立的、checkpoint-specific `v2` length manifest。128/192 是 model owner 指向的 E5 training recipe 证据；512 则由该具体 pinned checkpoint 的 config、tokenizer config、Sentence Transformers config 和 model card 直接共同确认。

## 2. 三类超长摘要处理选择

### 2.1 直接截断

**可执行性证据：** E5 model card 本身使用 `truncation=True, max_length=512`；Transformers [padding/truncation 文档](https://huggingface.co/docs/transformers/main/en/pad_truncation) 定义了这一行为。

可分成两种实际政策：

1. dense-only truncation：lexical 看全文，dense 只看前部；
2. all-arm head truncation：所有 scorer 都只看共同的前 512-safe tokens。

第一种不公平，因为 scorer 与可见证据同时变化，无法判断 dense 的失分来自 representation 还是尾部信息被删除。第二种输入相同，但把任务改成“只按摘要开头排序”；publisher abstract 的结果、讨论或结论可能位于被删除的后部，丢失内容没有任务层面的理由。

截断只适合作为显式 diagnostic/sensitivity arm，或产品本来就规定只索引开头的场景；它不是当前主政策。尤其不能在 tokenizer 内静默发生，因为这会让 evidence provenance 无法解释“为什么某条来源内容没有机会被检索”。

### 2.2 共同分块

Transformers tokenizer API 原生支持 [`return_overflowing_tokens`、`stride` 和 fast-tokenizer offset mapping](https://huggingface.co/docs/transformers/main_classes/tokenizer)，证明 fixed-window overflow、重叠和源位置回链在工具层面可实现。Jina Embeddings 2 原论文也把 splitting documents into smaller chunks 识别为应对传统 512-token 模型的常见路径：[论文](https://arxiv.org/pdf/2310.19923)。

但工具支持不等于政策已经确定。分块至少引入四个新变量：边界、overlap、每篇 segment 数、segment-to-paper aggregation。对本实验最小且可归因的选择是：

- 优先按原文 sentence boundary，greedy 打包尽可能多的连续完整句子；
- 每个 chunk 用实际 `passage: ` + special tokens 验证 `<=512`；
- primary policy 使用 zero overlap，使源字符完整覆盖恰好一次，避免重复术语改变 lexical collection statistics，也避免给长文档额外的近重复“抽奖次数”；
- 若单句自身超限，按 pinned fast tokenizer 的 source offsets 切成连续、non-overlapping token-safe source slices，不通过 decode/rewrite 生成伪原文；
- 保存原始 source byte/character offsets、segment order、token count 和 coverage invariant；
- 短摘要不人为切碎，保持一篇一个 segment；
- 所有 lexical/dense arms 使用同一 segment bytes、同一 paper aggregation、同一 output budget。

共同分块的代价是 segment count 不再完全相同，`max(segment_score)` 会让 segment 较多的 paper 有更多机会取得高分。不过：

- `sum` 会更直接奖励长文档；
- `mean` 会把一个强 evidence segment 被其他无关 segment 稀释；
- 当前输出语义是“每篇返回一个最佳 evidence segment”，`max` 与这个语义一致。

因此当前可保留 `max`，但必须记录每篇 `segment_count`，检查结果是否由多 segment papers 驱动，并保留 segment-count imbalance fixture。若最终 winner 只在超长摘要上获胜或失败，应报告 length-policy interaction，而不是把差异全部归功于 scorer。

### 2.3 换成长上下文 embedding model

存在可信的一手替代路线，但没有“只把 E5 的 512 调大”这么简单：

- [`jinaai/jina-embeddings-v2-small-en` model card](https://huggingface.co/jinaai/jina-embeddings-v2-small-en) 和 [Jina Embeddings 2 论文](https://arxiv.org/pdf/2310.19923) 声明支持 8192 tokens，使用 bidirectional ALiBi；small 版本约 33M parameters，与 E5-small-v2 参数量同档。model card 同时明确 embedding model 训练长度为 512、靠 ALiBi extrapolate 到 8K；长上下文能力仍需在目标任务上实测，不是训练长度等于 8K。
- [`intfloat/e5-mistral-7b-instruct` model card](https://huggingface.co/intfloat/e5-mistral-7b-instruct) 的官方示例使用 4096，limitations 不建议输入超过 4096；它有约 7B parameters，而 `e5-small-v2` model card 报告约 33.4M。即使只算 FP32 parameter bytes，量级也约为 28 GB 对 134 MB，明显背离当前 portable CPU FP32 reference path 的成本目标。

Jina small 是未来更公平的长上下文 challenger，E5-Mistral 则在本地 CPU FP32 约束下不具备同档可比性。但二者都会同时改变 model family、training mixture、tokenizer、pooling、dependency/runtime contract 和模型得分分布。若把它们直接替换 E5，就无法知道收益来自更长输入还是更好的/不同的 embedding model。

因此，长上下文替代模型只应在以下任一条件成立时另立比较：

- 超长摘要占比或长度高到共同分块显著增加 latency/segment-count bias；
- qrels 证明相关 evidence 经常跨越 chunk boundary；
- shared chunking 下的 failure cases 对最终选择具有决定性影响；
- 真实 runtime 的输入升级为长全文，而不再只是 title + abstract。

## 3. 结合当前规模证据的政策判断

主线程在不向本研究暴露 private input 内容的前提下提供了 exact probe aggregate：

- 168 papers；
- 11 个完整 `passage: abstract` 输入超过 512，分布在 5 cases；
- 最大输入 1101 tokens；
- silent/all-arm head truncation 会丢 8,458 source chars、1,931 input tokens；
- 只对超限摘要做 deterministic sentence-aware、zero-overlap、full-coverage segmentation 后得到 180 segments：157 papers×1、10×2、1×3；
- 最大 segment 恰好 512 tokens；source loss=0、overlap=0；两次 fresh-process 输出 byte-identical。

这些数据改变了早先“可能只有 4 篇超限”的估计，但没有改变第一性原理判断：11/168 约为 6.5%，且最多只需 3 segments。共同分块的增量是 12 个 segments，相对 168 个 paper 很小；统一前截断却已经确认会删除可观的原始证据。对 N=3–36 的 exhaustive local ranking，节省这 12 个 segment 的计算没有足够价值去交换 0-loss provenance 和 scorer fairness。

因此，当前 probe 所验证的 policy shape 是合理的：

```text
raw title / publisher abstract
        │ immutable, no corpus cap
        ▼
exact pinned-tokenizer preflight with prefix + special tokens
        │
        ├── <= 512 → one unchanged segment
        └── > 512  → shared sentence-aware, zero-overlap,
                     full-coverage source segments
                         │ each encoded input <= 512
                         ▼
all lexical/dense arms score identical segments
                         ▼
fixed max segment-to-paper aggregation
```

这不是说 segmentation 一定提升 relevance；它只说明在不删除 source evidence、又不改变 pinned E5 模型身份的前提下，这是最小、可审计、可公平比较的 admissibility transform。最终效果仍由 blind qrels 和预注册 metrics 决定。

## 4. 应冻结的验收条件

正式 qrels/ranking 前，length policy 至少应满足：

- model/tokenizer revision 与文件 hashes 固定；
- query 使用完整 `query: ` 输入计数，超限 typed-fail，不对 query 分块；
- title 使用完整 `passage: ` 输入计数，超限 typed-fail 或在运行前单独批准 title policy，不静默截断；
- abstract segment 的完整 `passage: ` 输入 `<=512`；
- tokenizer inference path 不启用 silent truncation；
- 原始 abstract bytes/hash 不变；segments 可按 source offsets 回链；
- concatenated source coverage 无丢失、无重叠，顺序稳定；
- 所有 arms 的 paper IDs、segment IDs、segment bytes 完全一致；
- segmentation policy 不进入 scorer 参数 sweep；
- fresh-process 生成的 canonical segments 与 manifest byte-identical；
- 结果报告单独列出 multi-segment papers，检查 segment-count/length interaction。

只要这些条件成立，512 上限不是任意的工程惯例，而是 pinned E5 arm 的必要模型合同；共同分段则是为了不让这一模型合同污染 scorer 公平比较而引入的最小数据视图转换。

## 一手来源索引

1. [`intfloat/e5-small-v2` pinned model card](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/README.md)：官方 prefix、512 truncation 示例、limitations、Training Details 入口、参数量。
2. [Pinned `config.json`](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/config.json)：`BertModel`、absolute position embeddings、`max_position_embeddings=512`。
3. [Pinned `tokenizer_config.json`](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/tokenizer_config.json)：`model_max_length=512`。
4. [Pinned `sentence_bert_config.json`](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/sentence_bert_config.json)：`max_seq_length=512`。
5. [E5 原论文](https://arxiv.org/pdf/2212.03533)：Appendix B / Table 11 的 128/192 training lengths 与 512 evaluation length。
6. [Transformers `BertEmbeddings` 官方源码](https://github.com/huggingface/transformers/blob/main/src/transformers/models/bert/modeling_bert.py)：position embedding table / position ids 由 `max_position_embeddings` 创建。
7. [Transformers padding/truncation 官方文档](https://huggingface.co/docs/transformers/main/en/pad_truncation)：truncation 是显式策略，并非 tokenizer 无条件行为。
8. [Transformers tokenizer 官方 API](https://huggingface.co/docs/transformers/main_classes/tokenizer)：`model_max_length`、special-token count、overflow、stride 与 offset mapping。
9. [`jina-embeddings-v2-small-en` 官方 model card](https://huggingface.co/jinaai/jina-embeddings-v2-small-en) 与 [Jina Embeddings 2 原论文](https://arxiv.org/pdf/2310.19923)：33M/8192-token 长上下文替代、512 training length 与 ALiBi extrapolation。
10. [`e5-mistral-7b-instruct` 官方 model card](https://huggingface.co/intfloat/e5-mistral-7b-instruct)：约 7B parameters、4096 官方用法和 `>4096` 不建议的限制。
