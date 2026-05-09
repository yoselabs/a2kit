from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from a2kit.app import App


_APP_CTX: ContextVar[App] = ContextVar("_APP_CTX")
