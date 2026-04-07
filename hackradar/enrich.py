"""enrich.py — Enrich Items with metadata from GitHub and HuggingFace.

For each item:
  - If github_url is set: fetch star count, primary language, license,
    and the first 500 chars of the README via PyGithub.
  - If huggingface_url is set: fetch model parameter count, total downloads,
    and whether a live demo Space exists via huggingface_hub.

All errors are caught per-item so one bad item never aborts the run.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

from hackradar import config
from hackradar.models import Item

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_github_repo(url: str) -> tuple[str, str] | None:
    """
    Return (owner, repo) from a GitHub URL, or None if it doesn't parse.

    Handles:
        https://github.com/facebookresearch/tribev2
        https://github.com/facebookresearch/tribev2/tree/main
    """
    try:
        parsed = urlparse(url)
        if "github.com" not in parsed.netloc.lower():
            return None
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return None


def _parse_hf_repo(url: str) -> str | None:
    """
    Return the 'owner/model-name' repo_id from a HuggingFace URL, or None.

    Handles:
        https://huggingface.co/facebook/tribev2
        https://huggingface.co/facebook/tribev2/tree/main
    """
    try:
        parsed = urlparse(url)
        if "huggingface.co" not in parsed.netloc.lower():
            return None
        parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(parts) >= 2:
            return f"{parts[0]}/{parts[1]}"
    except Exception:
        pass
    return None


def _safe_license_name(repo_license) -> str | None:
    """Extract license name string from a PyGithub license object."""
    try:
        if repo_license is None:
            return None
        return repo_license.spdx_id or repo_license.name or None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-item enrichers
# ---------------------------------------------------------------------------

def _enrich_github(item: Item, gh) -> None:
    """
    Populate item.stars, item.language, item.license, item.readme_excerpt
    using the PyGithub client *gh*.

    Modifies *item* in place. All exceptions are caught.
    """
    parsed = _parse_github_repo(item.github_url)
    if parsed is None:
        logger.warning("Could not parse GitHub URL: %s", item.github_url)
        return

    owner, repo_name = parsed
    try:
        repo = gh.get_repo(f"{owner}/{repo_name}")
    except Exception as exc:
        status = getattr(getattr(exc, "data", None), "get", lambda k, d=None: None)("status")
        code = getattr(exc, "status", None)
        if code == 404:
            logger.debug("GitHub 404: %s/%s", owner, repo_name)
        elif code == 403:
            logger.warning("GitHub rate-limit hit for %s/%s — skipping enrichment", owner, repo_name)
        else:
            logger.warning("GitHub error for %s/%s: %s", owner, repo_name, exc)
        return

    try:
        item.stars = repo.stargazers_count
    except Exception:
        pass

    try:
        item.language = repo.language
    except Exception:
        pass

    try:
        item.license = _safe_license_name(repo.license)
    except Exception:
        pass

    try:
        readme = repo.get_readme()
        content = readme.decoded_content.decode("utf-8", errors="replace")
        item.readme_excerpt = content[:500].strip()
    except Exception:
        # README may not exist
        pass


def _enrich_huggingface(item: Item) -> None:
    """
    Populate item.model_size, item.downloads, item.has_demo_space
    using huggingface_hub.

    Modifies *item* in place. All exceptions are caught.
    """
    from huggingface_hub import HfApi, hf_hub_url
    from huggingface_hub.utils import EntryNotFoundError, RepositoryNotFoundError

    repo_id = _parse_hf_repo(item.huggingface_url)
    if repo_id is None:
        logger.warning("Could not parse HuggingFace URL: %s", item.huggingface_url)
        return

    api = HfApi()

    # --- Model info ---
    try:
        model_info = api.model_info(repo_id, securityStatus=False)

        # Downloads
        try:
            item.downloads = model_info.downloads
        except Exception:
            pass

        # Model size: huggingface stores parameter count in safetensors metadata
        # Fall back to a human-readable string from the model card metadata.
        try:
            # safetensors_info may carry total parameter count
            st = getattr(model_info, "safetensors", None)
            if st and hasattr(st, "total"):
                params = st.total
                if params:
                    if params >= 1_000_000_000:
                        item.model_size = f"{params / 1_000_000_000:.1f}B params"
                    elif params >= 1_000_000:
                        item.model_size = f"{params / 1_000_000:.0f}M params"
                    else:
                        item.model_size = f"{params:,} params"
        except Exception:
            pass

        # If we still don't have a model_size, try card metadata tags
        if item.model_size is None:
            try:
                card_data = getattr(model_info, "cardData", None) or {}
                # Some cards have e.g. {"model-index": [...], "tags": ["7B"]}
                tags = card_data.get("tags", []) if isinstance(card_data, dict) else []
                size_tag = next(
                    (t for t in tags if re.search(r"\d+[BbMmKk]", str(t))), None
                )
                if size_tag:
                    item.model_size = str(size_tag)
            except Exception:
                pass

    except RepositoryNotFoundError:
        logger.debug("HuggingFace 404: %s", repo_id)
        return
    except Exception as exc:
        logger.warning("HuggingFace model_info error for %s: %s", repo_id, exc)
        return

    # --- Demo Space ---
    # A Space with the same name pattern as the model often exists.
    # We check for a Space whose ID matches "owner/model-name" or any Space
    # that lists this model as a base.
    try:
        owner = repo_id.split("/")[0]
        model_name = repo_id.split("/")[1]
        # Quick heuristic: look for a Space with the same owner/repo structure
        spaces = list(api.list_spaces(author=owner, limit=50))
        space_ids = {s.id.lower() for s in spaces}
        # Direct name match
        if f"{owner}/{model_name}".lower() in space_ids:
            item.has_demo_space = True
        else:
            # Check if any space has this model as a linked model
            for space in spaces:
                card = getattr(space, "cardData", None) or {}
                models = card.get("models", []) if isinstance(card, dict) else []
                if repo_id in models or repo_id.lower() in [m.lower() for m in models]:
                    item.has_demo_space = True
                    break
            else:
                item.has_demo_space = False
    except Exception as exc:
        logger.debug("HuggingFace space check error for %s: %s", repo_id, exc)
        item.has_demo_space = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def enrich_items(items: list[Item]) -> list[Item]:
    """
    Enrich each item with GitHub and HuggingFace metadata.

    Returns the same list (items are mutated in place) for convenience.
    """
    # Lazy-init GitHub client only if we have a token and at least one item
    # needs GitHub enrichment.
    gh = None
    needs_github = any(item.github_url for item in items)
    if needs_github:
        if config.GITHUB_TOKEN:
            try:
                from github import Github
                gh = Github(config.GITHUB_TOKEN)
                logger.debug("GitHub client initialised")
            except ImportError:
                logger.warning("PyGithub not installed — GitHub enrichment disabled")
        else:
            logger.warning("GITHUB_TOKEN not set — GitHub enrichment disabled")

    for item in items:
        # GitHub enrichment
        if item.github_url and gh is not None:
            try:
                _enrich_github(item, gh)
            except Exception as exc:
                logger.warning("Unexpected error enriching GitHub item %r: %s", item.title, exc)

        # HuggingFace enrichment
        if item.huggingface_url:
            try:
                _enrich_huggingface(item)
            except Exception as exc:
                logger.warning("Unexpected error enriching HF item %r: %s", item.title, exc)

    return items
