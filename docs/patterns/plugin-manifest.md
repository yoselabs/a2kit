# Plugin manifest

`a2kit.packages._plugin` is the framework's declarative
extension-point shape. Ported verbatim (modulo logger) from a2web's
`unify-plugin-manifests` change (a2web ADR-0001 Pattern 2). One shape
collapses registration, capability-aware configuration delivery, and
unavailability handling for every extension point that needs them.

## When to use it

Add a `MANIFEST = PluginManifest(...)` constant in a plugin module
when you're building a new extension surface where:

- Multiple plugins of the same protocol need to be discoverable at boot
- A plugin's availability depends on capability presence (API key,
  Keychain, optional dependency) that should be checked once at boot
- Order matters (priority-driven dispatch)

Today's pilot is **API-key auth providers** under
`packages/auth/_providers/`. Future candidates: connections (where
credentials presence varies), LDD sinks (otel optional), code-mode
tools, surface registry.

## The shape

```python
# packages/<surface>/_providers/<plugin_name>.py
from a2kit.packages._plugin import PluginManifest, Unavailable
from my_pkg.spec import MyProtocol

class MyImpl(MyProtocol):
    ...

def _factory(context: object) -> MyImpl | Unavailable:
    if not context_has_required_capability(context):
        return Unavailable("missing capability X")
    return MyImpl(...)

MANIFEST = PluginManifest(
    name="my_plugin",
    protocol=MyProtocol,
    factory=_factory,
    priority=0,
)
```

## The `Unavailable` discipline

Factories MUST return `Unavailable(reason)` (a `NamedTuple` with one
string field) when their capability is missing. They MUST NOT raise.

Reason: unavailability at boot is *expected*. Returning a value forces
the call site to handle it; `load_surface` silently drops `Unavailable`
entries before they reach the registry, logging one INFO line per
drop. Consumer code never sees the unavailable case.

## Side-effect-free imports

Every manifest module SHALL declare only:

- imports
- class / function definitions
- `MANIFEST = PluginManifest(...)` assignment
- the module docstring
- `if TYPE_CHECKING:` guards

No top-level network calls, no env reads, no registry mutation, no
calls other than `PluginManifest(...)`. `load_surface` imports every
module under the discovered surface path at boot; a side-effecting
top level breaks the model.

The test
`tests/capabilities/plugin_manifest/test_manifest_module_no_import_side_effects.py`
walks every discoverable manifest module's AST and fails if any
top-level node violates the contract.

## Discovery API

```python
from a2kit.packages._plugin import load_surface, load_surface_sorted

# Unordered registry by name
registry: dict[str, MyProtocol] = load_surface(
    "my_pkg._providers", MyProtocol, context
)

# Priority-ordered list (descending)
ordered: list[tuple[str, MyProtocol]] = load_surface_sorted(
    "my_pkg._providers", MyProtocol, context
)
```

## See also

- `openspec/specs/plugin-manifest/spec.md` — locked contract.
- `openspec/specs/surface-protocol/spec.md` — surfaces register via
  MANIFEST going forward.
- `src/a2kit/packages/auth/_providers/api_key.py` — pilot.
- a2web `_plugin.py` and ADR-0001 Pattern 2 — origin.
