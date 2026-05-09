"""Testing-package exceptions."""

from __future__ import annotations


class SchemaSnapshotMismatch(AssertionError):
    """Raised when a per-tool schema snapshot drifts from the recorded one.

    The message carries a unified diff so the failure log is actionable.
    """


__all__ = ["SchemaSnapshotMismatch"]
