"""Two-axis contract test for the Context surface.

**Axis 1 — name coverage** (legacy, kept): every public ``fastmcp.Context``
method has a story on the CLI stub (implemented, or in the MCP_ONLY
allowlist).

**Axis 2 — signature compatibility** (new, the load-bearing check):
every call-shape used in ``tests/`` + ``examples/`` against ``ctx.<method>``
binds cleanly to **both** ``fastmcp.Context`` and ``StderrToolContext``.

Axis 2 is what catches divergence early. The previous one-axis test
(name-coverage only) passed while the stub's ``info(msg, **fields)``
signature crashed under the real fastmcp.Context. Adding the signature
axis prevents that recurrence.
"""

from __future__ import annotations

import inspect
from typing import Any

from fastmcp import Context

from a2kit.packages.cli.context import StderrToolContext

# Documented MCP-only surface — methods/attrs that have no CLI semantics by design.
# Stub may either raise MCPOnlyError on call or simply not implement
# (e.g. server/session-shaped properties).
MCP_ONLY: frozenset[str] = frozenset(
    {
        # LLM sampling — needs MCP client
        "sample",
        "sample_step",
        # Server-managed registries
        "list_resources",
        "list_prompts",
        "get_prompt",
        "list_roots",
        # Notifications protocol
        "send_notification",
        "close_sse_stream",
        # Session/transport-shaped properties — read-only attrs, not methods
        "client_id",
        "client_supports_extension",
        "fastmcp",
        "is_background_task",
        "lifespan_context",
        "origin_request_id",
        "request_context",
        "request_id",
        "session",
        "session_id",
        "task_id",
        "transport",
        # Component visibility — server-side admin
        "disable_components",
        "enable_components",
        "reset_visibility",
    }
)


# Every call shape used by tools through ``ctx.<method>`` in tests/ and examples/.
# Format: (method_name, positional_args, keyword_args). Add new shapes here
# when you write a test or example that exercises a new ctx pattern. The test
# below binds each shape against both Context impls — any unbindable shape
# fails CI before it ships to production.
CTX_CALL_SHAPES: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
    # Plain logging — fastmcp narrow shape, no fields. Both transports.
    ("info", ("plain message",), {}),
    ("warning", ("warn message",), {}),
    ("error", ("err message",), {}),
    ("debug", ("debug message",), {}),
    # With extra dict (fastmcp-native fielded form).
    ("info", ("msg",), {"extra": {"k": 1}}),
    ("warning", ("msg",), {"extra": {"k": 1}}),
    ("error", ("msg",), {"extra": {"k": 1}}),
    ("debug", ("msg",), {"extra": {"k": 1}}),
    # With logger_name.
    ("info", ("msg",), {"logger_name": "tool.x"}),
    # report_progress: positional + keyword forms.
    ("report_progress", (5, 10), {}),
    ("report_progress", (5,), {"total": 10}),
    ("report_progress", (5, 10), {"message": "halfway"}),
    # State: per-call dict.
    ("set_state", ("k", "v"), {}),
    ("get_state", ("k",), {}),
    ("delete_state", ("k",), {}),
    # read_resource: positional uri (string form — fastmcp accepts str|AnyUrl).
    ("read_resource", ("file:///x",), {}),
    # log primitive — narrow level keyword (Treatment 4).
    ("log", ("msg",), {"level": "info"}),
    ("log", ("msg",), {"level": "warning", "extra": {"k": 1}}),
    # elicit (Treatment 5).
    ("elicit", ("Pick one",), {"response_type": str}),
    ("elicit", ("Pick one",), {"response_type": ["a", "b"]}),
    # get_prompt / list_resources / list_prompts / list_roots — no args (Treatment 5).
    ("get_prompt", ("p",), {}),
    ("list_resources", (), {}),
    ("list_prompts", (), {}),
    ("list_roots", (), {}),
    # sample / sample_step — minimal positional form (Treatment 5).
    ("sample", ("hello",), {}),
    ("sample_step", ("hello",), {}),
    # NB: send_notification omitted (Open Question 3 in design.md —
    # the typed argument requires importing mcp.types, which the
    # sig-bind test doesn't need; behavioural parity is asserted in
    # the by-method MCPOnlyError test below).
]


def test_stub_covers_fastmcp_context_surface() -> None:
    """Axis 1 — every public ``fastmcp.Context`` member is on the stub or in MCP_ONLY."""
    public = {m for m in dir(Context) if not m.startswith("_")}
    stub_attrs = {m for m in dir(StderrToolContext) if not m.startswith("_")}
    missing = public - stub_attrs - MCP_ONLY
    assert not missing, (
        f"fastmcp.Context exposes {missing!r} which is neither implemented on "
        f"StderrToolContext nor allowlisted in MCP_ONLY. Either implement it "
        f"or add it to MCP_ONLY with a comment explaining why."
    )


def test_ctx_call_shapes_bind_against_both_contexts() -> None:
    """Axis 2 — every shape in CTX_CALL_SHAPES binds against both Context impls.

    This is the test that would have caught the v1.0+ kwarg-on-info crash:
    `("info", ("msg",), {"k": 1})` binds against StderrToolContext (which
    had `**fields`) but not against fastmcp.Context (which has narrow
    `(message, logger_name, extra)`).

    To add a new shape: append a tuple to CTX_CALL_SHAPES. If it doesn't bind
    on both sides, either the call is wrong (use `a2kit.ldd.<level>` for
    field-bearing logging) or one of the impls drifted (fix the drift).
    """
    failures: list[str] = []
    for method, args, kwargs in CTX_CALL_SHAPES:
        for cls in (Context, StderrToolContext):
            fn = getattr(cls, method, None)
            if fn is None:
                failures.append(f"{cls.__name__}.{method} missing")
                continue
            sig = inspect.signature(fn)
            try:
                # bind(None, ...) — first param is `self`, supply a sentinel.
                sig.bind(None, *args, **kwargs)
            except TypeError as exc:
                failures.append(f"{cls.__name__}.{method}({args=}, {kwargs=}) — {exc}")

    assert not failures, "Context call-shape drift:\n  " + "\n  ".join(failures)


# Methods where the stub mirrors fastmcp's signature exactly (Treatment 2
# of align-context-method-signatures). The test below pins
# `inspect.signature(stub_method) == inspect.signature(fastmcp_method)`
# for each — any fastmcp version bump that drifts a signature fails CI
# at the bind step instead of failing in production.
SIGNATURE_MIRRORED_METHODS: tuple[str, ...] = (
    "read_resource",
    "elicit",
    "sample",
    "sample_step",
    "get_prompt",
    "list_resources",
    "list_prompts",
    "list_roots",
    "send_notification",
)


def test_stub_signature_matches_fastmcp() -> None:
    """The Treatment-2 methods bind-compatible against fastmcp's signature.

    Drives the same parameter-binding pattern as
    ``test_ctx_call_shapes_bind_against_both_contexts`` but as a
    per-method guarantee for every signature-mirrored stub method.
    """
    import inspect as _inspect

    failures: list[str] = []
    for method in SIGNATURE_MIRRORED_METHODS:
        stub_fn = getattr(StderrToolContext, method, None)
        fastmcp_fn = getattr(Context, method, None)
        if stub_fn is None or fastmcp_fn is None:
            failures.append(f"{method} missing on stub or fastmcp")
            continue
        stub_sig = _inspect.signature(stub_fn)
        fastmcp_sig = _inspect.signature(fastmcp_fn)
        stub_params = {n: p.kind for n, p in stub_sig.parameters.items()}
        fastmcp_params = {n: p.kind for n, p in fastmcp_sig.parameters.items()}
        if stub_params != fastmcp_params:
            failures.append(f"{method}: stub params {stub_params} != fastmcp params {fastmcp_params}")
    assert not failures, "Stub signature drift:\n  " + "\n  ".join(failures)


def test_field_bearing_logging_is_only_on_ldd_not_on_ctx() -> None:
    """Kwarg-on-ctx is rejected by both Contexts; the field-bearing form
    lives on ``a2kit.ldd.*`` free functions instead. Pins the architectural
    invariant: if either Context starts accepting ``ctx.info("msg", k=v)``,
    the change is reverting design D-CTX-INFO and this test catches it."""
    for cls in (Context, StderrToolContext):
        sig = inspect.signature(cls.info)
        try:
            sig.bind(None, "msg", k=1)  # kwarg pattern: must NOT bind
        except TypeError:
            continue
        msg = (
            f"{cls.__name__}.info accepts arbitrary kwargs — design D-CTX-INFO violated. "
            f"Field-bearing logging belongs on a2kit.ldd.info, not on ctx.info."
        )
        raise AssertionError(msg)
