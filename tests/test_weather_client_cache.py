import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
MCP_SHARED_DIR = PROJECT_DIR / "mcp" / "shared"
if str(MCP_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(MCP_SHARED_DIR))

import weather_client  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


WTTR_PAYLOAD = {
    "current_condition": [
        {
            "temp_C": "26",
            "FeelsLikeC": "28",
            "humidity": "70",
            "windspeedKmph": "12",
            "weatherDesc": [{"value": "Partly cloudy"}],
            "observation_time": "09:30 AM",
        }
    ],
    "nearest_area": [{"areaName": [{"value": "Shanghai"}]}],
    "weather": [
        {
            "date": "2026-09-21",
            "maxtempC": "29",
            "mintempC": "22",
            "hourly": [{"chanceofrain": "10", "weatherDesc": [{"value": "Sunny"}]}],
        },
        {
            "date": "2026-09-22",
            "maxtempC": "28",
            "mintempC": "21",
            "hourly": [{"chanceofrain": "40", "weatherDesc": [{"value": "Patchy rain"}]}],
        },
    ],
}


def _stub_urlopen(monkeypatch):
    calls: list[str] = []

    def fake_urlopen(req, timeout=0):
        calls.append(req.full_url)
        return _FakeResponse(WTTR_PAYLOAD)

    monkeypatch.setattr(weather_client.urllib.request, "urlopen", fake_urlopen)
    weather_client.clear_weather_cache()
    return calls


def test_current_plus_forecast_share_one_http_request(monkeypatch) -> None:
    calls = _stub_urlopen(monkeypatch)

    current = weather_client.fetch_current_weather("Shanghai")
    forecast = weather_client.fetch_weather_forecast("Shanghai", days=3)

    assert len(calls) == 1
    assert "format=j1" in calls[0]
    assert current["temperature_c"] == "26"
    assert current["observation_time"] == "09:30 AM"
    assert len(forecast["forecast"]) == 2

    weather_client.clear_weather_cache()


def test_second_call_within_ttl_hits_cache(monkeypatch) -> None:
    calls = _stub_urlopen(monkeypatch)

    first = weather_client.fetch_current_weather("Shanghai")
    second = weather_client.fetch_current_weather("Shanghai")

    assert len(calls) == 1
    assert second == first

    weather_client.clear_weather_cache()


def test_cache_expires_after_ttl(monkeypatch) -> None:
    calls = _stub_urlopen(monkeypatch)

    weather_client.fetch_current_weather("Shanghai")
    # Back-date the cached entry beyond the TTL.
    with weather_client._weather_cache_lock:
        timestamp, payload = weather_client._weather_cache["Shanghai"]
        weather_client._weather_cache["Shanghai"] = (
            timestamp - weather_client.WEATHER_CACHE_TTL_SECONDS - 1,
            payload,
        )
    weather_client.fetch_current_weather("Shanghai")

    assert len(calls) == 2

    weather_client.clear_weather_cache()
