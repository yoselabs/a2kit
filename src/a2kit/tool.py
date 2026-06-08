from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal, Protocol

from a2kit._verbs import enricher, list_, read, write

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from a2effect import AppError

    from a2kit.metadata import A2KitMeta
    from a2kit.packages.di import Container
    from a2kit.packages.formatter import EncodingPlan
    from a2kit.routers import Router

Visibility = Literal["hidden", "cli", "all"]

_EMPTY_VIEW: Mapping[str, Any] = MappingProxyType({})


@dataclass(frozen=True)
class ToolDescriptor:
    """Typed introspection record for a registered tool.

    Materialized by ``App.add_router`` once per tool. ``format_hint`` is
    pre-computed from the tool's resolved return type so the CLI runtime can
    skip per-call format heuristics — see
    ``a2kit.packages.formatter.inference.infer_format_hint``.

    ``encoding_plan`` is the static :class:`EncodingPlan` for the return
    type — computed once here so the MCP format-routing wrapper consults it
    per call at zero decision cost (ADR 0014). It is the structured
    counterpart of ``format_hint``: it additionally marks flat-array fields
    nested inside a ``BaseModel`` envelope.

    ``verb`` carries the decorator family (``"read"``/``"list"``/``"write"``)
    so substrate adapters and selectors can filter by verb without
    re-reading ``A2KitMeta``. ``expose`` is the ordered tuple of
    substrates the projection tool registers on; default
    ``("mcp", "api")``. ``authorize`` is the optional per-tool
    authorization callable (enforcement lands in ``add-auth``).
    """

    name: str
    router: Router
    fn: Callable[..., Any]
    return_type: Any | None
    format_hint: Literal["tsv", "json", "page-tsv"]
    encoding_plan: EncodingPlan
    verb: Literal["read", "list", "write"] = "read"
    expose: tuple[str, ...] = ("mcp", "api")
    authorize: Callable[..., Any] | None = None
    # Projected from A2KitMeta at materialization (extend-descriptor-fields).
    # Container-dependent fields default to None and are finalised by
    # defer-descriptor-materialization once App.build() runs with container.
    ctx_param_name: str | None = None
    timeout: float | None = None
    annotations_view: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_VIEW)
    metadata_view: Mapping[str, Any] = field(default_factory=lambda: _EMPTY_VIEW)
    wire_param_names: frozenset[str] | None = None
    lazy_param_names: frozenset[str] | None = None
    # Typed error vocabulary materialized from `Annotated[ReturnT, Raises(...)]`
    # on the tool's return annotation (a2effect-foundation). Empty when no
    # Raises marker is present. Multiple markers in one Annotated[...] are
    # flattened additively.
    raises: tuple[type[AppError], ...] = ()
    # Private projection of the full A2KitMeta object. Substrate adapters in
    # `a2kit.packages.*` read this instead of reaching for `_get_meta(fn)` —
    # `ToolDescriptor` is the single read surface (privatize-tool-metadata).
    # Leading underscore signals "internal projection field; not part of
    # the user-facing descriptor contract".
    _meta: A2KitMeta | None = None


class DispatchHook(Protocol):
    """Wire-side pre-resolution hook for a tool dispatch.

    v0.37 contract (dispatch-lifecycle-wiring): given the tool function
    and the wire-supplied kwargs, return wire-side resolved kwargs.
    The hook does NOT perform DI — the framework runs
    ``Container.resolve_params`` AFTER the hook on its output. Typical
    use: convert a wire ``connection: str`` to a typed
    ``ConnectionConfig`` instance.
    """

    def __call__(
        self,
        fn: Callable[..., Any],
        wire_kwargs: dict[str, Any],
    ) -> dict[str, Any] | Awaitable[dict[str, Any]]: ...


def _strip_raises_from_annotation(annotation: Any) -> Any:
    """Strip `Raises(...)` markers from an `Annotated[T, Raises(...), ...]` return
    annotation, returning either the bare `T` (when only Raises markers remain)
    or a re-built `Annotated[T, ...]` preserving non-Raises metadata. Non-Annotated
    types pass through unchanged.
    """
    from typing import Annotated, get_args, get_origin

    from a2effect import Raises

    if get_origin(annotation) is not Annotated:
        return annotation
    bare, *metadata = get_args(annotation)
    preserved = [m for m in metadata if not isinstance(m, Raises)]
    if not preserved:
        return bare
    return Annotated[(bare, *preserved)]


def _build_descriptors(router: Router, container: Container | None = None) -> list[ToolDescriptor]:
    """Materialize one ``ToolDescriptor`` per tool on ``router``.

    When ``container`` is supplied (typically at ``runtime.build`` time),
    populates ``wire_param_names`` and ``lazy_param_names``. Without a
    container (``add_router`` time), those sentinel fields stay ``None``
    and substrate adapters that need them MUST read via
    ``AppRuntime.descriptor_for(name)``.
    """
    from types import MappingProxyType

    from a2effect import AppError, Raises

    from a2kit._surfaces import matrix_for, mounted_surfaces, resolve_canonical_name
    from a2kit.metadata import _get_meta
    from a2kit.packages.di import lazy_inner_type
    from a2kit.packages.formatter import build_encoding_plan, infer_format_hint
    from a2kit.signature import resolve_hints, wire_input_params

    out: list[ToolDescriptor] = []
    for fn in router.bound_tools():
        hints = resolve_hints(fn)
        return_type = hints.get("return")
        # Strip Annotated[ReturnT, Raises(...)] for format inference: the
        # Raises metadata is invisible to format-hint / encoding-plan logic.
        raises = Raises.flatten_from_annotation(fn)
        for cls in raises:
            if not (isinstance(cls, type) and issubclass(cls, AppError)):
                msg = (
                    f"tool {getattr(fn, '__name__', fn)!r}: Raises({cls!r}) member "
                    f"is not an AppError subclass; subclass a2effect.AppError or "
                    f"register an enricher / raises_as mapping"
                )
                raise TypeError(msg)
        bare_return_type = _strip_raises_from_annotation(return_type)
        format_hint = infer_format_hint(bare_return_type)
        encoding_plan = build_encoding_plan(bare_return_type)
        meta = _get_meta(fn)
        # Canonical name = flat slug_leaf (ADR 0028 Wave 2). The override pins
        # it verbatim; otherwise a router verb derives to `{slug}_{leaf}` and
        # an app-level verb stays the bare leaf. desc.name is the identity
        # used on MCP/HTTP and in the audit log.
        leaf = getattr(fn, "__name__", "<callable>")
        name = resolve_canonical_name(meta.extras.canonical_name_override, meta.extras.router_slug, leaf) if meta is not None else leaf
        # Carry the multi-surface fields onto the descriptor so substrate
        # adapters and selectors can filter without re-reading A2KitMeta.
        # `verb` defaults to "read" — the safest default for unstamped
        # tools (e.g. the _meta.health helper that uses _read_internal).
        # A2KitMeta.verb is `Literal["read", "write", "list", "tool"]`;
        # ToolDescriptor.verb is narrowed to read/list/write because
        # `tool` is the @app.mcp.tool family that does NOT produce a
        # ToolDescriptor (mcp_surface holds them separately).
        meta_verb = meta.verb if meta is not None else "read"
        verb: Literal["read", "list", "write"] = meta_verb if meta_verb in ("read", "list", "write") else "read"  # type: ignore[assignment]
        # Compat ``expose`` tuple = mounted NETWORK surfaces only (mcp/api).
        # CLI is a LOCAL surface tracked in the matrix, not in expose, so
        # membership reads (`"mcp" in expose`) and the network surface-name
        # validation keep their historical meaning.
        expose: tuple[str, ...] = (
            tuple(s for s in mounted_surfaces(matrix_for(meta.extras)) if s != "cli") if meta is not None else ("mcp", "api")
        )
        authorize = meta.extras.authorize if meta is not None else None
        ctx_param_name = meta.context_param_name if meta is not None else None
        timeout = meta.extras.timeout_seconds if meta is not None else None
        annotations_view = MappingProxyType(dict(meta.annotations_as_dict())) if meta is not None else MappingProxyType({})
        if meta is not None:
            metadata_view = MappingProxyType(
                {
                    "verb": meta.verb,
                    "tags": frozenset(meta.tags),
                    "context_param_name": meta.context_param_name,
                    "tool_name": meta.tool_name,
                    "extras": MappingProxyType(meta.extras.model_dump()),
                }
            )
        else:
            metadata_view = MappingProxyType({})
        wire_param_names: frozenset[str] | None = None
        lazy_param_names: frozenset[str] | None = None
        if container is not None:
            wire_params, _scopes = wire_input_params(fn, container)
            wire_param_names = frozenset(wire_params.keys())
            lazy_param_names = frozenset(pname for pname, ann in hints.items() if pname != "return" and lazy_inner_type(ann) is not None)
        out.append(
            ToolDescriptor(
                name=name,
                router=router,
                fn=fn,
                return_type=bare_return_type,
                format_hint=format_hint,
                encoding_plan=encoding_plan,
                verb=verb,
                expose=expose,
                authorize=authorize,
                ctx_param_name=ctx_param_name,
                timeout=timeout,
                annotations_view=annotations_view,
                metadata_view=metadata_view,
                wire_param_names=wire_param_names,
                lazy_param_names=lazy_param_names,
                raises=raises,
                _meta=meta,
            )
        )
    return out


__all__ = [
    "DispatchHook",
    "ToolDescriptor",
    "Visibility",
    "_build_descriptors",
    "enricher",
    "list_",
    "read",
    "write",
]
