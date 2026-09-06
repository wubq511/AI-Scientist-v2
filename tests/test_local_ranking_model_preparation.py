from __future__ import annotations

from pathlib import Path

import pytest

from prototypes.local_ranking.errors import HarnessError
from prototypes.local_ranking.prepare_model import (
    MODEL_FILES,
    MODEL_REVISION,
    WEIGHT_BYTES,
    WEIGHT_SHA256,
    _download_url,
    prepare_model,
)


def test_model_download_urls_are_commit_pinned() -> None:
    assert len(MODEL_FILES) == 6
    for filename in MODEL_FILES:
        url = _download_url(filename)
        assert f"/resolve/{MODEL_REVISION}/" in url
        assert "/main/" not in url
    assert WEIGHT_BYTES == 133_466_304
    assert WEIGHT_SHA256 == (
        "45bfa60070649aae2244fbc9d508537779b93b6f353c17b0f95ceccb1c5116c1"
    )


def test_manifest_cannot_pollute_the_model_allowlist_directory(tmp_path: Path) -> None:
    with pytest.raises(HarnessError) as raised:
        prepare_model(tmp_path, "model-files", "model-files/manifest.json")

    assert raised.value.code == "INVALID_PATH"
    assert not (tmp_path / "model-files").exists()


def test_model_preparation_never_reuses_an_existing_attempt(tmp_path: Path) -> None:
    (tmp_path / "model-files").mkdir()

    with pytest.raises(HarnessError) as raised:
        prepare_model(tmp_path, "model-files", "manifests/model.json")

    assert raised.value.code == "ARTIFACT_EXISTS"
