"""tests/test_seen.py — Unit tests for seen-URL tracking in hackradar/main.py.

hackradar/main.py imports hackradar/scorer.py which in turn imports the
google-genai package.  That package may not be present in the test
environment, so we stub it out at the sys.modules level before the first
import of hackradar.main.
"""

from __future__ import annotations

import json
import logging
import sys
import types as _types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub out google.genai so hackradar.scorer (and therefore hackradar.main)
# can be imported even without the real package installed.
# ---------------------------------------------------------------------------
def _stub_google_genai():
    google_mod = sys.modules.get("google")
    if google_mod is None:
        google_mod = _types.ModuleType("google")
        sys.modules["google"] = google_mod

    if not hasattr(google_mod, "genai"):
        genai_mod = MagicMock()
        google_mod.genai = genai_mod
        sys.modules["google.genai"] = genai_mod
        sys.modules["google.genai.types"] = MagicMock()


_stub_google_genai()

import hackradar.main as main_module  # noqa: E402  (must come after stub)
from hackradar.models import Item  # noqa: E402
from tests.conftest import make_item  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_seen_path(tmp_path: Path):
    """Context manager: redirect SEEN_PATH to a temp file."""
    return patch.object(main_module, "SEEN_PATH", tmp_path / "seen.json")


# ---------------------------------------------------------------------------
# 1. Load existing seen.json → dict populated
# ---------------------------------------------------------------------------

def test_load_seen_existing_file(tmp_path):
    seen_file = tmp_path / "seen.json"
    data = {
        "https://ai.meta.com/blog/tribe-v2/": "2026-03-26",
        "https://arxiv.org/abs/2603.12345": "2026-03-27",
    }
    seen_file.write_text(json.dumps(data))

    with _patch_seen_path(tmp_path):
        result = main_module.load_seen()

    assert result == data
    assert len(result) == 2


# ---------------------------------------------------------------------------
# 2. First run, no file → empty dict
# ---------------------------------------------------------------------------

def test_load_seen_no_file(tmp_path):
    # tmp_path exists but seen.json does not
    with _patch_seen_path(tmp_path):
        result = main_module.load_seen()

    assert result == {}


# ---------------------------------------------------------------------------
# 3. Corrupted JSON file → log error, start with empty dict
# ---------------------------------------------------------------------------

def test_load_seen_corrupted_json(tmp_path, caplog):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text("{ this is not valid json !!!")

    with _patch_seen_path(tmp_path):
        with caplog.at_level(logging.ERROR):
            result = main_module.load_seen()

    assert result == {}
    assert any("seen.json" in msg for msg in caplog.messages), (
        "Expected an error log mentioning seen.json"
    )


# ---------------------------------------------------------------------------
# 4. Save seen.json → canonical URL as key, ISO date as value
# ---------------------------------------------------------------------------

def test_save_seen_writes_correct_content(tmp_path):
    item = make_item(source_url="https://ai.meta.com/blog/tribe-v2/")
    seen: dict[str, str] = {}

    with _patch_seen_path(tmp_path):
        main_module.mark_seen(item, seen)
        main_module.save_seen(seen)

        seen_file = tmp_path / "seen.json"
        saved = json.loads(seen_file.read_text())

    assert item.source_url in saved
    # Value must be a parseable ISO date string
    date_str = saved[item.source_url]
    parsed = datetime.strptime(date_str, "%Y-%m-%d")
    assert parsed.year >= 2026


# ---------------------------------------------------------------------------
# 5. Alternate URL lookup: is_seen checks github_url, hf_url, paper_url too
# ---------------------------------------------------------------------------

def test_is_seen_checks_all_urls(tmp_path):
    """is_seen must return True if ANY of the item's URLs appears in seen."""
    item = make_item(
        source_url="https://ai.meta.com/blog/tribe-v2/",
        github_url="https://github.com/facebookresearch/tribev2",
        huggingface_url="https://huggingface.co/facebook/tribev2",
        paper_url="https://arxiv.org/abs/2603.12345",
    )

    # Mark only the GitHub URL as seen
    seen = {"https://github.com/facebookresearch/tribev2": "2026-03-26"}
    assert main_module.is_seen(item, seen) is True

    # Mark only the HF URL as seen
    seen = {"https://huggingface.co/facebook/tribev2": "2026-03-26"}
    assert main_module.is_seen(item, seen) is True

    # Mark only the paper URL as seen
    seen = {"https://arxiv.org/abs/2603.12345": "2026-03-26"}
    assert main_module.is_seen(item, seen) is True

    # Nothing seen → not seen
    assert main_module.is_seen(item, {}) is False


# ---------------------------------------------------------------------------
# 6. Atomic write (tmp + rename pattern) — verify save_seen writes .tmp first
# ---------------------------------------------------------------------------

def test_save_seen_atomic_write(tmp_path, monkeypatch):
    """save_seen should write to a .tmp file and then rename it to seen.json."""
    written_paths: list[Path] = []
    renamed_from: list[Path] = []
    renamed_to: list[Path] = []

    original_write_text = Path.write_text

    def spy_write_text(self: Path, data, *args, **kwargs):
        written_paths.append(self)
        return original_write_text(self, data, *args, **kwargs)

    original_rename = Path.rename

    def spy_rename(self: Path, target):
        renamed_from.append(self)
        renamed_to.append(Path(target))
        return original_rename(self, target)

    monkeypatch.setattr(Path, "write_text", spy_write_text)
    monkeypatch.setattr(Path, "rename", spy_rename)

    seen = {"https://ai.meta.com/blog/tribe-v2/": "2026-03-26"}

    with _patch_seen_path(tmp_path):
        main_module.save_seen(seen)

    # The tmp file must have been written
    assert any(p.suffix == ".tmp" for p in written_paths), (
        "save_seen should write to a .tmp file before renaming"
    )
    # The rename must have happened
    assert len(renamed_from) >= 1
    assert any(p.suffix == ".tmp" for p in renamed_from), (
        "The .tmp file must be renamed (not written directly to seen.json)"
    )

    # Final seen.json must exist and be valid
    final = tmp_path / "seen.json"
    assert final.exists()
    assert json.loads(final.read_text()) == seen


# ---------------------------------------------------------------------------
# Edge case: mark_seen does not persist without save_seen
# ---------------------------------------------------------------------------

def test_mark_seen_updates_dict_in_memory():
    item = make_item(source_url="https://example.com/new-item")
    seen: dict[str, str] = {}
    main_module.mark_seen(item, seen)
    assert item.source_url in seen


# ---------------------------------------------------------------------------
# Edge case: seen.json contains a list (not a dict) → treated as corrupted
# ---------------------------------------------------------------------------

def test_load_seen_wrong_type_logs_error(tmp_path, caplog):
    seen_file = tmp_path / "seen.json"
    seen_file.write_text(json.dumps(["not", "a", "dict"]))

    with _patch_seen_path(tmp_path):
        with caplog.at_level(logging.ERROR):
            result = main_module.load_seen()

    assert result == {}
