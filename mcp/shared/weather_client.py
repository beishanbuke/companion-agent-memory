"""Shared wttr.in weather client used by the weather MCP and the demo server."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

WEATHER_REQUEST_HEADERS = {"User-Agent": "quickstart-mcp-weather"}
DEFAULT_TIMEOUT = 8
WEATHER_CACHE_TTL_SECONDS = 900  # 15 minutes


class WeatherError(RuntimeError):
    """Raised when weather data cannot be fetched or parsed."""


# Process-wide TTL cache of raw wttr.in j1 payloads, keyed by city. The j1
# format already contains both current_condition and forecast, so one cached
# response serves fetch_current_weather and fetch_weather_forecast alike.
_weather_cache: dict[str, tuple[float, dict]] = {}
_weather_cache_lock = threading.Lock()


def clear_weather_cache() -> None:
    """Drop all cached weather payloads (mainly for tests)."""
    with _weather_cache_lock:
        _weather_cache.clear()


def _fetch_wttr(city: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    encoded_city = urllib.parse.quote((city or "").strip())
    if not encoded_city:
        raise WeatherError("city is required")
    url = f"https://wttr.in/{encoded_city}?format=j1"
    req = urllib.request.Request(url, headers=WEATHER_REQUEST_HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise WeatherError(f"weather request failed for {city!r}: {exc}") from exc


def _fetch_wttr_cached(city: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Cached variant of _fetch_wttr; failed requests are never cached."""
    key = (city or "").strip()
    now = time.monotonic()
    with _weather_cache_lock:
        entry = _weather_cache.get(key)
        if entry is not None and now - entry[0] < WEATHER_CACHE_TTL_SECONDS:
            return entry[1]
    data = _fetch_wttr(city, timeout=timeout)
    with _weather_cache_lock:
        _weather_cache[key] = (time.monotonic(), data)
    return data


def fetch_current_weather(city: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Current weather summary for a city."""
    data = _fetch_wttr_cached(city, timeout=timeout)
    current = (data.get("current_condition") or [{}])[0]
    nearest = (data.get("nearest_area") or [{}])[0]
    weather_desc = (current.get("weatherDesc") or [{}])[0].get("value", "")

    return {
        "city": (city or "").strip(),
        "resolved_area": nearest.get("areaName", [{}])[0].get("value", city),
        "temperature_c": current.get("temp_C"),
        "feels_like_c": current.get("FeelsLikeC"),
        "humidity": current.get("humidity"),
        "wind_kmph": current.get("windspeedKmph"),
        "description": weather_desc,
        "observation_time": current.get("observation_time"),
    }


def fetch_weather_forecast(city: str, days: int = 3, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """Short weather forecast (1-3 days) for a city."""
    days = max(1, min(3, int(days)))
    data = _fetch_wttr_cached(city, timeout=timeout)
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

    return {"city": (city or "").strip(), "days": days, "forecast": rows}


def current_to_prompt_text(current: dict) -> str:
    """Compact Chinese summary injected into the chat prompt."""
    rain_hint = ""
    desc = str(current.get("description") or "")
    if any(k in desc for k in ("雨", "Rain", "Drizzle", "Shower", "Thunder")):
        rain_hint = "今天有降雨可能，出门记得带伞；室内活动、雨天歌单都是好选择。"
    return (
        f"[天气 MCP 已查询 {current.get('resolved_area') or current.get('city')} 当前天气]\n"
        f"实际温度 {current.get('temperature_c')}°C，体感 {current.get('feels_like_c')}°C，"
        f"湿度 {current.get('humidity')}%，风速 {current.get('wind_kmph')} km/h，"
        f"天气：{desc}，观测时间 {current.get('observation_time')}。\n"
        f"请结合以上数据回答，并可顺势给出穿搭、出行、活动或歌单建议。{rain_hint}"
    )
