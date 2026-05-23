"""Three-way signature classifier for substrate-facing wrappers.

Per ADR 0020 / `substrate-signature-split`: every parameter of a tool
function classifies into exactly one of three buckets per substrate.

- **Substrate-reserved**: the annotation matches a frozen allowlist for
  the named substrate (FastAPI: ``Request``/``Response``/``BackgroundTasks``/
  ``WebSocket``; FastMCP: ``Context``). The substrate populates it at
  dispatch; passes through to the wrapper's surface signature.
- **Container-known**: ``container.has_provider(annotation)`` is true.
  The wrapper body resolves it via ``Container.call_scope``; it does
  NOT appear in the wrapper's surface signature.
- **Wire**: everything else. Appears in the wrapper's surface signature;
  the substrate routes it from request body/query/path/form.

Cross-substrate misclassification (e.g. ``ctx: Context`` on the FastAPI
substrate) raises :class:`SubstrateSignatureError` at install time —
both substrate-reserved frozensets are inspected so the error names the
foreign substrate where the type IS reserved.

Allowlists are frozen at module load. Extending them requires an ADR
0020 amendment plus a one-line frozenset edit; the test in
``tests/packages/dispatch/test_substrate_reserved_allowlist.py`` asserts
membership against a baseline so any unrecorded change fails CI.

This module deliberately keeps the substrate types behind lazy lookups:
``import a2kit.packages.dispatch.substrate`` does not pull ``fastapi``,
``starlette``, or ``fastmcp``. Cold-start preserved.
"""

from __future__ import annotations

import inspect
import sys
import types
import typing
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from a2kit.signature import resolve_hints

if TYPE_CHECKING:
    from collections.abc import Callable

    from a2kit.packages.di import Container

Substrate = Literal["fastapi", "fastmcp"]


class SubstrateSignatureError(TypeError):
    """A parameter's annotation is reserved by a different substrate.

    Raised when classifying a tool against substrate ``S`` finds a
    parameter whose annotation is in the **other** substrate's reserved
    allowlist. The author either registered the tool on the wrong
    surface, or pulled in a substrate-specific type by mistake.
    """

    def __init__(
        self,
        *,
        fn_name: str,
        param_name: str,
        annotation: Any,
        wrong_substrate: Substrate,
        right_substrate: Substrate,
    ) -> None:
        self.fn_name = fn_name
        self.param_name = param_name
        self.annotation = annotation
        self.wrong_substrate = wrong_substrate
        self.right_substrate = right_substrate
        ann_name = getattr(annotation, "__name__", repr(annotation))
        msg = (
            f"{fn_name}: parameter {param_name!r} is annotated {ann_name}, "
            f"which is reserved by the {right_substrate!r} substrate, not "
            f"{wrong_substrate!r}. If MCP semantics are intended, register the "
            f"tool with @app.mcp.tool; for HTTP, use only FastAPI-native "
            f"reserved types (Request, Response, BackgroundTasks, WebSocket)."
        )
        super().__init__(msg)


@dataclass(frozen=True)
class SplitSignature:
    """The three buckets produced by :func:`split_signature`.

    Each bucket maps ``param_name -> inspect.Parameter``. The original
    ``Parameter`` is preserved (default, kind, annotation) so callers
    that rebuild a substrate-facing signature do not have to re-resolve
    type hints.

    - ``reserved``: substrate-native types the substrate populates.
    - ``container``: types a2kit DI resolves via ``call_scope``.
    - ``wire``: everything else; substrate routes from the request.

    ``substrate`` records which substrate this split was computed
    against; consumers use it to pick the matching reserved allowlist
    when rebuilding signatures.
    """

    substrate: Substrate
    reserved: dict[str, inspect.Parameter] = field(default_factory=dict)
    container: dict[str, inspect.Parameter] = field(default_factory=dict)
    wire: dict[str, inspect.Parameter] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reserved allowlists. Lazy-resolved by name to keep cold-start clean.
# ---------------------------------------------------------------------------

# Module-path -> attribute names. Lookups happen via ``sys.modules``: if
# the substrate is not yet imported in this process, the type cannot have
# been used in any annotation either, so the type cannot match. This
# means the allowlist check is correct *and* free at cold-start.
_FASTAPI_RESERVED_SPECS: tuple[tuple[str, str], ...] = (
    ("starlette.requests", "Request"),
    ("starlette.responses", "Response"),
    ("fastapi", "BackgroundTasks"),
    ("starlette.websockets", "WebSocket"),
)

_FASTMCP_RESERVED_SPECS: tuple[tuple[str, str], ...] = (("fastmcp", "Context"),)


def _reserved_types(specs: tuple[tuple[str, str], ...]) -> frozenset[type]:
    """Resolve ``(module, name)`` specs into a frozenset of live types.

    Only modules already in ``sys.modules`` contribute — if a substrate
    is not yet imported, none of its types can appear in any annotation,
    so omitting them is correct. The full module is imported on demand
    only when the caller passes ``force=True`` (the strict-baseline test
    uses this to assert exact membership against fully-imported state).
    """
    out: set[type] = set()
    for mod_path, attr in specs:
        mod = sys.modules.get(mod_path)
        if mod is None:
            continue
        cls = getattr(mod, attr, None)
        if isinstance(cls, type):
            out.add(cls)
    return frozenset(out)


def fastapi_reserved() -> frozenset[type]:
    """Return the FastAPI reserved-type allowlist (lazy, cold-start-safe)."""
    return _reserved_types(_FASTAPI_RESERVED_SPECS)


def fastmcp_reserved() -> frozenset[type]:
    """Return the FastMCP reserved-type allowlist (lazy, cold-start-safe)."""
    return _reserved_types(_FASTMCP_RESERVED_SPECS)


def _force_reserved(specs: tuple[tuple[str, str], ...]) -> frozenset[type]:
    """Import every spec's module and return the materialized set.

    Used only by the allowlist-baseline test. Production callers use
    the lazy ``fastapi_reserved`` / ``fastmcp_reserved`` accessors.
    """
    import importlib

    out: set[type] = set()
    for mod_path, attr in specs:
        try:
            mod = importlib.import_module(mod_path)
        except ImportError:
            continue
        cls = getattr(mod, attr, None)
        if isinstance(cls, type):
            out.add(cls)
    return frozenset(out)


# ---------------------------------------------------------------------------
# Annotation unwrapping
# ---------------------------------------------------------------------------


def _unwrap_annotation(ann: Any) -> Any:
    """Strip ``Annotated[T, ...]``, ``Optional[T]``, and ``T | None``.

    Returns the inner concrete type so the classifier can compare via
    identity (``is``) against the reserved allowlist and ``has_provider``.

    Cases:

    - ``Annotated[T, m1, m2, ...]`` -> ``T`` (drop metadata)
    - ``Optional[T]`` / ``T | None`` / ``Union[T, None]`` -> ``T``
      (drop the ``None`` arm)
    - ``Union[A, B]`` with no ``None`` -> returned unchanged (ambiguous;
      the classifier treats it as wire — substrates own union decoding)
    - ``ForwardRef``/strings -> returned unchanged; ``resolve_hints``
      should have resolved them upstream. If one slips through, the
      classifier falls through to wire — safe default.
    """
    if ann is None or ann is inspect.Parameter.empty:
        return ann
    # Annotated[T, ...] — peel metadata, recurse on the inner type so
    # Annotated[Optional[T], ...] also unwinds.
    if typing.get_origin(ann) is typing.Annotated or (hasattr(ann, "__metadata__") and hasattr(ann, "__origin__")):
        inner = typing.get_args(ann)[0] if typing.get_args(ann) else ann
        return _unwrap_annotation(inner)
    origin = typing.get_origin(ann)
    if origin is typing.Union or origin is types.UnionType:
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        if len(args) == 1:
            return _unwrap_annotation(args[0])
        # Multi-arm union with no None — substrates decide; treat as wire.
        return ann
    return ann


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


_BOUND_FIRST = frozenset({"self", "cls"})


def split_signature(
    fn: Callable[..., Any],
    substrate: Substrate,
    container: Container,
) -> SplitSignature:
    """Classify ``fn``'s parameters into reserved / container / wire.

    Walks the raw signature, skipping only ``self``/``cls`` (the bound
    first param for methods). Every other parameter is classified — in
    particular, FastMCP's ``Context`` lands in the ``reserved`` bucket
    on the ``fastmcp`` substrate, and triggers
    :class:`SubstrateSignatureError` on the ``fastapi`` substrate.

    Resolution order per parameter:

    1. If the unwrapped annotation is in the **other** substrate's
       reserved set -> raise :class:`SubstrateSignatureError`.
    2. If the unwrapped annotation is in **this** substrate's reserved
       set -> ``reserved`` bucket.
    3. If ``container.has_provider(<original ann>)`` is true ->
       ``container`` bucket. (The original annotation is passed, not the
       unwrapped one, so providers registered against ``Annotated``
       forms still match.)
    4. Else -> ``wire`` bucket.

    The order matters: substrate-reserved beats container-known. An
    author who registers a provider for ``Request`` would otherwise
    leak the substrate-reserved type into the DI graph silently; the
    explicit precedence makes that a no-op (the substrate populates it).
    """
    if substrate == "fastapi":
        this_reserved = fastapi_reserved()
        other_reserved = fastmcp_reserved()
        other_name: Substrate = "fastmcp"
    elif substrate == "fastmcp":
        this_reserved = fastmcp_reserved()
        other_reserved = fastapi_reserved()
        other_name = "fastapi"
    else:  # pragma: no cover -- Literal narrows this in practice
        msg = f"unknown substrate {substrate!r}; expected 'fastapi' or 'fastmcp'"
        raise ValueError(msg)

    fn_name = getattr(fn, "__qualname__", getattr(fn, "__name__", "<callable>"))
    hints = resolve_hints(fn)
    sig = inspect.signature(fn)
    split = SplitSignature(substrate=substrate)

    for i, (name, param) in enumerate(sig.parameters.items()):
        if i == 0 and name in _BOUND_FIRST:
            continue
        raw = hints.get(name, param.annotation)
        unwrapped = _unwrap_annotation(raw)
        if isinstance(unwrapped, type) and unwrapped in other_reserved:
            raise SubstrateSignatureError(
                fn_name=fn_name,
                param_name=name,
                annotation=unwrapped,
                wrong_substrate=substrate,
                right_substrate=other_name,
            )
        if isinstance(unwrapped, type) and unwrapped in this_reserved:
            split.reserved[name] = param
            continue
        if container.has_provider(raw) or (unwrapped is not raw and container.has_provider(unwrapped)):
            split.container[name] = param
            continue
        split.wire[name] = param

    return split


__all__ = [
    "_FASTAPI_RESERVED_SPECS",
    "_FASTMCP_RESERVED_SPECS",
    "SplitSignature",
    "Substrate",
    "SubstrateSignatureError",
    "_force_reserved",
    "fastapi_reserved",
    "fastmcp_reserved",
    "split_signature",
]
