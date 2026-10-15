from __future__ import annotations

import sys
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'mcp'. Install with: pip install mcp"
    ) from exc

SHARED_DIR = Path(__file__).resolve().parent / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from horoscope_engine import (  # noqa: E402
    THEMES,
    ZODIAC_SIGNS,
    generate_horoscope,
)


mcp = FastMCP("horoscope-mcp")


@mcp.tool()
def get_horoscope(
    sign: str,
    date: str = "",
    emotion: str = "",
    theme: str = "general",
    style: str = "gentle",
) -> dict:
    """Get a structured daily horoscope card for entertainment/companion use.

    Args:
        sign: Zodiac sign, e.g. "libra" / "天秤座" / "天秤".
        date: Query date "YYYY-MM-DD"; empty means today.
        emotion: Current emotion of the user, e.g. "焦虑"; adjusts phrasing only.
        theme: One of general/study/love/social/health/wealth.
        style: One of gentle(温柔安抚)/cheerful(活泼轻快)/calm(稳重简洁).
    """
    if not (sign or "").strip():
        raise ValueError("sign is required")

    card = generate_horoscope(
        sign=sign.strip(),
        date=date.strip() or None,
        emotion=emotion.strip(),
        theme=theme.strip() or "general",
        style=style.strip() or "gentle",
    )
    return card


@mcp.tool()
def list_zodiac_signs() -> list[dict]:
    """List supported zodiac signs with names and symbols."""
    return [
        {
            "sign": key,
            "name": info["name"],
            "symbol": info["symbol"],
            "element": info["element"],
        }
        for key, info in ZODIAC_SIGNS.items()
    ]


@mcp.tool()
def list_themes() -> dict:
    """List supported fortune themes and styles."""
    return {"themes": THEMES, "styles": ["gentle", "cheerful", "calm"]}


if __name__ == "__main__":
    mcp.run()
