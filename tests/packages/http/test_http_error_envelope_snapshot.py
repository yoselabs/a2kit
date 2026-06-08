"""HTTP error-envelope wire snapshots — byte-equivalence baseline.

Every ``AppError`` subclass currently emitted by the HTTP path is exercised
end-to-end and the full response (status code + body bytes + content-type)
is asserted against an explicit inline expectation. This is the load-bearing
regression net for ``dispatch-pipeline-parity-on-http``: when the HTTP path
folds the dispatch pipeline and rendering moves to ``HttpErrorRenderStage``,
every byte here MUST remain identical.

When envelope shape evolves intentionally, update the expected dicts here
and bump the envelope schema version.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi.testclient import TestClient

import a2kit
from a2effect import AppError, Raises
from a2effect.errors import AuthError, InfrastructureError, InputError, PolicyError
from a2kit.packages.http.build import build_http_app
from a2kit.runtime import build
from a2kit.testing import app_of


# ---------- Author subclasses standing in for canonical conventions ---------- #


class _NotFound(AppError):
    """404 via per-class http_status override; kind=input."""

    kind = "input"
    http_status = 404
    hint = "verify the id from list_memories"


class _Timeout(AppError):
    """504 via per-class http_status override; kind=infra; retryable like upstream timeouts."""

    kind = "infra"
    http_status = 504
    retryable = True


class _Oops(AppError):
    """Generic bug kind — no http_status override; defaults to 500."""

    kind = "bug"


# ----------------------------------------------------------------------------- #


def _client(router_cls: type[a2kit.Router]) -> TestClient:
    app = app_of("snap", router_cls())
    fast_app = build_http_app(build(app))
    # raise_server_exceptions=False forces the unhandled-exception path to go
    # through the FastAPI exception-handler stack (the contract under test),
    # not bubble out to the test harness.
    return TestClient(fast_app, raise_server_exceptions=False)


def _assert_wire(
    resp: Any,
    *,
    status: int,
    expected_envelope: dict[str, Any],
    expected_extra_keys: tuple[str, ...] = (),
) -> None:
    """Assert byte-shape: status, content-type, body equals envelope wrapped in ``{"error": ...}``.

    ``expected_extra_keys`` lists envelope keys that are present but value-
    dependent (e.g. ``cause.trace_id`` for UnexpectedDefect); their presence
    is asserted but the value is not pinned.
    """
    assert resp.status_code == status, f"status: got {resp.status_code}"
    ct = resp.headers["content-type"]
    assert ct.startswith("application/json"), f"content-type: got {ct!r}"
    body = resp.json()
    assert set(body.keys()) == {"error"}, f"top-level keys: got {sorted(body.keys())}"
    env = body["error"]
    for k in expected_extra_keys:
        assert k in env, f"expected envelope key {k!r} present (value not pinned)"
        env.pop(k, None)
    assert env == expected_envelope, (
        f"envelope drift:\n  got     {json.dumps(env, sort_keys=True)}\n  expect  {json.dumps(expected_envelope, sort_keys=True)}"
    )


# ---------- Per-AppError-subclass byte snapshots ----------------------------- #


async def test_snapshot_not_found_404() -> None:
    class R(a2kit.Router):
        slug = "mem"

        @a2kit.read()
        async def fetch(self, *, id: str) -> Annotated[dict, Raises(_NotFound)]:
            raise _NotFound(f"memory id {id!r} does not exist", details={"id": id})

    resp = _client(R).post("/mem_fetch", json={"id": "abc"})
    _assert_wire(
        resp,
        status=404,
        expected_envelope={
            "type": "_NotFound",
            "kind": "input",
            "base_kind": "input",
            "retryable": False,
            "hint": "verify the id from list_memories",
            "details": {"id": "abc"},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_input_error_400() -> None:
    class R(a2kit.Router):
        slug = "val"

        @a2kit.read()
        async def check(self, *, x: int) -> Annotated[dict, Raises(InputError)]:
            raise InputError("bad input shape")

    resp = _client(R).post("/val_check", json={"x": 1})
    _assert_wire(
        resp,
        status=400,
        expected_envelope={
            "type": "InputError",
            "kind": "input",
            "base_kind": "input",
            "retryable": False,
            "hint": None,
            "details": {},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_auth_error_401() -> None:
    class R(a2kit.Router):
        slug = "sec"

        @a2kit.read()
        async def call(self, *, x: int) -> Annotated[dict, Raises(AuthError)]:
            raise AuthError("missing credentials")

    resp = _client(R).post("/sec_call", json={"x": 1})
    _assert_wire(
        resp,
        status=401,
        expected_envelope={
            "type": "AuthError",
            "kind": "auth",
            "base_kind": "auth",
            "retryable": False,
            "hint": None,
            "details": {},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_policy_error_403() -> None:
    class R(a2kit.Router):
        slug = "pol"

        @a2kit.read()
        async def call(self, *, x: int) -> Annotated[dict, Raises(PolicyError)]:
            raise PolicyError("not allowed")

    resp = _client(R).post("/pol_call", json={"x": 1})
    _assert_wire(
        resp,
        status=403,
        expected_envelope={
            "type": "PolicyError",
            "kind": "policy",
            "base_kind": "policy",
            "retryable": False,
            "hint": None,
            "details": {},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_infra_error_503() -> None:
    class R(a2kit.Router):
        slug = "svc"

        @a2kit.read()
        async def call(self, *, x: int) -> Annotated[dict, Raises(InfrastructureError)]:
            raise InfrastructureError("downstream gone")

    resp = _client(R).post("/svc_call", json={"x": 1})
    _assert_wire(
        resp,
        status=503,
        expected_envelope={
            "type": "InfrastructureError",
            "kind": "infra",
            "base_kind": "infra",
            "retryable": True,
            "hint": None,
            "details": {},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_timeout_504_via_class_override() -> None:
    class R(a2kit.Router):
        slug = "slow"

        @a2kit.read()
        async def call(self, *, x: int) -> Annotated[dict, Raises(_Timeout)]:
            raise _Timeout("hit the deadline")

    resp = _client(R).post("/slow_call", json={"x": 1})
    _assert_wire(
        resp,
        status=504,
        expected_envelope={
            "type": "_Timeout",
            "kind": "infra",
            "base_kind": "infra",
            "retryable": True,
            "hint": None,
            "details": {},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_generic_bug_500() -> None:
    class R(a2kit.Router):
        slug = "boom"

        @a2kit.read()
        async def call(self, *, x: int) -> Annotated[dict, Raises(_Oops)]:
            raise _Oops("internal explosion")

    resp = _client(R).post("/boom_call", json={"x": 1})
    _assert_wire(
        resp,
        status=500,
        expected_envelope={
            "type": "_Oops",
            "kind": "bug",
            "base_kind": "bug",
            "retryable": False,
            "hint": None,
            "details": {},
            "cause": None,
            "envelope_version": "1",
        },
    )


async def test_snapshot_unexpected_defect_500_from_keyerror() -> None:
    """Non-AppError → quarantined to UnexpectedDefect.

    ``cause.trace_id`` is non-deterministic per run; assert its presence but
    don't pin the value. Everything else MUST be byte-stable.
    """

    class R(a2kit.Router):
        slug = "raw"

        @a2kit.read()
        async def call(self, *, x: int) -> dict:
            raise KeyError(f"missing-{x}")

    resp = _client(R).post("/raw_call", json={"x": 1})
    body = resp.json()
    cause = body["error"].get("cause")
    # Today's baseline: cause carries the underlying exception's type, message,
    # and a fresh trace_id. If a future change tightens defect redaction (hides
    # type/message from the wire), update this snapshot in the same change so
    # the wire delta is explicit.
    assert isinstance(cause, dict), "UnexpectedDefect envelope MUST carry a populated `cause` object today"
    assert cause.get("type") == "KeyError"
    assert "missing-1" in cause.get("message", "")
    assert isinstance(cause.get("trace_id"), str)
    _assert_wire(
        resp,
        status=500,
        expected_envelope={
            "type": "UnexpectedDefect",
            "kind": "bug",
            "base_kind": "bug",
            "retryable": False,
            "hint": None,
            "details": {},
            "envelope_version": "1",
        },
        expected_extra_keys=("cause",),
    )
