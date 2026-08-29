# 《The Dynamics of Frailty Among Older Adults》abstract 补齐调查

调查日期：2026-08-29（Asia/Shanghai）

## 结论

这条记录**没有可补齐的论文原始 abstract**。精确 DOI、PMID 和出版社页面均指向同一篇文章；NCBI PubMed XML、Europe PMC core record 和 Crossref work record 都未提供 abstract。JAMA Network Open 官方全文将文章类型明确标为 **Invited Commentary**，元数据之后直接进入正文，页面中既没有 `Abstract` 区块，也没有 `Key Points` 区块（[PubMed EFetch XML](https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=31373644&retmode=xml)、[Europe PMC core record](https://www.ebi.ac.uk/europepmc/webservices/rest/article/MED/31373644?resultType=core&format=json)、[Crossref work record](https://api.crossref.org/works/10.1001%2Fjamanetworkopen.2019.8438)、[JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775)）。

因此不能把以下内容当作 abstract：

- 原始数据中的 `falls,`：它显然不是 abstract；
- 原始数据中的 target citation context：它是另一篇论文如何引用本文的上下文，不是本文作者提交或出版社发布的 abstract；
- JAMA 正文首段、全文摘录或本报告生成的摘要：它们都是正文或二次加工，不是原始 abstract；
- JAMA 同期关联研究《Global Incidence of Frailty and Prefrailty Among Community-Dwelling Older Adults》的 abstract：那是被本篇 commentary 评论的另一篇论文，不属于当前 DOI（[关联研究官方页](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740784)）。

**不需要 Robert 人工访问来判断 abstract 是否存在。** 现有官方证据已足够排除原始 abstract 和 Key Points。只有在项目要求额外保存出版社 PDF 作为证据时，才可能需要 Robert 在浏览器中完成 JAMA 的 Cloudflare 检查或免费账户登录；PDF 访问本身不会把正文变成 abstract，也不应作为 `abstract` 补齐前置条件。

## 记录与身份核对

| 字段 | 核对结果 | 第一方证据 |
| --- | --- | --- |
| 本地 `paperId` | `ddd7c556a8eb08cdb08010cc3fbc90b3f13b7f77` | 本地 corpus identity；外部来源不认识该内部 ID |
| DOI | `10.1001/jamanetworkopen.2019.8438` | [Crossref exact-DOI record](https://api.crossref.org/works/10.1001%2Fjamanetworkopen.2019.8438)、[JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775) |
| PMID | `31373644` | [NCBI PubMed record](https://pubmed.ncbi.nlm.nih.gov/31373644/)、[NCBI EFetch XML](https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=31373644&retmode=xml) |
| 标题 | `The Dynamics of Frailty Among Older Adults` | [NCBI PubMed record](https://pubmed.ncbi.nlm.nih.gov/31373644/)、[Crossref record](https://api.crossref.org/works/10.1001%2Fjamanetworkopen.2019.8438)、[JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775) |
| 作者、期刊与日期 | Steven M. Albert；JAMA Network Open；2019-08-02 | [NCBI EFetch XML](https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=31373644&retmode=xml)、[JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775) |
| JAMA article id | `2740775` | DOI resolver 跳转到 [JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775)；PubMed XML 的 PII 也是 `2740775`（[DOI 入口](https://doi.org/10.1001/jamanetworkopen.2019.8438)） |

所有公开身份字段一致，没有发现 DOI/PMID 指向错误论文或同名论文混淆。

## 各官方来源的 abstract 证据

### NCBI PubMed

精确 PMID 的 EFetch XML 返回题名、作者、期刊、日期、DOI 和 publication types，但 `<Article>` 中没有 `<Abstract>` / `<AbstractText>` 元素。它把本文编目为 `Comment`、`Journal Article` 和 `Research Support, N.I.H., Extramural`，并以 `CommentOn` 关系指向 DOI `10.1001/jamanetworkopen.2019.8398` 的关联研究（[NCBI EFetch XML](https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=31373644&retmode=xml)）。

结论：PubMed 中不存在可取回的原始 abstract；`CommentOn` 引用的研究 abstract 不能移植到本文。

### Europe PMC

精确 `MED/31373644` 的 core record 返回相同 DOI、题名和 publication types，但响应没有 `abstractText`。记录还显示 `inEPMC=N`、`inPMC=N`、`hasPDF=N`；`fullTextUrlList` 仅给出 DOI 入口（[Europe PMC core record](https://www.ebi.ac.uk/europepmc/webservices/rest/article/MED/31373644?resultType=core&format=json)）。

结论：Europe PMC 没有 abstract，也没有可由 Europe PMC 提供的官方全文/PDF 副本。其访问可用性字段不用于推翻出版社页面自身的开放获取声明。

### Crossref

精确 DOI work record 返回匹配的题名、作者、期刊和出版社，类型为 `journal-article`；响应中的 `abstract` 为 `null`。对 DOI resolver 发送 `Accept: application/vnd.citationstyles.csl+json` 得到的 CSL JSON 也返回同一身份和 `abstract: null`。Crossref 记录提供一个 JAMA Network 官方 PDF URL，但没有任何可作为 abstract 的文本（[DOI content-negotiation 入口](https://doi.org/10.1001/jamanetworkopen.2019.8438)、[Crossref exact-DOI record](https://api.crossref.org/works/10.1001%2Fjamanetworkopen.2019.8438)、[Crossref 所列官方 PDF](https://jamanetwork.com/journals/jamanetworkopen/article-pdf/2/8/e198438/17755458/albert_2019_ic_190091.pdf)）。

结论：Crossref 不能补齐 abstract；PDF 链接只证明存在官方全文载体，不证明存在 abstract。

### JAMA Network Open

出版社的 article page 在标题上方明确显示 `Invited Commentary`。页面从出版信息直接进入正文，在完整文章页中没有 `Abstract` 或 `Key Points` 标题；文章信息区声明本文为 CC-BY open access（[JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775)）。JAMA 2019 年 8 月期刊目录也把本文放在关联研究之后，并明确标为 `Invited Commentary`（[JAMA 2019 年 8 月目录](https://jamanetwork.com/journals/jamanetworkopen/issue/2/8)）。

结论：该文章只有 commentary 正文，没有出版社发布的 abstract，也没有可替代的 Key Points。

## 官方全文与 PDF 入口

| 入口 | 2026-08-29 自动访问结果 | 能否改变 abstract 结论 |
| --- | --- | --- |
| [DOI resolver](https://doi.org/10.1001/jamanetworkopen.2019.8438) | `302` 到 JAMA article id `2740775`；命令行继续跟随时触发 Cloudflare challenge | 否；身份跳转已确认 |
| [DOI content negotiation](https://doi.org/10.1001/jamanetworkopen.2019.8438) | 请求 CSL JSON 成功，身份一致且 `abstract=null` | 否；没有 abstract payload |
| [JAMA HTML 全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775) | 搜索索引可读取完整正文；直接 `curl` 得到 Cloudflare `403` challenge | 否；可读取版本已明确无 Abstract/Key Points |
| [JAMA DOI PDF 路由](https://jamanetwork.com/journals/jamanetworkopen/articlepdf/10.1001/jamanetworkopen.2019.8438) | 命令行访问得到 Cloudflare `403` challenge | 否 |
| [Crossref 所列 JAMA PDF](https://jamanetwork.com/journals/jamanetworkopen/article-pdf/2/8/e198438/17755458/albert_2019_ic_190091.pdf) | `HEAD` 与 range `GET` 均得到 Cloudflare `403` challenge | 否 |

JAMA HTML 页面本身展示 `Download PDF` 入口，并提示可通过免费个人账户登录访问 PDF；这说明当前失败是自动访问限制，不是“论文不存在”。但全文页面、期刊目录和三个结构化元数据源已经独立一致地表明本文是无 abstract 的 Invited Commentary，所以没有必要把人工 PDF 下载当作本次决策的阻塞项（[JAMA 官方全文](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2740775)、[JAMA OpenURL/PDF 路由说明](https://jamanetwork.com/pages/open-url)）。

## 对 frozen corpus contract 的事实输入

本调查只提供事实，不替后续合同票选择 retrieval fallback：

1. 当前记录应视为“权威来源确认 abstract 不存在”，而不是“enrichment 暂时失败”。
2. 若合同要求 `title + validated abstract` 才能检索，则本文可以保留 membership 和 provenance，但不能伪造 abstract；其 retrieval eligibility 应由该合同明确决定。
3. 若以后评估 title-only、正文检索或 target citation context fallback，必须使用独立字段和独立策略名称；这些文本都不得写入 `abstract` 字段，也不得声称是原始 abstract。
4. 无需人工继续寻找 abstract；Robert 只需在项目确实要求归档出版社 PDF 时再尝试交互式访问。

## 访问失败与限制记录

- Web 抓取器直接打开 PubMed HTML 时遇到 reCAPTCHA；NCBI EFetch exact-PMID XML 正常返回，因此没有改用第三方页面。
- JAMA full-text、DOI PDF 路由和 Crossref 所列历史 PDF URL 的直接命令行请求均触发 Cloudflare `403` challenge；搜索索引仍返回了出版社官方完整 article page 内容和结构。
- Europe PMC API 正常返回，但没有 `abstractText`，且不托管本文全文/PDF。
- Crossref API 正常返回，但 `abstract=null`。
- 没有使用 fuzzy title search、Semantic Scholar、第三方聚合摘要、引用本文的 citation context、模型生成摘要或人工改写正文来填补 `abstract`。
