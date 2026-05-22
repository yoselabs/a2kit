"""Sandboxed code-execution surface — the single import site for FastMCP's ``CodeMode`` transform and the Monty runtime.

The transform implementation lives in :mod:`a2kit.packages.codemode.transform`
(``A2kitCodeMode``, ``build_code_mode_transform``); the sandbox runtime,
result marshalling, and stub generation live in the ``runtime`` / ``marshal``
/ ``stubs`` submodules.
"""

from __future__ import annotations

from a2kit.packages.codemode.runtime import A2kitSandboxProvider
from a2kit.packages.codemode.transform import A2kitCodeMode, build_code_mode_transform

__all__ = [
    "A2kitCodeMode",
    "A2kitSandboxProvider",
    "build_code_mode_transform",
]
