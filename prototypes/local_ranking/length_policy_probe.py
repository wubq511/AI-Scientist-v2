from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .canonical import canonical_json_bytes, sha256_bytes, write_json_once
from .errors import HarnessError, fail

SCHEMA_VERSION = "local-ranking-length-policy-probe-v1"
MODEL_ID = "intfloat/e5-small-v2"
MODEL_REVISION = "ffb93f3bd4047442299a41ebb6fa998a38507c52"
TOKENIZER_JSON_SHA256 = (
    "d241a60d5e8f04cc1b2b3e9ef7a4921b27bf526d9f6050ab90f9267a1f9e5c66"
)
TOKENIZERS_VERSION = "0.23.1"
PASSAGE_PREFIX = "passage: "
MAX_INPUT_TOKENS = 512
WHITESPACE = re.compile(r"\s+")
SENTENCE_TERMINALS = frozenset(".!?")
TRAILING_CLOSERS = "\"'”’)]}"


def _sentence_boundaries(text: str) -> tuple[int, ...]:
    boundaries: list[int] = []
    for match in WHITESPACE.finditer(text):
        before = text[: match.start()].rstrip(TRAILING_CLOSERS)
        if before and before[-1] in SENTENCE_TERMINALS:
            boundaries.append(match.end())
    if not boundaries or boundaries[-1] != len(text):
        boundaries.append(len(text))
    return tuple(boundaries)


def _whitespace_boundaries(text: str) -> tuple[int, ...]:
    boundaries = [match.end() for match in WHITESPACE.finditer(text)]
    if not boundaries or boundaries[-1] != len(text):
        boundaries.append(len(text))
    return tuple(boundaries)


def _furthest_fitting(
    text: str,
    start: int,
    boundaries: tuple[int, ...],
    token_length: Callable[[str], int],
    maximum: int,
) -> int | None:
    fitting = [
        end
        for end in boundaries
        if end > start and token_length(text[start:end]) <= maximum
    ]
    return max(fitting, default=None)


def segment_source_text(
    text: str,
    token_length: Callable[[str], int],
    *,
    maximum: int = MAX_INPUT_TOKENS,
) -> tuple[tuple[int, int, str], ...]:
    if not text:
        fail("INVALID_ABSTRACT", "Abstract text must be non-empty")
    if token_length(text) <= maximum:
        return ((0, len(text), text),)

    sentence_boundaries = _sentence_boundaries(text)
    whitespace_boundaries = _whitespace_boundaries(text)
    segments: list[tuple[int, int, str]] = []
    start = 0
    while start < len(text):
        end = _furthest_fitting(text, start, sentence_boundaries, token_length, maximum)
        if end is None:
            end = _furthest_fitting(
                text, start, whitespace_boundaries, token_length, maximum
            )
        if end is None:
            for candidate in range(start + 1, len(text) + 1):
                if token_length(text[start:candidate]) <= maximum:
                    end = candidate
        if end is None or end <= start:
            fail(
                "UNSPLITTABLE_ABSTRACT",
                "No non-empty source span fits the pinned tokenizer limit",
                source_start=start,
            )
        segment = text[start:end]
        if not segment:
            fail("EMPTY_SEGMENT", "Length policy emitted an empty segment")
        segments.append((start, end, segment))
        start = end

    if "".join(segment for _, _, segment in segments) != text:
        fail("NON_REVERSIBLE_SEGMENTATION", "Segments do not reconstruct source")
    return tuple(segments)


def _percentile(values: list[int], probability: float) -> int:
    ordered = sorted(values)
    index = max(0, math.ceil(probability * len(ordered)) - 1)
    return ordered[index]


def _load_approved_abstracts(
    approval_root: Path, corpora_root: Path
) -> tuple[list[tuple[str, str, str]], str]:
    approved_path = approval_root / "approved-corpora.json"
    approved_bytes = approved_path.read_bytes()
    try:
        approved = json.loads(approved_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        fail("INVALID_APPROVAL", "approved-corpora.json is invalid", error=str(exc))
    if not isinstance(approved, dict) or not isinstance(approved.get("corpora"), list):
        fail("INVALID_APPROVAL", "approved-corpora.json has an invalid schema")
    if (
        not isinstance(approved.get("case_count"), int)
        or approved["case_count"] < 1
        or len(approved["corpora"]) != approved["case_count"]
    ):
        fail("INVALID_APPROVAL", "Approved case count is inconsistent")

    abstracts: list[tuple[str, str, str]] = []
    for corpus_entry in approved["corpora"]:
        if not isinstance(corpus_entry, dict):
            fail("INVALID_APPROVAL", "Approved corpus entry must be an object")
        case_id = corpus_entry.get("case_id")
        expected_hash = corpus_entry.get("corpus_sha256")
        expected_count = corpus_entry.get("record_count")
        if (
            not isinstance(case_id, str)
            or not isinstance(expected_hash, str)
            or not isinstance(expected_count, int)
            or expected_count < 1
        ):
            fail("INVALID_APPROVAL", "Approved corpus identity is invalid")
        corpus_path = corpora_root / case_id / "corpus.json"
        corpus_bytes = corpus_path.read_bytes()
        if sha256_bytes(corpus_bytes) != expected_hash:
            fail("CORPUS_DRIFT", "Approved corpus hash changed", case_id=case_id)
        try:
            corpus = json.loads(corpus_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            fail("INVALID_CORPUS", "corpus.json is invalid", error=str(exc))
        records = corpus.get("records") if isinstance(corpus, dict) else None
        if not isinstance(records, list) or len(records) != expected_count:
            fail("INVALID_CORPUS", "Approved record count changed", case_id=case_id)
        for record in records:
            if not isinstance(record, dict) or not isinstance(
                record.get("paper_id"), str
            ):
                fail("INVALID_CORPUS", "Paper record is invalid", case_id=case_id)
            items = record.get("content_items")
            if not isinstance(items, list) or len(items) != 1:
                fail(
                    "INVALID_CORPUS",
                    "v1.1 requires exactly one content item per paper",
                    case_id=case_id,
                )
            item = items[0]
            if (
                not isinstance(item, dict)
                or item.get("type") != "publisher_abstract"
                or item.get("status") != "validated"
                or not isinstance(item.get("text"), str)
                or not item["text"]
            ):
                fail(
                    "INVALID_CORPUS",
                    "Formal content must be a validated publisher abstract",
                    case_id=case_id,
                )
            abstracts.append((case_id, record["paper_id"], item["text"]))
    if not abstracts:
        fail("INVALID_APPROVAL", "Approval contains no abstracts")
    return abstracts, sha256_bytes(approved_bytes)


def run_probe(
    *, approval_root: Path, corpora_root: Path, tokenizer_json: Path
) -> dict[str, Any]:
    try:
        import tokenizers
        from tokenizers import Tokenizer
    except ImportError as exc:
        fail(
            "MISSING_DEPENDENCY",
            "Run the probe with the pinned tokenizers package",
            error=str(exc),
        )
    tokenizer_bytes = tokenizer_json.read_bytes()
    tokenizer_hash = sha256_bytes(tokenizer_bytes)
    if tokenizer_hash != TOKENIZER_JSON_SHA256:
        fail(
            "TOKENIZER_HASH_MISMATCH",
            "Tokenizer bytes differ from the pinned E5 revision",
            expected=TOKENIZER_JSON_SHA256,
            actual=tokenizer_hash,
        )
    if tokenizers.__version__ != TOKENIZERS_VERSION:
        fail(
            "DEPENDENCY_VERSION_MISMATCH",
            "tokenizers version differs from the frozen length probe",
            expected=TOKENIZERS_VERSION,
            actual=tokenizers.__version__,
        )
    tokenizer = Tokenizer.from_file(str(tokenizer_json))
    truncating_tokenizer = Tokenizer.from_file(str(tokenizer_json))
    truncating_tokenizer.enable_truncation(max_length=MAX_INPUT_TOKENS)

    def token_length(text: str) -> int:
        return len(tokenizer.encode(PASSAGE_PREFIX + text).ids)

    abstracts, approved_hash = _load_approved_abstracts(approval_root, corpora_root)
    full_lengths: list[int] = []
    segment_lengths: list[int] = []
    overflow_cases: set[str] = set()
    segment_histogram: Counter[int] = Counter()
    removed_characters = 0
    removed_tokens = 0
    segment_records: list[dict[str, Any]] = []

    for case_id, paper_id, text in abstracts:
        full_length = token_length(text)
        full_lengths.append(full_length)
        if full_length > MAX_INPUT_TOKENS:
            overflow_cases.add(case_id)
            removed_tokens += full_length - MAX_INPUT_TOKENS
            truncated = truncating_tokenizer.encode(PASSAGE_PREFIX + text)
            retained_input_end = max(
                (end for start, end in truncated.offsets), default=0
            )
            retained_abstract_characters = max(
                0, retained_input_end - len(PASSAGE_PREFIX)
            )
            removed_characters += len(text) - retained_abstract_characters

        first = segment_source_text(text, token_length)
        second = segment_source_text(text, token_length)
        if first != second:
            fail("NON_DETERMINISTIC_SEGMENTATION", "Repeated segmentation changed")
        if "".join(segment for _, _, segment in first) != text:
            fail("NON_REVERSIBLE_SEGMENTATION", "Segments do not reconstruct source")
        lengths = [token_length(segment) for _, _, segment in first]
        if any(length > MAX_INPUT_TOKENS for length in lengths):
            fail("SEGMENT_TOO_LONG", "Segment exceeds pinned tokenizer limit")
        segment_lengths.extend(lengths)
        segment_histogram[len(first)] += 1
        segment_records.append(
            {
                "case_id": case_id,
                "paper_id_sha256": sha256_bytes(paper_id.encode("utf-8")),
                "source_sha256": sha256_bytes(text.encode("utf-8")),
                "full_input_tokens": full_length,
                "segments": [
                    {
                        "source_start": start,
                        "source_end": end,
                        "input_tokens": length,
                        "text_sha256": sha256_bytes(segment.encode("utf-8")),
                    }
                    for (start, end, segment), length in zip(
                        first, lengths, strict=True
                    )
                ],
            }
        )

    segmentation_hash = sha256_bytes(canonical_json_bytes(segment_records))
    overflow_count = sum(length > MAX_INPUT_TOKENS for length in full_lengths)
    return {
        "schema_version": SCHEMA_VERSION,
        "input": {
            "approved_corpora_sha256": approved_hash,
            "case_count": len({case_id for case_id, _, _ in abstracts}),
            "paper_count": len(abstracts),
        },
        "tokenizer": {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "tokenizer_json_sha256": tokenizer_hash,
            "tokenizers_version": tokenizers.__version__,
            "passage_prefix": PASSAGE_PREFIX,
            "maximum_input_tokens": MAX_INPUT_TOKENS,
            "special_tokens_included": True,
        },
        "full_abstract_inputs": {
            "minimum_tokens": min(full_lengths),
            "p50_tokens": _percentile(full_lengths, 0.50),
            "p95_tokens": _percentile(full_lengths, 0.95),
            "maximum_tokens": max(full_lengths),
            "within_limit_count": len(full_lengths) - overflow_count,
            "overflow_count": overflow_count,
            "overflow_case_count": len(overflow_cases),
            "overflow_cases": sorted(overflow_cases),
        },
        "candidate_b_truncation": {
            "affected_paper_count": overflow_count,
            "removed_source_characters": removed_characters,
            "removed_input_tokens": removed_tokens,
            "source_complete": removed_characters == 0,
        },
        "candidate_c_segmentation": {
            "status": "pass",
            "paper_count": len(abstracts),
            "changed_paper_count": overflow_count,
            "total_segment_count": len(segment_lengths),
            "segments_per_paper_histogram": {
                str(count): papers
                for count, papers in sorted(segment_histogram.items())
            },
            "maximum_segment_input_tokens": max(segment_lengths),
            "empty_segment_count": 0,
            "uncovered_source_characters": 0,
            "overlap_source_characters": 0,
            "reconstruction_failure_count": 0,
            "repeatable": True,
            "segmentation_sha256": segmentation_hash,
        },
        "private_records": segment_records,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Probe the E5 length policy without running a ranker"
    )
    parser.add_argument("--approval-root", type=Path, required=True)
    parser.add_argument("--corpora-root", type=Path, required=True)
    parser.add_argument("--tokenizer-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = run_probe(
            approval_root=args.approval_root,
            corpora_root=args.corpora_root,
            tokenizer_json=args.tokenizer_json,
        )
        write_json_once(args.output, result)
    except (HarnessError, FileNotFoundError, OSError, ValueError) as exc:
        if isinstance(exc, HarnessError):
            print(json.dumps(exc.to_dict(), sort_keys=True))
        else:
            print(json.dumps({"code": "PROBE_FAILED", "message": str(exc)}))
        return 2
    print(json.dumps({"status": "success", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
