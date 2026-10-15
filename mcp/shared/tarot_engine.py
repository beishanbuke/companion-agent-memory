"""Tarot engine: card catalog, spreads and draw logic.

Card meanings come from the crawled JobCannon tarot pages
(mcp/catalog/tarot_cards.json, original wording preserved).
Draws are random per call; orientation is 正位/逆位 with equal odds.
"""

from __future__ import annotations

import json
import random
import secrets
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent.parent / "catalog" / "tarot_cards.json"

SPREADS = {
    "single": {"name": "单张指引", "positions": ["当下的指引"]},
    "three": {"name": "三张牌阵", "positions": ["过去 · 根基", "现在 · 状态", "未来 · 趋势"]},
}

SUIT_NAMES = {"wands": "权杖", "cups": "圣杯", "swords": "宝剑", "pentacles": "钱币"}


class TarotError(RuntimeError):
    pass


class TarotEngine:
    def __init__(self, catalog_path: Path | str = CATALOG_PATH):
        self._path = Path(catalog_path)
        if not self._path.exists():
            raise TarotError(f"tarot catalog not found: {self._path}")
        data = json.loads(self._path.read_text(encoding="utf-8"))
        self._cards: list[dict[str, Any]] = data["cards"]
        self._by_slug = {c["slug"]: c for c in self._cards}

    # ---------- queries ----------

    def list_cards(self) -> list[dict[str, Any]]:
        return [
            {
                "num": c["num"],
                "slug": c["slug"],
                "name": c["name"],
                "arcana": c["arcana"],
                "suit": c["suit"],
                "suit_name": SUIT_NAMES.get(c["suit"] or ""),
                "subtitle": c.get("subtitle"),
                "image": f"/tarot/{c['slug']}.webp",
            }
            for c in self._cards
        ]

    def get_card(self, slug: str) -> dict[str, Any]:
        card = self._by_slug.get(slug)
        if not card:
            raise TarotError(f"unknown card slug: {slug!r}")
        return card

    # ---------- drawing ----------

    def draw(self, spread: str = "single") -> dict[str, Any]:
        if spread not in SPREADS:
            raise TarotError(f"unknown spread: {spread!r}")
        positions = SPREADS[spread]["positions"]
        count = len(positions)
        chosen = secrets.SystemRandom().sample(self._cards, count)
        rng = random.Random(secrets.randbelow(2**63))
        cards = []
        for position, card in zip(positions, chosen):
            reversed_ = rng.random() < 0.5
            cards.append(self._drawn_card_payload(card, reversed_, position))
        return {
            "spread": spread,
            "spread_name": SPREADS[spread]["name"],
            "positions": positions,
            "cards": cards,
            "disclaimer": "塔罗解读仅供娱乐与自我反思参考，真正的选择在你自己手中。",
        }

    def _drawn_card_payload(
        self, card: dict[str, Any], reversed_: bool, position: str
    ) -> dict[str, Any]:
        return {
            "slug": card["slug"],
            "num": card["num"],
            "name": card["name"],
            "arcana": card["arcana"],
            "arcana_name": "大阿尔卡纳" if card["arcana"] == "major" else "小阿尔卡纳",
            "suit": card["suit"],
            "suit_name": SUIT_NAMES.get(card["suit"] or ""),
            "subtitle": card.get("subtitle"),
            "element_planet": card.get("element_planet"),
            "position": position,
            "orientation": "reversed" if reversed_ else "upright",
            "orientation_name": "逆位" if reversed_ else "正位",
            "keywords": card["keywords_reversed"] if reversed_ else card["keywords_upright"],
            "meaning": card["reversed_text"] if reversed_ else card["upright_text"],
            "affirmation": card.get("affirmation"),
            "love": card.get("love"),
            "career": card.get("career"),
            "archetype": card.get("archetype"),
            "image": f"/tarot/{card['slug']}.webp",
        }

    # ---------- prompt text ----------

    def to_prompt_text(self, draw: dict[str, Any], question: str = "") -> str:
        lines = [
            f"[塔罗 MCP 已完成抽牌：{draw['spread_name']}]",
        ]
        for card in draw["cards"]:
            lines.append(
                f"- {card['position']}：《{card['name']}》（{card['arcana_name']}"
                f"{('·' + card['suit_name']) if card['suit_name'] else ''}，{card['orientation_name']}）"
                f"关键词：{'、'.join(card['keywords'])}。{card['meaning']}"
            )
            if card.get("affirmation"):
                lines.append(f"  肯定语：“{card['affirmation']}”")
        if question:
            lines.append(f"用户想问的主题：{question}")
        lines.append(
            "请结合以上牌面含义、用户的历史记忆和当前情绪，写一段专属的塔罗解读："
            "先逐张呼应牌面，再把牌串联成一条线，最后落到一个温柔而具体的行动建议上。"
            "语气像熟悉的朋友，不要绝对化预言；结尾带上娱乐参考提醒。"
        )
        return "\n".join(lines)


_default_engine: TarotEngine | None = None


def get_engine() -> TarotEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = TarotEngine()
    return _default_engine
