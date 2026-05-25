"""Principal → DI scope seeding helper (substrate-internal).

The spec contract (``principal-propagation``, ``dispatch-pipeline``):
dispatch stages MUST resolve ``Principal`` exclusively via the per-call
DI scope. This helper exists to convert the substrate-published Principal
(currently carried on an internal contextvar between the substrate
authentication boundary and the per-call DI scope opening) into a
SCOPED entry on the about-to-be-opened ``call_scope``. Stages call this
helper; they MUST NOT import ``_a2kit_request_principal`` directly.

The contextvar is a substrate-internal mechanism — production code under
``packages/auth/`` and ``packages/mcp/`` writes it at the auth boundary;
``packages/http/build.py`` writes it from a FastAPI ``Security`` guard.
A future iteration could push the publication path into the substrate
container scope directly; for now this helper isolates the read so
``stages.py`` is clean per the spec scenarios.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from a2kit.packages.context import Principal


_WIRE_KEY = "_a2kit_principal"


def current_request_principal() -> Principal | None:
    """Return the substrate-published Principal for the current request."""
    from a2kit.packages.context import _a2kit_request_principal

    return _a2kit_request_principal.get()


def seed_principal_into_wire(wire_kwargs: dict[str, Any]) -> None:
    """Seed the current-request Principal into ``wire_kwargs`` as a SCOPED
    DI value.

    ``Container.call_scope`` walks ``wire_kwargs.values()`` and registers
    each value's concrete type as a SCOPED provider on the child container,
    so the wire-key string is incidental — only the value's type matters.
    """
    principal = current_request_principal()
    if principal is not None:
        wire_kwargs.setdefault(_WIRE_KEY, principal)


__all__ = ["current_request_principal", "seed_principal_into_wire"]
