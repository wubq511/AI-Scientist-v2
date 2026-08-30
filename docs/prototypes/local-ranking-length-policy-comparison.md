# Local ranking 长度政策最小比较

Protocol date: 2026-08-30（Asia/Shanghai）
Status: **Approved addendum / evidence complete**
Decision ticket: `Choose and calibrate local literature ranking`

这是一个 throwaway comparative prototype，用来回答一个问题：pinned `intfloat/e5-small-v2` 只能接收至多 512 tokens 时，ticket 021 应怎样处理较长的 `publisher_abstract`，既不丢失 source evidence，也不让 lexical/dense arms 获得不同输入。

## 第一性原理边界

- 排序对象是 approved paper；摘要是 source evidence，不应因为某个 candidate 的实现限制而被拒绝或永久裁掉。
- `512` 若来自 pinned model architecture，就是 dense candidate 的单次模型输入边界，不是 corpus、paper 或 abstract 的语义长度上限。
- 比较必须让所有 arms 看到相同 source characters、相同 Retrieval Segments 和相同 paper aggregation；不得只让 dense 静默截断。
- 每个 formal segment 必须能用 source character offsets 精确回链；所有 segments 按 source order 无遗漏、无重叠地重建完整 normalized abstract。
- 长度安全不能读取 query/qrels/ranker output，也不能按 relevance 调整边界。

## 候选政策

| ID | 政策 | 预期优点 | 失败条件 |
| --- | --- | --- | --- |
| A | 拒绝或排除超过 512 tokens 的摘要 | 最简单 | 丢失 approved papers/evidence，违反 corpus completeness |
| B | 所有 arms 只保留开头 512-token 可见部分 | 输入相同、实现简单 | 丢失尾部 source evidence，且位置偏差不可恢复 |
| C | 仅将超限摘要做 deterministic sentence-aware、无重叠、完整覆盖分段；全部 arms 共用；paper aggregation 保持 `max` | 完整保留 source、最小扰动多数摘要、仍可公平比较 | 不能精确重建、任一 segment 超限、产生空段或非确定结果 |
| D | 全部摘要统一切成固定长度 windows | segment 尺度更统一 | 改写绝大多数本来合法的输入，并可能引入更多 segment-count/max bias |
| E | 替换为长上下文 dense model | 避免 512 边界 | 同时改变模型质量、资源、依赖和已完成的 Windows preflight，不能归因于长度政策 |
| F | 删除 dense candidate | 无 neural 长度边界 | 在没有 relevance evidence 前提前删除一个已批准 challenger |

## 冻结输入与测量

- 输入：`inputs-007` 已批准的 12 cases、168 篇 normalized `publisher_abstract`；只做长度与可逆性检查，不生成 query、不运行 ranker、不读取 qrels。
- Tokenizer：pinned E5 revision `ffb93f3bd4047442299a41ebb6fa998a38507c52` 的 exact tokenizer；测量字符串为 `passage: ` + segment，计入 tokenizer 自动加入的 special tokens。
- 对每篇记录 full-abstract exact token count；汇总超过 512 的 paper 数、case 分布、最大值与分位数，不在 tracked 文档暴露 private title/abstract。
- 对 C 记录 segment-count distribution、最大 segment token count、source character coverage、overlap、reconstruction 与 repeatability。
- 对 B 记录会被删除的 source character/token 比例，用于证明是否存在不可接受的信息损失。
- 对 D 只做结构性比较：若 C 已完整、确定、只改变必要输入，而 D 改变更多 approved inputs 且没有 qrels 能证明收益，则按最小干预原则淘汰 D，不伪造 relevance 结论。

## 决策规则

1. A 或 B 只要丢失 approved source characters 就淘汰。
2. C 只有在 168/168 可完整重建、0 overlap、0 empty、所有 segment（含 prefix/special tokens）`<=512`、两次输出完全一致时合格。
3. E 只有在 C 失败，或以后独立 relevance/cost comparison 证明长上下文模型有物质净收益时才重开；本轮不把换模型混入长度变量。
4. F 只有 dense runtime/quality gate 失败时才采用，不能仅因少量长摘要而采用。
5. 多个方案满足不变量时，选择改变 approved input 最少、依赖最少、最容易审计者。

本比较只能决定输入长度政策，不能决定 ranker winner；任何 relevance 差异仍由后续 frozen queries、blind qrels 和 development/holdout protocol 决定。

## 一手资料结论

- 冻结 E5 revision 的 [model config](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/config.json) 是 BERT + absolute position embeddings，`max_position_embeddings=512`。这是该 checkpoint 一次 forward pass 的 architecture boundary，不能靠把 tokenizer 参数写成更大来安全突破。
- 同一 revision 的 [official model card](https://huggingface.co/intfloat/e5-small-v2/blob/ffb93f3bd4047442299a41ebb6fa998a38507c52/README.md) 示例明确使用 `max_length=512, truncation=True`，并把长文本截到 512 tokens 列为限制。Hugging Face [tokenizer API](https://huggingface.co/docs/transformers/en/main_classes/tokenizer) 也明确说明 truncation 会逐 token 删除超出最大长度的内容；它解决 tensor shape，不解决 information preservation。
- E5 原论文把 scientific `(title, abstract)` pairs 纳入训练数据，但同时指出固定长度单向量能否完整编码 long document 仍是 open research question；因此不能把“模型能接收至多 512 tokens”误写成“摘要超过 512 就没有检索价值”。见 [E5 paper](https://arxiv.org/abs/2212.03533)。
- 同一论文 Appendix B / Table 11 的通用 E5 recipe 是 pre-training max length 128、fine-tuning 192，并因部分 evaluation datasets 有长文本而冻结 position embeddings、把 evaluation maximum 设为 512。公开资料没有独立的 `e5-small-v2` checkpoint-specific v2 training-length manifest；因此本 addendum 只把 512 声明为 pinned checkpoint 的 architecture/official inference support boundary，不声称它在 512-token 对比样本上训练。完整证据边界见 [E5 512-token 边界研究](e5-length-policy-research.md)。
- [LongEmbed](https://aclanthology.org/2024.emnlp-main.47/) 把 short-context 模型处理长输入的方法明确区分为 divide-and-conquer、position reorganization、position interpolation，并把 zero-overlap chunking 作为 divide-and-conquer 基线。换成长上下文 checkpoint 或扩展 position embeddings 是另一个模型干预，不是一个免费的 tokenizer 参数。

## 实测证据

使用 pinned revision 的 exact `tokenizer.json`（SHA-256 `d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66`）与 frozen `tokenizers==0.23.1` 对 approved corpus 做了两个 fresh-process probes。Harness 对 tokenizer bytes 和 dependency version fail closed。两次 `result.json` byte-identical，SHA-256 都是 `fedd7fc747f587903d1c4f5329ec59c0242e9ac57a7c48f72cee70a97ea79083`。Raw private evidence 位于：

```text
artifacts/local-ranking-prototype/length-policy-v1/attempts/length-003/result.json
artifacts/local-ranking-prototype/length-policy-v1/attempts/length-004/result.json
```

`length-001/002` 得到相同 aggregate/segmentation hash，但只记录 tokenizer hash，没有把 hash 与 `tokenizers` dependency version设为 fail-closed gate；原 artifacts 保留并由 hardened `length-003/004` supersede，不作为当前 replay identity。

| Measure | Result |
| --- | ---: |
| Approved papers | 168 |
| Full abstract inputs `<=512` | 157 |
| Full abstract inputs `>512` | 11（分布在 5 cases） |
| Full-input token min / p50 / p95 / max | 67 / 323 / 567 / 1101 |
| Candidate B 会删除的 input tokens | 1,931 |
| Candidate B 会删除的 source characters | 8,458 |
| Candidate C 输出 segments | 180 |
| Candidate C segments/paper | 157×1、10×2、1×3 |
| Candidate C maximum segment input | 512 tokens |
| Candidate C loss / overlap / empty / reconstruction failure | 0 / 0 / 0 / 0 |

之前“4 篇超过 450 whitespace words”只是风险筛查，不是 tokenizer 结论。WordPiece 会拆分术语、标点和子词，并且 formal input 还包含 `passage: `、`[CLS]`、`[SEP]`；因此 exact 结果是 11 篇，后续不得再用 word count 代替 length gate。

## 批准决定

批准 Candidate C，淘汰 A/B/D/E/F 作为 ticket 021 v1.1 的当前长度政策：

1. `512` 保留为 pinned E5 **单个模型输入**的 hard safety gate；它不是 corpus、paper 或 abstract 上限。
2. Approved abstract 永不因该 gate 被排除或裁掉。只有 exact `passage: ` + abstract（含 special tokens）超过 512 的 paper 才分段；当前是 11/168。
3. 分段优先取能容纳的最远 sentence boundary；单句仍超限时回退到 whitespace boundary；极端无空白 span 才按 source character boundary 回退。每个输出 span 都以 `[source_start, source_end)` 回链。
4. Segments 必须按 source order、无重叠、无遗漏；拼接必须 byte-for-byte 重建 normalized source text。不得加入 overlap、摘要重写、LLM 摘要或 relevance-aware boundary。
5. Lexical、dense、fusion 全部读取同一 frozen segments；paper aggregation 继续使用预注册的 `max`。这样仍可能存在 multi-segment paper 的 max-opportunity effect，但该 effect 对所有 arms 相同，且比只给 dense 截断或让不同 arms 使用不同 retrieval units 更可归因。正式结果必须单列这 11 篇的 subgroup 指标，若 winner 只靠该 subgroup 翻转则把结论标为 sensitivity risk，而不是静默推广。
6. Query 另做 exact `query: ` length gate；当前的 256 Unicode scalars validation 不能替代 tokenizer check，也不能反过来把 512 解释成 query authoring target。
7. 只有 shared segmentation 以后在 blind qrels 上暴露系统性失败，才单独预注册 chunk/aggregation 或 long-context model comparison；不在本轮同时换模型、改长度和改 aggregation。

这份 addendum 完成 `local-literature-ranking-comparison-protocol.md` v1.1 已预注册的 length-safety gate，不修改已被 input approval hash 绑定的 v1.1 protocol bytes。它也不完成 formal input adapter、queries 或 qrels。
