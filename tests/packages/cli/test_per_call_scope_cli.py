"""BDD: per-call scope under the CLI runtime (dispatch-lifecycle-wiring).

Covers spec ``request-scoped-di``: ``invoke_tool_sync`` (the CLI in-process
runtime) opens a per-call child container per tool call; a ``per_call=True``
resource enters once during the call and exits once when the call returns.
"""

from __future__ import annotations

import pytest

import a2kit
from a2kit.packages.cli.runtime import invoke_tool_sync


class _Transaction:
    enter_count: int = 0
    exit_count: int = 0
    last_exc_type: type[BaseException] | None = None

    async def __aenter__(self) -> _Transaction:
        type(self).enter_count += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        type(self).exit_count += 1
        type(self).last_exc_type = exc_type


@pytest.fixture(autouse=True)
def _reset() -> None:
    _Transaction.enter_count = 0
    _Transaction.exit_count = 0
    _Transaction.last_exc_type = None


@a2kit.read()
async def _use_tx(tx: _Transaction) -> dict:
    return {"tx_id": id(tx)}


def test_per_call_resource_cleaned_up_at_cli_call_exit() -> None:
    """One CLI tool invocation enters Transaction once, exits once on clean return."""
    app = a2kit.App("per-call-cli")
    app.provide(_Transaction, per_call=True)

    invoke_tool_sync(_use_tx, {}, fmt="json", app=app)

    assert _Transaction.enter_count == 1, (
        f"Transaction entered {_Transaction.enter_count} times — expected 1"
    )
    assert _Transaction.exit_count == 1, (
        f"Transaction exited {_Transaction.exit_count} times — expected 1"
    )
    assert _Transaction.last_exc_type is None
