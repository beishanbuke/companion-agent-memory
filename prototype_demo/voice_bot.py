"""Voice bot for the memory prototype demo.

Run:
    uv run prototype_demo/voice_bot.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.runner.types import RunnerArguments, SmallWebRTCRunnerArguments
from pipecat.services.cartesia.tts import CartesiaTTSService, GenerationConfig, Language
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.tts_service import TTSService
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from http_memory import HTTPMemoryBackend
from memory_processor import MemoryProcessor
from voice import (
    VolcengineASRStreamingService,
    VolcengineBidirectionalTTSService,
    VolcengineTTSConfig,
)

load_dotenv(PROJECT_DIR / ".env", override=True)

SYSTEM_PROMPT = """你是一个温和、自然、简洁的陪伴型助手。

请像真实的对话伙伴一样回答，不要显得像在背诵资料。
如果系统提供了长期记忆，请合理利用，让回答体现出连续性和了解感。
如果没有长期记忆，就只基于当前对话作答，不要假装记得以前的事情。
"""


class DynamicOpenAILLMService(OpenAILLMService):
    """OpenAI LLM service that supports runtime updates of api_key and base_url."""

    def update_client(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        """Recreate the underlying AsyncOpenAI client with new credentials.

        This allows switching between providers (e.g. SiliconFlow → Kimi)
        without rebuilding the entire Pipecat pipeline.
        """
        try:
            self._client = self.create_client(
                api_key=api_key,
                base_url=base_url,
            )
            logger.info("Updated LLM client: base_url={}", base_url)
        except Exception as exc:
            logger.warning("Failed to update LLM client: {}", exc)


def memory_api_base_url() -> str:
    explicit_base_url = os.getenv("MEMORY_API_BASE_URL", "").strip()
    if explicit_base_url:
        return explicit_base_url.rstrip("/")

    host = os.getenv("PROTOTYPE_HOST", "127.0.0.1").strip() or "127.0.0.1"
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(os.getenv("PROTOTYPE_PORT", "8765"))
    return f"http://{host}:{port}".rstrip("/")


def build_tts_service(active_card: dict[str, object] | None = None) -> TTSService:
    voice_cfg = (active_card or {}).get("voice")
    if not isinstance(voice_cfg, dict):
        voice_cfg = {}
    provider = str(voice_cfg.get("provider") or os.getenv("TTS_PROVIDER", "cartesia")).strip().lower()

    if provider == "volcengine":
        app_id = os.getenv("VOLCENGINE_APP_ID", "").strip()
        access_key = (
            os.getenv("VOLCENGINE_TTS_API_KEY", "").strip()
            or os.getenv("VOLCENGINE_TTS_ACCESS_KEY", "").strip()
            or os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
            or os.getenv("VOLCENGINE_SECRET_KEY", "").strip()
        )
        if not app_id or not access_key:
            raise RuntimeError(
                "TTS_PROVIDER=volcengine 但缺少 VOLCENGINE_APP_ID 或 TTS 密钥"
            )

        voice_type = str(
            voice_cfg.get("voice_type") or os.getenv("VOLCENGINE_VOICE_TYPE", "zh_female_vv_uranus_bigtts")
        ).strip()
        resource_id = str(voice_cfg.get("resource_id") or os.getenv("VOLCENGINE_RESOURCE_ID", "seed-tts-1.0")).strip()
        model_name = str(voice_cfg.get("model") or os.getenv("VOLCENGINE_MODEL") or "").strip() or None
        return VolcengineBidirectionalTTSService(
            config=VolcengineTTSConfig(
                app_id=app_id,
                access_key=access_key,
                resource_id=resource_id,
                speaker=voice_type,
                model=model_name,
                sample_rate=int(os.getenv("VOLCENGINE_SAMPLE_RATE", "24000")),
                uid=os.getenv("VOLCENGINE_UID", "pipecat-user"),
            )
        )

    cartesia_voice = os.getenv("CARTESIA_VOICE_ID", "a53c3509-ec3f-425c-a223-977f5f7424dd")
    return CartesiaTTSService(
        api_key=os.getenv("CARTESIA_API_KEY"),
        voice_id=cartesia_voice,
        params=CartesiaTTSService.InputParams(
            language=Language.ZH_CN,
            generation_config=GenerationConfig(speed=1, volume=1.1),
        ),
    )


def build_stt_service():
    provider = os.getenv("STT_PROVIDER", "volcengine").strip().lower()

    if provider == "volcengine":
        app_id = os.getenv("VOLCENGINE_APP_ID", "").strip()
        access_key = os.getenv("VOLCENGINE_ACCESS_KEY", "").strip()
        if not app_id or not access_key:
            raise RuntimeError(
                "STT_PROVIDER=volcengine 但缺少 VOLCENGINE_APP_ID 或 VOLCENGINE_ACCESS_KEY"
            )
        return VolcengineASRStreamingService(
            app_id=app_id,
            access_key=access_key,
            resource_id=os.getenv(
                "VOLCENGINE_ASR_RESOURCE_ID",
                "volc.seedasr.sauc.duration",
            ),
            endpoint=os.getenv(
                "VOLCENGINE_ASR_ENDPOINT",
                "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async",
            ),
            language=os.getenv("VOLCENGINE_ASR_LANGUAGE", "zh-CN"),
            sample_rate=int(os.getenv("VOLCENGINE_ASR_SAMPLE_RATE", "16000")),
            chunk_ms=int(os.getenv("VOLCENGINE_ASR_CHUNK_MS", "200")),
            audio_passthrough=True,
        )

    from deepgram import LiveOptions

    return DeepgramSTTService(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        live_options=LiveOptions(
            model="nova-2",
            language="zh-CN",
            encoding="linear16",
            sample_rate=16000,
            interim_results=True,
            smart_format=True,
            filler_words=False,
            utterance_end_ms="1500",
            endpointing=300,
            no_delay=True,
        ),
    )


class UserTranscriptMirrorProcessor(FrameProcessor):
    def __init__(self, memory_backend: HTTPMemoryBackend):
        super().__init__()
        self._memory_backend = memory_backend

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, TranscriptionFrame) and direction == FrameDirection.DOWNSTREAM:
            text = (getattr(frame, "text", "") or "").strip()
            if text:
                try:
                    await self._memory_backend.append_transcript_message("user", text)
                except Exception as exc:
                    logger.warning(f"Failed to mirror user transcript to demo UI: {exc}")
        await self.push_frame(frame, direction)


class AssistantTranscriptMirrorProcessor(FrameProcessor):
    def __init__(self, memory_backend: HTTPMemoryBackend):
        super().__init__()
        self._memory_backend = memory_backend
        self._chunks: list[str] = []
        self._started = False

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, LLMFullResponseStartFrame):
                self._chunks = []
                self._started = True
                try:
                    await self._memory_backend.start_assistant_transcript()
                except Exception as exc:
                    logger.warning(f"Failed to start assistant transcript in demo UI: {exc}")
            elif isinstance(frame, LLMTextFrame) and self._started:
                self._chunks.append(frame.text)
                try:
                    await self._memory_backend.update_assistant_transcript("".join(self._chunks))
                except Exception as exc:
                    logger.warning(f"Failed to update assistant transcript in demo UI: {exc}")
            elif isinstance(frame, LLMFullResponseEndFrame):
                final_text = "".join(self._chunks).strip()
                self._started = False
                self._chunks = []
                if final_text:
                    try:
                        await self._memory_backend.update_assistant_transcript(final_text)
                    except Exception as exc:
                        logger.warning(f"Failed to finalize assistant transcript in demo UI: {exc}")
        await self.push_frame(frame, direction)


async def run_bot(transport: BaseTransport):
    logger.info("Starting prototype voice bot")

    memory = HTTPMemoryBackend(base_url=memory_api_base_url())
    active_card = await memory.get_active_character_card()
    runtime_prompt = str(active_card.get("system_prompt") or SYSTEM_PROMPT).strip() or SYSTEM_PROMPT
    runtime_model = str((active_card.get("llm") or {}).get("model") if isinstance(active_card.get("llm"), dict) else "").strip()
    logger.info(
        "Active character card: id={}, name={}, tts_voice={}",
        active_card.get("id"),
        active_card.get("name"),
        (active_card.get("voice") or {}).get("voice_type") if isinstance(active_card.get("voice"), dict) else "",
    )
    stt = build_stt_service()
    tts = build_tts_service(active_card)

    # Load current model config from server so the voice bot uses the same
    # provider/api_key/base_url as the text chat.
    llm_config = await memory.get_selected_llm_config()
    llm_api_key = llm_config.get("api_key") or os.getenv("OPENAI_API_KEY")
    llm_base_url = llm_config.get("base_url") or os.getenv("OPENAI_BASE_URL")
    llm_model = llm_config.get("model") or runtime_model or os.getenv("OPENAI_MODEL")

    llm = DynamicOpenAILLMService(
        model=llm_model,
        api_key=llm_api_key,
        base_url=llm_base_url,
    )
    vad_params = VADParams(
        start_secs=float(os.getenv("VOICE_VAD_START_SECS", "0.12")),
        stop_secs=float(os.getenv("VOICE_VAD_STOP_SECS", "0.15")),
        confidence=float(os.getenv("VOICE_VAD_CONFIDENCE", "0.7")),
        min_volume=float(os.getenv("VOICE_VAD_MIN_VOLUME", "0.55")),
    )

    context = LLMContext([{"role": "system", "content": runtime_prompt}])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(params=vad_params)
        ),
    )
    user_transcript_mirror = UserTranscriptMirrorProcessor(memory)
    assistant_transcript_mirror = AssistantTranscriptMirrorProcessor(memory)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_transcript_mirror,
            user_aggregator,
            MemoryProcessor(memory),
            llm,
            assistant_transcript_mirror,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    # Track currently applied settings to avoid unnecessary resets mid-stream
    _current_prompt = runtime_prompt
    _current_voice = (
        (active_card.get("voice") or {}).get("voice_type")
        if isinstance(active_card.get("voice"), dict)
        else ""
    )
    _current_model = runtime_model

    async def refresh_runtime_card(reason: str) -> None:
        nonlocal _current_prompt, _current_voice, _current_model
        try:
            card = await memory.get_active_character_card()
        except Exception as exc:
            logger.warning("Failed to fetch active character card on {}: {}", reason, exc)
            return

        next_prompt = str(card.get("system_prompt") or SYSTEM_PROMPT).strip() or SYSTEM_PROMPT
        next_model = str((card.get("llm") or {}).get("model") if isinstance(card.get("llm"), dict) else "").strip()
        next_voice = (
            (card.get("voice") or {}).get("voice_type")
            if isinstance(card.get("voice"), dict)
            else ""
        )

        # Only reset conversation context when the prompt actually changes to avoid
        # wiping conversation history on reconnect.
        if next_prompt != _current_prompt:
            context.set_messages([{"role": "system", "content": next_prompt}])
            _current_prompt = next_prompt
            logger.info("Switched system prompt on {}", reason)

        # Only switch TTS voice when it actually changes to avoid timbre shifts
        # mid-reply caused by reconnects.
        if next_voice and next_voice != _current_voice and hasattr(tts, "set_voice"):
            try:
                tts.set_voice(str(next_voice))
                _current_voice = next_voice
                logger.info("Switched TTS voice to {} on {}", next_voice, reason)
            except Exception as exc:
                logger.warning("Failed to switch TTS voice on {}: {}", reason, exc)

        # When the model changes we must also update api_key/base_url so that
        # the voice bot calls the same provider as the text chat.
        if next_model and next_model != _current_model:
            try:
                new_config = await memory.get_selected_llm_config()
                new_api_key = new_config.get("api_key") or os.getenv("OPENAI_API_KEY")
                new_base_url = new_config.get("base_url") or os.getenv("OPENAI_BASE_URL")
                new_actual_model = new_config.get("model") or next_model

                if hasattr(llm, "update_client"):
                    llm.update_client(api_key=new_api_key, base_url=new_base_url)
                if hasattr(llm, "set_full_model_name"):
                    llm.set_full_model_name(new_actual_model)

                _current_model = next_model
                logger.info(
                    "Switched LLM to {} (provider={}) on {}",
                    new_actual_model,
                    new_config.get("provider", "unknown"),
                    reason,
                )
            except Exception as exc:
                logger.warning("Failed to switch LLM model on {}: {}", reason, exc)

        try:
            await memory.update_voice_runtime_card(
                card_id=str(card.get("id") or ""),
                card_name=str(card.get("name") or ""),
                voice_type=str(next_voice or ""),
                model=str(next_model or os.getenv("OPENAI_MODEL") or ""),
                source=f"voice_bot:{reason}",
            )
        except Exception as exc:
            logger.warning("Failed to report runtime card on {}: {}", reason, exc)

        logger.info(
            "Applied active card on {}: id={}, name={}, tts_voice={}, model={}",
            reason,
            card.get("id"),
            card.get("name"),
            next_voice,
            next_model or os.getenv("OPENAI_MODEL"),
        )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Voice client connected")
        await refresh_runtime_card("client_connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Voice client disconnected")
        await task.cancel()

    runner = PipelineRunner(handle_sigint=False)
    await runner.run(task)


async def bot(runner_args: RunnerArguments):
    transport = None

    match runner_args:
        case SmallWebRTCRunnerArguments():
            webrtc_connection: SmallWebRTCConnection = runner_args.webrtc_connection
            transport = SmallWebRTCTransport(
                webrtc_connection=webrtc_connection,
                params=TransportParams(
                    audio_in_enabled=True,
                    audio_out_enabled=True,
                ),
            )
        case _:
            logger.error(f"Unsupported runner arguments type: {type(runner_args)}")
            return

    await run_bot(transport)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
