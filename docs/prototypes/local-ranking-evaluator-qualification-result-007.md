# Local-ranking evaluator qualification-007 result

Run date: 2026-09-01（Asia/Shanghai）  
Status: **FAIL — DeepSeek mirror stability 22/24 below frozen 23/24 gate**

适用协议：[qualification v1.5](local-ranking-evaluator-qualification-protocol-v1.5.md)。Robert 的 exact-payload
authorization 见 [authorization-007](local-ranking-evaluator-qualification-authorization-007.md)。本 attempt
只运行了预注册顺序中的 DeepSeek orientation 1/2；发现 terminal qualification gate failure 后停止，未运行
Kimi、未 retry、未打开 private mapping。

## 1. Transport and mechanical results

| orientation | HTTP / cost | usage input / output / total | local items | trace SHA-256 |
| ---: | --- | --- | --- | --- |
| 1 | 200 / `"0"` | 58,043 / 36,385 / 94,428 | 24/24 PASS | `c0f8ca4fa14a0dc09d270dccd5cb83e9db756e5e282d4181f8fca9c7b217e766` |
| 2 | 200 / `"0"` | 58,039 / 38,748 / 96,787 | 24/24 PASS | `21009fdbfd8bc7447cfb94b8b2bb44e481ec2739f7ace039b90abd1c51a9ad6f` |

两路均为 exact OpenCode Go direct Chat requests，response root、bundle/evaluator binding、24-item coverage、
visible segment refs、support/rationale bounds 与 local semantic validator 全部通过。Orientation 1/2 raw response
SHA-256 分别为 `fe094cc97b3a415dad6481a3902ff35266755fff7c8f9d4a624a0a636d9bdccd`、
`357576e5b783532985af7b38ce81de9d793a869df77156bc0600d0a61ef5558a`。这确认 v1.6 transport 修复成功；
qualification failure 不再是 renderer、漏字段或 schema 问题。

## 2. Frozen mirror gate

把 orientation 2 的 left/right winner 机械反转回 orientation 1 side frame 后：

- stable: `22/24`；
- required: `>=23/24`；
- orientation 1 winner distribution: left `5`、right `9`、tie `10`；
- orientation 2 raw distribution: left `11`、right `4`、tie `9`。

Side outputs 并未 collapse 为全 left/right/tie；失败是两个具体 query 的 position instability。因为 gate 在
output 前已冻结，不能在看到 22 后把阈值从 23 改成 22，也不能把两条手工标成 resolved。

## 3. Blind diagnosis without mapping

诊断只读公开 bundles/traces，不读 baseline/challenger mapping：

1. `lr-hol-05-focused`：orientation 1 选择一侧，强调 NK infiltration、CXCR3 chemotaxis 与 metastasis；
   orientation 2 映射回来选择另一侧，强调 ECM barrier 加 chemotaxis 的覆盖广度。两次都能引用可见证据，
   但对完整 top-3 的互补 coverage 给出相反权重，属于真实方向翻转。
2. `lr-dev-02-focused`：orientation 1 对 alcohol-specific pharmacological evidence 与 dietary intervention
   判 tie；orientation 2 映射回来判含 dietary + pharmacological combination 的一侧胜。差异来自是否充分
   credit 第三个 paper 对 query component coverage 的贡献，属于 tie boundary 加 set-coverage oversight。

两个 item 都是 `focused` query；没有证据表明失败来自 side ID、segment reference、prompt truncation 或
closed-output transport。Flash 能完成主体判断，但在本项目要求的完整 top-3 setwise position stability 上没有
达到预注册门槛。

## 4. Fail-closed consequence

- qualification-007 永久为 excluded failure evidence；
- Kimi orientations 不启动，避免在 panel 已失败后产生不可复用 judgments；
- private mapping 保持 sealed；
- 两个 DeepSeek PASS traces 不得复制到后续 attempt；
- 不运行 reducer、不计算候选方向、不影响 BM25/E5 winner。

## 5. Next technical decision

推荐下一候选为同一 `provider=opencode-go` 的 `deepseek-v4-pro`，保持 v1.2 model-visible schema、rubric、
23/24 mirror gate、no-retry 与全部 local validators不变，并先做 synthetic direct-Chat qualification，再以新
attempt 全量验证。理由是当前失败面已经从 transport 收敛为 set-coverage semantic stability；升级 evaluator
capacity 比事后降低 gate、增加 retry 或继续扩张输出 schema 更直接，也更容易归因。

这只是待验证候选，不声称 Pro 必然通过。切换 model 属于 material model decision，必须由 Robert 明确批准；
若不批准，次选才是为 Flash 设计全六篇 paper-assessment scaffold，并用另一套 untouched qualification cases
验证，而不是继续在同 24 items 上调 prompt 直到过关。
