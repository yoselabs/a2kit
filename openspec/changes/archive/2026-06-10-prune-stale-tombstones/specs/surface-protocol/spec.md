## REMOVED Requirements

### Requirement: `Substrate` Literal import SHALL raise with migration hint

**Reason**: the `Substrate` Literal was removed in `remove-substrate-literal` (~v0.38), past the migration horizon. Under the tombstone sunset rule (`AGENTS.md` §1) the dedicated raising-`__getattr__` is swept: `a2kit.packages.dispatch.substrate.Substrate` is simply absent, and a normal `ImportError` / `AttributeError` fires with no bespoke hint.

**Migration**: use `Surface` / `SURFACE_REGISTRY` (recorded in the CHANGELOG); no hinted error is retained.
