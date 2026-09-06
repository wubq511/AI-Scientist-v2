"""Deterministic Canary v1.1 case selection for Ticket 035.

Implements the constraint-driven 12-case Canary selection contract:
- 8 clusters full coverage
- Base 11 slots: Health & Medicine (2), Genetics & Molecular Biology (2),
  Neuroscience & Cognitive Sciences (2), and 1 from each of the other 5 clusters.
- 12th slot: constraint-driven edge slot assigned to the rarest unmet hard requirement.
- Hard requirements across the 12: min reference count (3), median reference count (7),
  max reference count (32), exactly three references, unavailable reference abstract (1),
  and strategy=2 target (1).
- Freshness: strictly excludes smoke case and formal local-ranking batches (24 targets).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any

from ai_scientist.ideation.canonical import (
    canonical_json_bytes,
    sha256_bytes,
)
from ai_scientist.ideation.errors import fail
from ai_scientist.ideation.schema import case_id as parse_case_id

SELECTION_VERSION = "canary-case-selection-v1.1"
SELECTION_MANIFEST_SCHEMA = "canary-case-selection-manifest-v1.1"

BASE_CLUSTER_QUOTAS: dict[str, int] = {
    "Environmental Sciences": 1,
    "Genetics & Molecular Biology": 2,
    "Health & Medicine": 2,
    "Materials Science": 1,
    "Neuroscience & Cognitive Sciences": 2,
    "Public Health & Policy": 1,
    "Social & Behavioral Sciences": 1,
    "Technology & Engineering": 1,
}

EXPECTED_SPENT_COUNT = 24


@dataclass(frozen=True)
class CanaryCandidate:
    target_id: str
    cluster: str
    strategy: int
    ref_count: int
    has_unavail_abstract: bool
    key: str
    case_id: str
    target_row_number: int
    target_row_sha256: str


@dataclass(frozen=True)
class SelectedCanaryCase:
    slot_index: int
    role: str  # "base_slot" or "constraint_driven_edge_slot"
    case_id: str
    cluster: str
    ref_count: int
    strategy: int
    has_unavail_abstract: bool
    target_id: str
    target_row_number: int
    target_row_sha256: str
    edge_tags: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "cluster": self.cluster,
            "edge_tags": list(self.edge_tags),
            "has_unavail_abstract": self.has_unavail_abstract,
            "ref_count": self.ref_count,
            "role": self.role,
            "slot_index": self.slot_index,
            "strategy": self.strategy,
            "target_id": self.target_id,
            "target_row_number": self.target_row_number,
            "target_row_sha256": self.target_row_sha256,
        }

    def to_sanitized_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "cluster": self.cluster,
            "edge_tags": list(self.edge_tags),
            "has_unavail_abstract": self.has_unavail_abstract,
            "ref_count": self.ref_count,
            "role": self.role,
            "slot_index": self.slot_index,
            "strategy": self.strategy,
        }


def load_spent_target_ids(workspace_root: Path) -> set[str]:
    spent: set[str] = set()

    # 1. Smoke case
    smoke_prep_path = (
        workspace_root
        / "artifacts"
        / "ideation-inputs"
        / "workshops"
        / "case-229e495f82a24cff9e6082aa058955b9"
        / "preparations"
        / "preparation-001"
        / "preparation-manifest.json"
    )
    if smoke_prep_path.is_file():
        smoke_data = json.loads(smoke_prep_path.read_text(encoding="utf-8"))
        spent.add(smoke_data["target_identity"]["paper_id"])

    # 2. Local-ranking dev & holdout
    dev_hol_path = (
        workspace_root
        / "artifacts"
        / "local-ranking-prototype"
        / "input-preparation-v1"
        / "attempts"
        / "inputs-008-replay"
        / "selection-manifest.json"
    )
    if dev_hol_path.is_file():
        dev_hol_data = json.loads(dev_hol_path.read_text(encoding="utf-8"))
        for c in dev_hol_data.get("cases", []):
            spent.add(c["target_paper_id"])

    # 3. Local-ranking operational
    op_path = (
        workspace_root
        / "artifacts"
        / "local-ranking-prototype"
        / "operational-input-v1"
        / "attempts"
        / "operational-inputs-003-replay"
        / "selection-manifest.json"
    )
    if op_path.is_file():
        op_data = json.loads(op_path.read_text(encoding="utf-8"))
        for c in op_data.get("cases", []):
            spent.add(c["target_paper_id"])

    if len(spent) != EXPECTED_SPENT_COUNT:
        fail(
            "SPENT_SET_MISMATCH",
            f"Expected exactly {EXPECTED_SPENT_COUNT} spent targets, found {len(spent)}",
            found=len(spent),
            expected=EXPECTED_SPENT_COUNT,
        )
    return spent


def select_canary_v11_cases(
    workspace_root: Path,
    *,
    source_root: str = "data/raw",
    authority_path: str = "ai_scientist/ideation/policies/reference-authority-v1.json",
) -> tuple[SelectedCanaryCase, ...]:
    raw_dir = workspace_root / source_root
    target_path = raw_dir / "target_papers.csv"
    ref_path = raw_dir / "filtered_references.csv"
    cluster_path = raw_dir / "ideabench_clustering.json"
    auth_file = workspace_root / authority_path

    for path in (target_path, ref_path, cluster_path, auth_file):
        if not path.is_file():
            fail("MISSING_SOURCE", f"Required input file missing: {path}")

    target_bytes = target_path.read_bytes()
    ref_bytes = ref_path.read_bytes()
    cluster_bytes = cluster_path.read_bytes()
    auth_bytes = auth_file.read_bytes()

    source_hashes = {
        "filtered_references.csv": sha256_bytes(ref_bytes),
        "ideabench_clustering.json": sha256_bytes(cluster_bytes),
        "reference-authority-v1.json": sha256_bytes(auth_bytes),
        "target_papers.csv": sha256_bytes(target_bytes),
    }

    targets = list(csv.DictReader(target_bytes.decode("utf-8").splitlines()))
    refs = list(csv.DictReader(ref_bytes.decode("utf-8").splitlines()))
    cluster_map: dict[str, list[str]] = json.loads(cluster_bytes.decode("utf-8"))
    auth_policy: dict[str, Any] = json.loads(auth_bytes.decode("utf-8"))["records"]

    spent_target_ids = load_spent_target_ids(workspace_root)
    spent_sha256 = hashlib.sha256(
        "".join(sorted(spent_target_ids)).encode()
    ).hexdigest()

    sorted_source_hashes = "|".join(
        f"{k}:{source_hashes[k]}" for k in sorted(source_hashes)
    )
    seed = f"{SELECTION_VERSION}|{spent_sha256}|{sorted_source_hashes}"

    target_to_cluster: dict[str, str] = {}
    for cluster, pids in cluster_map.items():
        for pid in pids:
            target_to_cluster[pid] = cluster

    target_refs: dict[str, list[dict[str, str]]] = {}
    for r in refs:
        target_refs.setdefault(r["targetPaperId"], []).append(r)

    # Compute target row sha256
    target_row_hashes: dict[str, str] = {}
    target_row_numbers: dict[str, int] = {}
    for row_num, t in enumerate(targets, start=1):
        pid = t["paperId"]
        target_row_numbers[pid] = row_num
        row_norm = {k: v for k, v in t.items() if k is not None}
        target_row_hashes[pid] = sha256_bytes(canonical_json_bytes(row_norm))

    fresh_targets = [t for t in targets if t["paperId"] not in spent_target_ids]
    if len(fresh_targets) != 213:
        fail(
            "FRESH_POPULATION_MISMATCH",
            f"Expected 213 fresh targets, got {len(fresh_targets)}",
        )

    candidates: list[CanaryCandidate] = []
    for t in fresh_targets:
        pid = t["paperId"]
        cl = target_to_cluster[pid]
        strat = int(t["strategy"])
        rc = len(target_refs[pid])
        has_unavail = False
        for r in target_refs[pid]:
            r_pid = r["paperId"]
            if (
                r_pid in auth_policy
                and auth_policy[r_pid].get("abstract_status") == "not_published"
            ):
                has_unavail = True
                break
            if not r.get("abstract", "").strip():
                has_unavail = True
                break

        key = hashlib.sha256(f"{seed}|{pid}".encode()).hexdigest()
        case_digest = hashlib.sha256(f"{seed}|case_id|{pid}".encode()).hexdigest()[:32]
        c_id = f"case-{case_digest}"
        parse_case_id(c_id)

        candidates.append(
            CanaryCandidate(
                target_id=pid,
                cluster=cl,
                strategy=strat,
                ref_count=rc,
                has_unavail_abstract=has_unavail,
                key=key,
                case_id=c_id,
                target_row_number=target_row_numbers[pid],
                target_row_sha256=target_row_hashes[pid],
            )
        )

    ref_counts = [c.ref_count for c in candidates]
    min_ref = min(ref_counts)
    max_ref = max(ref_counts)
    med_ref = int(statistics.median(ref_counts))

    if min_ref != 3 or max_ref != 32 or med_ref != 7:
        fail(
            "POPULATION_STATS_MISMATCH",
            f"Expected min=3, med=7, max=32; got min={min_ref}, med={med_ref}, max={max_ref}",
        )

    by_cluster: dict[str, list[CanaryCandidate]] = {}
    for c in candidates:
        by_cluster.setdefault(c.cluster, []).append(c)
    for cl in by_cluster:
        by_cluster[cl].sort(key=lambda item: item.key)

    # 1. Base 11 selection
    base_11: list[CanaryCandidate] = []

    # Environmental Sciences (1)
    base_11.append(by_cluster["Environmental Sciences"][0])

    # Genetics & Molecular Biology (2): 1 max_ref (32) + 1 canonical first
    gen_max = [
        c for c in by_cluster["Genetics & Molecular Biology"] if c.ref_count == 32
    ][0]
    gen_other = [
        c
        for c in by_cluster["Genetics & Molecular Biology"]
        if c.target_id != gen_max.target_id
    ][0]
    base_11.extend([gen_other, gen_max])

    # Health & Medicine (2): 1 strategy=2 + 1 canonical first other (not unavail)
    health_strat2 = [c for c in by_cluster["Health & Medicine"] if c.strategy == 2][0]
    health_other = [
        c
        for c in by_cluster["Health & Medicine"]
        if c.target_id != health_strat2.target_id and not c.has_unavail_abstract
    ][0]
    base_11.extend([health_strat2, health_other])

    # Materials Science (1)
    base_11.append(by_cluster["Materials Science"][0])

    # Neuroscience & Cognitive Sciences (2)
    base_11.extend(by_cluster["Neuroscience & Cognitive Sciences"][:2])

    # Public Health & Policy (1)
    base_11.append(by_cluster["Public Health & Policy"][0])

    # Social & Behavioral Sciences (1)
    base_11.append(by_cluster["Social & Behavioral Sciences"][0])

    # Technology & Engineering (1)
    base_11.append(by_cluster["Technology & Engineering"][0])

    if len(base_11) != 11:
        fail(
            "BASE_SELECTION_FAILED", f"Base slots count is {len(base_11)}, expected 11"
        )

    # 2. Check unmet requirements on base 11
    has_min = any(c.ref_count == min_ref for c in base_11)
    has_med = any(c.ref_count == med_ref for c in base_11)
    has_max = any(c.ref_count == max_ref for c in base_11)
    has_3ref = any(c.ref_count == 3 for c in base_11)
    has_unavail = any(c.has_unavail_abstract for c in base_11)
    has_strat2 = any(c.strategy == 2 for c in base_11)

    if not (has_min and has_med and has_max and has_3ref and has_strat2):
        fail(
            "BASE_REQUIREMENT_DEFICIT",
            "Base 11 slots must satisfy all edge requirements except at most one",
            has_min=has_min,
            has_med=has_med,
            has_max=has_max,
            has_3ref=has_3ref,
            has_strat2=has_strat2,
        )

    if has_unavail:
        fail(
            "UNEXPECTED_COVERAGE", "Unavailable abstract was already covered in base 11"
        )

    # 3. 12th slot: constraint-driven edge slot for rarest unmet requirement
    unavail_candidates = [c for c in candidates if c.has_unavail_abstract]
    if len(unavail_candidates) != 1:
        fail(
            "UNAVAIL_CANDIDATES_COUNT_MISMATCH",
            f"Expected exactly 1 unavail candidate, found {len(unavail_candidates)}",
        )
    slot_12 = unavail_candidates[0]

    all_12 = base_11 + [slot_12]

    # Verify no duplicate targets or cases
    selected_target_ids = [c.target_id for c in all_12]
    if len(set(selected_target_ids)) != 12:
        fail("DUPLICATE_SELECTION", "Selected 12 cases contain duplicate targets")

    result: list[SelectedCanaryCase] = []
    for idx, c in enumerate(all_12, start=1):
        role = "base_slot" if idx <= 11 else "constraint_driven_edge_slot"
        edge_tags: list[str] = []
        if c.ref_count == 3:
            edge_tags.append("min_ref(3)")
        if c.ref_count == 7:
            edge_tags.append("median_ref(7)")
        if c.ref_count == 8:
            edge_tags.append("dataset_median_ref(8)")
        if c.ref_count == 32:
            edge_tags.append("max_ref(32)")
        if c.strategy == 2:
            edge_tags.append("strategy=2")
        if c.has_unavail_abstract:
            edge_tags.append("unavailable_reference_abstract")

        result.append(
            SelectedCanaryCase(
                slot_index=idx,
                role=role,
                case_id=c.case_id,
                cluster=c.cluster,
                ref_count=c.ref_count,
                strategy=c.strategy,
                has_unavail_abstract=c.has_unavail_abstract,
                target_id=c.target_id,
                target_row_number=c.target_row_number,
                target_row_sha256=c.target_row_sha256,
                edge_tags=tuple(edge_tags),
            )
        )

    return tuple(result)


def build_selection_manifest(
    workspace_root: Path,
    selected: tuple[SelectedCanaryCase, ...],
) -> dict[str, Any]:
    spent_target_ids = load_spent_target_ids(workspace_root)
    spent_sha256 = hashlib.sha256(
        "".join(sorted(spent_target_ids)).encode()
    ).hexdigest()

    raw_dir = workspace_root / "data" / "raw"
    source_hashes = {
        "filtered_references.csv": sha256_bytes(
            (raw_dir / "filtered_references.csv").read_bytes()
        ),
        "ideabench_clustering.json": sha256_bytes(
            (raw_dir / "ideabench_clustering.json").read_bytes()
        ),
        "reference-authority-v1.json": sha256_bytes(
            (
                workspace_root
                / "ai_scientist"
                / "ideation"
                / "policies"
                / "reference-authority-v1.json"
            ).read_bytes()
        ),
        "target_papers.csv": sha256_bytes((raw_dir / "target_papers.csv").read_bytes()),
    }

    return {
        "cases": [c.to_dict() for c in selected],
        "cluster_distribution": {
            cluster: sum(1 for c in selected if c.cluster == cluster)
            for cluster in sorted({c.cluster for c in selected})
        },
        "eligible_case_count": 237,
        "excluded_spent_case_count": len(spent_target_ids),
        "fresh_candidate_count": 213,
        "schema_version": SELECTION_MANIFEST_SCHEMA,
        "selection_version": SELECTION_VERSION,
        "source_hashes": source_hashes,
        "spent_sha256": spent_sha256,
    }


def generate_sanitized_summary_table(selected: tuple[SelectedCanaryCase, ...]) -> str:
    lines = [
        "| Slot | Case ID | Role | Scientific Domain (Cluster) | Reference Count | Edge Properties |",
        "|---|---|---|---|---|---|",
    ]
    for c in selected:
        tag_str = ", ".join(c.edge_tags) if c.edge_tags else "standard"
        lines.append(
            f"| {c.slot_index:02d} | `{c.case_id}` | `{c.role}` | {c.cluster} | {c.ref_count} | {tag_str} |"
        )
    return "\n".join(lines)
