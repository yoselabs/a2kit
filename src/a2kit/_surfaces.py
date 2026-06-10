"""Surface projection matrix (ADR 0028 Wave 2 — surfaces-projection-axis).

A verb's placement is one fact per registered surface: for each surface
the verb is ABSENT, LISTED, or UNLISTED.

    ABSENT     not mounted at all
    LISTED     mounted + advertised (listing / --help / schema)
    UNLISTED   mounted + callable, hidden from advertisement

Authoring spelling (the ``surfaces=`` kwarg on the verb decorators):

    surfaces=("mcp", "cli")        tuple → LISTED on each named, ABSENT elsewhere
    surfaces={"cli": "unlisted"}   dict  → state per key, ABSENT elsewhere
    (omitted)                      default → LISTED on every registered surface

The matrix is fully resolved (every default-registered surface has a
state) and is the single thing every surface reads to decide
mount + advertise.
"""

from __future__ import annotations

from typing import Literal, cast

ABSENT = "absent"
LISTED = "listed"
UNLISTED = "unlisted"

SurfaceState = Literal["absent", "listed", "unlisted"]

#: Default registered surfaces, resolved against when the author does not
#: name an exhaustive set. ``runtime.build()`` validates named surfaces
#: against the actually-composed registry (this is only the resolution
#: universe for ABSENT-filling).
DEFAULT_SURFACES: tuple[str, ...] = ("mcp", "api", "cli")

_VALID_STATES = frozenset({ABSENT, LISTED, UNLISTED})

# Sentinel distinguishing "author omitted surfaces=" from an explicit value,
# so a Router-level default can still apply before resolution.
UNSET: object = object()


def resolve_surfaces(
    surfaces: object = UNSET,
    *,
    registered: tuple[str, ...] = DEFAULT_SURFACES,
) -> dict[str, SurfaceState]:
    """Resolve an authoring spec to a full per-surface state matrix.

    ``surfaces`` is the ``surfaces=`` kwarg (tuple, dict, or UNSET). When
    it is UNSET the default is LISTED on every registered surface — a verb
    is available on all surfaces unless it opts out.
    """
    if surfaces is not UNSET:
        return _resolve_explicit(surfaces, registered)
    return dict.fromkeys(registered, LISTED)


def _resolve_explicit(surfaces: object, registered: tuple[str, ...]) -> dict[str, SurfaceState]:
    matrix: dict[str, SurfaceState] = dict.fromkeys(registered, ABSENT)
    if isinstance(surfaces, dict):
        for raw_name, raw_state in surfaces.items():
            state = str(raw_state)
            if state not in _VALID_STATES:
                msg = f"surfaces[{raw_name!r}]={raw_state!r} invalid; use 'listed' | 'unlisted' | 'absent'."
                raise ValueError(msg)
            matrix[str(raw_name)] = cast("SurfaceState", state)
        return matrix
    if isinstance(surfaces, (tuple, list)):
        if not surfaces:
            msg = "surfaces=() is empty: a verb must be placed on at least one surface."
            raise ValueError(msg)
        for raw_name in surfaces:
            matrix[str(raw_name)] = LISTED
        return matrix
    msg = f"surfaces= must be a tuple of names or a dict of states, got {type(surfaces).__name__}."
    raise TypeError(msg)


def matrix_for(extras: object) -> dict[str, SurfaceState]:
    """Resolve the surface matrix for a verb's ``A2KitMetaExtras``.

    ``surfaces=`` is the only placement axis: every verb carries a fully
    resolved ``extras.surfaces`` matrix (stamped at decoration time). This
    returns it, falling back to the LISTED-everywhere default only for the
    defensive case where a descriptor predates the matrix. Duck-typed on
    ``extras`` to avoid importing :mod:`a2kit.metadata` here.
    """
    explicit = getattr(extras, "surfaces", None)
    if explicit is not None:
        return explicit
    return resolve_surfaces()


def resolve_canonical_name(
    override: str | None,
    router_slug: str | None,
    leaf: str,
) -> str:
    """Resolve a verb's flat canonical name (ADR 0028 Wave 2, decision 5).

    Precedence:
      1. ``override`` (``canonical_name_override=``) → used VERBATIM, no slug.
      2. under a Router (``router_slug`` set) → ``f"{router_slug}_{leaf}"``.
      3. app-level verb (no router) → ``leaf``.

    A pin is complete: the slug is never re-applied
    (override="jira_search" under slug="jira" stays "jira_search"). This is
    rendered identically on every surface and is the call-log/audit key.
    """
    if override is not None:
        return override
    if router_slug:
        return f"{router_slug}_{leaf}"
    return leaf


def mounted_on(matrix: dict[str, SurfaceState], surface: str) -> bool:
    """Whether the verb is callable on ``surface`` (LISTED or UNLISTED)."""
    return matrix.get(surface, ABSENT) in {LISTED, UNLISTED}


def advertised_on(matrix: dict[str, SurfaceState], surface: str) -> bool:
    """Whether the verb is advertised on ``surface`` (LISTED only)."""
    return matrix.get(surface, ABSENT) == LISTED


def mounted_surfaces(matrix: dict[str, SurfaceState]) -> tuple[str, ...]:
    """The surfaces the verb is mounted on, in matrix order (compat for the
    old ``expose`` tuple — membership reads stay correct)."""
    return tuple(s for s, state in matrix.items() if state in {LISTED, UNLISTED})


__all__ = [
    "ABSENT",
    "DEFAULT_SURFACES",
    "LISTED",
    "UNLISTED",
    "UNSET",
    "SurfaceState",
    "advertised_on",
    "matrix_for",
    "mounted_on",
    "mounted_surfaces",
    "resolve_canonical_name",
    "resolve_surfaces",
]
