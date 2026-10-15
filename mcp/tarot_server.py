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

from tarot_engine import SPREADS, TarotError, get_engine  # noqa: E402


mcp = FastMCP("tarot-mcp")
ENGINE = get_engine()


@mcp.tool()
def draw_tarot(spread: str = "single", question: str = "") -> dict:
    """Draw tarot cards for an entertainment/reflection reading.

    Args:
        spread: "single" (单张指引) or "three" (三张牌阵：过去/现在/未来).
        question: Optional theme the user asks about, used for prompt context.
    """
    if spread not in SPREADS:
        raise ValueError(f"spread must be one of {sorted(SPREADS)}")
    draw = ENGINE.draw(spread=spread)
    if question.strip():
        draw["question"] = question.strip()
    return draw


@mcp.tool()
def get_card_meaning(slug: str, orientation: str = "upright") -> dict:
    """Get meaning of a single tarot card.

    Args:
        slug: Card slug, e.g. "the-fool" / "ace-of-cups".
        orientation: "upright" or "reversed".
    """
    if orientation not in ("upright", "reversed"):
        raise ValueError("orientation must be upright or reversed")
    card = ENGINE.get_card(slug)
    reversed_ = orientation == "reversed"
    return {
        "slug": card["slug"],
        "num": card["num"],
        "name": card["name"],
        "arcana": card["arcana"],
        "subtitle": card.get("subtitle"),
        "element_planet": card.get("element_planet"),
        "orientation": orientation,
        "keywords": card["keywords_reversed"] if reversed_ else card["keywords_upright"],
        "meaning": card["reversed_text"] if reversed_ else card["upright_text"],
        "affirmation": card.get("affirmation"),
        "love": card.get("love"),
        "career": card.get("career"),
        "archetype": card.get("archetype"),
        "faq": card.get("faq", []),
        "image": f"/tarot/{card['slug']}.webp",
    }


@mcp.tool()
def list_tarot_cards() -> list[dict]:
    """List all 78 tarot cards with slug, name, arcana and suit."""
    return ENGINE.list_cards()


if __name__ == "__main__":
    mcp.run()
