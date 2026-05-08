"""`a2kit.contrib` — opt-in batteries built on top of the kit core.

`contrib.<name>` modules are *not* part of the core import path; pulling them
in is an explicit author choice. The core kit (App, Router, Provider, the
middleware chain, the DI resolver) has zero knowledge of contrib's contents.

v0.13 ships:

- `a2kit.contrib.connections` — the connection-aware bits previously hard-
  wired into the tool decorator (store lookup, write-enforcement, the
  `login` / `logout` / `connections list` tools).
"""

from __future__ import annotations

__all__: list[str] = []
