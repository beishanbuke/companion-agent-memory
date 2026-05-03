"""Local prototype server for demonstrating the long-term memory module.

Run:
    python prototype_demo/server.py
"""

from __future__ import annotations

import asyncio
import difflib
import io
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib import error, request
from urllib.parse import quote, urljoin, urlparse
import wave

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
MEMORY_FILE = PROJECT_DIR / "prototype_memory_store.json"
CHARACTER_CARDS_FILE = PROJECT_DIR / "prototype_character_cards.json"
VOICE_SERVICE_BASE_URL = os.getenv("VOICE_SERVICE_BASE_URL", "http://127.0.0.1:7860").rstrip("/")
VOICE_CLIENT_PATH = "/" + os.getenv("VOICE_CLIENT_PATH", "client").lstrip("/")
VOICE_PROXY_PATH = "/" + os.getenv("VOICE_PROXY_PATH", "voice-client").strip("/")
SOFTWARE_CATALOG_PATH = PROJECT_DIR / "mcp" / "catalog" / "software_catalog.json"

def load_local_env() -> None:
    env_path = PROJECT_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

# Load environment variables before defining model configurations
load_local_env()

# ---- Available LLM Models Configuration ----
_AVAILABLE_MODELS_CONFIG = [
    {
        "id": "deepseek-v3",
        "name": "DeepSeek-V3",
        "provider": "siliconflow",
        "provider_name": "SiliconFlow",
        "env_api_key": "OPENAI_API_KEY",
        "env_base_url": "OPENAI_BASE_URL",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "model": "deepseek-ai/DeepSeek-V3",
        "icon": "siliconflow",
    },
    {
        "id": "kimi-k2.6",
        "name": "Kimi K2.6",
        "provider": "kimi",
        "provider_name": "Moonshot",
        "env_api_key": "KIMI_API_KEY",
        "env_base_url": "KIMI_BASE_URL",
        "default_base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-k2.6",
        "icon": "kimi",
    },
    {
        "id": "kimi-latest",
        "name": "Kimi Latest",
        "provider": "kimi",
        "provider_name": "Moonshot",
        "env_api_key": "KIMI_API_KEY",
        "env_base_url": "KIMI_BASE_URL",
        "default_base_url": "https://api.moonshot.cn/v1",
        "model": "kimi-latest",
        "icon": "kimi",
    },
    {
        "id": "gpt-4o-mini",
        "name": "GPT-4o Mini",
        "provider": "openai",
        "provider_name": "OpenAI",
        "env_api_key": "OPENAI_API_KEY",
        "env_base_url": "OPENAI_BASE_URL",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "model": "gpt-4o-mini",
        "icon": "openai",
    },
]

def _build_available_models() -> list[dict[str, Any]]:
    """Build available models list from environment variables."""
    models = []
    for cfg in _AVAILABLE_MODELS_CONFIG:
        models.append({
            "id": cfg["id"],
            "name": cfg["name"],
            "provider": cfg["provider"],
            "provider_name": cfg["provider_name"],
            "api_key": os.getenv(cfg["env_api_key"], ""),
            "base_url": os.getenv(cfg["env_base_url"], cfg["default_base_url"]),
            "model": cfg["model"],
            "icon": cfg["icon"],
        })
    return models

AVAILABLE_MODELS: list[dict[str, Any]] = _build_available_models()

def _get_model_config(model_id: str) -> dict[str, Any]:
    """Get configuration for a specific model."""
    for model in AVAILABLE_MODELS:
        if model["id"] == model_id:
            return model
    # Fallback to default
    return AVAILABLE_MODELS[0]

def _get_available_models() -> list[dict[str, Any]]:
    """Return available models with API key availability status."""
    result = []
    for model in AVAILABLE_MODELS:
        result.append({
            "id": model["id"],
            "name": model["name"],
            "provider": model["provider"],
            "provider_name": model["provider_name"],
            "icon": model["icon"],
            "available": bool(model["api_key"]),
        })
    return result

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from memory import StructuredLongTermMemory
from context_engine import load_scene_strategies, pack_context_messages

# Context Engine V3 (Companion Runtime Brain)
from context_engine_v2 import build_context_v3, ContextBuildInput
from context_engine_v2.types import ChatMessage

# Companion Agent Core
from companion_agent import CompanionAgentCore
from companion_agent.persona import PersonaConfig

# Companion Agent Core V2
from companion_agent.v2 import CompanionAgentCoreV2, CharacterStyle

from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import ConnectionClosedOK

SYSTEM_PROMPT = """你是一个温和、自然、简洁的陪伴型助手。

请像真实的对话伙伴一样回答，不要显得像在背诵资料。
如果系统提供了长期记忆，请合理利用，让回答体现出连续性和了解感。
如果没有长期记忆，就只基于当前对话作答，不要假装记得以前的事情。
默认先像人在接话，再决定要不要建议、解释或提问。
"""

TEXT_CHAT_GUARDRAILS = """\
[文字聊天规则]
回复自然、简洁、有生活感。
默认不用列表；只有用户明确要步骤/选项时再列。
可以出现必要的代码/英文缩写。
不要输出舞台说明或括号动作。
不要写成客服话术、心理咨询腔或模板小作文。
"""

VOICE_CHAT_GUARDRAILS = """\
[语音输出规则]
输出即语音，要求听觉自洽。
禁止依赖视觉/文字形态的表达。
禁止 emoji 叙事、ASCII 图形、代码符号直读。
禁止括号动作、旁白、舞台说明。
单轮最多一个问题。
"""

def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

DEFAULT_VOICE_OPTIONS: list[dict[str, str]] = [
    {"name": "vivi 2.0", "voice_type": "zh_female_vv_uranus_bigtts", "scene": "通用场景"},
    {"name": "爽快思思 2.0", "voice_type": "zh_female_shuangkuaisisi_uranus_bigtts", "scene": "通用场景"},
    {"name": "大壹", "voice_type": "zh_male_dayi_saturn_bigtts", "scene": "视频配音"},
    {"name": "黑猫侦探社咪仔", "voice_type": "zh_female_mizai_saturn_bigtts", "scene": "视频配音"},
    {"name": "黑猫侦探社咪仔 2.0", "voice_type": "zh_female_mizai_uranus_bigtts", "scene": "视频配音"},
    {"name": "猴哥 2.0", "voice_type": "zh_male_sunwukong_uranus_bigtts", "scene": "视频配音"},
    {"name": "鸡汤女", "voice_type": "zh_female_jitangnv_saturn_bigtts", "scene": "视频配音"},
    {"name": "魅力女友", "voice_type": "zh_female_meilinvyou_saturn_bigtts", "scene": "视频配音"},
    {"name": "流畅女声", "voice_type": "zh_female_santongyongns_saturn_bigtts", "scene": "视频配音"},
    {"name": "儒雅逸辰", "voice_type": "zh_male_ruyayichen_saturn_bigtts", "scene": "视频配音"},
    {"name": "儿童绘本", "voice_type": "zh_female_xueayi_saturn_bigtts", "scene": "有声阅读"},
    {"name": "可爱女生", "voice_type": "ICL_zh_female_keainvsheng_tob", "scene": "角色扮演"},
    {"name": "调皮公主", "voice_type": "ICL_zh_female_tiaopigongzhu_tob", "scene": "角色扮演"},
    {"name": "爽朗少年", "voice_type": "ICL_zh_male_shuanglangshaonian_tob", "scene": "角色扮演"},
    {"name": "天才同桌", "voice_type": "ICL_zh_male_tiancaitongzhuo_tob", "scene": "角色扮演"},
    {"name": "湾区大叔", "voice_type": "zh_female_wanqudashu_moon_bigtts", "scene": "方言口音替代"},
    {"name": "广州德哥", "voice_type": "zh_male_guozhoudege_moon_bigtts", "scene": "方言口音替代"},
    {"name": "呆萌川妹", "voice_type": "zh_female_daimengchuanmei_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "豫州子轩", "voice_type": "zh_male_yuzhouzixuan_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "广西远舟", "voice_type": "zh_male_guangxiyuanzhou_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "双节棍小哥", "voice_type": "zh_male_zhoujielun_emo_v2_mars_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "湾湾小何", "voice_type": "zh_female_wanwanxiaohe_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "浩宇小哥", "voice_type": "zh_male_haoyuxiaoge_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "北京小爷", "voice_type": "zh_male_beijingxiaoye_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "京腔侃爷", "voice_type": "zh_male_jingqiangkanye_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "妹坨洁儿", "voice_type": "zh_female_meituojieer_moon_bigtts", "scene": "seed-tts-1.0 方言"},
    {"name": "粤语小溏", "voice_type": "zh_female_yueyunv_mars_bigtts", "scene": "seed-tts-1.0 方言"},
]


def _default_card() -> dict[str, Any]:
    return {
        "id": "default_companion",
        "name": "温和陪伴",
        "system_prompt": _with_prompt_guardrails(SYSTEM_PROMPT, modality="text"),
        "llm": {"model": os.getenv("OPENAI_MODEL", "").strip()},
        "voice": {
            "provider": "volcengine",
            "voice_type": os.getenv("VOLCENGINE_VOICE_TYPE", "zh_female_vv_uranus_bigtts"),
            "resource_id": os.getenv("VOLCENGINE_RESOURCE_ID", "seed-tts-1.0"),
            "model": os.getenv("VOLCENGINE_MODEL", "").strip(),
        },
    }


def _normalize_card_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", (value or "").strip())
    return normalized.strip("_").lower()[:64]


def _with_prompt_guardrails(prompt: str, modality: str = "text") -> str:
    normalized = str(prompt or "").strip()
    if not normalized:
        return ""

    def _strip_legacy_guardrails(text: str) -> str:
        cleaned = text
        legacy_block_patterns = (
            r"(?:\[(?:通道声明|内容禁令|表达禁令|语言纪律|交互控制)\][^\n]*)+\s*",
            r"(?:\[(?:语音输出|交互原则|表达控制)\][^\n]*)+\s*",
        )
        for pattern in legacy_block_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.DOTALL).strip()
        return cleaned

    # Remove old manual preface to avoid duplicated guardrails after migration.
    if normalized.startswith("前置说明："):
        parts = normalized.split("\n\n", 1)
        if len(parts) == 2:
            normalized = parts[1].strip()

    guardrails = VOICE_CHAT_GUARDRAILS if modality == "voice" else TEXT_CHAT_GUARDRAILS
    body = normalized
    if normalized.startswith(guardrails):
        body = normalized[len(guardrails):].strip()

    body = _strip_legacy_guardrails(body)
    if not body:
        body = SYSTEM_PROMPT.strip()

    return f"{guardrails}\n\n{body}"


def _normalize_character_card(raw: dict[str, Any]) -> dict[str, Any]:
    card_id = _normalize_card_id(str(raw.get("id") or raw.get("name") or "card"))
    if not card_id:
        raise ValueError("card id is required")
    name = str(raw.get("name") or card_id).strip()
    system_prompt = _with_prompt_guardrails(str(raw.get("system_prompt") or ""), modality="text")
    if not system_prompt:
        raise ValueError(f"card `{card_id}` missing system_prompt")
    voice = raw.get("voice") or {}
    llm = raw.get("llm") or {}
    return {
        "id": card_id,
        "name": name,
        "system_prompt": system_prompt,
        "llm": {"model": str(llm.get("model") or "").strip()},
        "voice": {
            "provider": str(voice.get("provider") or "volcengine").strip().lower() or "volcengine",
            "voice_type": str(
                voice.get("voice_type")
                or raw.get("voice_type")
                or os.getenv("VOLCENGINE_VOICE_TYPE", "zh_female_vv_uranus_bigtts")
            ).strip(),
            "resource_id": str(
                voice.get("resource_id")
                or os.getenv("VOLCENGINE_RESOURCE_ID", "seed-tts-1.0")
            ).strip(),
            "model": str(voice.get("model") or "").strip(),
        },
    }


class CharacterCardStore:
    def __init__(self, path: Path):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            default = _default_card()
            payload = {"active_card_id": default["id"], "cards": [default]}
            self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

        cards_raw = payload.get("cards")
        normalized_cards: list[dict[str, Any]] = []
        if isinstance(cards_raw, list):
            for card in cards_raw:
                if isinstance(card, dict):
                    try:
                        normalized_cards.append(_normalize_character_card(card))
                    except Exception:
                        continue

        if not normalized_cards:
            normalized_cards = [_default_card()]

        active = str(payload.get("active_card_id") or normalized_cards[0]["id"])
        if all(card["id"] != active for card in normalized_cards):
            active = normalized_cards[0]["id"]

        normalized = {"active_card_id": active, "cards": normalized_cards}
        self._path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
        return normalized

    def _save(self) -> None:
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def list_payload(self) -> dict[str, Any]:
        return {
            "active_card_id": self._data["active_card_id"],
            "cards": self._data["cards"],
            "voice_options": DEFAULT_VOICE_OPTIONS,
        }

    def get_active_card(self) -> dict[str, Any]:
        active = self._data.get("active_card_id")
        for card in self._data.get("cards", []):
            if card.get("id") == active:
                return card
        return self._data["cards"][0]

    def select_card(self, card_id: str) -> dict[str, Any]:
        target = _normalize_card_id(card_id)
        if not target:
            raise ValueError("card_id is required")
        if all(card.get("id") != target for card in self._data.get("cards", [])):
            raise ValueError("card_id not found")
        self._data["active_card_id"] = target
        self._save()
        return self.list_payload()

    def upsert_card(self, raw_card: dict[str, Any]) -> dict[str, Any]:
        card = _normalize_character_card(raw_card)
        cards = self._data.get("cards", [])
        for idx, item in enumerate(cards):
            if item.get("id") == card["id"]:
                cards[idx] = card
                break
        else:
            cards.append(card)
        self._data["cards"] = cards
        if not self._data.get("active_card_id"):
            self._data["active_card_id"] = card["id"]
        self._save()
        return self.list_payload()

    def import_cards(self, raw_text: str) -> dict[str, Any]:
        if not raw_text.strip():
            raise ValueError("raw_text is required")
        parsed = json.loads(raw_text)
        imported: list[dict[str, Any]] = []

        if isinstance(parsed, dict) and isinstance(parsed.get("cards"), list):
            for item in parsed.get("cards", []):
                if isinstance(item, dict):
                    imported.append(_normalize_character_card(item))
        elif isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    imported.append(_normalize_character_card(item))
        elif isinstance(parsed, dict):
            imported.append(_normalize_character_card(parsed))
        else:
            raise ValueError("invalid card payload")

        if not imported:
            raise ValueError("no valid cards found")

        existing = {item["id"]: item for item in self._data.get("cards", [])}
        for item in imported:
            existing[item["id"]] = item

        self._data["cards"] = list(existing.values())
        if not self._data.get("active_card_id"):
            self._data["active_card_id"] = self._data["cards"][0]["id"]
        self._save()
        return self.list_payload()

    def delete_card(self, card_id: str) -> dict[str, Any]:
        target = _normalize_card_id(card_id)
        if not target:
            raise ValueError("card_id is required")
        cards = self._data.get("cards", [])
        if len(cards) <= 1:
            raise ValueError("cannot delete the last character card")
        new_cards = [card for card in cards if card.get("id") != target]
        if len(new_cards) == len(cards):
            raise ValueError("card_id not found")
        self._data["cards"] = new_cards
        if self._data.get("active_card_id") == target:
            self._data["active_card_id"] = new_cards[0]["id"]
        self._save()
        return self.list_payload()


def voice_client_url() -> str:
    return urljoin(f"{VOICE_SERVICE_BASE_URL}/", VOICE_CLIENT_PATH.lstrip("/"))


def voice_proxy_url() -> str:
    return VOICE_PROXY_PATH.rstrip("/") + "/"


def get_voice_status() -> dict[str, Any]:
    client_url = voice_client_url()
    payload = {
        "available": False,
        "client_url": client_url,
        "proxy_client_url": voice_proxy_url(),
        "base_url": VOICE_SERVICE_BASE_URL,
        "run_hint": "在 quickstart 目录运行 ./start_prototype_demo.sh restart，或单独执行 ./.venv/bin/python prototype_demo/voice_bot.py --host 0.0.0.0",
    }
    req = request.Request(
        client_url,
        headers={"User-Agent": "memory-prototype-demo"},
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=1.5) as resp:
            status_code = getattr(resp, "status", HTTPStatus.OK)
            payload["available"] = int(status_code) < 500
            payload["status_code"] = int(status_code)
    except Exception as exc:  # pragma: no cover - depends on local runtime state
        payload["error"] = str(exc)
    return payload


def _chat_api_config(model_id: str = "") -> tuple[str, str, str]:
    """Get API config for a specific model or fallback to env defaults."""
    if model_id:
        config = _get_model_config(model_id)
        return config["api_key"], config["base_url"] + "/chat/completions", config["model"]
    
    # Fallback to env defaults
    api_key = (
        os.getenv("CHAT_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("MEMORY_LLM_API_KEY")
        or ""
    )
    endpoint = (
        os.getenv("CHAT_API_URL")
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("MEMORY_LLM_URL")
        or "https://api2.aigcbest.top/v1/chat/completions"
    )
    model = (
        os.getenv("CHAT_MODEL")
        or os.getenv("OPENAI_MODEL")
        or os.getenv("MEMORY_LLM_MODEL")
        or "gpt-4o-mini"
    )
    return api_key, endpoint, model


def _normalize_transcript_text(text: str) -> str:
    normalized = re.sub(r"\s+", " ", (text or "")).strip()
    if len(normalized) < 8:
        return normalized
    for split in range(max(4, len(normalized) // 3), min(len(normalized) - 4, (len(normalized) * 2) // 3 + 1)):
        left = normalized[:split].strip(" ,，。！？")
        right = normalized[split:].strip(" ,，。！？")
        if not left or not right:
            continue
        if difflib.SequenceMatcher(None, left, right).ratio() >= 0.93:
            return right if len(right) >= len(left) else left
    return normalized


def _audio_suffix_for_mime(mime_type: str) -> str:
    mime = (mime_type or "").lower()
    if "webm" in mime:
        return ".webm"
    if "mp4" in mime or "m4a" in mime:
        return ".m4a"
    if "wav" in mime:
        return ".wav"
    if "ogg" in mime:
        return ".ogg"
    return ".bin"


def _convert_audio_to_pcm(audio_bytes: bytes, mime_type: str) -> bytes:
    suffix = _audio_suffix_for_mime(mime_type)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as src:
        src.write(audio_bytes)
        src_path = src.name
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as dst:
        dst_path = dst.name

    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                src_path,
                "-ac",
                "1",
                "-ar",
                "16000",
                "-f",
                "s16le",
                dst_path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg conversion failed: {stderr[:400]}")
        return Path(dst_path).read_bytes()
    finally:
        for path in (src_path, dst_path):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass


def _build_volcengine_header(*, message_type: int, flags: int, serialization: int, compression: int) -> bytes:
    version_and_header = (0x1 << 4) | 0x1
    type_and_flags = ((message_type & 0x0F) << 4) | (flags & 0x0F)
    ser_and_comp = ((serialization & 0x0F) << 4) | (compression & 0x0F)
    return bytes([version_and_header, type_and_flags, ser_and_comp, 0x00])


def _build_volcengine_full_request(language: str, sample_rate: int) -> bytes:
    payload = {
        "user": {"uid": "prototype-inline-mic"},
        "audio": {
            "format": "pcm",
            "codec": "raw",
            "rate": sample_rate,
            "bits": 16,
            "channel": 1,
            "language": language,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": False,
            "show_utterances": True,
            "result_type": "single",
        },
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = _build_volcengine_header(message_type=0x1, flags=0x0, serialization=0x1, compression=0x0)
    return header + struct.pack(">I", len(payload_bytes)) + payload_bytes


def _build_volcengine_audio_packet(audio: bytes, is_final: bool = False) -> bytes:
    flags = 0x2 if is_final else 0x0
    header = _build_volcengine_header(message_type=0x2, flags=flags, serialization=0x0, compression=0x0)
    return header + struct.pack(">I", len(audio)) + audio


def _build_volcengine_tts_request(*, event: int, payload: dict[str, Any], session_id: str | None = None) -> bytes:
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    header = _build_volcengine_header(message_type=0x1, flags=0x4, serialization=0x1, compression=0x0)
    if session_id:
        session_bytes = session_id.encode("utf-8")
        return (
            header
            + struct.pack(">i", event)
            + struct.pack(">I", len(session_bytes))
            + session_bytes
            + struct.pack(">I", len(payload_bytes))
            + payload_bytes
        )
    return header + struct.pack(">i", event) + struct.pack(">I", len(payload_bytes)) + payload_bytes


def _parse_volcengine_text_packet(data: bytes) -> tuple[str, bool]:
    if len(data) < 4:
        return "", False

    header = data[1]
    message_type = (header >> 4) & 0x0F
    flags = header & 0x0F

    if message_type == 0xF:
        code = struct.unpack(">I", data[4:8])[0] if len(data) >= 8 else 0
        msg_len = struct.unpack(">I", data[8:12])[0] if len(data) >= 12 else 0
        msg = data[12 : 12 + msg_len].decode("utf-8", errors="ignore") if msg_len > 0 else ""
        raise RuntimeError(f"Volcengine ASR error {code}: {msg}")

    if message_type != 0x9:
        return "", False

    cursor = 4
    if flags in {0x1, 0x3} and len(data) >= cursor + 4:
        cursor += 4
    if len(data) < cursor + 4:
        return "", False

    payload_size = struct.unpack(">I", data[cursor : cursor + 4])[0]
    cursor += 4
    payload = data[cursor : cursor + payload_size]
    if not payload:
        return "", False

    try:
        message_json = json.loads(payload.decode("utf-8", errors="ignore"))
    except Exception:
        return "", False

    result = message_json.get("result") or {}
    utterances = result.get("utterances") or []
    if utterances:
        latest = utterances[-1]
        utterance_text = _normalize_transcript_text((latest.get("text") or "").strip())
        if utterance_text:
            return utterance_text, bool(latest.get("definite"))

    text = _normalize_transcript_text(result.get("text") or "")
    return text, False


def _parse_volcengine_tts_packet(data: bytes) -> dict[str, Any]:
    if len(data) < 4:
        return {"msg_type": None}

    byte1 = data[1]
    msg_type = (byte1 >> 4) & 0x0F
    has_event = (byte1 & 0x0F) == 0x4

    if msg_type == 0xF:
        code = struct.unpack(">i", data[4:8])[0] if len(data) >= 8 else -1
        detail = data[8:].decode("utf-8", errors="ignore") if len(data) > 8 else ""
        return {"msg_type": msg_type, "error": f"code={code}, detail={detail}"}

    cursor = 4
    event = None
    if has_event and len(data) >= cursor + 4:
        event = struct.unpack(">i", data[cursor : cursor + 4])[0]
        cursor += 4

    if msg_type == 0x9:
        response_id = ""
        payload_json: dict[str, Any] = {}
        if len(data) >= cursor + 4:
            response_id_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
            cursor += 4
            if len(data) >= cursor + response_id_len:
                response_id = data[cursor : cursor + response_id_len].decode("utf-8", errors="ignore")
                cursor += response_id_len
        if len(data) >= cursor + 4:
            payload_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
            cursor += 4
            payload_bytes = data[cursor : cursor + payload_len]
            if payload_bytes:
                try:
                    payload_json = json.loads(payload_bytes.decode("utf-8", errors="ignore"))
                except Exception:
                    payload_json = {}
        return {
            "msg_type": msg_type,
            "event": event,
            "response_id": response_id,
            "payload_json": payload_json,
        }

    if msg_type == 0xB:
        response_id = ""
        audio = b""
        if len(data) >= cursor + 4:
            response_id_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
            cursor += 4
            if len(data) >= cursor + response_id_len:
                response_id = data[cursor : cursor + response_id_len].decode("utf-8", errors="ignore")
                cursor += response_id_len
        if len(data) >= cursor + 4:
            audio_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
            cursor += 4
            audio = data[cursor : cursor + audio_len]
        return {
            "msg_type": msg_type,
            "event": event,
            "response_id": response_id,
            "audio": audio,
        }

    return {"msg_type": msg_type, "event": event}


def _pcm_to_wav(audio_bytes: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)
    return buffer.getvalue()


async def _transcribe_pcm_with_volcengine_async(pcm_bytes: bytes) -> str:
    app_id = os.getenv("VOLCENGINE_APP_ID", "").strip()
    access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
    if not app_id or not access_key:
        raise RuntimeError("Missing VOLCENGINE_APP_ID or VOLCENGINE_ACCESS_KEY in .env")

    endpoint = os.getenv(
        "VOLCENGINE_ASR_ENDPOINT",
        "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
    )
    resource_id = os.getenv("VOLCENGINE_ASR_RESOURCE_ID", "volc.seedasr.sauc.duration")
    language = os.getenv("VOLCENGINE_ASR_LANGUAGE", "zh-CN")
    sample_rate = int(os.getenv("VOLCENGINE_ASR_SAMPLE_RATE", "16000"))
    chunk_ms = int(os.getenv("VOLCENGINE_ASR_CHUNK_MS", "200"))
    chunk_size = int(sample_rate * 2 * chunk_ms / 1000)

    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }

    latest_text = ""
    async with websocket_connect(endpoint, additional_headers=headers, max_size=None) as websocket:
        await websocket.send(_build_volcengine_full_request(language=language, sample_rate=sample_rate))
        for index in range(0, len(pcm_bytes), chunk_size):
            await websocket.send(_build_volcengine_audio_packet(pcm_bytes[index : index + chunk_size]))
        await websocket.send(_build_volcengine_audio_packet(b"", is_final=True))

        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            timeout = max(0.1, deadline - time.monotonic())
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            except ConnectionClosedOK:
                break
            except asyncio.TimeoutError:
                break
            if isinstance(message, str):
                continue
            text, definite = _parse_volcengine_text_packet(message)
            if text:
                latest_text = text
            if definite and text:
                return text

    return latest_text


async def _synthesize_with_volcengine_async(
    text: str,
    *,
    voice_type: str | None = None,
    resource_id: str | None = None,
    model_name: str | None = None,
) -> tuple[bytes, int]:
    app_id = os.getenv("VOLCENGINE_APP_ID", "").strip()
    access_key = (
        os.getenv("VOLCENGINE_TTS_API_KEY", "").strip()
        or os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
    )
    if not app_id or not access_key:
        raise RuntimeError("Missing VOLCENGINE_APP_ID or VOLCENGINE_ACCESS_KEY/TTS_API_KEY in .env")

    endpoint = os.getenv(
        "VOLCENGINE_TTS_ENDPOINT",
        "wss://openspeech.bytedance.com/api/v3/tts/bidirection",
    )
    resource_id = (resource_id or os.getenv("VOLCENGINE_RESOURCE_ID", "seed-tts-1.0")).strip()
    speaker = (voice_type or os.getenv("VOLCENGINE_VOICE_TYPE", "zh_female_vv_uranus_bigtts")).strip()
    model = (model_name if model_name is not None else os.getenv("VOLCENGINE_MODEL", "")).strip()
    sample_rate = int(os.getenv("VOLCENGINE_SAMPLE_RATE", "24000"))
    uid = os.getenv("VOLCENGINE_UID", "pipecat-user")

    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_key,
        "X-Api-Resource-Id": resource_id,
        "X-Api-Connect-Id": str(uuid.uuid4()),
        "X-Control-Require-Usage-Tokens-Return": "text_words",
    }

    start_session_payload = {
        "user": {"uid": uid},
        "namespace": "BidirectionalTTS",
        "req_params": {
            "speaker": speaker,
            "text": text,
            "audio_params": {
                "format": "pcm",
                "sample_rate": sample_rate,
            },
        },
    }
    if model:
        start_session_payload["req_params"]["model"] = model

    task_payload = {
        "user": {"uid": uid},
        "namespace": "BidirectionalTTS",
        "req_params": {"text": text},
    }

    session_id = str(uuid.uuid4())
    audio_chunks: list[bytes] = []

    async with websocket_connect(endpoint, additional_headers=headers, max_size=None) as websocket:
        await websocket.send(_build_volcengine_tts_request(event=1, payload={}))

        while True:
            message = await websocket.recv()
            if isinstance(message, str):
                continue
            parsed = _parse_volcengine_tts_packet(message)
            if parsed.get("msg_type") == 0xF:
                raise RuntimeError(f"Volcengine TTS connection failed: {parsed.get('error', 'unknown error')}")
            event = parsed.get("event")
            if event == 50:
                break
            if event == 51:
                raise RuntimeError(f"Volcengine TTS connection failed: {parsed.get('payload_json') or {}}")

        try:
            await websocket.send(
                _build_volcengine_tts_request(
                    event=100,
                    payload=start_session_payload,
                    session_id=session_id,
                )
            )
            await websocket.send(
                _build_volcengine_tts_request(
                    event=200,
                    payload=task_payload,
                    session_id=session_id,
                )
            )
            await websocket.send(
                _build_volcengine_tts_request(
                    event=102,
                    payload={},
                    session_id=session_id,
                )
            )

            while True:
                message = await websocket.recv()
                if isinstance(message, str):
                    continue

                parsed = _parse_volcengine_tts_packet(message)
                msg_type = parsed.get("msg_type")
                event = parsed.get("event")

                if msg_type == 0xF:
                    raise RuntimeError(f"Volcengine TTS error: {parsed.get('error', 'unknown error')}")

                if msg_type == 0xB and event == 352:
                    if parsed.get("response_id") != session_id:
                        continue
                    audio = parsed.get("audio") or b""
                    if audio:
                        audio_chunks.append(audio)
                    continue

                if msg_type == 0x9 and parsed.get("response_id") != session_id:
                    continue

                if event == 152:
                    break

                if event == 153:
                    payload = parsed.get("payload_json") or {}
                    raise RuntimeError(f"Volcengine TTS session failed: {payload.get('message', 'session failed')}")
        finally:
            try:
                await websocket.send(_build_volcengine_tts_request(event=2, payload={}))
            except Exception:
                pass

    return b"".join(audio_chunks), sample_rate


def _transcribe_with_deepgram(audio_bytes: bytes) -> str:
    deepgram_key = os.getenv("DEEPGRAM_API_KEY", "").strip()
    if not deepgram_key:
        raise RuntimeError("Missing DEEPGRAM_API_KEY in .env")

    from deepgram import DeepgramClient

    client = DeepgramClient(api_key=deepgram_key)
    response = client.listen.v1.media.transcribe_file(
        request=audio_bytes,
        model="nova-2",
        language="zh-CN",
        smart_format=True,
        punctuate=True,
        utterances=True,
    )
    payload = response.model_dump() if hasattr(response, "model_dump") else {}
    results = payload.get("results") or {}
    channels = results.get("channels") or []
    if not channels:
        return ""
    alternatives = channels[0].get("alternatives") or []
    if not alternatives:
        return ""
    return str(alternatives[0].get("transcript") or "").strip()


def transcribe_audio_bytes(audio_bytes: bytes, mime_type: str = "application/octet-stream") -> str:
    if not audio_bytes:
        return ""

    provider = os.getenv("STT_PROVIDER", "volcengine").strip().lower()
    if provider == "volcengine":
        pcm_bytes = _convert_audio_to_pcm(audio_bytes, mime_type=mime_type)
        if not pcm_bytes:
            return ""
        return asyncio.run(_transcribe_pcm_with_volcengine_async(pcm_bytes))

    return _transcribe_with_deepgram(audio_bytes)


def synthesize_audio_bytes(text: str) -> tuple[bytes, str]:
    normalized_text = str(text or "").strip()
    if not normalized_text:
        return b"", "audio/wav"

    provider = os.getenv("TTS_PROVIDER", "volcengine").strip().lower()
    if provider != "volcengine":
        raise RuntimeError(f"Inline audio playback does not support TTS provider: {provider}")

    active_card = CARD_STORE.get_active_card()
    voice_cfg = active_card.get("voice") or {}
    primary_voice_type = str(voice_cfg.get("voice_type") or "").strip() or None
    primary_resource_id = str(voice_cfg.get("resource_id") or "").strip() or None
    primary_model_name = str(voice_cfg.get("model") or "").strip() or None

    try:
        audio_bytes, sample_rate = asyncio.run(
            _synthesize_with_volcengine_async(
                normalized_text,
                voice_type=primary_voice_type,
                resource_id=primary_resource_id,
                model_name=primary_model_name,
            )
        )
    except Exception:
        # Fallback to env defaults when imported card voice/resource is not compatible.
        audio_bytes, sample_rate = asyncio.run(
            _synthesize_with_volcengine_async(
                normalized_text,
                voice_type=None,
                resource_id=None,
                model_name=None,
            )
        )

    if not audio_bytes:
        return b"", "audio/wav"

    return _pcm_to_wav(audio_bytes, sample_rate), "audio/wav"


def _endpoint_candidates(endpoint: str) -> list[str]:
    base = endpoint.rstrip("/")
    endpoints: list[str] = []
    if base.endswith("/chat/completions"):
        endpoints.append(base)
    elif base.endswith("/chat/completion"):
        endpoints.extend([base, base + "s"])
    else:
        endpoints.extend([base + "/chat/completions", base + "/chat/completion"])
    deduped = []
    for item in endpoints:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _get_model_temperature(model_id: str) -> float:
    """Get appropriate temperature for a model."""
    if "kimi" in model_id.lower():
        return 1.0
    return 0.6


def call_chat_completion(messages: list[dict[str, str]], model_id: str = "") -> str:
    api_key, endpoint, model = _chat_api_config(model_id)

    if not api_key:
        raise RuntimeError("Missing CHAT_API_KEY or MEMORY_LLM_API_KEY in .env")

    payload = {
        "model": model,
        "temperature": _get_model_temperature(model_id),
        "messages": messages,
    }
    body = json.dumps(payload).encode("utf-8")

    last_error: Exception | None = None
    for current_endpoint in _endpoint_candidates(endpoint):
        for attempt in range(2):
            req = request.Request(
                current_endpoint,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                method="POST",
            )
            try:
                with request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    return (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
            except error.HTTPError as exc:
                response_text = exc.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"HTTP {exc.code}: {response_text}") from exc
            except Exception as exc:  # pragma: no cover - network instability
                last_error = exc
                if attempt == 0:
                    time.sleep(0.6)
                    continue
                break

    raise RuntimeError(f"Chat request failed: {last_error}")


def iter_chat_completion_chunks(messages: list[dict[str, str]], model_id: str = ""):
    api_key, endpoint, model = _chat_api_config(model_id)
    if not api_key:
        raise RuntimeError("Missing CHAT_API_KEY or MEMORY_LLM_API_KEY in .env")

    payload = {
        "model": model,
        "temperature": _get_model_temperature(model_id),
        "messages": messages,
        "stream": True,
    }
    for current_endpoint in _endpoint_candidates(endpoint):
        try:
            yielded = False
            for chunk in _stream_chat_completion_once(current_endpoint, api_key, payload):
                yielded = True
                yield chunk
            if yielded:
                return
        except Exception as exc:  # pragma: no cover - network/provider variability
            continue

    full_reply = call_chat_completion(messages, model_id)
    for chunk in _chunk_text(full_reply):
        yield chunk


def _stream_chat_completion_once(
    endpoint: str,
    api_key: str,
    payload: dict[str, Any],
):
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with request.urlopen(req, timeout=45) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:") :].strip()
            if data == "[DONE]":
                break
            packet = json.loads(data)
            choice = packet.get("choices", [{}])[0]
            delta = choice.get("delta", {}).get("content")
            if delta is None:
                delta = choice.get("message", {}).get("content")
            if delta:
                yield str(delta)


def _chunk_text(text: str, size: int = 12) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    return [cleaned[index : index + size] for index in range(0, len(cleaned), size)]


def _sanitize_assistant_text(text: str) -> str:
    cleaned = str(text or "")
    # Remove parenthetical stage directions and emotion markers.
    cleaned = re.sub(r"[（(][^）)]{0,120}[）)]", "", cleaned)
    cleaned = cleaned.replace("（", "").replace("）", "").replace("(", "").replace(")", "")

    # Keep at most one question mark to avoid continuous rhetorical questions.
    question_seen = False
    output_chars: list[str] = []
    for ch in cleaned:
        if ch in {"?", "？"}:
            if question_seen:
                output_chars.append("。")
                continue
            question_seen = True
        output_chars.append(ch)

    sanitized = "".join(output_chars)
    sanitized = re.sub(r"\n{3,}", "\n\n", sanitized)
    return sanitized.strip()


def _sanitize_stream_chunk(chunk: str, in_parenthetical: bool) -> tuple[str, bool]:
    if not chunk:
        return "", in_parenthetical

    kept_chars: list[str] = []
    inside = in_parenthetical
    for ch in chunk:
        if ch in {"（", "("}:
            inside = True
            continue
        if ch in {"）", ")"}:
            inside = False
            continue
        if inside:
            continue
        kept_chars.append(ch)
    return "".join(kept_chars), inside


def count_retrieved_items(memory_text: str) -> int:
    if not memory_text:
        return 0
    return sum(1 for line in memory_text.splitlines() if line.startswith("- "))


def should_store_user_message(user_message: str) -> bool:
    text = user_message.strip().lower()

    # Never store memory probe queries
    memory_probe_patterns = (
        r"^你还记得",
        r"^你记得",
        r"^还记得我",
        r"^我叫什么",
        r"^我住哪",
        r"^我住哪里",
        r"^我喜欢什么",
        r"^do you remember",
        r"^what do you remember",
        r"^can you remember",
        r"^what is my name",
        r"^where do i live",
    )
    if any(re.search(pattern, text) for pattern in memory_probe_patterns):
        return False

    # Only store stable identity, preferences, style feedback, and long-term patterns
    stable_patterns = [
        r"我叫",
        r"我是",
        r"我住在",
        r"我喜欢",
        r"我不喜欢",
        r"我讨厌",
        r"我习惯",
        r"我经常",
        r"我一般",
        r"我希望你",
        r"你以后",
        r"以后回复",
        r"不要.*说教",
        r"别.*长篇",
        r"我更喜欢",
        r"我的项目",
        r"我最近在做",
    ]

    return any(re.search(pattern, text) for pattern in stable_patterns)


def serialize_memory(snapshot: dict[str, Any]) -> dict[str, Any]:
    persona = snapshot.get("persona_slots", {})
    preferences = snapshot.get("preference_slots", {})
    preference_profiles = snapshot.get("preference_profiles", {})
    conflicts = list(reversed(snapshot.get("conflicts", [])[-8:]))
    memories = snapshot.get("memories", [])

    active_events = [
        item
        for item in memories
        if item.get("memory_type") == "event" and item.get("status") == "active"
    ]
    active_events.sort(key=lambda item: item.get("updated_at", ""), reverse=True)

    rendered_preferences = []
    if preference_profiles:
        for key, items in sorted(preference_profiles.items(), key=lambda item: slot_label(item[0])):
            active_items = [item for item in items if item.get("status") == "active"]
            active_items.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
            for item in active_items:
                scope = item.get("scope", "global")
                label = slot_label(key)
                if scope != "global":
                    label = f"{label} ({scope_label(scope)})"
                rendered_preferences.append(
                    {
                        "key": key,
                        "label": label,
                        "value": item.get("value"),
                        "updated_at": item.get("updated_at"),
                        "memory_id": item.get("source_memory_id"),
                    }
                )
    else:
        rendered_preferences = [
            {
                "key": key,
                "label": slot_label(key),
                "value": value.get("value"),
                "updated_at": value.get("updated_at"),
                "memory_id": value.get("source_memory_id"),
            }
            for key, value in sorted(preferences.items(), key=lambda item: slot_label(item[0]))
        ]

    return {
        "persona": [
            {
                "key": key,
                "label": slot_label(key),
                "value": value.get("value"),
                "updated_at": value.get("updated_at"),
                "memory_id": value.get("source_memory_id"),
            }
            for key, value in sorted(persona.items(), key=lambda item: slot_label(item[0]))
        ],
        "preferences": rendered_preferences,
        "events": [
            {
                "memory_id": item.get("id"),
                "summary": item.get("summary"),
                "content": item.get("content"),
                "updated_at": item.get("updated_at"),
                "tags": item.get("tags", []),
            }
            for item in active_events[:8]
        ],
        "conflicts": conflicts,
    }


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    changes = []
    for area in ("persona_slots", "preference_slots"):
        before_slots = before.get(area, {})
        after_slots = after.get(area, {})
        for key, after_value in after_slots.items():
            before_value = before_slots.get(key, {}).get("value")
            current_value = after_value.get("value")
            if before_value == current_value:
                continue
            changes.append(
                {
                    "area": "persona" if area == "persona_slots" else "preference",
                    "key": key,
                    "label": slot_label(key),
                    "before": before_value,
                    "after": current_value,
                    "change_type": "added" if before_value is None else "updated",
                }
            )
        for key, before_value in before_slots.items():
            if key in after_slots:
                continue
            changes.append(
                {
                    "area": "persona" if area == "persona_slots" else "preference",
                    "key": key,
                    "label": slot_label(key),
                    "before": before_value.get("value"),
                    "after": "",
                    "change_type": "deleted",
                }
            )
    return changes


def slot_label(key: str) -> str:
    labels = {
        "name": "姓名",
        "occupation": "职业",
        "age": "年龄",
        "home_city": "当前城市",
        "work_city": "工作/学习城市",
        "work_context": "工作场景",
        "relationship_status": "关系状态",
        "favorite_beverage": "饮品偏好",
        "favorite_food": "食物偏好",
        "food_spice": "辣度偏好",
        "food_flavor": "口味偏好",
        "music_style": "音乐偏好",
        "activity_style": "活动偏好",
        "social_style": "社交偏好",
        "living_preference": "居住偏好",
    }
    return labels.get(key, key.replace("_", " "))


def scope_label(scope: str) -> str:
    labels = {
        "global": "长期",
        "breakfast": "早餐",
        "nighttime": "晚上",
        "workday": "工作时",
        "weekend": "周末",
        "with_friends": "和朋友一起时",
        "alone": "独处时",
    }
    return labels.get(scope, scope)


@dataclass
class DemoSession:
    memory: StructuredLongTermMemory
    short_history: list[dict[str, str]] = field(default_factory=list)
    last_updates: list[dict[str, Any]] = field(default_factory=list)
    last_memory_text: str = ""
    last_memory_count: int = 0
    current_model: str = ""
    companion_core: CompanionAgentCore | None = field(default=None, repr=False)
    companion_core_v2: CompanionAgentCoreV2 | None = field(default=None, repr=False)
    _event_queue: list[dict[str, Any]] = field(default_factory=list, repr=False)
    _event_listeners: list[asyncio.Queue] = field(default_factory=list, repr=False)
    # 会话标识
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "demo-user"

    def __post_init__(self):
        if self.companion_core is None:
            self.companion_core = CompanionAgentCore(
                memory_engine=self.memory,
                persona_config=PersonaConfig(name="姜姜"),
            )
        if self.companion_core_v2 is None:
            self.companion_core_v2 = CompanionAgentCoreV2(
                memory_engine=self.memory,
                persona_config=PersonaConfig(name="姜姜"),
                character_style=CharacterStyle(name="姜姜"),
                session_id=self.session_id,
                user_id=self.user_id,
            )

    def _active_card(self) -> dict[str, Any]:
        return CARD_STORE.get_active_card()
    
    async def _stream_v2_reply(
        self,
        user_message: str,
        memory_enabled: bool,
        active_card: dict[str, Any],
    ) -> list[dict]:
        """辅助方法：调用 v2 流式生成并收集所有 chunk。"""
        chunks = []
        async for chunk in self.companion_core_v2.generate_reply_streaming(
            user_message=user_message,
            conversation_history=self.short_history,
            character_card_prompt=active_card.get("system_prompt", ""),
            memory_enabled=memory_enabled,
            session_id=self.session_id,
            user_id=self.user_id,
        ):
            chunks.append(chunk)
        return chunks
    
    def _push_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Push an event to all SSE listeners."""
        event = {"type": event_type, "data": data, "timestamp": time.time()}
        self._event_queue.append(event)
        # Keep only last 100 events
        if len(self._event_queue) > 100:
            self._event_queue = self._event_queue[-100:]
        # Notify listeners
        for queue in self._event_listeners:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def get_event_queue(self) -> list[dict[str, Any]]:
        """Get a copy of recent events."""
        return list(self._event_queue)

    def create_event_listener(self) -> asyncio.Queue:
        """Create a new event listener queue."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._event_listeners.append(queue)
        return queue

    def remove_event_listener(self, queue: asyncio.Queue) -> None:
        """Remove an event listener."""
        if queue in self._event_listeners:
            self._event_listeners.remove(queue)

    async def send_message(
        self,
        user_message: str,
        memory_enabled: bool,
        context_engine_v2: bool = False,
        debug: bool = False,
        use_v2_brain: bool = False,
    ) -> dict[str, Any]:
        before_snapshot = self.memory.snapshot()
        active_card = self._active_card()

        # === Companion Agent Core V2 ===
        if use_v2_brain:
            # 新流程：generate_reply 内部完成 signal -> thread -> state -> policy -> assemble -> generate -> judge -> learn
            v2_result = await self.companion_core_v2.generate_reply(
                user_message=user_message,
                conversation_history=self.short_history,
                character_card_prompt=active_card.get("system_prompt", ""),
                memory_enabled=memory_enabled,
                session_id=self.session_id,
                user_id=self.user_id,
            )
            assistant_reply = v2_result.reply

            self.short_history.append({"role": "user", "content": user_message})
            self.short_history.append({"role": "assistant", "content": assistant_reply})

            # Memory update (统一由编排层决策，session 层只提交一次)
            after_snapshot = before_snapshot
            updates = []
            if memory_enabled and v2_result.memory_decision.action in ("add", "update"):
                if not v2_result.memory_decision.requires_confirmation:
                    # 调用 commit_memory 统一提交（避免双写）
                    memory_committed = await self.companion_core_v2.commit_memory()
                    if memory_committed:
                        after_snapshot = self.memory.snapshot()
                        updates = diff_snapshots(before_snapshot, after_snapshot)
                else:
                    updates.append({
                        "change_type": "pending",
                        "label": "记忆待确认",
                        "reason": v2_result.memory_decision.reason,
                        "privacy_level": v2_result.memory_decision.privacy_level,
                    })

            self.last_updates = updates
            self.last_memory_text = v2_result.memory_context.to_prompt_section()
            self.last_memory_count = v2_result.memory_context.memory_count

            return {
                "reply": assistant_reply,
                "messages": self.short_history,
                "memory_panel": serialize_memory(after_snapshot),
                "memory_used": v2_result.memory_context.memory_count > 0,
                "memory_used_count": v2_result.memory_context.memory_count,
                "memory_preview": v2_result.memory_context.to_prompt_section(),
                "updates": updates,
                "active_card_id": active_card.get("id"),
                "active_card_name": active_card.get("name"),
                "ncp": None,
                "companion": {
                    "situation": v2_result.intent.primary_intent,
                    "situation_confidence": v2_result.intent.intent_confidence,
                    "brain_mode": v2_result.policy.goal,
                    "mode_confidence": 0.8,
                    "memory_decision": {
                        "action": v2_result.memory_decision.action,
                        "reason": v2_result.memory_decision.reason,
                        "requires_confirmation": v2_result.memory_decision.requires_confirmation,
                    },
                    "emotional_state": v2_result.intent.emotional_state,
                    "conversation_rhythm": v2_result.intent.conversation_rhythm,
                    "current_state": v2_result.conversation_state.current_state,
                    "active_thread": v2_result.active_thread.get("name", ""),
                    "safety_flag": v2_result.safety_flag,
                },
                "context_meta": {
                    "scene": v2_result.intent.task_category,
                    "history_window": len(self.short_history),
                    "memory_limit": v2_result.memory_context.memory_count,
                    "companion_enabled": True,
                    "v2_brain": True,
                },
                "debug_info": v2_result.debug_info,
            }

        if context_engine_v2:
            # === Context Engine V3 (Companion Runtime Brain) ===
            history = [ChatMessage(role=m["role"], content=m["content"]) for m in self.short_history]
            
            # Retrieve memory if enabled
            memory_text = ""
            memory_count = 0
            if memory_enabled:
                memory_text = await self.memory.retrieve(query=user_message, limit=5)
                memory_count = count_retrieved_items(memory_text)
            
            ctx_input = ContextBuildInput(
                user_id="demo-user",
                character_id=active_card.get("id", "default-companion"),
                conversation_id="demo-conversation",
                user_message=user_message,
                history=history,
                debug=debug,
                character_prompt=active_card.get("system_prompt", ""),
            )
            ctx_result = await build_context_v3(ctx_input)

            # Inject memory into blocks if available
            if memory_text and memory_count > 0:
                from context_engine_v2.types import ContextBlock
                from context_engine_v2.token_budget import estimate_tokens
                memory_block = ContextBlock(
                    id="memory:retrieved",
                    type="memory",
                    role="system",
                    title="User Memory",
                    content=f"以下是与用户相关的记忆，请自然地在回复中运用：\n{memory_text}",
                    priority=70,
                    tokens=estimate_tokens(memory_text),
                    source="memory_store",
                    reason=f"Retrieved {memory_count} memory items relevant to query",
                    position="before_history",
                )
                # Insert before history blocks (which are at the end)
                ctx_result.blocks.insert(-1, memory_block)
                # Recompose messages with memory
                from context_engine_v2.prompt_composer import compose_messages
                ctx_result.messages = compose_messages(
                    ctx_result.blocks,
                    history[-8:],
                    user_message,
                )

            messages = ctx_result.messages

            assistant_reply = await asyncio.to_thread(call_chat_completion, messages, self.current_model)
            assistant_reply = _sanitize_assistant_text(assistant_reply)

            self.short_history.append({"role": "user", "content": user_message})
            self.short_history.append({"role": "assistant", "content": assistant_reply})

            # Memory update
            after_snapshot = self.memory.snapshot()
            updates: list[dict[str, Any]] = []
            if memory_enabled and should_store_user_message(user_message):
                await self.memory.store("user", user_message)
                after_snapshot = self.memory.snapshot()
                updates = diff_snapshots(before_snapshot, after_snapshot)

            # Update instance state for /api/state endpoint
            self.last_updates = updates
            self.last_memory_text = memory_text if memory_count > 0 else ""
            self.last_memory_count = memory_count

            # Push memory update events
            if updates:
                self._push_event("memory_updates", {
                    "updates": updates,
                    "memory_panel": serialize_memory(after_snapshot),
                })

            result_payload: dict[str, Any] = {
                "reply": assistant_reply,
                "messages": self.short_history,
                "memory_panel": serialize_memory(after_snapshot),
                "memory_used": memory_count > 0,
                "memory_used_count": memory_count,
                "memory_preview": memory_text if memory_count > 0 else "本次回答没有使用长期记忆",
                "updates": updates,
                "active_card_id": active_card.get("id"),
                "active_card_name": active_card.get("name"),
                "ncp": None,
                "companion": {
                    "situation": ctx_result.route.intent,
                    "situation_confidence": 1.0,
                    "memory_decision": {
                        "action": "add" if memory_enabled and should_store_user_message(user_message) else "ignore",
                        "reason": "Context Engine V3 with memory" if memory_enabled else "Memory disabled",
                        "requires_confirmation": False,
                    },
                    "skills_activated": ctx_result.route.skills,
                    "safety_flag": ctx_result.route.intent == "crisis",
                },
                "context_meta": {
                    "scene": ctx_result.route.intent,
                    "history_window": len(self.short_history),
                    "memory_limit": memory_count,
                    "companion_enabled": True,
                    "context_engine_v2": True,
                    "context_engine_v3": True,
                },
                "mcp_tool_results": [
                    {
                        "skill": r["skill"],
                        "tool_results": r["result"].get("tool_results", []),
                        "formatted_context": r["result"].get("formatted_context", ""),
                    }
                    for r in ctx_result.mcp_tool_results
                ] if ctx_result.mcp_tool_results else [],
            }
            if debug:
                result_payload["debug"] = {
                    "route": {
                        "intent": ctx_result.route.intent,
                        "emotion": ctx_result.route.emotion,
                        "skills": ctx_result.route.skills,
                        "need_memory": ctx_result.route.need_memory,
                        "need_lorebook": ctx_result.route.need_lorebook,
                        "need_robot_context": ctx_result.route.need_robot_context,
                        "response_style": ctx_result.route.response_style,
                    },
                    "blocks": [
                        {
                            "id": b.id,
                            "type": b.type,
                            "title": b.title,
                            "priority": b.priority,
                            "tokens": b.tokens,
                            "required": b.required,
                            "source": b.source,
                            "reason": b.reason,
                            "position": b.position,
                            "content": b.content,
                        }
                        for b in ctx_result.blocks
                    ],
                    "token_summary": {
                        "max_input_tokens": ctx_result.token_summary.max_input_tokens,
                        "used_tokens": ctx_result.token_summary.used_tokens,
                        "removed_blocks": [
                            {
                                "id": b.id,
                                "type": b.type,
                                "title": b.title,
                                "priority": b.priority,
                                "tokens": b.tokens,
                            }
                            for b in ctx_result.token_summary.removed_blocks
                        ],
                    },
                    "trace": [
                        {
                            "step": t.step,
                            "detail": t.detail,
                            "data": t.data,
                        }
                        for t in ctx_result.trace
                    ],
                    "final_messages": ctx_result.messages,
                }
            return result_payload

        # === Companion Agent Core Processing ===
        companion_result = await self.companion_core.process_message(
            user_message=user_message,
            conversation_history=self.short_history,
            character_card_prompt=active_card.get("system_prompt", ""),
            memory_enabled=memory_enabled,
        )

        # Build messages for LLM using companion core's system prompt
        messages = self.companion_core.build_messages_for_llm(
            result=companion_result,
            user_message=user_message,
            history=self.short_history,
        )

        assistant_reply = await asyncio.to_thread(call_chat_completion, messages, self.current_model)

        # Format response through companion core
        assistant_reply = self.companion_core.format_response(
            raw_response=assistant_reply,
            result=companion_result,
            user_message=user_message,
            history=self.short_history,
        )

        self.short_history.append({"role": "user", "content": user_message})
        self.short_history.append({"role": "assistant", "content": assistant_reply})

        # Memory update (using companion core's decision)
        after_snapshot = before_snapshot
        updates = []
        if memory_enabled and companion_result.memory_decision.action in ("add", "update"):
            if not companion_result.memory_decision.requires_confirmation:
                await self.memory.store("user", user_message)
                after_snapshot = self.memory.snapshot()
                updates = diff_snapshots(before_snapshot, after_snapshot)
            else:
                # Mark as pending confirmation
                updates.append({
                    "change_type": "pending",
                    "label": "记忆待确认",
                    "reason": companion_result.memory_decision.reason,
                    "privacy_level": companion_result.memory_decision.privacy_level,
                })

        self.last_updates = updates
        self.last_memory_text = companion_result.memory_context.to_prompt_section()
        self.last_memory_count = companion_result.memory_context.memory_count

        return {
            "reply": assistant_reply,
            "messages": self.short_history,
            "memory_panel": serialize_memory(after_snapshot),
            "memory_used": companion_result.memory_context.memory_count > 0,
            "memory_used_count": companion_result.memory_context.memory_count,
            "memory_preview": companion_result.memory_context.to_prompt_section(),
            "updates": updates,
            "active_card_id": active_card.get("id"),
            "active_card_name": active_card.get("name"),
            "ncp": None,
            "companion": {
                "situation": companion_result.situation,
                "situation_confidence": companion_result.situation_confidence,
                "memory_decision": {
                    "action": companion_result.memory_decision.action,
                    "reason": companion_result.memory_decision.reason,
                    "requires_confirmation": companion_result.memory_decision.requires_confirmation,
                },
                "skills_activated": companion_result.skills_activated,
                "safety_flag": companion_result.safety_flag,
            },
            "context_meta": {
                "scene": companion_result.situation,
                "history_window": len(self.short_history),
                "memory_limit": companion_result.memory_context.memory_count,
                "companion_enabled": True,
            },
        }

    def stream_message(
        self,
        user_message: str,
        memory_enabled: bool,
        context_engine_v2: bool = False,
        debug: bool = False,
        use_v2_brain: bool = False,
    ):
        before_snapshot = self.memory.snapshot()
        active_card = self._active_card()

        # === Companion Agent Core V2 (Streaming) ===
        if use_v2_brain:
            assistant_reply = ""
            in_parenthetical = False
            v2_result = None

            for chunk in asyncio.run(self._stream_v2_reply(
                user_message=user_message,
                memory_enabled=memory_enabled,
                active_card=active_card,
            )):
                if chunk["type"] == "delta":
                    filtered_chunk, in_parenthetical = _sanitize_stream_chunk(chunk["delta"], in_parenthetical)
                    if not filtered_chunk:
                        continue
                    assistant_reply += filtered_chunk
                    yield {"type": "assistant_delta", "delta": filtered_chunk}
                elif chunk["type"] == "final":
                    v2_result = chunk["result"]

            assistant_reply = _sanitize_assistant_text(assistant_reply)

            self.short_history.append({"role": "user", "content": user_message})
            self.short_history.append({"role": "assistant", "content": assistant_reply})

            after_snapshot = before_snapshot
            updates = []
            if v2_result and memory_enabled and v2_result.memory_decision.action in ("add", "update"):
                if not v2_result.memory_decision.requires_confirmation:
                    memory_committed = asyncio.run(self.companion_core_v2.commit_memory())
                    if memory_committed:
                        after_snapshot = self.memory.snapshot()
                        updates = diff_snapshots(before_snapshot, after_snapshot)
                else:
                    updates.append({
                        "change_type": "pending",
                        "label": "记忆待确认",
                        "reason": v2_result.memory_decision.reason,
                        "privacy_level": v2_result.memory_decision.privacy_level,
                    })

            self.last_updates = updates
            if v2_result:
                self.last_memory_text = v2_result.memory_context.to_prompt_section()
                self.last_memory_count = v2_result.memory_context.memory_count

            yield {
                "type": "final",
                "payload": {
                    "reply": assistant_reply,
                    "messages": self.short_history,
                    "memory_panel": serialize_memory(after_snapshot),
                    "memory_used": v2_result.memory_context.memory_count > 0 if v2_result else False,
                    "memory_used_count": v2_result.memory_context.memory_count if v2_result else 0,
                    "memory_preview": v2_result.memory_context.to_prompt_section() if v2_result else "",
                    "updates": updates,
                    "active_card_id": active_card.get("id"),
                    "active_card_name": active_card.get("name"),
                    "ncp": None,
                    "companion": {
                        "situation": v2_result.intent.primary_intent if v2_result else "",
                        "situation_confidence": v2_result.intent.intent_confidence if v2_result else 0,
                        "brain_mode": v2_result.policy.goal if v2_result else "",
                        "mode_confidence": 0.8,
                        "memory_decision": {
                            "action": v2_result.memory_decision.action if v2_result else "ignore",
                            "reason": v2_result.memory_decision.reason if v2_result else "",
                            "requires_confirmation": v2_result.memory_decision.requires_confirmation if v2_result else False,
                        },
                        "emotional_state": v2_result.intent.emotional_state if v2_result else "",
                        "conversation_rhythm": v2_result.intent.conversation_rhythm if v2_result else "",
                        "current_state": v2_result.conversation_state.current_state if v2_result else "",
                        "active_thread": v2_result.active_thread.get("name", "") if v2_result else "",
                        "safety_flag": v2_result.safety_flag if v2_result else False,
                    },
                    "context_meta": {
                        "scene": v2_result.intent.task_category if v2_result else "",
                        "history_window": len(self.short_history),
                        "memory_limit": v2_result.memory_context.memory_count if v2_result else 0,
                        "companion_enabled": True,
                        "v2_brain": True,
                    },
                    "debug_info": v2_result.debug_info if v2_result else {},
                },
            }
            return

        if context_engine_v2:
            # === Context Engine V3 (Companion Runtime Brain) ===
            history = [ChatMessage(role=m["role"], content=m["content"]) for m in self.short_history]
            
            # Retrieve memory if enabled
            memory_text = ""
            memory_count = 0
            if memory_enabled:
                memory_text = asyncio.run(self.memory.retrieve(query=user_message, limit=5))
                memory_count = count_retrieved_items(memory_text)
            
            ctx_input = ContextBuildInput(
                user_id="demo-user",
                character_id=active_card.get("id", "default-companion"),
                conversation_id="demo-conversation",
                user_message=user_message,
                history=history,
                debug=debug,
                character_prompt=active_card.get("system_prompt", ""),
            )
            ctx_result = asyncio.run(build_context_v3(ctx_input))

            # Inject memory into blocks if available
            if memory_text and memory_count > 0:
                from context_engine_v2.types import ContextBlock
                from context_engine_v2.token_budget import estimate_tokens
                memory_block = ContextBlock(
                    id="memory:retrieved",
                    type="memory",
                    role="system",
                    title="User Memory",
                    content=f"以下是与用户相关的记忆，请自然地在回复中运用：\n{memory_text}",
                    priority=70,
                    tokens=estimate_tokens(memory_text),
                    source="memory_store",
                    reason=f"Retrieved {memory_count} memory items relevant to query",
                    position="before_history",
                )
                ctx_result.blocks.insert(-1, memory_block)
                from context_engine_v2.prompt_composer import compose_messages
                ctx_result.messages = compose_messages(
                    ctx_result.blocks,
                    history[-8:],
                    user_message,
                )

            messages = ctx_result.messages

            chunks = iter_chat_completion_chunks(messages, self.current_model)
            assistant_reply = ""
            in_parenthetical = False
            for chunk in chunks:
                filtered_chunk, in_parenthetical = _sanitize_stream_chunk(chunk, in_parenthetical)
                if not filtered_chunk:
                    continue
                assistant_reply += filtered_chunk
                yield {"type": "assistant_delta", "delta": filtered_chunk}

            assistant_reply = _sanitize_assistant_text(assistant_reply)

            self.short_history.append({"role": "user", "content": user_message})
            self.short_history.append({"role": "assistant", "content": assistant_reply})

            # Memory update
            after_snapshot = self.memory.snapshot()
            updates = []
            if memory_enabled and should_store_user_message(user_message):
                asyncio.run(self.memory.store("user", user_message))
                after_snapshot = self.memory.snapshot()
                updates = diff_snapshots(before_snapshot, after_snapshot)

            # Update instance state for /api/state endpoint
            self.last_updates = updates
            self.last_memory_text = memory_text if memory_count > 0 else ""
            self.last_memory_count = memory_count

            result_payload = {
                "reply": assistant_reply,
                "messages": self.short_history,
                "memory_panel": serialize_memory(after_snapshot),
                "memory_used": memory_count > 0,
                "memory_used_count": memory_count,
                "memory_preview": memory_text if memory_count > 0 else "本次回答没有使用长期记忆",
                "updates": updates,
                "active_card_id": active_card.get("id"),
                "active_card_name": active_card.get("name"),
                "ncp": None,
                "companion": {
                    "situation": ctx_result.route.intent,
                    "situation_confidence": 1.0,
                    "memory_decision": {
                        "action": "add" if memory_enabled and should_store_user_message(user_message) else "ignore",
                        "reason": "Context Engine V3 with memory" if memory_enabled else "Memory disabled",
                        "requires_confirmation": False,
                    },
                    "skills_activated": ctx_result.route.skills,
                    "safety_flag": ctx_result.route.intent == "crisis",
                },
                "context_meta": {
                    "scene": ctx_result.route.intent,
                    "history_window": len(self.short_history),
                    "memory_limit": memory_count,
                    "companion_enabled": True,
                    "context_engine_v2": True,
                    "context_engine_v3": True,
                },
                "mcp_tool_results": [
                    {
                        "skill": r["skill"],
                        "tool_results": r["result"].get("tool_results", []),
                        "formatted_context": r["result"].get("formatted_context", ""),
                    }
                    for r in ctx_result.mcp_tool_results
                ] if ctx_result.mcp_tool_results else [],
            }
            if debug:
                result_payload["debug"] = {
                    "route": {
                        "intent": ctx_result.route.intent,
                        "emotion": ctx_result.route.emotion,
                        "skills": ctx_result.route.skills,
                        "need_memory": ctx_result.route.need_memory,
                        "need_lorebook": ctx_result.route.need_lorebook,
                        "need_robot_context": ctx_result.route.need_robot_context,
                        "response_style": ctx_result.route.response_style,
                    },
                    "blocks": [
                        {
                            "id": b.id,
                            "type": b.type,
                            "title": b.title,
                            "priority": b.priority,
                            "tokens": b.tokens,
                            "required": b.required,
                            "source": b.source,
                            "reason": b.reason,
                            "position": b.position,
                            "content": b.content,
                        }
                        for b in ctx_result.blocks
                    ],
                    "token_summary": {
                        "max_input_tokens": ctx_result.token_summary.max_input_tokens,
                        "used_tokens": ctx_result.token_summary.used_tokens,
                        "removed_blocks": [
                            {
                                "id": b.id,
                                "type": b.type,
                                "title": b.title,
                                "priority": b.priority,
                                "tokens": b.tokens,
                            }
                            for b in ctx_result.token_summary.removed_blocks
                        ],
                    },
                    "trace": [
                        {
                            "step": t.step,
                            "detail": t.detail,
                            "data": t.data,
                        }
                        for t in ctx_result.trace
                    ],
                    "final_messages": ctx_result.messages,
                }
            yield {"type": "final", "payload": result_payload}
            return

        # === Companion Agent Core Processing ===
        companion_result = asyncio.run(self.companion_core.process_message(
            user_message=user_message,
            conversation_history=self.short_history,
            character_card_prompt=active_card.get("system_prompt", ""),
            memory_enabled=memory_enabled,
        ))

        # Build messages for LLM
        messages = self.companion_core.build_messages_for_llm(
            result=companion_result,
            user_message=user_message,
            history=self.short_history,
        )

        chunks = iter_chat_completion_chunks(messages, self.current_model)
        assistant_reply = ""
        in_parenthetical = False
        for chunk in chunks:
            filtered_chunk, in_parenthetical = _sanitize_stream_chunk(chunk, in_parenthetical)
            if not filtered_chunk:
                continue
            assistant_reply += filtered_chunk
            yield {"type": "assistant_delta", "delta": filtered_chunk}

        assistant_reply = _sanitize_assistant_text(assistant_reply)

        # Format response
        assistant_reply = self.companion_core.format_response(
            raw_response=assistant_reply,
            result=companion_result,
            user_message=user_message,
            history=self.short_history,
        )

        self.short_history.append({"role": "user", "content": user_message})
        self.short_history.append({"role": "assistant", "content": assistant_reply})

        # Memory update (using companion core's decision)
        after_snapshot = before_snapshot
        updates = []
        if memory_enabled and companion_result.memory_decision.action in ("add", "update"):
            if not companion_result.memory_decision.requires_confirmation:
                asyncio.run(self.memory.store("user", user_message))
                after_snapshot = self.memory.snapshot()
                updates = diff_snapshots(before_snapshot, after_snapshot)
            else:
                updates.append({
                    "change_type": "pending",
                    "label": "记忆待确认",
                    "reason": companion_result.memory_decision.reason,
                    "privacy_level": companion_result.memory_decision.privacy_level,
                })

        self.last_updates = updates
        self.last_memory_text = companion_result.memory_context.to_prompt_section()
        self.last_memory_count = companion_result.memory_context.memory_count

        yield {
            "type": "final",
            "payload": {
                "reply": assistant_reply,
                "messages": self.short_history,
                "memory_panel": serialize_memory(after_snapshot),
                "memory_used": companion_result.memory_context.memory_count > 0,
                "memory_used_count": companion_result.memory_context.memory_count,
                "memory_preview": companion_result.memory_context.to_prompt_section(),
                "updates": updates,
                "active_card_id": active_card.get("id"),
                "active_card_name": active_card.get("name"),
                "ncp": None,
                "companion": {
                    "situation": companion_result.situation,
                    "situation_confidence": companion_result.situation_confidence,
                    "memory_decision": {
                        "action": companion_result.memory_decision.action,
                        "reason": companion_result.memory_decision.reason,
                        "requires_confirmation": companion_result.memory_decision.requires_confirmation,
                    },
                    "skills_activated": companion_result.skills_activated,
                    "safety_flag": companion_result.safety_flag,
                },
                "context_meta": {
                    "scene": companion_result.situation,
                    "history_window": len(self.short_history),
                    "memory_limit": companion_result.memory_context.memory_count,
                    "companion_enabled": True,
                },
            },
        }

    async def reset_session(self) -> dict[str, Any]:
        self.short_history.clear()
        self.last_updates = []
        self.last_memory_text = ""
        self.last_memory_count = 0
        # Reset v2 state tracker (full reset)
        if self.companion_core_v2:
            self.companion_core_v2.state_tracker.reset_session(full_reset=True)
            # Relationship memory can be optionally reset too
            # self.companion_core_v2.relationship_memory._profiles.clear()
        return self.state()

    async def clear_memory(self) -> dict[str, Any]:
        self.short_history.clear()
        self.last_updates = []
        self.last_memory_text = ""
        self.last_memory_count = 0
        await self.memory.clear()
        return self.state()

    def state(self) -> dict[str, Any]:
        snapshot = self.memory.snapshot()
        return {
            "messages": self.short_history,
            "memory_panel": serialize_memory(snapshot),
            "memory_used": bool(self.last_memory_text),
            "memory_used_count": self.last_memory_count,
            "memory_preview": self.last_memory_text,
            "updates": self.last_updates,
            "active_card_id": self._active_card().get("id"),
            "active_card_name": self._active_card().get("name"),
            "current_model": self.current_model,
        }

    async def memory_retrieve(
        self,
        query: str = "",
        filters: dict[str, Any] | None = None,
        limit: int = 6,
    ) -> dict[str, Any]:
        memory_text = await self.memory.retrieve(query=query, filters=filters, limit=limit)
        self.last_memory_text = memory_text
        self.last_memory_count = count_retrieved_items(memory_text)
        snapshot = self.memory.snapshot()
        return {
            "memory_text": memory_text,
            "memory_panel": serialize_memory(snapshot),
            "memory_used": bool(memory_text),
            "memory_used_count": self.last_memory_count,
        }

    async def memory_store(self, role: str, content: str) -> dict[str, Any]:
        before_snapshot = self.memory.snapshot()
        await self.memory.store(role, content)
        after_snapshot = self.memory.snapshot()
        updates = diff_snapshots(before_snapshot, after_snapshot)
        self.last_updates = updates
        return {
            "ok": True,
            "updates": updates,
            "memory_panel": serialize_memory(after_snapshot),
        }

    async def memory_delete(self, memory_id: str) -> dict[str, Any]:
        before_snapshot = self.memory.snapshot()
        deleted_memory = await self.memory.delete_memory(memory_id)
        if deleted_memory is None:
            raise ValueError("memory_id not found")

        after_snapshot = self.memory.snapshot()
        updates = diff_snapshots(before_snapshot, after_snapshot)
        if not updates:
            updates = [
                {
                    "area": deleted_memory.memory_type,
                    "key": deleted_memory.slot_key or deleted_memory.id,
                    "label": deleted_memory.summary or slot_label(deleted_memory.slot_key or "memory"),
                    "before": deleted_memory.value or deleted_memory.summary,
                    "after": "",
                    "change_type": "deleted",
                }
            ]

        self.last_updates = updates
        self.last_memory_text = ""
        self.last_memory_count = 0
        return {
            "ok": True,
            "deleted_memory_id": deleted_memory.id,
            "updates": updates,
            "memory_panel": serialize_memory(after_snapshot),
        }

    def append_transcript_message(self, role: str, content: str) -> dict[str, Any]:
        normalized_role = role.strip().lower()
        if normalized_role not in {"user", "assistant"}:
            raise ValueError("role must be user or assistant")

        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("content is required")

        self.short_history.append({"role": normalized_role, "content": normalized_content})
        return self.state()

    def start_assistant_transcript(self) -> dict[str, Any]:
        if not self.short_history or self.short_history[-1].get("role") != "assistant":
            self.short_history.append({"role": "assistant", "content": ""})
        return self.state()

    def update_assistant_transcript(self, content: str) -> dict[str, Any]:
        if not self.short_history or self.short_history[-1].get("role") != "assistant":
            self.short_history.append({"role": "assistant", "content": ""})
        self.short_history[-1] = {"role": "assistant", "content": content}
        return self.state()


load_local_env()

ENABLE_SCENE_ROUTER = env_flag("ENABLE_SCENE_ROUTER", True)
ENABLE_CONTEXT_PACKER_V2 = env_flag("ENABLE_CONTEXT_PACKER_V2", True)
ENABLE_MEMORY_RERANK_V2 = env_flag("ENABLE_MEMORY_RERANK_V2", True)
SCENE_STRATEGIES = load_scene_strategies()

CARD_STORE = CharacterCardStore(path=CHARACTER_CARDS_FILE)
SESSION = DemoSession(memory=StructuredLongTermMemory(file_path=str(MEMORY_FILE)))
SESSION_LOCK = threading.Lock()


@dataclass
class VoiceRuntimeState:
    card_id: str = ""
    card_name: str = ""
    voice_type: str = ""
    model: str = ""
    updated_at: float = 0.0
    source: str = ""

    def to_payload(self) -> dict[str, Any]:
        active = CARD_STORE.get_active_card()
        active_voice = active.get("voice") if isinstance(active.get("voice"), dict) else {}
        return {
            "runtime_card": {
                "card_id": self.card_id,
                "card_name": self.card_name,
                "voice_type": self.voice_type,
                "model": self.model,
                "updated_at": self.updated_at,
                "source": self.source,
            },
            "active_card": {
                "card_id": active.get("id"),
                "card_name": active.get("name"),
                "voice_type": active_voice.get("voice_type") if isinstance(active_voice, dict) else "",
                "model": (active.get("llm") or {}).get("model") if isinstance(active.get("llm"), dict) else "",
            },
            "is_runtime_synced": bool(self.card_id) and self.card_id == active.get("id"),
        }


VOICE_RUNTIME_STATE = VoiceRuntimeState()


class PrototypeHandler(BaseHTTPRequestHandler):
    server_version = "MemoryPrototype/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == VOICE_PROXY_PATH:
            self.send_response(HTTPStatus.TEMPORARY_REDIRECT)
            self.send_header("Location", voice_proxy_url())
            self.end_headers()
            return
        if parsed.path == voice_proxy_url().rstrip("/") or parsed.path.startswith(voice_proxy_url()):
            upstream_path = VOICE_CLIENT_PATH.rstrip("/") + parsed.path[len(VOICE_PROXY_PATH) :]
            self._proxy_upstream_get(upstream_path, parsed.query)
            return
        if parsed.path == "/app.js":
            self._serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/state":
            with SESSION_LOCK:
                payload = SESSION.state()
            self._send_json(payload)
            return
        if parsed.path == "/api/voice-status":
            self._send_json(get_voice_status())
            return
        if parsed.path == "/api/cards":
            with SESSION_LOCK:
                payload = CARD_STORE.list_payload()
            self._send_json(payload)
            return
        if parsed.path == "/api/cards/active":
            with SESSION_LOCK:
                payload = {"card": CARD_STORE.get_active_card()}
            self._send_json(payload)
            return
        if parsed.path == "/api/models":
            self._send_json({
                "models": _get_available_models(),
                "current_model": SESSION.current_model,
            })
            return
        if parsed.path == "/api/voice/llm-config":
            # Only allow local access to protect API keys
            client_ip = self.client_address[0]
            if client_ip not in ("127.0.0.1", "::1", "localhost"):
                self.send_error(HTTPStatus.FORBIDDEN, "Forbidden")
                return
            config = _get_model_config(SESSION.current_model)
            self._send_json({
                "model_id": SESSION.current_model,
                "api_key": config["api_key"],
                "base_url": config["base_url"],
                "model": config["model"],
                "provider": config["provider"],
            })
            return
        if parsed.path == "/api/voice/runtime-card":
            with SESSION_LOCK:
                payload = VOICE_RUNTIME_STATE.to_payload()
            self._send_json(payload)
            return
        if parsed.path == "/api/events":
            self._send_sse_events()
            return
        if parsed.path == "/start" or parsed.path.startswith("/sessions/"):
            self._proxy_upstream_request("GET", parsed.path, parsed.query)
            return
        self.send_error(HTTPStatus.NOT_FOUND, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)

        try:
            if parsed.path == "/start" or parsed.path.startswith("/sessions/"):
                raw_body = self._read_raw_body()
                self._proxy_upstream_request("POST", parsed.path, parsed.query, body=raw_body)
                return

            if parsed.path == "/api/transcribe-audio":
                audio_bytes = self._read_raw_body()
                mime_type = self.headers.get("Content-Type", "application/octet-stream")
                transcript = transcribe_audio_bytes(audio_bytes, mime_type=mime_type)
                self._send_json(
                    {
                        "transcript": transcript,
                        "mime_type": mime_type,
                        "has_audio": bool(audio_bytes),
                    }
                )
                return

            body = self._read_json_body()

            if parsed.path == "/api/synthesize-audio":
                text = str(body.get("text", "")).strip()
                if not text:
                    self._send_json({"error": "text is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                audio_bytes, content_type = synthesize_audio_bytes(text)
                if not audio_bytes:
                    self._send_json({"error": "No audio synthesized"}, status=HTTPStatus.BAD_GATEWAY)
                    return
                self._send_bytes(audio_bytes, content_type)
                return

            if parsed.path == "/api/chat-stream":
                message = str(body.get("message", "")).strip()
                memory_enabled = bool(body.get("memory_enabled", True))
                context_engine_v2 = bool(body.get("context_engine_v2", False))
                use_v2_brain = bool(body.get("use_v2_brain", False))
                debug = bool(body.get("debug", False))
                if not message:
                    self._send_json({"error": "Message is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                self._send_stream_headers()
                try:
                    with SESSION_LOCK:
                        for event in SESSION.stream_message(
                            message,
                            memory_enabled,
                            context_engine_v2=context_engine_v2,
                            use_v2_brain=use_v2_brain,
                            debug=debug,
                        ):
                            self._send_stream_event(event)
                except BrokenPipeError:
                    return
                except Exception as exc:
                    self._send_stream_event({"type": "error", "error": str(exc)})
                    self.close_connection = True
                    return
                self.close_connection = True
                return

            if parsed.path == "/api/memory/retrieve":
                query = str(body.get("query", ""))
                filters = body.get("filters")
                if filters is not None and not isinstance(filters, dict):
                    filters = None
                try:
                    limit = int(body.get("limit", 6))
                except (TypeError, ValueError):
                    limit = 6
                with SESSION_LOCK:
                    payload = asyncio.run(SESSION.memory_retrieve(query=query, filters=filters, limit=limit))
                self._send_json(payload)
                return

            if parsed.path == "/api/memory/store":
                role = str(body.get("role", "")).strip().lower()
                content = str(body.get("content", "")).strip()
                if not role or not content:
                    self._send_json(
                        {"error": "role and content are required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                with SESSION_LOCK:
                    payload = asyncio.run(SESSION.memory_store(role, content))
                self._send_json(payload)
                return

            if parsed.path == "/api/memory/delete":
                memory_id = str(body.get("memory_id", "")).strip()
                if not memory_id:
                    self._send_json(
                        {"error": "memory_id is required"},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return
                try:
                    with SESSION_LOCK:
                        payload = asyncio.run(SESSION.memory_delete(memory_id))
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.NOT_FOUND)
                    return
                self._send_json(payload)
                return

            if parsed.path == "/api/transcript/message":
                role = str(body.get("role", "")).strip().lower()
                content = str(body.get("content", "")).strip()
                with SESSION_LOCK:
                    payload = SESSION.append_transcript_message(role, content)
                self._send_json(payload)
                return

            if parsed.path == "/api/transcript/assistant/start":
                with SESSION_LOCK:
                    payload = SESSION.start_assistant_transcript()
                self._send_json(payload)
                return

            if parsed.path == "/api/transcript/assistant/update":
                content = str(body.get("content", ""))
                with SESSION_LOCK:
                    payload = SESSION.update_assistant_transcript(content)
                self._send_json(payload)
                return

            if parsed.path == "/api/chat":
                message = str(body.get("message", "")).strip()
                memory_enabled = bool(body.get("memory_enabled", True))
                context_engine_v2 = bool(body.get("context_engine_v2", False))
                use_v2_brain = bool(body.get("use_v2_brain", False))
                debug = bool(body.get("debug", False))
                if not message:
                    self._send_json({"error": "Message is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                with SESSION_LOCK:
                    payload = asyncio.run(
                        SESSION.send_message(
                            message,
                            memory_enabled,
                            context_engine_v2=context_engine_v2,
                            use_v2_brain=use_v2_brain,
                            debug=debug,
                        )
                    )
                self._send_json(payload)
                return

            if parsed.path == "/api/models/select":
                model_id = str(body.get("model_id", "")).strip()
                if not model_id:
                    self._send_json({"error": "model_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                config = _get_model_config(model_id)
                if not config["api_key"]:
                    self._send_json({"error": f"Model {model_id} API key not configured"}, status=HTTPStatus.BAD_REQUEST)
                    return
                with SESSION_LOCK:
                    SESSION.current_model = model_id
                self._send_json({
                    "model_id": model_id,
                    "name": config["name"],
                    "provider": config["provider"],
                })
                return

            if parsed.path == "/api/cards/select":
                card_id = str(body.get("card_id", "")).strip()
                if not card_id:
                    self._send_json({"error": "card_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                with SESSION_LOCK:
                    payload = CARD_STORE.select_card(card_id)
                self._send_json(payload)
                return

            if parsed.path == "/api/cards/upsert":
                card = body.get("card")
                if not isinstance(card, dict):
                    self._send_json({"error": "card is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                with SESSION_LOCK:
                    payload = CARD_STORE.upsert_card(card)
                self._send_json(payload)
                return

            if parsed.path == "/api/cards/import":
                raw_text = str(body.get("raw_text", ""))
                if not raw_text.strip():
                    self._send_json({"error": "raw_text is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                with SESSION_LOCK:
                    payload = CARD_STORE.import_cards(raw_text)
                self._send_json(payload)
                return

            if parsed.path == "/api/cards/delete":
                card_id = str(body.get("card_id", "")).strip()
                if not card_id:
                    self._send_json({"error": "card_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                try:
                    with SESSION_LOCK:
                        payload = CARD_STORE.delete_card(card_id)
                    self._send_json(payload)
                except ValueError as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return

            if parsed.path == "/api/voice/runtime-card/update":
                card_id = str(body.get("card_id", "")).strip()
                card_name = str(body.get("card_name", "")).strip()
                voice_type = str(body.get("voice_type", "")).strip()
                model = str(body.get("model", "")).strip()
                source = str(body.get("source", "voice_bot")).strip() or "voice_bot"
                if not card_id:
                    self._send_json({"error": "card_id is required"}, status=HTTPStatus.BAD_REQUEST)
                    return
                with SESSION_LOCK:
                    VOICE_RUNTIME_STATE.card_id = card_id
                    VOICE_RUNTIME_STATE.card_name = card_name
                    VOICE_RUNTIME_STATE.voice_type = voice_type
                    VOICE_RUNTIME_STATE.model = model
                    VOICE_RUNTIME_STATE.updated_at = time.time()
                    VOICE_RUNTIME_STATE.source = source
                    payload = VOICE_RUNTIME_STATE.to_payload()
                self._send_json(payload)
                return

            if parsed.path == "/api/reset-session":
                with SESSION_LOCK:
                    payload = asyncio.run(SESSION.reset_session())
                self._send_json(payload)
                return

            if parsed.path == "/api/clear-memory":
                with SESSION_LOCK:
                    payload = asyncio.run(SESSION.clear_memory())
                self._send_json(payload)
                return

            if parsed.path == "/api/companion/status":
                with SESSION_LOCK:
                    v2_status = SESSION.companion_core_v2.get_status() if SESSION.companion_core_v2 else {}
                    legacy_status = SESSION.companion_core.get_status() if SESSION.companion_core else {}
                    payload = {
                        "v2": v2_status,
                        "legacy": legacy_status,
                    }
                self._send_json(payload)
                return

            if parsed.path == "/api/companion/situations":
                with SESSION_LOCK:
                    payload = {
                        "situations": SESSION.companion_core.router.get_all_situations(),
                        "skills": SESSION.companion_core.skills.get_skill_descriptions(),
                    }
                self._send_json(payload)
                return

            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _read_raw_body(self) -> bytes:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return b""
        return self.rfile.read(content_length)

    def _send_json(self, payload: dict[str, Any], status: int = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_bytes(self, payload: bytes, content_type: str, status: int = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_sse_events(self) -> None:
        """Send Server-Sent Events for real-time memory updates."""
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        with SESSION_LOCK:
            queue = SESSION.create_event_listener()
            # Send any existing recent events
            for event in SESSION.get_event_queue()[-10:]:
                data = json.dumps(event, ensure_ascii=False)
                try:
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except Exception:
                    break

        try:
            while True:
                with SESSION_LOCK:
                    if queue not in SESSION._event_listeners:
                        break
                # Use a timeout to periodically check connection
                try:
                    event = loop.run_until_complete(asyncio.wait_for(queue.get(), timeout=1.0))
                    data = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except asyncio.TimeoutError:
                    # Send a keepalive comment
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                except Exception:
                    break
        finally:
            with SESSION_LOCK:
                SESSION.remove_event_listener(queue)
            loop.close()

    def _send_stream_headers(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def _send_stream_event(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.wfile.write(data)
        self.wfile.flush()

    def _proxy_upstream_get(self, upstream_path: str, query: str = "") -> None:
        upstream_url = urljoin(f"{VOICE_SERVICE_BASE_URL}/", upstream_path.lstrip("/"))
        if query:
            upstream_url = f"{upstream_url}?{query}"
        req = request.Request(
            upstream_url,
            headers={"User-Agent": "memory-prototype-demo"},
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                status = getattr(resp, "status", HTTPStatus.OK)
                self.send_response(status)
                content_type = resp.headers.get("Content-Type")
                if content_type:
                    self.send_header("Content-Type", content_type)
                cache_control = resp.headers.get("Cache-Control")
                if cache_control:
                    self.send_header("Cache-Control", cache_control)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except error.HTTPError as exc:
            body = exc.read()
            status = exc.code or HTTPStatus.BAD_GATEWAY
            self.send_response(status)
            content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _proxy_upstream_request(
        self,
        method: str,
        upstream_path: str,
        query: str = "",
        body: bytes | None = None,
    ) -> None:
        upstream_url = urljoin(f"{VOICE_SERVICE_BASE_URL}/", upstream_path.lstrip("/"))
        if query:
            upstream_url = f"{upstream_url}?{query}"

        headers = {"User-Agent": "memory-prototype-demo"}
        content_type = self.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type

        req = request.Request(
            upstream_url,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                status = getattr(resp, "status", HTTPStatus.OK)
                self.send_response(status)
                response_content_type = resp.headers.get("Content-Type")
                if response_content_type:
                    self.send_header("Content-Type", response_content_type)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
        except error.HTTPError as exc:
            data = exc.read()
            status = exc.code or HTTPStatus.BAD_GATEWAY
            self.send_response(status)
            response_content_type = exc.headers.get("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Type", response_content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)


def main() -> None:
    host = os.getenv("PROTOTYPE_HOST", "127.0.0.1")
    port = int(os.getenv("PROTOTYPE_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), PrototypeHandler)
    print(f"Prototype server running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
