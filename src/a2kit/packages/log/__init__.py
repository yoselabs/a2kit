"""``a2kit.log`` — the author-facing emission surface, on stdlib ``logging``.

One concept: stdlib level methods (``debug`` / ``info`` / ``warning`` /
``error``). Each accepts a message + fields OR a typed instance. There is no
``event()`` / ``report()`` / loose ``log()`` verb, and no second public
namespace for durable records — the call access-log is internal plumbing
(the ``a2kit.calls`` logger + an opt-in file handler), configured not called.
"""

from __future__ import annotations

from a2kit.packages.log.emission import debug, error, info, warning

__all__ = ["debug", "error", "info", "warning"]
