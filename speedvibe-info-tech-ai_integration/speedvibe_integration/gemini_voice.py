"""
Standalone Gemini Live voice for Speedvibe (no app.modules.telephonics dependency).
Same WebSocket protocol as the main backend's gemini_live.py + LMS widget.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import struct
import time
import uuid
from typing import Any, Optional

from fastapi import WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

from speedvibe_integration.config import settings
from speedvibe_integration.constants import SPEEDVIBE_SYSTEM_INSTRUCTIONS

logger = logging.getLogger(__name__)

MODEL = os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-latest")
BROWSER_SAMPLE_RATE = 24000
GEMINI_INPUT_RATE = 16000
GEMINI_OUTPUT_RATE = 24000

_rag: Any = None


def _get_speedvibe_rag():
    global _rag
    if _rag is None:
        from speedvibe_integration.rag_chroma import SpeedvibeChromaRAG

        _rag = SpeedvibeChromaRAG()
    return _rag


class LiveAudioSession:
    """Gemini Live session (mirrors telephonics/gemini_live.LiveAudioSession; no CostService)."""

    def __init__(self, websocket: WebSocket, system_instruction: str, api_key: str):
        self.websocket = websocket
        self.system_instruction = system_instruction
        self.client = genai.Client(api_key=api_key)
        self.config = self._get_live_config(system_instruction)

        self.session_manager = None
        self.session = None
        self.running = False
        self.tasks: list[asyncio.Task] = []

        self.audio_send_buffer = bytearray()
        self.SEND_CHUNK_BYTES = 4800
        self.audio_output_queue: asyncio.Queue = asyncio.Queue()

        self.ai_speaking_until = 0.0
        self._audio_packets_received = 0
        self._audio_packets_suppressed = 0
        self._audio_chunks_sent = 0

        self.total_input_duration = 0.0
        self.total_output_duration = 0.0
        self.session_id = str(uuid.uuid4())
        self.company_id = "speedvibe"

    def _get_live_config(self, system_instruction: str) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            system_instruction=types.Content(parts=[types.Part(text=system_instruction)]),
            generation_config=types.GenerationConfig(temperature=0.7),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(
                    disabled=False,
                    start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                    end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,
                    silence_duration_ms=1000,
                )
            ),
        )

    async def start(self) -> bool:
        try:
            max_retries = 3
            last_error: Optional[Exception] = None
            for attempt in range(max_retries):
                try:
                    logger.info("Connecting to Gemini Live (attempt %s/%s)...", attempt + 1, max_retries)
                    self.session_manager = self.client.aio.live.connect(model=MODEL, config=self.config)
                    self.session = await self.session_manager.__aenter__()
                    self.running = True
                    break
                except Exception as e:
                    logger.warning("Connection attempt %s failed: %s", attempt + 1, e)
                    last_error = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(1.0)

            if not self.running:
                raise last_error or RuntimeError("Failed to connect after retries")

            self.tasks.append(asyncio.create_task(self._receive_from_gemini()))
            self.tasks.append(asyncio.create_task(self._send_audio_to_frontend()))

            logger.info("Triggering initial AI greeting...")
            await self.session.send(input="Greet the caller in one short sentence.", end_of_turn=True)
            logger.info("Gemini Live session started successfully")
            return True
        except Exception as e:
            logger.error("Failed to start Gemini Live session: %s", e, exc_info=True)
            return False

    async def stop(self) -> None:
        self.running = False
        for task in self.tasks:
            task.cancel()
        if self.session_manager:
            await self.session_manager.__aexit__(None, None, None)
        logger.info(
            "Gemini Live session stopped (input %.2fs output %.2fs)",
            self.total_input_duration,
            self.total_output_duration,
        )

    async def _flush_send_buffer(self) -> None:
        if not self.audio_send_buffer or not self.running or not self.session:
            return
        chunk = bytes(self.audio_send_buffer)
        self.audio_send_buffer.clear()
        try:
            loop = asyncio.get_event_loop()
            resampled = await loop.run_in_executor(
                None, self._resample_audio, chunk, BROWSER_SAMPLE_RATE, GEMINI_INPUT_RATE
            )
            await self.session.send_realtime_input(
                audio={"data": resampled, "mime_type": "audio/pcm;rate=16000"}
            )
        except Exception as e:
            logger.error("Error flushing audio buffer: %s", e)

    async def send_audio(self, audio_data: bytes) -> None:
        if not self.running or not self.session:
            return

        duration_sec = len(audio_data) / (BROWSER_SAMPLE_RATE * 2)
        self.total_input_duration += duration_sec
        self._audio_packets_received += 1

        if time.monotonic() < self.ai_speaking_until:
            self._audio_packets_suppressed += 1
            return

        if self._audio_packets_suppressed > 0:
            self._audio_packets_suppressed = 0

        self.audio_send_buffer.extend(audio_data)
        if len(self.audio_send_buffer) < self.SEND_CHUNK_BYTES:
            return

        chunk = bytes(self.audio_send_buffer)
        self.audio_send_buffer.clear()

        try:
            loop = asyncio.get_event_loop()
            resampled = await loop.run_in_executor(
                None, self._resample_audio, chunk, BROWSER_SAMPLE_RATE, GEMINI_INPUT_RATE
            )
            await self.session.send_realtime_input(
                audio={"data": resampled, "mime_type": "audio/pcm;rate=16000"}
            )
            self._audio_chunks_sent += 1
        except Exception as e:
            logger.error("Error sending audio to Gemini: %s", e)

    @staticmethod
    def _resample_audio(audio_data: bytes, from_rate: int, to_rate: int) -> bytes:
        if from_rate == to_rate or len(audio_data) < 4:
            return audio_data
        n_samples = len(audio_data) // 2
        samples = struct.unpack(f"<{n_samples}h", audio_data)
        ratio = from_rate / to_rate
        new_length = int(n_samples / ratio)
        resampled: list[int] = []
        for i in range(new_length):
            src_pos = i * ratio
            src_idx = int(src_pos)
            if src_idx >= n_samples - 1:
                resampled.append(samples[-1])
            else:
                frac = src_pos - src_idx
                val = int(samples[src_idx] * (1 - frac) + samples[src_idx + 1] * frac)
                resampled.append(max(-32768, min(32767, val)))
        return struct.pack(f"<{len(resampled)}h", *resampled)

    async def _handle_interruption(self) -> None:
        self.audio_send_buffer.clear()
        cleared = 0
        while not self.audio_output_queue.empty():
            try:
                self.audio_output_queue.get_nowait()
                self.audio_output_queue.task_done()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        try:
            await self.websocket.send_json({"type": "interrupt"})
        except Exception:
            pass
        if cleared:
            logger.info("Interruption: cleared %s queued audio chunks", cleared)

    async def _receive_from_gemini(self) -> None:
        try:
            while self.running:
                async for response in self.session.receive():
                    if not self.running:
                        break
                    if response.data:
                        await self.audio_output_queue.put(response.data)
                    server_content = response.server_content
                    if server_content:
                        if server_content.interrupted:
                            logger.info("User interrupted AI — clearing audio queue")
                            await self._handle_interruption()
                        if server_content.input_transcription:
                            transcript = server_content.input_transcription.text
                            if transcript:
                                logger.info("User said: %s", transcript)
                                await self.websocket.send_json(
                                    {"type": "transcript", "speaker": "user", "text": transcript}
                                )
                        if server_content.output_transcription:
                            transcript = server_content.output_transcription.text
                            if transcript:
                                logger.info("AI said: %s", transcript)
                    if response.text:
                        logger.info("Gemini: %s", response.text)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error receiving from Gemini: %s", e)
            self.running = False

    async def _send_audio_to_frontend(self) -> None:
        try:
            while self.running:
                audio_data = await self.audio_output_queue.get()
                output_duration = len(audio_data) / (GEMINI_OUTPUT_RATE * 2)
                self.total_output_duration += output_duration
                self.ai_speaking_until = time.monotonic() + 0.6
                await self.websocket.send_bytes(audio_data)
                self.audio_output_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Error sending audio to frontend: %s", e)


async def handle_speedvibe_gemini_web_call(websocket: WebSocket) -> None:
    """
    Full Gemini Live handler for standalone Speedvibe deployments.
    """
    await websocket.accept()
    logger.info("[Speedvibe] WebSocket connected (standalone Gemini Live)")

    if not (settings.GEMINI_API_KEY or "").strip():
        logger.error("GEMINI_API_KEY is not set; cannot start voice")
        try:
            await websocket.send_json({"type": "error", "message": "GEMINI_API_KEY not configured on server"})
        except Exception:
            pass
        await websocket.close(code=1011)
        return

    voice_guidelines = """
    VOICE GUIDELINES: Be extremely concise. Short sentences only. Ask one follow-up question. Stop if interrupted. Wait through silence.
    """

    # Broad query so retrieved chunks match typical caller questions (same idea as chat top_k context).
    rag_query = (
        "Speedvibe Info Tech Nigeria technology services IT consulting "
        "software development digital solutions company contact"
    )

    async def get_rag_context() -> str:
        try:
            rag = _get_speedvibe_rag()
            relevant_docs = await rag.search_relevant_content(rag_query, top_k=3)
            if not relevant_docs:
                return ""
            parts = []
            for doc in relevant_docs:
                # Align with text chat (`chat.py`) so voice and chat see the same excerpts.
                if doc.get("similarity", 0) > 0.2:
                    parts.append(doc["content"][:1200])
            if parts:
                ctx = "\n\nKNOWLEDGE BASE:\n" + "\n\n".join(parts)
                logger.info("[Speedvibe] RAG context loaded (%s docs)", len(parts))
                return ctx
        except Exception as e:
            logger.warning("[Speedvibe] RAG unavailable for voice: %s", e)
        return ""

    # Embedding + Chroma routinely take 0.5–5s; a 0.3s timeout dropped KB every time.
    try:
        knowledge_context = await asyncio.wait_for(get_rag_context(), timeout=45.0)
    except asyncio.TimeoutError:
        logger.warning("[Speedvibe] RAG lookup timed out for voice (>%ss)", 45)
        knowledge_context = ""

    system_instruction = SPEEDVIBE_SYSTEM_INSTRUCTIONS + voice_guidelines + knowledge_context
    logger.info("System instruction length: %s characters", len(system_instruction))

    api_key = (settings.GEMINI_API_KEY or "").strip()
    session = LiveAudioSession(websocket, system_instruction, api_key)
    started = await session.start()
    if not started:
        await websocket.close(code=1011)
        return

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message:
                await session.send_audio(message["bytes"])
            elif "text" in message:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("type")
                    if msg_type == "start":
                        logger.info("Received start message from browser")
                    elif msg_type == "audio" and data.get("audio"):
                        audio_bytes = base64.b64decode(data["audio"])
                        await session.send_audio(audio_bytes)
                except Exception:
                    pass
    except WebSocketDisconnect:
        logger.info("Browser disconnected")
    except RuntimeError as e:
        if "disconnect" in str(e).lower():
            logger.info("Browser disconnected (runtime)")
        else:
            logger.error("Runtime error in web call: %s", e)
    except Exception as e:
        logger.error("Error in web call handler: %s", e)
    finally:
        await session.stop()
        try:
            await websocket.close()
        except Exception:
            pass
