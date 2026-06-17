"""Public alias for ``a2kit.packages.spoke`` — the internal-spoke client.

Lets first-party jobs import the discoverable surface as
``from a2kit.spoke import client``. Implementation lives in
``a2kit.packages.spoke`` to keep the canonical layout under ``packages/``.
"""

from __future__ import annotations

from a2kit.packages.spoke import SpokeClient, SpokeError, client

__all__ = ["SpokeClient", "SpokeError", "client"]
