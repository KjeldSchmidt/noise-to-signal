"""Registry for staff custom admin pages (non-ModelAdmin views).

Annotate a view with ``@custom_admin_page(...)``; ``patch_admin_site`` wires
URLs and injects entries into the default admin index context.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from django.http import HttpRequest, HttpResponse

ViewFunc = Callable[[HttpRequest], HttpResponse]
F = TypeVar("F", bound=ViewFunc)


@dataclass(frozen=True, slots=True)
class CustomAdminPage:
    """One custom admin tool page listed on /admin/ and mounted under admin URLs."""

    name: str
    path: str
    title: str
    view: ViewFunc
    description: str = ""


_REGISTRY: list[CustomAdminPage] = []


def custom_admin_page(
    *,
    name: str,
    path: str,
    title: str,
    description: str = "",
) -> Callable[[F], F]:
    """Register a staff admin view so it gets a URL and an index link."""

    def decorator(view: F) -> F:
        if any(p.name == name for p in _REGISTRY):
            raise ValueError(f"custom admin page name already registered: {name!r}")
        _REGISTRY.append(
            CustomAdminPage(
                name=name,
                path=path.lstrip("/"),
                title=title,
                view=view,
                description=description,
            )
        )
        return view

    return decorator


def iter_custom_admin_pages() -> list[CustomAdminPage]:
    """Return registered custom pages in decoration order."""
    return list(_REGISTRY)
