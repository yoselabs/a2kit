"""${VAR} and op:// resolvers used by the eager pydantic-settings sources."""

from __future__ import annotations

import re
import shutil
import subprocess
from os import environ

from a2kit.packages.connections.exceptions import EnvVarNotFound, OpResolutionError

_ENV_REF_RE = re.compile(r"\$\{(\w+)\}")
_OP_REF_RE = re.compile(r"^op://[^\s]+$")


def has_env_ref(value: str) -> bool:
    return bool(_ENV_REF_RE.search(value))


def is_op_ref(value: str) -> bool:
    return bool(_OP_REF_RE.match(value))


def resolve_env(value: str) -> str:
    """Expand `${VAR}` references; raise `EnvVarNotFound` if any var is missing."""

    def _sub(match: re.Match[str]) -> str:
        var = match.group(1)
        try:
            return environ[var]
        except KeyError as exc:
            raise EnvVarNotFound(var=var, ref=match.group(0)) from exc

    return _ENV_REF_RE.sub(_sub, value)


def resolve_op(value: str) -> str:
    """Resolve a `op://vault/item/field` reference via the 1Password CLI."""
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


def resolve_value(value: str) -> str:
    """Resolve a single string: op:// wins, then ${VAR}, else literal."""
    if is_op_ref(value):
        return resolve_op(value)
    if has_env_ref(value):
        return resolve_env(value)
    return value
