"""Docstring helpers — canonical phrasings for recurring tool params.

Two layers:

- `connection_param_doc(...)` — canonical phrasing for `connection`. Same as v0.2.
- `register_param_doc(name, text)` / `param_doc(name)` (v0.3) — registry for
  any recurring parameter. The fat `@a2kit.tool` decorator will inject the
  registered text into a tool's docstring if the existing docstring doesn't
  already reference the parameter. Token-budget friendly: write once, dedupe
  across N tools.
"""

from __future__ import annotations

_PARAM_DOCS: dict[str, str] = {}


def connection_param_doc(
    name: str = "connection",
    *,
    cli: str = "a2kit",
    example: str = "prod",
    custom_suffix: str | None = None,
) -> str:
    """Canonical sentence for the connection parameter — eliminates per-tool drift."""
    base = (
        f"{name}: Saved {cli} connection name (e.g. {example!r}), not a project key or ID. "
        f"Use `{cli} connections list` to see available names."
    )
    if custom_suffix:
        base = f"{base} {custom_suffix}"
    return base


def register_param_doc(name: str, text: str) -> None:
    """Register canonical text for a parameter name. Last write wins."""
    _PARAM_DOCS[name] = text


def param_doc(name: str) -> str:
    """Return the registered text for `name`, or empty string if absent."""
    return _PARAM_DOCS.get(name, "")


def clear_param_docs() -> None:
    """Drop every registered param doc. Test helper."""
    _PARAM_DOCS.clear()


def _registered_param_docs() -> dict[str, str]:
    """Internal seam for the `@a2kit.tool` decorator."""
    return _PARAM_DOCS


__all__ = [
    "clear_param_docs",
    "connection_param_doc",
    "param_doc",
    "register_param_doc",
]
