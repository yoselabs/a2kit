from __future__ import annotations

import inspect
import json
import tokenize
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import tomllib  # type: ignore[no-redef]

_STUB_PATH = Path(__file__).parent / "_stubs" / "raises_registry.json"

_INLINE_PREFIX = "# a2effect: may-raise "

_cached: dict[str, frozenset[str]] | None = None
_extensions: dict[str, frozenset[str]] = {}


def _load_builtins() -> dict[str, frozenset[str]]:
    raw = json.loads(_STUB_PATH.read_text(encoding="utf-8"))
    return {k: frozenset(v) for k, v in raw.items()}


def _get_cache() -> dict[str, frozenset[str]]:
    global _cached  # noqa: PLW0603 — module-level lazy cache, intentional
    if _cached is None:
        _cached = _load_builtins()
    return _cached


def get(fq_func_name: str) -> frozenset[str]:
    cache = _get_cache()
    if fq_func_name in _extensions:
        return _extensions[fq_func_name]
    return cache.get(fq_func_name, frozenset())


def extend(extra: dict[str, list[str] | tuple[str, ...]]) -> None:
    for key, value in extra.items():
        _extensions[key] = frozenset(value)


def load_pyproject_extension(project_root: Path) -> None:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    extra = data.get("tool", {}).get("a2effect", {}).get("raises_registry", {})
    if not isinstance(extra, dict):
        return
    extend({k: v for k, v in extra.items() if isinstance(v, (list, tuple))})


def reset_for_testing() -> None:
    global _cached  # noqa: PLW0603 — module-level lazy cache, intentional
    _cached = None
    _extensions.clear()


def read_inline_annotation(fn: Callable[..., Any]) -> frozenset[str]:
    try:
        source = inspect.getsource(fn)
    except (OSError, TypeError):
        return frozenset()
    collected: set[str] = set()
    try:
        tokens = list(tokenize.generate_tokens(StringIO(source).readline))
    except tokenize.TokenizeError:
        return frozenset()
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        text = tok.string.rstrip()
        if not text.startswith(_INLINE_PREFIX):
            continue
        body = text[len(_INLINE_PREFIX) :]
        for part in body.split(","):
            name = part.strip()
            if name:
                collected.add(name)
    return frozenset(collected)
