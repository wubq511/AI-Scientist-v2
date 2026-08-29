from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.schema import (
    parse_protocol,
    parse_qrels,
    parse_ranking_input,
)

FIXTURES = Path("prototypes/local_ranking/fixtures")


def _json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def test_fixture_contract_is_complete_and_closed() -> None:
    ranking_input = parse_ranking_input(_json("input.json"))
    protocol = parse_protocol(_json("protocol.json"))
    qrels = parse_qrels(_json("qrels.json"), ranking_input)

    assert protocol.protocol_version == "1.0.0"
    assert len(ranking_input.queries) == 2
    assert len(qrels.paper_grades) == 6
    assert len(qrels.segment_grades) == 3


def test_forbidden_metadata_cannot_reach_a_scorer() -> None:
    value = _json("input.json")
    value["cases"][0]["papers"][0]["citation_count"] = 999

    with pytest.raises(HarnessError) as raised:
        parse_ranking_input(value)

    assert raised.value.code == "INVALID_SCHEMA"
    assert "citation_count" in raised.value.details["unknown"]


def test_unapproved_content_type_is_a_boundary_violation() -> None:
    value = _json("input.json")
    value["cases"][0]["papers"][0]["segments"][0]["content_type"] = "derived_text"

    with pytest.raises(HarnessError) as raised:
        parse_ranking_input(value)

    assert raised.value.code == "BOUNDARY_VIOLATION"


def test_incomplete_qrels_are_rejected() -> None:
    ranking_input = parse_ranking_input(_json("input.json"))
    value = _json("qrels.json")
    value["paper_judgments"].pop()

    with pytest.raises(HarnessError) as raised:
        parse_qrels(value, ranking_input)

    assert raised.value.code == "INCOMPLETE_QRELS"


def test_formal_protocol_must_enforce_reference_runtime() -> None:
    value = _json("protocol.json")
    value["split"] = "development"
    value["runtime"]["enforce_reference_runtime"] = False

    with pytest.raises(HarnessError) as raised:
        parse_protocol(value)

    assert raised.value.code == "PROTOCOL_DEVIATION"


def test_rrf_sources_must_precede_the_fusion_candidate() -> None:
    value = _json("protocol.json")
    rrf = copy.deepcopy(value["candidates"][-1])
    value["candidates"] = [rrf, *value["candidates"][:-1]]

    with pytest.raises(HarnessError) as raised:
        parse_protocol(value)

    assert raised.value.code == "INVALID_SCHEMA"
