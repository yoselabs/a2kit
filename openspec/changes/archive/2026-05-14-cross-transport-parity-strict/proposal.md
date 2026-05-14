# Cross-transport parity for unknown-kwarg rejection (case 5)

## Why

`tests/test_transport_parity.py:177` skips `test_case5_unknown_kwarg_parity`
with the rationale:

> in-process dispatcher silently drops unknown kwargs while FastMCP
> rejects them at the wire. This is a separate parity issue, not in
> scope for fix-mcp-dispatch-strips-ctx.

The skip was authored **before** `rebuild-test-client-on-real-context`
landed. After that rebuild, the test-harness "CLI" leg now drives
`fastmcp.Client(transport=build_mcp_server(app))` — i.e. **both legs
go through FastMCP** at the transport boundary, and FastMCP rejects
unknown kwargs at both ends. The skip rationale may already be
obsolete.

The case still warrants a change because:

1. **Verification gap**: nobody has run the case against the rebuilt
   harness. If both legs pass identically (likely), the skip is dead
   weight and removing it adds a guarded contract. If the legs still
   diverge (possible — e.g. CLI runtime's dispatcher hook silently
   accepts unknown kwargs that never reach FastMCP), the bug surfaces
   and gets fixed.

2. **Production-CLI scope**: the test-harness "CLI" leg is one of
   three CLI surfaces:
   ```
   ┌──────────────────────────────┬───────────────────────┐
   │ surface                       │ unknown-kwarg posture │
   ├──────────────────────────────┼───────────────────────┤
   │ test-harness CLI (post-rebuild)│ FastMCP-strict (rebuild)│
   │ production Typer CLI         │ Typer rejects flags   │
   │ in-process runtime dispatcher│ ???                   │
   └──────────────────────────────┴───────────────────────┘
   ```
   The "in-process runtime dispatcher" surface (`_invoke_tool_in_process`
   in `src/a2kit/packages/cli/runtime.py`) is what FastMCP's Typer
   callback also calls into for `<app> tasks <name> --kwargs`. If THAT
   surface silently drops unknown kwargs, the production CLI is
   already covered by Typer's strict flag-parsing, but any future
   programmatic caller (e.g. a future a2kit-side test that bypasses
   Typer) is exposed.

3. **Documentation**: the OPERATIONAL_CONTRACTS document currently
   says nothing about unknown-kwarg handling. After this change, the
   contract is "both transports raise on unknown kwargs; behaviour is
   consistent" — captured once and enforced by the parity test.

## What Changes

- **MODIFY** `tests/test_transport_parity.py:177-188` — remove the
  `@pytest.mark.skip(...)` decorator. The test asserts both legs
  raise an exception when called with an undeclared kwarg.

- **VERIFY** the test passes. If it does not, audit
  `src/a2kit/packages/cli/runtime.py::_invoke_tool_in_process` and
  `src/a2kit/packages/testing/client.py::TestClient.invoke` for the
  silent-drop path. If a fix is needed, the fix is small (validate
  `call_kwargs` against `inspect.signature(fn).parameters` before
  calling `fn(**call_kwargs)`).

- **ADD** an `OPERATIONAL_CONTRACTS.md` clause documenting the
  contract: "Unknown kwargs are rejected at both transport boundaries
  with a `TypeError`-shaped error (CLI Typer surfaces as
  `BadParameter`; FastMCP surfaces as the structured ToolError
  envelope wrapping `TypeError`)."

- **ADD** a `cross-transport-parity-strict` requirement to
  `mcp-context-passthrough` spec.

## Impact

- One test transitions from skip → pass (or surfaces a real defect to
  fix; either outcome is progress).
- Possible small fix in `runtime.py` if the gap is real: validate
  `call_kwargs` keys against `inspect.signature(fn).parameters` keys;
  raise `TypeError` on extras.
- `OPERATIONAL_CONTRACTS.md` gains a new short section.
- No consumer-facing behaviour change in the green-path case. Edge
  case (passing unknown kwargs programmatically) goes from
  silent-drop to loud-reject — which is the correct behaviour and
  matches how Typer already behaves for CLI flags.

## Risk

Low. If the gap doesn't exist, this is a one-line skip removal +
OPERATIONAL_CONTRACTS entry. If the gap does exist, the fix is small
and well-bounded.

The only real risk: existing consumer code that *relies on* the
silent-drop behaviour (e.g. forwards a dict of `**user_kwargs` that
includes app-level keys to a tool that only declares a subset). The
fix is to whitelist what the consumer passes — also the correct
behaviour. Low likelihood; even lower likelihood of being a real
deployment.
