import json
import struct
import uuid
from dataclasses import dataclass
from typing import AsyncGenerator, Optional

import websockets
from loguru import logger
from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.services.tts_service import TTSService

EVENT_START_CONNECTION = 1
EVENT_FINISH_CONNECTION = 2
EVENT_CONNECTION_STARTED = 50
EVENT_CONNECTION_FAILED = 51
EVENT_START_SESSION = 100
EVENT_FINISH_SESSION = 102
EVENT_SESSION_FINISHED = 152
EVENT_SESSION_FAILED = 153
EVENT_TASK_REQUEST = 200
EVENT_TTS_RESPONSE = 352

MSG_FULL_CLIENT_REQUEST = 0x1
MSG_FULL_SERVER_RESPONSE = 0x9
MSG_AUDIO_ONLY_RESPONSE = 0xB
MSG_ERROR = 0xF

FLAG_HAS_EVENT = 0x4
SERIALIZATION_JSON = 0x1
COMPRESSION_NONE = 0x0


@dataclass
class VolcengineTTSConfig:
    app_id: str
    access_key: str
    resource_id: str = "seed-tts-1.0"
    speaker: str = "zh_female_vv_uranus_bigtts"
    model: Optional[str] = None
    sample_rate: int = 24000
    uid: str = "pipecat-user"
    endpoint: str = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"


class VolcengineBidirectionalTTSService(TTSService):
    """Volcengine bidirectional TTS with connection reuse."""

    def __init__(self, *, config: VolcengineTTSConfig, **kwargs):
        super().__init__(aggregate_sentences=True, push_stop_frames=False, **kwargs)
        self._config = config
        self._voice_id = config.speaker
        self._ws = None
        self._connection_open = False
        self._connection_lock = None
        self._session_lock = None

    async def start(self, frame):
        await super().start(frame)
        if self._connection_lock is None:
            import asyncio

            self._connection_lock = asyncio.Lock()
        if self._session_lock is None:
            import asyncio

            self._session_lock = asyncio.Lock()

    async def stop(self, frame):
        await self._close_connection()
        await super().stop(frame)

    def set_voice(self, voice: str):
        self._voice_id = voice

    def _build_header(self, *, msg_type: int, has_event: bool) -> bytes:
        version_and_header_size = (0x1 << 4) | 0x1
        type_and_flags = (msg_type << 4) | (FLAG_HAS_EVENT if has_event else 0x0)
        ser_and_comp = (SERIALIZATION_JSON << 4) | COMPRESSION_NONE
        return bytes([version_and_header_size, type_and_flags, ser_and_comp, 0x0])

    def _build_full_request(self, *, event: int, payload: dict, session_id: Optional[str] = None) -> bytes:
        payload_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        header = self._build_header(msg_type=MSG_FULL_CLIENT_REQUEST, has_event=True)
        if session_id:
            sid = session_id.encode("utf-8")
            return (
                header
                + struct.pack(">i", event)
                + struct.pack(">I", len(sid))
                + sid
                + struct.pack(">I", len(payload_bytes))
                + payload_bytes
            )
        return header + struct.pack(">i", event) + struct.pack(">I", len(payload_bytes)) + payload_bytes

    def _parse_frame(self, data: bytes) -> dict:
        if len(data) < 4:
            return {"msg_type": None}

        byte1 = data[1]
        msg_type = (byte1 >> 4) & 0x0F
        has_event = (byte1 & 0x0F) == FLAG_HAS_EVENT

        if msg_type == MSG_ERROR:
            code = struct.unpack(">i", data[4:8])[0] if len(data) >= 8 else -1
            body = data[8:].decode("utf-8", errors="ignore") if len(data) > 8 else ""
            return {"msg_type": msg_type, "error": f"code={code}, detail={body}"}

        cursor = 4
        event = None
        if has_event and len(data) >= cursor + 4:
            event = struct.unpack(">i", data[cursor : cursor + 4])[0]
            cursor += 4

        if msg_type == MSG_FULL_SERVER_RESPONSE:
            response_id = ""
            payload_json = {}
            if len(data) >= cursor + 4:
                rid_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
                cursor += 4
                if len(data) >= cursor + rid_len:
                    response_id = data[cursor : cursor + rid_len].decode("utf-8", errors="ignore")
                    cursor += rid_len
            if len(data) >= cursor + 4:
                payload_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
                cursor += 4
                payload = data[cursor : cursor + payload_len]
                if payload:
                    try:
                        payload_json = json.loads(payload.decode("utf-8", errors="ignore"))
                    except Exception:
                        payload_json = {}
            return {
                "msg_type": msg_type,
                "event": event,
                "response_id": response_id,
                "payload_json": payload_json,
            }

        if msg_type == MSG_AUDIO_ONLY_RESPONSE:
            response_id = ""
            audio = b""
            if len(data) >= cursor + 4:
                rid_len = struct.unpack(">I", data[cursor : cursor + 4])[0]
                cursor += 4
                if len(data) >= cursor + rid_len:
                    response_id = data[cursor : cursor + rid_len].decode("utf-8", errors="ignore")
                    cursor += rid_len
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

    async def _ensure_connection(self):
        if self._connection_open and self._ws:
            return

        async with self._connection_lock:
            if self._connection_open and self._ws:
                return

            cfg = self._config
            headers = {
                "X-Api-App-Key": cfg.app_id,
                "X-Api-Access-Key": cfg.access_key,
                "X-Api-Resource-Id": cfg.resource_id,
                "X-Api-Connect-Id": str(uuid.uuid4()),
                "X-Control-Require-Usage-Tokens-Return": "text_words",
            }
            self._ws = await websockets.connect(cfg.endpoint, additional_headers=headers, max_size=None)
            await self._ws.send(self._build_full_request(event=EVENT_START_CONNECTION, payload={}))

            while True:
                raw = await self._ws.recv()
                if isinstance(raw, str):
                    continue
                parsed = self._parse_frame(raw)
                if parsed.get("msg_type") == MSG_ERROR:
                    raise RuntimeError(f"Volcengine connection failed: {parsed.get('error', 'unknown error')}")
                event = parsed.get("event")
                if event == EVENT_CONNECTION_STARTED:
                    self._connection_open = True
                    logger.info("Volcengine TTS websocket connected")
                    return
                if event == EVENT_CONNECTION_FAILED:
                    raise RuntimeError(f"Volcengine connection failed: {parsed.get('payload_json') or {}}")

    async def _close_connection(self):
        if not self._ws:
            self._connection_open = False
            return
        try:
            await self._ws.send(self._build_full_request(event=EVENT_FINISH_CONNECTION, payload={}))
        except Exception:
            pass
        try:
            await self._ws.close()
        except Exception:
            pass
        self._ws = None
        self._connection_open = False

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        if not text.strip():
            return

        cfg = self._config
        start_session_payload = {
            "user": {"uid": cfg.uid},
            "namespace": "BidirectionalTTS",
            "req_params": {
                "speaker": self._voice_id,
                "text": text,
                "audio_params": {
                    "format": "pcm",
                    "sample_rate": cfg.sample_rate,
                },
            },
        }
        if cfg.model:
            start_session_payload["req_params"]["model"] = cfg.model

        task_payload = {
            "user": {"uid": cfg.uid},
            "namespace": "BidirectionalTTS",
            "req_params": {"text": text},
        }

        session_id = str(uuid.uuid4())

        try:
            await self.start_ttfb_metrics()
            yield TTSStartedFrame(context_id=context_id)

            async with self._session_lock:
                await self._ensure_connection()
                await self._ws.send(
                    self._build_full_request(
                        event=EVENT_START_SESSION,
                        payload=start_session_payload,
                        session_id=session_id,
                    )
                )
                await self._ws.send(
                    self._build_full_request(
                        event=EVENT_TASK_REQUEST,
                        payload=task_payload,
                        session_id=session_id,
                    )
                )
                await self._ws.send(
                    self._build_full_request(
                        event=EVENT_FINISH_SESSION,
                        payload={},
                        session_id=session_id,
                    )
                )

                got_first_audio = False
                while True:
                    raw = await self._ws.recv()
                    if isinstance(raw, str):
                        continue

                    parsed = self._parse_frame(raw)
                    msg_type = parsed.get("msg_type")
                    event = parsed.get("event")

                    if msg_type == MSG_ERROR:
                        yield ErrorFrame(error=parsed.get("error", "volcengine tts error"))
                        break

                    if msg_type == MSG_AUDIO_ONLY_RESPONSE and event == EVENT_TTS_RESPONSE:
                        if parsed.get("response_id") != session_id:
                            continue
                        audio = parsed.get("audio") or b""
                        if audio:
                            if not got_first_audio:
                                got_first_audio = True
                                await self.stop_ttfb_metrics()
                            yield TTSAudioRawFrame(
                                audio=audio,
                                sample_rate=cfg.sample_rate,
                                num_channels=1,
                                context_id=context_id,
                            )
                        continue

                    if msg_type == MSG_FULL_SERVER_RESPONSE and parsed.get("response_id") != session_id:
                        continue

                    if event == EVENT_SESSION_FINISHED:
                        break

                    if event == EVENT_SESSION_FAILED:
                        payload = parsed.get("payload_json") or {}
                        message = payload.get("message", "session failed")
                        yield ErrorFrame(error=f"Volcengine session failed: {message}")
                        break

            await self.start_tts_usage_metrics(text)
        except Exception as e:
            logger.exception(f"Volcengine TTS request failed: {e}")
            yield ErrorFrame(error=f"Volcengine TTS error: {e}")
            await self._close_connection()
        finally:
            await self.stop_ttfb_metrics()
            yield TTSStoppedFrame(context_id=context_id)
