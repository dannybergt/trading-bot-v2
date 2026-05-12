"""In-app help and documentation surface.

Markdown sources live in `docs/inapp/<topic>.md`. The service reads them
on demand so an admin can edit the files in the running container (or
ship a docs-only release) without redeploying. The path resolution is
strict: every topic name is matched against `[a-z0-9_-]{1,40}` before
the filesystem is touched, so a malicious request can't escape into
the wider repo.

A `topics.yaml`-style registry doesn't exist yet — instead, every `.md`
in the directory becomes a topic. The frontmatter (first H1) becomes
the title; the optional `page` mapping at the very top maps a topic to
the frontend route it documents (e.g. `/scanner` → `scanner`). That
mapping powers the contextual help drawer.
"""
from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _candidate_dirs() -> list[Path]:
    explicit = os.getenv("DOCS_INAPP_DIR")
    if explicit:
        return [Path(explicit)]
    here = Path(__file__).resolve()
    return [
        # Repo layout: src/backend/app/docs_service.py → docs/inapp
        here.parent.parent.parent.parent / "docs" / "inapp",
        # Container layout when shipped: /app/docs/inapp
        Path("/app/docs/inapp"),
    ]


def _docs_dir() -> Path | None:
    for candidate in _candidate_dirs():
        if candidate.is_dir():
            return candidate
    return None


_TOPIC_PATTERN = re.compile(r"^[a-z0-9_-]{1,40}$")
_PAGE_FRONTMATTER = re.compile(r"^<!--\s*page:\s*(.+?)\s*-->", re.IGNORECASE)
_TITLE_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_SUPPORTED_LOCALES = ("en", "de")
_DEFAULT_LOCALE = "en"


def _normalize_locale(value: str | None) -> str:
    if not value:
        return _DEFAULT_LOCALE
    lower = value.strip().lower()
    if lower in _SUPPORTED_LOCALES:
        return lower
    # Accept browser-style "de-DE" or "en-US"
    short = lower.split("-", 1)[0]
    if short in _SUPPORTED_LOCALES:
        return short
    return _DEFAULT_LOCALE


def _resolve_topic_path(docs_dir: Path, slug: str, locale: str) -> Path | None:
    # Lookup-Order: <slug>.<locale>.md (if non-default) → <slug>.md
    if locale != _DEFAULT_LOCALE:
        localized = docs_dir / f"{slug}.{locale}.md"
        if localized.is_file():
            return localized
    fallback = docs_dir / f"{slug}.md"
    if fallback.is_file():
        return fallback
    return None


def _parse_title_and_page(content: str) -> tuple[str | None, str | None]:
    page: str | None = None
    page_match = _PAGE_FRONTMATTER.search(content)
    if page_match:
        page = page_match.group(1).strip()
    title_match = _TITLE_PATTERN.search(content)
    title = title_match.group(1).strip() if title_match else None
    return title, page


def list_topics(locale: str | None = None) -> list[dict[str, Any]]:
    """Return the metadata for every topic in the docs directory.

    Locale resolution: for each slug, prefer `<slug>.<locale>.md`; fall back
    to `<slug>.md` so a partial translation still surfaces every topic. The
    `*.<locale>.md` files are skipped at directory-iteration time so they
    don't appear as standalone topics like `dashboard-de`.
    """
    docs_dir = _docs_dir()
    if docs_dir is None:
        return []
    resolved_locale = _normalize_locale(locale)
    topics: list[dict[str, Any]] = []
    for path in sorted(docs_dir.glob("*.md")):
        slug = path.stem
        # Skip locale variants (foo.de, foo.en) — only the base slug counts.
        if "." in slug:
            continue
        if not _TOPIC_PATTERN.match(slug):
            continue
        resolved = _resolve_topic_path(docs_dir, slug, resolved_locale)
        if resolved is None:
            continue
        try:
            content = resolved.read_text(encoding="utf-8")
        except Exception:
            logger.exception("docs_inapp_read_failed slug=%s", slug)
            continue
        title, page = _parse_title_and_page(content)
        topics.append(
            {
                "slug": slug,
                "title": title or slug.replace("-", " ").title(),
                "page": page,
                "locale": resolved_locale if resolved.name.endswith(f".{resolved_locale}.md") else _DEFAULT_LOCALE,
            }
        )
    return topics


def get_topic(slug: str, locale: str | None = None) -> dict[str, Any] | None:
    if not slug or not _TOPIC_PATTERN.match(slug):
        return None
    docs_dir = _docs_dir()
    if docs_dir is None:
        return None
    resolved_locale = _normalize_locale(locale)
    path = _resolve_topic_path(docs_dir, slug, resolved_locale)
    if path is None:
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        logger.exception("docs_inapp_read_failed slug=%s", slug)
        return None
    title, page = _parse_title_and_page(content)
    return {
        "slug": slug,
        "title": title or slug.replace("-", " ").title(),
        "page": page,
        "content": content,
        "locale": resolved_locale if path.name.endswith(f".{resolved_locale}.md") else _DEFAULT_LOCALE,
    }


@lru_cache(maxsize=4)
def get_page_to_topic_map(locale: str | None = None) -> dict[str, str]:
    """Map frontend route prefix → topic slug, derived from the
    `<!-- page: ... -->` annotation at the top of each markdown file.
    Used by the help drawer to look up the right topic for the
    currently-rendered page."""
    mapping: dict[str, str] = {}
    for entry in list_topics(locale=locale):
        page = entry.get("page")
        if not page:
            continue
        normalized = page if page.startswith("/") else f"/{page}"
        mapping[normalized] = entry["slug"]
    return mapping


def supported_locales() -> tuple[str, ...]:
    return _SUPPORTED_LOCALES


def reset_caches_for_tests() -> None:
    get_page_to_topic_map.cache_clear()
