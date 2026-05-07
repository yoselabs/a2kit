"""Example: type-system-first decorator — what ty would catch at compile time.

Demonstrates patterns ty (or any strict type checker) catches before runtime:

  1. `-> str` returns from tools — flagged via the `R` TypeVar bound on `tool`.
     ty would emit: "Argument of type 'Callable[..., Coroutine[..., str]]' is
     incompatible with parameter expecting return Mapping/BaseModel/Sequence".

  2. Missing connection_param — A2K001 lint rule (AST fallback when ty unavailable).

Run: `uv run python examples/typed_decorator.py`
"""

from __future__ import annotations

import a2kit


# --- Caught at runtime by the `_check_return_annotation` gate ---------------
# The fat decorator refuses `-> str` at decoration time.
# ty would catch the same issue at compile time via the R bound on @overload.
async def _bad_str_return(x: int) -> str:  # ty: error: incompatible return type
    return f"hello {x}"


# --- Type-OK example --------------------------------------------------------
@a2kit.tool()
async def good_dict_return(x: int) -> dict:
    """Returns a dict — ty + runtime gate both happy."""
    return {"x": x}


# --- Pydantic model return (preferred) --------------------------------------
from pydantic import BaseModel  # noqa: E402


class Result(BaseModel):
    x: int


@a2kit.tool()
async def good_model_return(x: int) -> Result:
    return Result(x=x)


def main() -> None:
    print("Tools registered:")
    print(f"  good_dict_return: caps={sorted(good_dict_return._a2kit_capabilities)}")
    print(f"  good_model_return: caps={sorted(good_model_return._a2kit_capabilities)}")
    print()
    print("If you uncomment the `@a2kit.tool` line on `_bad_str_return`,")
    print("the runtime gate raises InvalidToolReturnTypeError at decoration.")
    print("ty (when available) catches the same at compile time.")


if __name__ == "__main__":
    main()
