"""a2kit's typed configuration surface.

This module implements the provider-chain configuration model documented
in ADR 0022. The single root, :class:`A2kitConfig`, composes subsystem
sub-models (``mcp``, ``http``, ``cli``) plus cross-cutting scalar fields.

Source precedence (inverted from pydantic-settings' default — consumer
beats code, every time):

    process env  >  .env file  >  init kwargs  >  field defaults

This inversion is load-bearing per ADR 0022: a developer who passes
``A2kitConfig(mcp=McpConfig(structured_output=True))`` is offering a
*default suggestion*, not a *binding*. A consumer who sets
``A2KIT_MCP__STRUCTURED_OUTPUT=false`` in their deployment env wins.

Env var convention: ``A2KIT_`` prefix, double-underscore (``__``)
delimits nested sub-model boundaries; single underscores are part of
field names (e.g., ``A2KIT_MCP__STRUCTURED_OUTPUT`` →
``cfg.mcp.structured_output``).

No public ``freeze`` / ``lock`` / ``bypass_env`` surface exists. The
recursive rule from ADR 0022 (consumer beats code at every link in the
provider chain) is enforced by the absence of such an API.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class McpConfig(BaseModel):
    """MCP-surface configuration (consumer-owned)."""

    structured_output: bool = Field(
        default=False,
        description=(
            "Strict structured-output wire mode. "
            "Set via env: A2KIT_MCP__STRUCTURED_OUTPUT=true. "
            "Default False: spec-compliant dual-emit per MCP 2025-06-18 "
            "(structuredContent + serialized JSON in content[]). Works on every "
            "MCP host. "
            "Set True: emit structuredContent + a short type-identifying marker "
            "in content[] (no duplicate JSON payload). Saves ~50% success tokens "
            "on hosts that forward structuredContent to the model (Anthropic API, "
            "Claude Code/Desktop/.ai/Cowork, ChatGPT, Codex CLI ≥v0.120, GitHub "
            "Copilot). Degrades on Cursor, Hermes Agent, OpenClaw, Kiro, and "
            "Vercel-AI-SDK consumers (they rely on the content[] fallback)."
        ),
    )


class HttpConfig(BaseModel):
    """HTTP-surface configuration (consumer-owned). Empty stub — knobs land per follow-up changes."""


class CliConfig(BaseModel):
    """CLI-surface configuration (consumer-owned). Empty stub — knobs land per follow-up changes."""


class A2kitConfig(BaseSettings):
    """Typed configuration root for a2kit.

    Construct without arguments to pick up env / .env / defaults. Pass
    kwargs to suggest code-side defaults (env still wins per ADR 0022).
    """

    mcp: McpConfig = McpConfig()
    http: HttpConfig = HttpConfig()
    cli: CliConfig = CliConfig()

    model_config = SettingsConfigDict(
        env_prefix="A2KIT_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(  # type: ignore[override]
        cls,
        settings_cls,  # noqa: ANN001, ARG003
        init_settings,  # noqa: ANN001
        env_settings,  # noqa: ANN001
        dotenv_settings,  # noqa: ANN001
        file_secret_settings,  # noqa: ANN001
    ) -> tuple[Any, ...]:
        # Inverted source order — consumer beats code, per ADR 0022.
        # Process env wins over .env wins over init kwargs wins over defaults.
        return env_settings, dotenv_settings, init_settings, file_secret_settings


__all__ = ["A2kitConfig", "CliConfig", "HttpConfig", "McpConfig"]
