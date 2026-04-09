"""GitHub research org watcher — new repos from top AI research organizations."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

from github import Github, GithubException

from hackradar import config
from hackradar.models import Item, ScrapeResult
from hackradar.sources import register_source

logger = logging.getLogger(__name__)

# Must match the label in config.HIGH_TRUST_SOURCES exactly.
_SOURCE = "GitHub Research Orgs"


@register_source("github_research_orgs")
def scrape(lookback_hours: int = 48) -> ScrapeResult:
    items: list[Item] = []
    errors: list[str] = []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

    if not config.GITHUB_TOKEN:
        errors.append("GITHUB_TOKEN not set — skipping github_research_orgs (rate limits will apply)")
        g = Github()
    else:
        g = Github(config.GITHUB_TOKEN)

    for org_name in config.GITHUB_ORGS:
        try:
            org = g.get_organization(org_name)
            # Get repos sorted by creation date
            repos = org.get_repos(sort="created", direction="desc")

            for repo in repos:
                try:
                    created_at = repo.created_at
                    if created_at.tzinfo is None:
                        created_at = created_at.replace(tzinfo=timezone.utc)

                    if created_at < cutoff:
                        break  # sorted descending, safe to stop

                    description = repo.description or ""
                    # Grab first bit of README if description is empty
                    readme_excerpt = None
                    if not description:
                        try:
                            readme = repo.get_readme()
                            readme_excerpt = readme.decoded_content.decode("utf-8", errors="ignore")[:500]
                            description = readme_excerpt[:200]
                        except Exception:
                            description = f"New repository from {org_name}"

                    item = Item(
                        title=f"{org_name}/{repo.name}",
                        description=description,
                        date=created_at,
                        source=_SOURCE,
                        source_url=repo.html_url,
                        github_url=repo.html_url,
                        category="ai_research",
                        stars=repo.stargazers_count,
                        language=repo.language,
                        license=repo.license.name if repo.license else None,
                        readme_excerpt=readme_excerpt,
                    )
                    items.append(item)

                except GithubException as e:
                    errors.append(f"github_research_orgs repo error ({org_name}): {e}")
                except Exception as e:
                    errors.append(f"github_research_orgs item error ({org_name}): {e}")

        except GithubException as e:
            errors.append(f"github_research_orgs org error ({org_name}): {e}")
        except Exception as e:
            errors.append(f"github_research_orgs failed for {org_name}: {e}")

    logger.info("github_research_orgs: %d items, %d errors", len(items), len(errors))
    return ScrapeResult(items=items, errors=errors)
