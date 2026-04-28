from __future__ import annotations

import json
import urllib.parse
import urllib.request


try:
    from mcp.server.fastmcp import FastMCP
except Exception as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'mcp'. Install with: pip install mcp"
    ) from exc


mcp = FastMCP("weather-mcp")


def _fetch_wttr(city: str) -> dict:
    encoded_city = urllib.parse.quote(city.strip())
    url = f"https://wttr.in/{encoded_city}?format=j1"
    req = urllib.request.Request(url, headers={"User-Agent": "quickstart-mcp-weather"}, method="GET")
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode("utf-8"))


@mcp.tool()
def get_current_weather(city: str) -> dict:
    """Get current weather summary for a city using wttr.in public API."""
    if not city.strip():
        raise ValueError("city is required")

    data = _fetch_wttr(city)
    current = (data.get("current_condition") or [{}])[0]
    nearest = (data.get("nearest_area") or [{}])[0]
    weather_desc = (current.get("weatherDesc") or [{}])[0].get("value", "")

    return {
        "city": city,
        "resolved_area": nearest.get("areaName", [{}])[0].get("value", city),
        "temperature_c": current.get("temp_C"),
        "feels_like_c": current.get("FeelsLikeC"),
        "humidity": current.get("humidity"),
        "wind_kmph": current.get("windspeedKmph"),
        "description": weather_desc,
        "observation_time": current.get("observation_time"),
    }


@mcp.tool()
def get_weather_forecast(city: str, days: int = 3) -> dict:
    """Get short weather forecast for a city. days range: 1-3."""
    if not city.strip():
        raise ValueError("city is required")
    days = max(1, min(3, int(days)))

    data = _fetch_wttr(city)
    rows = []
    for item in (data.get("weather") or [])[:days]:
        hourly = (item.get("hourly") or [{}])[0]
        rows.append(
            {
                "date": item.get("date"),
                "max_temp_c": item.get("maxtempC"),
                "min_temp_c": item.get("mintempC"),
                "chance_of_rain": hourly.get("chanceofrain"),
                "description": (hourly.get("weatherDesc") or [{}])[0].get("value", ""),
            }
        )

    return {"city": city, "days": days, "forecast": rows}


if __name__ == "__main__":
    mcp.run()
