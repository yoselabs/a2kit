"""``a2kit.packages.*`` — internal scaffolding, NOT the consumer API.

This namespace holds a2kit's implementation packages (formatter, ldd,
di, dispatch, http, mcp, cli, lint, ...). It is the substrate's
internal organization. **Consumers should import from the top-level
``a2kit`` package**, which re-exports the canonical surface
(``a2kit.App``, ``a2kit.Router``, ``a2kit.read``, ``a2kit.write``,
``a2kit.list_``, ``a2kit.Lazy``, ``a2kit.LddEmission``,
``a2kit.ToolContext``, ``a2kit.HealthResult``, ``a2kit.A2KitError``).

Per a2kit's CONSTITUTION.md Article VI (Magic Budget) and Article IX
(Self-Application): private vocabulary stays inside this namespace.
The convention mirrors stdlib (``_thread`` vs ``threading``).

Imports under ``a2kit.packages.*`` continue to work indefinitely
(back-compat), but they are not a stability surface — modules may be
reorganized internally without a deprecation window. The top-level
``a2kit.*`` re-exports ARE the stability surface.
"""
