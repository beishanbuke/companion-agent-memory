from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class SoftwareItem:
    name: str
    summary: str
    categories: list[str]
    platforms: list[str]
    tags: list[str]
    homepage: str


def load_catalog(catalog_path: Path) -> list[SoftwareItem]:
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    items: list[SoftwareItem] = []
    for item in raw:
        items.append(
            SoftwareItem(
                name=str(item.get("name") or "").strip(),
                summary=str(item.get("summary") or "").strip(),
                categories=[str(x).strip().lower() for x in item.get("categories", [])],
                platforms=[str(x).strip().lower() for x in item.get("platforms", [])],
                tags=[str(x).strip().lower() for x in item.get("tags", [])],
                homepage=str(item.get("homepage") or "").strip(),
            )
        )
    return items


def to_payload(item: SoftwareItem) -> dict[str, Any]:
    return {
        "name": item.name,
        "summary": item.summary,
        "categories": item.categories,
        "platforms": item.platforms,
        "tags": item.tags,
        "homepage": item.homepage,
    }
