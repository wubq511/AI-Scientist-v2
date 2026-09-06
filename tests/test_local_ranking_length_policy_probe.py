from itertools import pairwise

from prototypes.local_ranking.length_policy_probe import segment_source_text


def _character_tokens(text: str) -> int:
    return len(text) + 4


def test_within_limit_abstract_is_unchanged() -> None:
    text = "A short source abstract."

    assert segment_source_text(text, _character_tokens, maximum=40) == (
        (0, len(text), text),
    )


def test_overflow_prefers_sentence_boundaries_and_reconstructs_source() -> None:
    text = "One. Two. Three."

    segments = segment_source_text(text, _character_tokens, maximum=14)

    assert [segment for _, _, segment in segments] == ["One. Two. ", "Three."]
    assert "".join(segment for _, _, segment in segments) == text
    assert all(
        end == next_start for (_, end, _), (next_start, _, _) in pairwise(segments)
    )
    assert all(_character_tokens(segment) <= 14 for _, _, segment in segments)


def test_overlong_sentence_falls_back_without_loss_or_overlap() -> None:
    text = "abcdefghijk"

    first = segment_source_text(text, _character_tokens, maximum=10)
    second = segment_source_text(text, _character_tokens, maximum=10)

    assert first == second
    assert [segment for _, _, segment in first] == ["abcdef", "ghijk"]
    assert "".join(segment for _, _, segment in first) == text
    assert first[0][1] == first[1][0]
