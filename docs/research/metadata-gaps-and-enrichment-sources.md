# Metadata gaps and identifier-based enrichment sources

Research date: 2026-08-28 (Asia/Shanghai)

## Decision summary

The three raw files already prove the target/reference membership boundary: all 237 Target Papers have a non-empty Target Reference Corpus, every reference membership points to a known target, and there are no duplicate memberships, self-references, or cluster membership anomalies. They are therefore sufficient to define the retrieval boundary, but not sufficient to produce citation-complete, provenance-complete paper records.

The material gaps are:

- 18/2,296 reference memberships have no `venue`; all 18 were resolved by exact DOI against Crossref during this audit.
- 3/2,296 reference `abstract` values are not usable abstracts after manual inspection of every value shorter than 50 characters. Two are recoverable from an authoritative exact-identifier path; one source paper has no abstract in either Crossref or Europe PMC and needs an explicit `abstract_unavailable` policy.
- Authors, canonical URL, volume/issue/pages, publisher, language, record source, retrieval time, field-level provenance, and rights/license evidence are absent as columns from both paper tables. Authors and a venue/container or explicit preprint/repository substitute are blocking for complete bibliography output; provenance fields are blocking for the Evidence Chain.
- The Target Paper has enough source text to derive a Workshop File, but it does not contain a trustworthy separation of background/open problem from the target's method/results. `abstract_summary` is especially unsafe as a default Workshop File source: 236/237 values use the same `Given that ...` framing, and target-method/result markers are common (details below). This is not a public-metadata enrichment problem; it needs a leakage-aware derivation and validation contract.
- Local retrieval has title and some text for every reference, but the scorer must decide whether a paper with an authoritatively unavailable abstract may use `title + citation contexts`, or must be excluded/fail closed. The raw schema does not answer that decision.

No fuzzy title search, broad web crawling, Semantic Scholar lookup, or MAG lookup is required to cover the current 2,525 unique papers. All have at least one non-Semantic-Scholar exact public identifier: DOI, PMID, arXiv ID, or DBLP key.

## Scope and reproducible method

Only these inputs were read; no raw data was changed:

| File | SHA-256 | Logical records |
| --- | --- | ---: |
| `data/raw/target_papers.csv` | `ba71dc35e1209ff0e51a440dea1d3ba96dfa5a92a2af2e472313a1b79240b96c` | 237 |
| `data/raw/filtered_references.csv` | `afaa733c6cddac1b0d31c240189cc3dd73b449dc7b99cb9ddc0cd8a4847930a6` | 2,296 memberships |
| `data/raw/ideabench_clustering.json` | `ce67a168545067130f8892554a5453cde7a37073e583b8d09ea6fbbc21a4f423` | 8 clusters / 237 memberships |

The audit used the Python standard library (`csv`, `json`, `ast`, `re`, `collections`) with these checks:

1. Missing means an absent value or a trimmed, case-folded member of `{"", "nan", "none", "null", "na", "n/a"}`.
2. `externalIds`, `publicationTypes`, `contexts`, and `intents` were parsed with `ast.literal_eval`; their container and element types were checked. `eval` was not used.
3. Semantic Scholar `paperId`/`targetPaperId` values were checked as 40 lowercase hexadecimal characters. DOI syntax was checked as `10.<4-9 digits>/<non-space suffix>`; the remaining identifier namespaces were checked against their documented numeric/string shapes.
4. Numeric fields were checked for parseability, integer-valuedness, and non-negativity. Boolean and categorical value sets were enumerated.
5. Duplicate checks covered exact rows, Target Paper IDs, `(targetPaperId, paperId)` memberships, normalized titles, DOI-to-paper-ID mappings, and conflicts among repeated immutable paper fields.
6. Boundary checks covered reference foreign keys, empty corpora, self-reference, reference/target overlap, global reference reuse, and exactly-one cluster membership.
7. Text checks covered empty and placeholder abstracts, control/replacement characters, whitespace artifacts, and manual inspection of all abstracts shorter than 50 characters. The 50-character threshold is a triage rule, not a definition of abstract quality.
8. The 18 missing venues were queried on 2026-08-28 using exact `GET https://api.crossref.org/works/{percent-encoded-doi}` requests. All returned a non-empty `container-title`. The public-pool response advertised `x-rate-limit-limit: 5`, `x-rate-limit-interval: 1s`, and `x-concurrency-limit: 1`; clients must read these headers rather than assume these values are permanent.

Physical line counts are not record counts because quoted CSV fields contain newlines.

## Confirmed dataset findings

### Boundary and membership

| Check | Result |
| --- | ---: |
| Target Papers / unique `paperId` | 237 / 237 |
| Reference memberships / unique reference papers | 2,296 / 2,288 |
| Target Papers represented in reference table | 237/237 |
| References per target | min 3, mean 9.688, max 36 |
| Unknown `targetPaperId` foreign keys | 0 |
| Duplicate `(targetPaperId, paperId)` memberships | 0 |
| Exact duplicate reference rows | 0 |
| Self-references | 0 |
| Reference paper that is also any Target Paper | 0 |
| Reference papers reused by two targets | 8 |
| Maximum targets sharing one reference | 2 |
| Unknown/unclustered/multi-cluster Target Papers | 0 / 0 / 0 |

The eight globally reused references have identical `externalIds`, title, abstract, venue, year, citation count, and publication types across their two memberships. This is legitimate paper reuse, not a duplicate membership. It does expose an implementation constraint: immutable canonical paper metadata may be deduplicated globally, but membership, score, selected rank, prompts, reflection, and all mutable run state must be keyed by target/run. A mutable object keyed only by reference `paperId` would create cross-run contamination.

Cluster sizes are: Health & Medicine 76, Genetics & Molecular Biology 76, Neuroscience & Cognitive Sciences 25, Social & Behavioral Sciences 18, Public Health & Policy 13, Environmental Sciences 12, Technology & Engineering 11, and Materials Science 6.

### Missing and malformed values

All Target Paper fields are non-empty. All reference fields are non-empty except `venue` in 18 memberships (0.784%). All 18 affected rows have a syntactically valid DOI, and exact Crossref records supplied a container title in 18/18 checks.

No malformed 40-hex paper IDs, malformed DOI strings, unparseable nested literals, empty list/dict values, invalid numeric values, negative numeric values, duplicate list elements, Unicode replacement characters, or NUL characters were found.

Three reference abstracts are confirmed unusable:

| Reference `paperId` | Raw length/value | Exact identifiers | Authoritative result |
| --- | --- | --- | --- |
| `ddd7c556a8eb08cdb08010cc3fbc90b3f13b7f77` | 6, `falls,` | DOI `10.1001/jamanetworkopen.2019.8438`; PMID `31373644` | Crossref and Europe PMC identify the paper, but neither supplies an abstract. Record as unavailable; do not invent one. |
| `2ec2352d4009f3953d3322c8b7aaa9f6c8777043` | 32, `Statistics Working Papers Series` | DBLP `journals/jmlr/PerlichPS03` | The exact DBLP record leads to the official JMLR article page, which contains the abstract and complete citation. |
| `0bbeaef2fa56c0cbc4a08f7295498e44614202f8` | 34, a journal citation fragment | DOI `10.1111/j.1471-4159.2011.07343.x`; PMID `21668448` | Europe PMC exact PMID lookup returned a 1,490-character abstract. |

The next-shortest reference abstract is 95 characters and is substantive. There were no matches for common explicit placeholders such as `no abstract`, `not available`, `n/a`, or `unknown`; this does not prove that every longer abstract is complete.

Minor representation issues that require deterministic normalization, not data repair:

- All 237 target `year`/`citationCount` values use integer text, while all 2,296 reference values use integer-valued float text such as `2022.0` and `44.0`. All parse to non-negative integers; reference years span 1954–2024.
- Nested CSV values are Python-literal strings rather than JSON. They all parse today, but the canonical intermediate format should be real typed JSON, not a Python-specific representation.
- `publicationTypes` has logically equivalent order variants, for example `['JournalArticle', 'Study']` (98 rows) and `['Study', 'JournalArticle']` (26 rows). Treat it as a canonicalized set/list, not an ordered feature.
- `CorpusId` values inside `externalIds` are integers; other identifier values are strings. Canonical identifiers should be strings with namespace-specific normalization.
- `Unnamed: 0` is unique in both CSVs but is non-contiguous (target range 0–2,363; reference range 0–23,332). It is a source-row locator, not a durable paper or membership ID.
- 135 reference abstracts and 2 target abstracts contain embedded newlines; 2 reference abstracts and 1 target abstract have edge whitespace. Preserve raw text, but normalize whitespace in a derived retrieval field.
- `contexts` and `intents` are valid non-empty string lists, but their list lengths differ in 584/2,296 memberships. They must not be positionally zipped unless the upstream semantics are confirmed. The only intent values are `background`, `methodology`, and `result`.

### Identifier coverage

There are 2,525 unique papers across targets and references, with no target/reference paper overlap.

| Coverage | Target rows | Reference memberships | Unique reference papers where different |
| --- | ---: | ---: | ---: |
| DOI | 237/237 | 2,238/2,296 | 2,230/2,288 |
| PMID | 232/237 | 2,216/2,296 | 2,210/2,288 |
| PMCID | 218/237 | 753/2,296 | 749/2,288 |
| arXiv | 2/237 | 40/2,296 | 40/2,288 |
| DBLP | 2/237 | 80/2,296 | 80/2,288 |

All 58 reference memberships without a DOI still have an exact non-Semantic-Scholar authority path:

- 48 have a PMID;
- 9 have both arXiv and DBLP identifiers;
- 1 has a DBLP key only.

`MAG` and `CorpusId` are therefore not needed as enrichment keys. The eight duplicate DOI occurrences, six duplicate PMID occurrences, four duplicate PMCID occurrences, and three duplicate MAG occurrences are explained by the eight intentionally reused reference papers; no DOI maps to multiple paper IDs, and no normalized title maps to multiple paper IDs.

## What each pipeline stage actually needs

### Workshop File

Confirmed available for every Target Paper: stable local `paperId`, DOI, title, raw abstract, year, venue, publication type, broad cluster, and `abstract_summary`.

Required but not represented safely:

- a provenance link from every Workshop File statement to the immutable Target Paper input and its dataset hash;
- explicit fields for research area/background, problem or gap, and constraints, separated from target method, implementation, results, and conclusions;
- a leakage validation result and evidence, not merely a generated summary;
- a versioned derivation contract and hash so a Workshop File can be reproduced.

`abstract_summary` cannot be accepted as a safe Workshop File by presence alone. Confirmed surface signals are: 236/237 start with `Given that`; 166 mention `this study/work/research`; 156 mention results/findings; 84 use a form of `propose`; 72 mention method/approach/technique/framework/model/system; 69 use a form of `develop`; and 42 mention `novel`/`innovative`/`innovation`. These lexical counts do not by themselves prove leakage in each record, but they show that the field was not designed as a method/result-excluding topic contract.

Authors, volume, issue, and pages are not needed to generate the Workshop File. They are needed only if the Workshop artifact must carry a human-readable source citation.

### Scoped Literature Retriever

Required and mostly present:

- target-scoped membership: `targetPaperId + paperId` (complete and anomaly-free);
- searchable text: non-empty title and a validated abstract or an explicitly declared fallback;
- immutable identity/provenance: local paper ID plus exact external identifier(s);
- deterministic normalization and a frozen corpus hash.

Useful but not safe to assume:

- `contexts` can enrich retrieval/query evidence, but their relationship to `intents` is not positionally defined;
- `citationCount` and `isInfluential` can be ranking features only if their source, observation time, transformation, and frozen value are recorded. The raw data has no observation timestamp or source declaration;
- `venue`, publication type, and year are filters/display metadata, not substitutes for text relevance.

The three corrupt abstracts block a strict `title + abstract` invariant. A later design decision must choose one auditable behavior: (a) require authoritative abstract enrichment and exclude/fail when unavailable, or (b) define and separately evaluate a `title + target citation contexts` fallback. Silently indexing `falls,` is not acceptable.

### Citation-complete reference output and Evidence Chain

The minimum conditional bibliography record should contain:

- title, ordered authors, publication year, work type;
- container/venue for journal or conference work, or an explicit repository/preprint source;
- DOI or another persistent canonical URL;
- volume, issue, and pages/article number when applicable;
- the exact source record and retrieval timestamp.

The raw tables contain no author column at all (0/2,525 papers represented), and no dedicated URL, volume, issue, pages, publisher, language, source, retrieval timestamp, field provenance, or rights/license column. `externalIds` contains DOI but is not a citation record. These gaps are why enrichment is required even though almost every retrieval-text field is populated.

Every enriched field should be stored without mutating the raw files, with at least:

```json
{
  "field": "venue",
  "value": "...",
  "source": "crossref",
  "source_identifier": "doi:...",
  "request_url": "https://api.crossref.org/works/...",
  "retrieved_at": "RFC-3339 timestamp",
  "http_status": 200,
  "response_sha256": "...",
  "license_basis": "bibliographic facts; abstract handled separately",
  "transform": "container-title[0]; HTML entity decoding",
  "validation": "returned DOI equals normalized requested DOI"
}
```

The canonical paper payload may be enriched once per unique paper. Target membership and all run artifacts must remain separate and target/run-scoped.

## Authoritative identifier-only enrichment routes

### 1. DOI router, then registration agency

Do not assume every DOI belongs to Crossref. First call `GET https://doi.org/doiRA/{percent-encoded-doi}`; the DOI Foundation documents this exact Registration Agency lookup and the possible invalid/unknown outcomes. DOI resolution is persistent, but each Registration Agency owns its richer schema ([DOI resolution documentation](https://doi.org/help.html), [DOI content negotiation](https://www-new.doi.org/doi-handbook/HTML/content-negotiation.html)).

For a Crossref DOI, call:

```text
GET https://api.crossref.org/works/{percent-encoded-doi}
```

Crossref exposes title, contributors, dates, container title, volume/issue/pages, publisher, URL, license metadata, and sometimes abstracts. Its REST API is public and needs no sign-up; rate limits are returned in response headers and depend on the active pool ([Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/), [access and authentication](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)). Almost all bibliographic metadata is reusable as factual/public-domain material, but publisher/author copyright can apply to abstracts; an abstract must retain separate rights provenance ([Crossref metadata licensing](https://www.crossref.org/documentation/retrieve-metadata/)).

For a DataCite DOI, call:

```text
GET https://api.datacite.org/dois/{percent-encoded-doi}
```

The public API returns the complete DOI metadata record without authentication, including creators, titles, publisher, container, publication year, rights, URL, record version, and update timestamps ([DataCite single-DOI retrieval](https://support.datacite.org/docs/api-get-doi), [REST API](https://support.datacite.org/docs/rest-api)). Current documented limits are 500 requests per five minutes for unidentified clients, 1,000 for identified clients, and 3,000 authenticated, with `429` on excess; exponential backoff is recommended ([DataCite rate limits](https://support.datacite.org/docs/rate-limit)). The aggregated DataCite Data File is CC0 to the extent DataCite owns the rights, but this does not grant rights to linked resources or erase personal/privacy rights ([DataCite data-file policy](https://support.datacite.org/docs/datacite-data-file-use-policy)).

Dataset-specific confirmed result: all 18 missing venues returned a Crossref `container-title` by exact DOI. This proves that gap is mechanically fillable; it does not authorize overwriting raw data or trusting unrelated fields without validation.

### 2. PMID/PMCID: NCBI as source of record; Europe PMC as structured alternative

For an exact PMID, use NCBI EFetch rather than a search query:

```text
GET https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi
    ?db=pubmed&id={PMID}&retmode=xml&tool={tool_name}&email={contact_email}
```

PubMed records contain title, authors, journal, publication date, and, when supplied, abstract; EFetch accepts an explicit UID list ([PubMed guide](https://pubmed.ncbi.nlm.nih.gov/help/), [E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25497/)). NCBI requires no more than three requests per second without an API key; a key raises the standard limit to ten per second, and software should send `tool` and `email`. Do not log the API key or contact address. NLM does not claim PubMed abstract copyright, but publishers or authors may; downstream redistribution cannot assume permission ([NCBI usage and copyright policy](https://www.ncbi.nlm.nih.gov/home/about/policies/)).

Europe PMC also supports an exact source/id endpoint:

```text
GET https://www.ebi.ac.uk/europepmc/webservices/rest/article/MED/{PMID}
    ?resultType=core&format=json
```

Its `core` result includes full bibliographic metadata, abstract when available, full-text links, and MeSH terms ([Europe PMC REST API](https://europepmc.org/RestfulWebService)). A numeric rate limit was not found in the official documentation reviewed here: treat it as **unknown**, use low concurrency, cache, honor `429`/`Retry-After`, and do not infer unlimited service. Full-text availability is not a reuse license; only the OA subset carries item-specific open licenses, which must be checked per article ([Europe PMC OA subset](https://europepmc.org/downloads/openaccess)).

### 3. arXiv ID

Use the exact `id_list`, not a title query:

```text
GET https://export.arxiv.org/api/query?id_list={arxiv_id}
```

The Atom entry supplies title, authors, abstract/summary, dates, categories, links, and arXiv extensions; `id_list` may include a version suffix when a specific version is required ([arXiv API manual](https://info.arxiv.org/help/api/user-manual.html)). arXiv permits descriptive metadata—including title, abstract, authors, identifiers, and classifications—under CC0, while e-print content remains under its item-level copyright/license. The legacy API limit is one request every three seconds over a single connection ([arXiv API terms](https://info.arxiv.org/help/api/tou.html)). Record whether the lookup used a versioned or latest ID.

### 4. DBLP key

Use the exact key already stored in `externalIds`:

```text
GET https://dblp.org/rec/{dblp_key}.xml
```

DBLP bibliographic metadata is CC0, and persistent record keys expose authors, title, venue, year, pages, and electronic-edition links ([DBLP data license](https://dblp.org/faq/1474677.html), [DBLP record/search API](https://dblp.org/faq/13501473.html)). DBLP intentionally does not provide abstracts because abstracts have the same copyright restrictions as full text ([DBLP abstract policy](https://dblp.org/faq/Why%2Bare%2Bthere%2Bno%2Babstracts%2Bin%2Bdblp)). Its official crawler guidance recommends waiting at least one or two seconds between requests and honoring `429` plus `Retry-After` ([DBLP crawling policy](https://dblp.org/faq/1474706.html)).

For the one DBLP-only row with corrupt abstract, `journals/jmlr/PerlichPS03` resolves through its DBLP electronic-edition link to the [official JMLR article page](https://www.jmlr.org/papers/v4/perlich03a.html), which contains the abstract and complete citation. This is a verified one-record authority path, not permission for generalized publisher scraping. The page's abstract reuse terms were not established in this audit, so license status remains unknown.

### 5. Optional CC0 cross-check, not source-of-record override

OpenAlex can batch exact DOI lookups (up to 100 OR values) and return normalized authorships, source, bibliographic fields, open-access/license signals, and external IDs:

```text
GET https://api.openalex.org/works
    ?filter=doi:https://doi.org/{doi1}|https://doi.org/{doi2}
    &per_page=100&select=...
```

OpenAlex recommends identifier filters and documents that its data is CC0. A free API key increases the daily budget, but current service limits/billing are dynamic; `429` can mean exceeding the daily budget or 100 requests/second, and clients should read the rate-limit headers ([OpenAlex API](https://help.openalex.org/api/), [authentication and limits](https://help.openalex.org/api/authentication/), [batch DOI recipe](https://help.openalex.org/how-to/api-recipes/)). Because OpenAlex aggregates and derives records, use it to detect conflicts or fill a field only when the source policy explicitly permits it. It must never silently override a matching registration-agency/NCBI/arXiv/DBLP record, and its text fields must be treated as untrusted input.

## Enrichment and validation rules implied by the evidence

1. Keep `data/raw/` immutable. Produce an enrichment sidecar and a frozen canonical corpus with separate hashes.
2. Deduplicate network requests by canonical paper, not by membership: enrich 2,525 unique papers, then attach immutable metadata to 2,296 target/reference memberships.
3. Use exact identifiers only. Normalize DOI case/URL prefix, then verify that the response identifier equals the request. Do not automatically fall back to title search.
4. Preserve every raw non-empty value. An enrichment conflict is evidence to record and review, not permission to overwrite.
5. Apply source precedence per field, not per whole record. A Crossref citation and a PubMed abstract can coexist if both exact IDs cross-check.
6. Record request URL, source identifier, retrieval time, HTTP status, response hash, selected field path, transformation, license basis, and validation outcome. Store failure responses and retry history without credentials.
7. Treat abstracts separately from bibliographic facts for licensing. `available via API` is not equivalent to `safe to redistribute`.
8. Canonicalize typed fields: integer year/count, boolean influence, sorted/deduplicated publication types, string external IDs, normalized retrieval text. Preserve raw values alongside the canonical projection.
9. Do not refresh dynamic citation counts inside an Ideation Run. If used at all, freeze the value and `observed_at` during preprocessing so replay is deterministic.
10. Validate each target's frozen membership hash before indexing and again before returning results. Global paper deduplication must not broaden the membership set.

## Confirmed, inferred, and unknown

### Confirmed

- The structural counts, missingness, duplicate/type/membership results, hashes, identifier coverage, and lexical counts in this report are direct computations over the three raw files.
- The 18 missing venues are fillable by exact DOI through Crossref (18/18 live checks on 2026-08-28).
- The corrupt PMID `21668448` abstract is available from Europe PMC; PMID `31373644` has no abstract there, and its DOI record has no Crossref abstract.
- The DBLP-only corrupt record has a full abstract on its exact official JMLR page.
- The cited API paths, rate/licensing constraints, and returned field descriptions come from first-party documentation linked beside each claim.

### Inference

- `abstract_summary` appears template/model-derived and is likely to leak target method/results if copied into a Workshop File. The provenance is absent, so only the surface evidence—not its generator—is confirmed.
- The eight cross-target reference reuses are legitimate shared citations because immutable metadata agrees and memberships differ. The original dataset construction policy is absent, so intent is inferred.
- The raw `contexts` and `intents` probably represent, respectively, multiple citation spans and a deduplicated set of intent labels. Their 584 cardinality mismatches make this plausible, but not confirmed.
- Complete bibliography output will require authors and conditional container details; local retrieval relevance itself does not require every citation field.

### Unknown / design blockers

- The authoritative origin, snapshot timestamp, and license/provenance of each raw field, including the abstracts and citation counts.
- The meaning of target `strategy` values (`1` for 229 rows, `2` for 8) and whether it changes Workshop derivation.
- Whether `contexts` and `intents` are allowed to be used as retrieval features, and whether their upstream semantics are set-level or positional.
- Whether a reference without an authoritatively available abstract should be excluded/fail closed or indexed using a separately evaluated title/context fallback.
- The required human citation style and whether full author lists, first author plus `et al.`, volume/issue/pages, and publisher are mandatory in the final compatible JSON or only in the evidence sidecar.
- Whether the project permits OpenAlex as a fallback/cross-check or restricts enrichment strictly to registration agencies and discipline repositories.
- The allowed storage/reuse policy for publisher/author-owned abstracts. This must be decided before committing enriched abstract text to Git; source availability alone is insufficient.

These unknowns block the canonical metadata/enrichment contract, but they do not block proving target/reference membership isolation or designing the exact-identifier fetch plan.
