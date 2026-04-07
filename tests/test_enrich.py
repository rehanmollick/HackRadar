"""tests/test_enrich.py — Unit tests for hackradar.enrich.

GitHub is mocked at the PyGithub level (github.Github).
HuggingFace is mocked at the huggingface_hub level (HfApi).
"""

from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch, PropertyMock

from hackradar.models import Item
from hackradar import config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(
    title: str = "Test Project",
    github_url: str | None = None,
    huggingface_url: str | None = None,
) -> Item:
    return Item(
        title=title,
        description="A test item for enrichment.",
        date=datetime(2026, 3, 27),
        source="test_source",
        source_url="https://example.com/test",
        category="ai_research",
        github_url=github_url,
        huggingface_url=huggingface_url,
    )


def _make_mock_repo(
    stars: int = 1234,
    language: str = "Python",
    license_spdx: str = "MIT",
    readme_text: str = "# My Model\nAn impressive open-source model.",
) -> MagicMock:
    """Build a realistic PyGithub repo mock."""
    repo = MagicMock()
    repo.stargazers_count = stars
    repo.language = language

    license_obj = MagicMock()
    license_obj.spdx_id = license_spdx
    license_obj.name = license_spdx
    repo.license = license_obj

    readme = MagicMock()
    readme.decoded_content = readme_text.encode("utf-8")
    repo.get_readme.return_value = readme

    return repo


def _make_mock_model_info(
    downloads: int = 50000,
    param_total: int = 7_000_000_000,  # 7B
    card_data: dict | None = None,
) -> MagicMock:
    """Build a realistic huggingface_hub model_info mock."""
    model_info = MagicMock()
    model_info.downloads = downloads

    safetensors = MagicMock()
    safetensors.total = param_total
    model_info.safetensors = safetensors
    model_info.cardData = card_data or {}

    return model_info


def _make_mock_space(space_id: str, card_models: list[str] | None = None) -> MagicMock:
    space = MagicMock()
    space.id = space_id
    space.cardData = {"models": card_models} if card_models else {}
    return space


# ---------------------------------------------------------------------------
# Test 1: GitHub repo exists → enrichment fields populated
# ---------------------------------------------------------------------------

def test_github_enrichment_populates_fields():
    """When PyGithub returns a valid repo, stars/language/license/readme are set."""
    item = _make_item(
        title="TRIBE v2",
        github_url="https://github.com/facebookresearch/tribev2",
    )

    mock_repo = _make_mock_repo(
        stars=842,
        language="Python",
        license_spdx="MIT",
        readme_text="# TRIBE v2\nBrain activity prediction model.",
    )
    mock_gh = MagicMock()
    mock_gh.get_repo.return_value = mock_repo

    with patch.object(config, "GITHUB_TOKEN", "fake-token"), \
         patch("github.Github", return_value=mock_gh):
        from hackradar.enrich import enrich_items
        result = enrich_items([item])

    assert len(result) == 1
    enriched = result[0]
    assert enriched.stars == 842
    assert enriched.language == "Python"
    assert enriched.license == "MIT"
    assert enriched.readme_excerpt is not None
    assert "TRIBE v2" in enriched.readme_excerpt


# ---------------------------------------------------------------------------
# Test 2: GitHub repo 404 → fields stay None, no exception raised
# ---------------------------------------------------------------------------

def test_github_404_leaves_fields_none():
    """A 404 from PyGithub must leave all enrichment fields as None."""
    from github import GithubException  # real exception class used by PyGithub

    item = _make_item(
        title="Missing Repo",
        github_url="https://github.com/nobody/doesnotexist",
    )

    mock_gh = MagicMock()
    exc = GithubException(404, {"message": "Not Found"}, headers=None)
    mock_gh.get_repo.side_effect = exc

    with patch.object(config, "GITHUB_TOKEN", "fake-token"), \
         patch("github.Github", return_value=mock_gh):
        from hackradar.enrich import enrich_items
        result = enrich_items([item])  # must not raise

    enriched = result[0]
    assert enriched.stars is None
    assert enriched.language is None
    assert enriched.license is None
    assert enriched.readme_excerpt is None


# ---------------------------------------------------------------------------
# Test 3: GitHub rate-limit (403) → skip enrichment, log warning
# ---------------------------------------------------------------------------

def test_github_rate_limit_skips_enrichment(caplog):
    """A 403 from PyGithub (rate-limit) must skip enrichment gracefully."""
    import logging
    from github import GithubException

    item = _make_item(
        title="Rate-Limited Repo",
        github_url="https://github.com/facebookresearch/some-model",
    )

    mock_gh = MagicMock()
    exc = GithubException(403, {"message": "rate limit exceeded"}, headers=None)
    mock_gh.get_repo.side_effect = exc

    with patch.object(config, "GITHUB_TOKEN", "fake-token"), \
         patch("github.Github", return_value=mock_gh), \
         caplog.at_level(logging.WARNING, logger="hackradar.enrich"):
        from hackradar.enrich import enrich_items
        result = enrich_items([item])  # must not raise

    # Fields stay None
    enriched = result[0]
    assert enriched.stars is None

    # A rate-limit warning must have been emitted
    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("rate" in str(m).lower() or "rate-limit" in str(m).lower() for m in warning_messages), \
        f"Expected rate-limit warning, got: {warning_messages}"


# ---------------------------------------------------------------------------
# Test 4: HuggingFace model exists → downloads and model_size populated
# ---------------------------------------------------------------------------

def test_huggingface_enrichment_populates_fields():
    """When HfApi.model_info returns data, downloads and model_size are set."""
    item = _make_item(
        title="TRIBE v2",
        huggingface_url="https://huggingface.co/facebook/tribev2",
    )

    mock_model_info = _make_mock_model_info(downloads=12345, param_total=7_000_000_000)
    mock_api = MagicMock()
    mock_api.model_info.return_value = mock_model_info
    mock_api.list_spaces.return_value = []  # no demo spaces

    with patch("huggingface_hub.HfApi", return_value=mock_api):
        from hackradar.enrich import enrich_items
        result = enrich_items([item])

    enriched = result[0]
    assert enriched.downloads == 12345
    assert enriched.model_size is not None
    assert "7" in enriched.model_size  # "7.0B params"
    assert "B" in enriched.model_size


# ---------------------------------------------------------------------------
# Test 5: HuggingFace model not found → fields stay None, no exception
# ---------------------------------------------------------------------------

def test_huggingface_not_found_leaves_fields_none():
    """A RepositoryNotFoundError must leave HF fields as None without crashing."""
    from huggingface_hub.utils import RepositoryNotFoundError
    import httpx

    item = _make_item(
        title="Ghost Model",
        huggingface_url="https://huggingface.co/nobody/ghost-model",
    )

    # RepositoryNotFoundError requires a response object with a .headers attr
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.headers = {}
    mock_response.status_code = 404

    mock_api = MagicMock()
    mock_api.model_info.side_effect = RepositoryNotFoundError(
        "nobody/ghost-model", response=mock_response
    )

    with patch("huggingface_hub.HfApi", return_value=mock_api):
        from hackradar.enrich import enrich_items
        result = enrich_items([item])  # must not raise

    enriched = result[0]
    assert enriched.downloads is None
    assert enriched.model_size is None
    assert enriched.has_demo_space is None
