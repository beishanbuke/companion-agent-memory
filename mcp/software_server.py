from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path


try:
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'mcp'. Install with: pip install mcp"
    ) from exc


from shared.software_catalog import SoftwareItem, load_catalog, to_payload


mcp = FastMCP("software-mcp")
CATALOG_PATH = Path(__file__).resolve().parent / "catalog" / "software_catalog.json"
CATALOG = load_catalog(CATALOG_PATH)


def _score(item: SoftwareItem, query: str) -> float:
    q = query.strip().lower()
    if not q:
        return 0.0

    haystacks = [
        item.name.lower(),
        item.summary.lower(),
        " ".join(item.categories),
        " ".join(item.tags),
    ]

    score = 0.0
    for text in haystacks:
        if q in text:
            score += 2.0
        score += SequenceMatcher(None, q, text).ratio()
    return score


@mcp.tool()
def search_software(query: str, platform: str = "macos", limit: int = 8) -> list[dict]:
    """Search software recommendations from the local curated catalog."""
    if not query.strip():
        raise ValueError("query is required")

    platform_key = platform.strip().lower()
    limit = max(1, min(20, int(limit)))

    scored = []
    for item in CATALOG:
        if platform_key and platform_key not in item.platforms:
            continue
        s = _score(item, query)
        if s > 0:
            scored.append((s, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [to_payload(item) for _, item in scored[:limit]]


@mcp.tool()
def recommend_software(category: str = "social", platform: str = "macos", limit: int = 6) -> list[dict]:
    """Recommend software by category. Default category is social."""

    category_key = category.strip().lower()
    platform_key = platform.strip().lower()
    limit = max(1, min(20, int(limit)))

    matched = []
    for item in CATALOG:
        if platform_key and platform_key not in item.platforms:
            continue
        if category_key in item.categories or category_key in item.tags:
            matched.append(item)

    return [to_payload(item) for item in matched[:limit]]


@mcp.tool()
def recommend_social_software(platform: str = "macos", limit: int = 8) -> list[dict]:
    """Recommend social and messaging software, prioritized for the given platform."""
    platform_key = platform.strip().lower()
    limit = max(1, min(20, int(limit)))

    matched = []
    for item in CATALOG:
        if platform_key and platform_key not in item.platforms:
            continue
        if "social" in item.categories or "messaging" in item.categories:
            matched.append(item)

    return [to_payload(item) for item in matched[:limit]]


if __name__ == "__main__":
    mcp.run()
