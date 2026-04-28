import asyncio
import difflib
import json
import os
import re
import struct
import time
import uuid
from typing import AsyncGenerator

from loguru import logger
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    StartFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection
from pipecat.services.stt_service import WebsocketSTTService
from pipecat.transcriptions.language import Language
from pipecat.utils.time import time_now_iso8601

try:
    from websockets.asyncio.client import connect as websocket_connect
    from websockets.protocol import State
except ModuleNotFoundError as e:
    logger.error(f"Exception: {e}")
    logger.error("In order to use websocket STT, ensure websockets is installed.")
    raise


class VolcengineASRStreamingService(WebsocketSTTService):
    """Volcengine Seed ASR 2.0 streaming STT service."""

    def __init__(
        self,
        *,
        app_id: str,
        access_key: str,
        resource_id: str = "volc.seedasr.sauc.duration",
        endpoint: str = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
        language: str = "zh-CN",
        sample_rate: int = 16000,
        chunk_ms: int = 200,
        **kwargs,
    ):
        super().__init__(sample_rate=sample_rate, **kwargs)
        self._app_id = app_id
        self._access_key = access_key
        self._resource_id = resource_id
        self._endpoint = endpoint
        self._language = language
        self._chunk_ms = chunk_ms
        self._connected = False
        self._receive_task = None
        self._audio_buffer = bytearray()
        self._chunk_size_bytes = int(self.sample_rate * 2 * self._chunk_ms / 1000)
        self._preroll_ms = int(os.getenv("VOLCENGINE_ASR_PREROLL_MS", "320"))
        self._preroll_max_bytes = int(self.sample_rate * 2 * self._preroll_ms / 1000)
        self._preroll_buffer = bytearray()
        self._request_open = False
        self._latest_interim_text = ""
        self._last_final_text = ""
        self._last_final_ts = 0.0
        self._speaking = False
        self._final_emitted_in_turn = False
        self._final_wait_ms = int(os.getenv("VOLCENGINE_ASR_FINAL_WAIT_MS", "900"))
        self._fallback_finalize_enabled = self._env_bool("VOLCENGINE_ASR_FALLBACK_FINALIZE", True)
        self._fallback_min_chars = int(os.getenv("VOLCENGINE_ASR_FALLBACK_MIN_CHARS", "4"))
        self._model_name = os.getenv("VOLCENGINE_ASR_MODEL_NAME", "bigmodel").strip() or "bigmodel"
        self._enable_itn = self._env_bool("VOLCENGINE_ASR_ENABLE_ITN", True)
        self._enable_punc = self._env_bool("VOLCENGINE_ASR_ENABLE_PUNC", True)
        self._enable_ddc = self._env_bool("VOLCENGINE_ASR_ENABLE_DDC", False)
        self._show_utterances = self._env_bool("VOLCENGINE_ASR_SHOW_UTTERANCES", True)
        self._result_type = os.getenv("VOLCENGINE_ASR_RESULT_TYPE", "single").strip() or "single"
        # Volcengine may proactively close websocket sessions between short turns.
        # Pipecat defaults (5s/3 times) can trip and stop STT after a couple rounds.
        # Make this tunable so short reconnects don't permanently disable recognition.
        self._MIN_STABLE_CONNECTION_DURATION = float(
            os.getenv("VOLCENGINE_ASR_MIN_STABLE_SEC", "0.8")
        )
        self._MAX_CONSECUTIVE_QUICK_FAILURES = int(
            os.getenv("VOLCENGINE_ASR_MAX_QUICK_FAILURES", "12")
        )

    @staticmethod
    def _env_bool(key: str, default: bool) -> bool:
        raw = os.getenv(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def can_generate_metrics(self) -> bool:
        return True

    async def start(self, frame: StartFrame):
        await super().start(frame)
        self._chunk_size_bytes = int(self.sample_rate * 2 * self._chunk_ms / 1000)
        self._preroll_max_bytes = int(self.sample_rate * 2 * self._preroll_ms / 1000)
        await self._connect()

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._disconnect()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._disconnect()

    async def _connect(self):
        await super()._connect()
        await self._connect_websocket()
        self._request_open = False
        if self._websocket and not self._receive_task:
            self._receive_task = self.create_task(self._receive_task_handler(self._report_error))

    async def _disconnect(self):
        await super()._disconnect()
        try:
            if self._websocket and self._websocket.state is State.OPEN and self._request_open:
                if self._audio_buffer:
                    await self.send_with_retry(
                        self._build_audio_only_packet(bytes(self._audio_buffer)),
                        self._report_error,
                    )
                    self._audio_buffer.clear()
        except Exception:
            pass

        if self._receive_task:
            await self.cancel_task(self._receive_task)
            self._receive_task = None

        await self._disconnect_websocket()

    async def _connect_websocket(self):
        connect_id = os.getenv("VOLCENGINE_ASR_CONNECT_ID", "").strip() or str(uuid.uuid4())
        headers = {
            "X-Api-App-Key": self._app_id,
            "X-Api-Access-Key": self._access_key,
            "X-Api-Resource-Id": self._resource_id,
            "X-Api-Connect-Id": connect_id,
        }
        logger.info(
            "Volcengine ASR reconnect guard: min_stable={}s, max_quick_failures={}",
            self._MIN_STABLE_CONNECTION_DURATION,
            self._MAX_CONSECUTIVE_QUICK_FAILURES,
        )
        logger.info(
            "Volcengine ASR config: model={}, lang={}, chunk_ms={}, final_wait_ms={}, fallback_finalize={}",
            self._model_name,
            self._language,
            self._chunk_ms,
            self._final_wait_ms,
            self._fallback_finalize_enabled,
        )
        self._websocket = await websocket_connect(
            self._endpoint,
            additional_headers=headers,
            max_size=None,
        )
        self._connected = True
        await self._call_event_handler("on_connected")
        logger.info("Volcengine ASR websocket connected")

    async def _disconnect_websocket(self):
        try:
            if self._websocket:
                await self._websocket.close()
        except Exception:
            pass
        finally:
            self._websocket = None
            self._connected = False
            await self._call_event_handler("on_disconnected")

    async def _ensure_request_started(self):
        if self._websocket and self._websocket.state is State.OPEN and not self._request_open:
            await self.send_with_retry(self._build_full_client_request(), self._report_error)
            self._request_open = True

    def _normalize_transcript_text(self, text: str) -> str:
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

    def _is_duplicate_final(self, text: str) -> bool:
        if not text or not self._last_final_text:
            return False
        now = time.monotonic()
        if now - self._last_final_ts > 2.5:
            return False
        previous = self._last_final_text
        if previous == text or previous in text or text in previous:
            return True
        return difflib.SequenceMatcher(None, previous, text).ratio() >= 0.96

    async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame, None]:
        if not self._speaking:
            if self._preroll_max_bytes > 0:
                self._preroll_buffer.extend(audio)
                if len(self._preroll_buffer) > self._preroll_max_bytes:
                    self._preroll_buffer = self._preroll_buffer[-self._preroll_max_bytes :]
            yield None
            return

        self._audio_buffer.extend(audio)
        if self._websocket and self._websocket.state is State.OPEN:
            await self._ensure_request_started()
            while len(self._audio_buffer) >= self._chunk_size_bytes:
                chunk = bytes(self._audio_buffer[: self._chunk_size_bytes])
                self._audio_buffer = self._audio_buffer[self._chunk_size_bytes :]
                await self.send_with_retry(self._build_audio_only_packet(chunk), self._report_error)

        yield None

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._speaking = True
            self._final_emitted_in_turn = False
            self._latest_interim_text = ""
            await self.start_processing_metrics()
            await self._ensure_request_started()
            if self._preroll_buffer:
                self._audio_buffer = bytearray(self._preroll_buffer) + self._audio_buffer
                self._preroll_buffer.clear()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._speaking = False
            if self._websocket and self._websocket.state is State.OPEN and self._request_open:
                if self._audio_buffer:
                    await self.send_with_retry(
                        self._build_audio_only_packet(bytes(self._audio_buffer)),
                        self._report_error,
                    )
                    self._audio_buffer.clear()
                await self.send_with_retry(
                    self._build_audio_only_packet(b"", is_final=True),
                    self._report_error,
                )
                self._request_open = False

            wait_attempts = max(1, (self._final_wait_ms + 99) // 100)
            for _ in range(wait_attempts):
                if self._final_emitted_in_turn:
                    break
                await asyncio.sleep(0.1)

            if not self._final_emitted_in_turn and self._fallback_finalize_enabled:
                final_text = self._normalize_transcript_text(self._latest_interim_text)
                if (
                    final_text
                    and len(final_text) >= self._fallback_min_chars
                    and not self._is_duplicate_final(final_text)
                ):
                    language = None
                    try:
                        language = Language(self._language)
                    except Exception:
                        language = None
                    await self.push_frame(
                        TranscriptionFrame(
                            final_text,
                            self._user_id,
                            time_now_iso8601(),
                            language,
                            {"source": "vad_stop_finalize"},
                        )
                    )
                    self._last_final_text = final_text
                    self._last_final_ts = time.monotonic()
                    await self.stop_processing_metrics()

            self._latest_interim_text = ""

    async def _receive_messages(self):
        async for message in self._websocket:
            if isinstance(message, str):
                continue
            await self._handle_binary_message(message)

    async def _handle_binary_message(self, data: bytes):
        if len(data) < 4:
            return

        header = data[1]
        message_type = (header >> 4) & 0x0F
        flags = header & 0x0F

        if message_type == 0xF:
            code = struct.unpack(">I", data[4:8])[0] if len(data) >= 8 else 0
            msg_len = struct.unpack(">I", data[8:12])[0] if len(data) >= 12 else 0
            msg = data[12 : 12 + msg_len].decode("utf-8", errors="ignore") if msg_len > 0 else ""
            self._request_open = False
            await self.push_error(error_msg=f"Volcengine ASR error {code}: {msg}")
            return

        if message_type != 0x9:
            return

        cursor = 4
        if flags in {0x1, 0x3} and len(data) >= cursor + 4:
            cursor += 4

        if len(data) < cursor + 4:
            return

        payload_size = struct.unpack(">I", data[cursor : cursor + 4])[0]
        cursor += 4
        payload = data[cursor : cursor + payload_size]
        if not payload:
            return

        try:
            message_json = json.loads(payload.decode("utf-8", errors="ignore"))
        except Exception:
            return

        await self._emit_transcription_frames(message_json)

    async def _emit_transcription_frames(self, message_json: dict):
        result = message_json.get("result") or {}
        text = result.get("text") or ""
        utterances = result.get("utterances") or []

        language = None
        try:
            language = Language(self._language)
        except Exception:
            language = None

        if utterances:
            latest = utterances[-1]
            utterance_text = (latest.get("text") or "").strip()
            if not utterance_text:
                return
            definite = bool(latest.get("definite"))
            normalized = self._normalize_transcript_text(utterance_text)
            if definite:
                self._final_emitted_in_turn = True
                self._latest_interim_text = ""
                if not self._is_duplicate_final(normalized):
                    await self.push_frame(
                        TranscriptionFrame(
                            normalized,
                            self._user_id,
                            time_now_iso8601(),
                            language,
                            message_json,
                        )
                    )
                    self._last_final_text = normalized
                    self._last_final_ts = time.monotonic()
                    await self.stop_processing_metrics()
            else:
                self._latest_interim_text = normalized
                await self.push_frame(
                    InterimTranscriptionFrame(
                        normalized,
                        self._user_id,
                        time_now_iso8601(),
                        language,
                        message_json,
                    )
                )
            return

        if text:
            normalized = self._normalize_transcript_text(text)
            self._latest_interim_text = normalized
            await self.push_frame(
                InterimTranscriptionFrame(
                    normalized,
                    self._user_id,
                    time_now_iso8601(),
                    language,
                    message_json,
                )
            )

    def _build_header(self, *, message_type: int, flags: int, serialization: int, compression: int) -> bytes:
        version_and_header = (0x1 << 4) | 0x1
        type_and_flags = ((message_type & 0x0F) << 4) | (flags & 0x0F)
        ser_and_comp = ((serialization & 0x0F) << 4) | (compression & 0x0F)
        return bytes([version_and_header, type_and_flags, ser_and_comp, 0x00])

    def _build_full_client_request(self) -> bytes:
        payload = {
            "user": {"uid": "pipecat-user"},
            "audio": {
                "format": "pcm",
                "codec": "raw",
                "rate": self.sample_rate,
                "bits": 16,
                "channel": 1,
                "language": self._language,
            },
            "request": {
                "model_name": self._model_name,
                "enable_itn": self._enable_itn,
                "enable_punc": self._enable_punc,
                "enable_ddc": self._enable_ddc,
                "show_utterances": self._show_utterances,
                "result_type": self._result_type,
            },
        }
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = self._build_header(message_type=0x1, flags=0x0, serialization=0x1, compression=0x0)
        return header + struct.pack(">I", len(payload_bytes)) + payload_bytes

    def _build_audio_only_packet(self, audio: bytes, is_final: bool = False) -> bytes:
        flags = 0x2 if is_final else 0x0
        header = self._build_header(message_type=0x2, flags=flags, serialization=0x0, compression=0x0)
        return header + struct.pack(">I", len(audio)) + audio
