"""``prune_empty()`` marker + dump helper for return-type opt-in to empty-field pruning.

A2kit's formatter serializes return types with ``model_dump(mode="json")`` by
default, which emits every optional field even when empty (``byline: null``,
``next_links: []``). On token-sensitive tools (a2web's ``ask``, agent-facing
endpoints generally) that is pure noise in the calling agent's context.

The opt-in is a **model-level marker** on ``pydantic.ConfigDict``. When set,
``_dump_model_pruned`` post-processes the JSON dump to drop keys whose value is
``None``, ``""``, ``[]``, or ``{}``. Other zero-valued types (``0``, ``False``,
``Decimal(0)``, empty ``frozenset``) are KEPT — they carry information.

The marker leaves the JSON schema unchanged: ``outputSchema`` advertises the
fields as optional regardless. The wire payload is the only thing affected.

Designed in change ``a2web-handoff-prep``; spec at
``openspec/specs/type-driven-format-routing/spec.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import BaseModel

PRUNE_EMPTY_KEY = "a2kit_prune_empty"


def prune_empty() -> dict[str, Any]:
    """Return a `ConfigDict` fragment opting into empty-field pruning.

    Use as the value of `model_config` (merged with `pydantic.ConfigDict`) on
    a return type::

        from pydantic import BaseModel, ConfigDict
        from a2kit.formatter import prune_empty

        class FetchResponse(BaseModel):
            model_config = ConfigDict(**prune_empty())
            url: str
            byline: str | None = None

    The default formatter behavior (no marker) is unchanged.
    """
    return {PRUNE_EMPTY_KEY: True}


def model_wants_prune(model: BaseModel | type[BaseModel]) -> bool:
    """True if the model (or model class) opts into empty-field pruning."""
    config = getattr(model, "model_config", None)
    if not isinstance(config, dict):
        return False
    return bool(config.get(PRUNE_EMPTY_KEY, False))


def _is_empty(value: Any) -> bool:
    """Empty per the marker spec: ``None`` / ``""`` / ``[]`` / ``{}``.

    Non-empty: ``0``, ``False``, ``Decimal(0)``, empty ``frozenset``, etc.
    Only the four literal empty containers + ``None`` qualify.
    """
    if value is None:
        return True
    return isinstance(value, (str, list, dict)) and len(value) == 0


def prune_dict(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values from the top level of `payload`. Non-recursive by design."""
    return {k: v for k, v in payload.items() if not _is_empty(v)}


def dump_model_for_wire(model: BaseModel) -> dict[str, Any]:
    """`model.model_dump(mode="json")` plus prune-if-opted-in.

    The single substrate helper to use anywhere the formatter serializes a
    model for the wire. Replaces direct `model.model_dump(mode="json")` at
    the points where the result becomes a wire payload (NOT internal
    transformations).
    """
    payload = model.model_dump(mode="json")
    if model_wants_prune(model):
        return prune_dict(payload)
    return payload
