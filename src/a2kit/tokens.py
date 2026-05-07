"""Token resolvers — `${ENV_VAR}`, `op://vault/item/field`, and literal fallback.

Resolution is **lazy**: callers invoke `resolve_token(value)` at API-call time, not at
load time. Failures surface as typed exceptions (`EnvVarNotFound`, `OpResolutionError`).

The resolver registry is module-global by default but a fresh `ResolverRegistry` can be
instantiated and passed to `resolve_token(value, registry=...)` for tests or per-store
overrides. See README "Open questions".
"""

from __future__ import annotations

import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from os import environ

from a2kit.exceptions import EnvVarNotFound, OpResolutionError

_ENV_REF_RE = re.compile(r"\$\{(\w+)\}")
_OP_REF_RE = re.compile(r"^op://[^\s]+$")

Resolver = Callable[[str], str]
"""A resolver takes a raw token value and returns a resolved string. Raises on failure."""


def resolve_env(value: str) -> str:
    """Expand `${VAR}` references; raise `EnvVarNotFound` if any var is missing.

    Values without `${...}` pass through unchanged.
    """

    def _sub(match: re.Match[str]) -> str:
        var = match.group(1)
        try:
            return environ[var]
        except KeyError as exc:
            raise EnvVarNotFound(var=var, ref=match.group(0)) from exc

    return _ENV_REF_RE.sub(_sub, value)


def resolve_op(value: str) -> str:
    """Resolve a `op://vault/item/field` reference via the 1Password CLI.

    Raises `OpResolutionError` if `op` is missing, returns non-zero, or times out.
    """
    if shutil.which("op") is None:
        raise OpResolutionError(ref=value, hint="`op` binary not found on PATH; install 1Password CLI.")
    try:
        result = subprocess.run(  # noqa: S603
            ["op", "read", value],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired as exc:
        raise OpResolutionError(ref=value, hint="`op read` timed out after 10s.") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip() or "non-zero exit"
        raise OpResolutionError(
            ref=value,
            hint=f"`op read` failed: {stderr}. Re-authenticate with `op signin` and retry.",
        ) from exc
    return result.stdout.rstrip("\n")


def resolve_literal(value: str) -> str:
    """Literal-string fallback. Returns the value unchanged."""
    return value


@dataclass
class ResolverRegistry:
    """Pluggable registry of (predicate, resolver) pairs, applied in order.

    First predicate that matches wins. If no predicate matches, the literal resolver
    is used.
    """

    rules: list[tuple[Callable[[str], bool], Resolver]] = field(default_factory=list)

    def register(self, predicate: Callable[[str], bool], resolver: Resolver) -> None:
        """Register a resolver. Predicates are tried in registration order."""
        self.rules.append((predicate, resolver))

    def resolve(self, value: str) -> str:
        """Resolve `value` using the first matching rule, or the literal fallback."""
        for predicate, resolver in self.rules:
            if predicate(value):
                return resolver(value)
        return resolve_literal(value)


def _is_op_ref(value: str) -> bool:
    return bool(_OP_REF_RE.match(value))


def _has_env_ref(value: str) -> bool:
    return bool(_ENV_REF_RE.search(value))


def _build_default_registry() -> ResolverRegistry:
    registry = ResolverRegistry()
    registry.register(_is_op_ref, resolve_op)
    registry.register(_has_env_ref, resolve_env)
    return registry


_DEFAULT_REGISTRY = _build_default_registry()


def default_registry() -> ResolverRegistry:
    """Return the module-global default registry (op:// → ${ENV} → literal)."""
    return _DEFAULT_REGISTRY


def resolve_token(value: str, *, registry: ResolverRegistry | None = None) -> str:
    """Resolve a token value lazily. Defaults to the module-global registry."""
    return (registry or _DEFAULT_REGISTRY).resolve(value)
