"""Template helpers for news UI."""

from __future__ import annotations

from urllib.parse import urlparse

from django import template
from django.templatetags.static import static

from news.models import Feed

register = template.Library()

# Host fragment → static logo under static/img/sources/
_SOURCE_LOGOS: dict[str, str] = {
    "bbc.com": "img/sources/bbc.svg",
    "bbc.co.uk": "img/sources/bbc.svg",
    "npr.org": "img/sources/npr.svg",
    "theverge.com": "img/sources/theverge.svg",
    "arstechnica.com": "img/sources/arstechnica.svg",
    "nature.com": "img/sources/nature.svg",
    "theguardian.com": "img/sources/guardian.svg",
    "apnews.com": "img/sources/ap.svg",
}


def _host(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _logo_static_path(feed: Feed) -> str | None:
    for candidate in (feed.site_url, feed.url):
        host = _host(candidate or "")
        if not host:
            continue
        for needle, path in _SOURCE_LOGOS.items():
            if host == needle or host.endswith("." + needle):
                return path
    title = (feed.title or "").lower()
    title_map = {
        "bbc": "img/sources/bbc.svg",
        "npr": "img/sources/npr.svg",
        "verge": "img/sources/theverge.svg",
        "ars technica": "img/sources/arstechnica.svg",
        "nature": "img/sources/nature.svg",
        "guardian": "img/sources/guardian.svg",
        "associated press": "img/sources/ap.svg",
        "ap ": "img/sources/ap.svg",
    }
    for needle, path in title_map.items():
        if needle in title:
            return path
    return None


@register.filter
def source_logo_url(feed: Feed) -> str:
    """Return a static logo URL for known feeds, else empty string."""
    path = _logo_static_path(feed)
    return static(path) if path else ""


@register.filter
def source_logo_slug(feed: Feed) -> str:
    """CSS-friendly slug for per-source fallback styling."""
    path = _logo_static_path(feed)
    if not path:
        return "generic"
    return path.rsplit("/", 1)[-1].removesuffix(".svg")
