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

from weather_client import fetch_current_weather, fetch_weather_forecast  # noqa: E402


mcp = FastMCP("weather-mcp")


@mcp.tool()
def get_current_weather(city: str) -> dict:
    """Get current weather summary for a city using wttr.in public API."""
    if not city.strip():
        raise ValueError("city is required")
    return fetch_current_weather(city)


@mcp.tool()
def get_weather_forecast(city: str, days: int = 3) -> dict:
    """Get short weather forecast for a city. days range: 1-3."""
    if not city.strip():
        raise ValueError("city is required")
    return fetch_weather_forecast(city, days=days)


if __name__ == "__main__":
    mcp.run()
