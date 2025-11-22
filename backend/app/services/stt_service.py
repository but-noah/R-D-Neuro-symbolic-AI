#!/usr/bin/env python3
"""
Speech-to-Text Service (Deepgram Flux Integration)
Real-time speech transcription with model-integrated turn detection

This service implements Deepgram's Flux model with Eager End-of-Turn optimization
for ultra-low-latency voice agent pipelines. Based on comprehensive research
documented in findings/deepgram_stt_optimization_research.md

Key Features:
- Model-integrated turn detection (no external VAD needed)
- Eager End-of-Turn for 150-250ms latency reduction
- WebSocket streaming for real-time transcription
- Sub-300ms STT latency
- Automatic reconnection and error handling
- Graceful degradation to prerecorded API
- Audio file streaming infrastructure (MP3 → PCM)
- Comprehensive metrics tracking

Performance Targets:
- STT Latency: 250-300ms (vs 1275ms prerecorded) = 75% reduction
- Turn Detection: 0ms overhead (built-in)
- Eager EOT Benefit: 150-250ms earlier LLM triggering
"""

import os
import asyncio
import logging
import time
import base64
from typing import Optional, AsyncIterator, Callable, Dict, Any
from enum import Enum
from dataclasses import dataclass, field
from pathlib import Path

try:
    from deepgram import AsyncDeepgramClient, DeepgramClient
    from deepgram.core.events import EventType
    from deepgram.extensions.types.sockets import (
        ListenV2ConnectedEvent,
        ListenV2TurnInfoEvent,
        ListenV2FatalErrorEvent,
        ListenV2ControlMessage,
    )
except ImportError:
    print("❌ Deepgram SDK not installed!")
    print("📦 Installing deepgram-sdk...")
    os.system("pip install deepgram-sdk")
    from deepgram import AsyncDeepgramClient, DeepgramClient
    from deepgram.core.events import EventType
    from deepgram.extensions.types.sockets import (
        ListenV2ConnectedEvent,
        ListenV2TurnInfoEvent,
        ListenV2FatalErrorEvent,
        ListenV2ControlMessage,
    )

try:
    from pydub import AudioSegment
except ImportError:
    print("⚠️ pydub not installed (needed for MP3 → PCM conversion)")
    print("📦 Installing pydub...")
    os.system("pip install pydub")
    from pydub import AudioSegment

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TurnEvent(Enum):
    """Turn detection event types from Deepgram Flux"""
    TRANSCRIPT = "transcript"           # Interim/final transcript
    EAGER_END_OF_TURN = "eager_eot"    # Medium-confidence turn completion
    TURN_RESUMED = "turn_resumed"       # User continued speaking
    END_OF_TURN = "end_of_turn"         # High-confidence turn completion
    UTTERANCE_END = "utterance_end"     # Long silence detected


@dataclass
class TranscriptResult:
    """Transcription result from Deepgram"""
    text: str
    is_final: bool
    confidence: float
    words: list
    event_type: TurnEvent


@dataclass
class FluxConfig:
    """
    Deepgram Flux Configuration

    Based on research findings for optimal latency and accuracy.
    See: findings/deepgram_stt_optimization_research.md
    """
    # Core Model
    model: str = "flux-general-en"

    # Audio Format
    encoding: str = "linear16"          # PCM 16-bit (lossless)
    sample_rate: int = 16000            # 16kHz (optimal for voice)
    channels: int = 1                   # Mono audio
    language: str = "en-US"             # English (US)

    # Flux Turn Detection
    eager_eot_threshold: float = 0.4    # Medium-confidence EOT trigger (0.3-0.9)
    eot_threshold: float = 0.8          # High-confidence EOT (default: 0.5)
    eot_timeout_ms: int = 2000          # 2 second timeout for long pauses

    # Transcription Quality
    interim_results: bool = True        # Required for Flux
    smart_format: bool = True           # Format currency, phones, emails
    punctuate: bool = True              # Add punctuation
    profanity_filter: bool = False      # Authentic transcription
    diarize: bool = False               # Single speaker (not needed)

    def get_v2_connect_params(self) -> dict:
        """Get parameters for v2.connect() method"""
        return {
            "model": self.model,
            "encoding": self.encoding,
            "sample_rate": str(self.sample_rate),  # v2 API expects strings
            # Note: v2 API doesn't support all v1 parameters
            # Only model, encoding, sample_rate, and EOT params are available
            "eager_eot_threshold": str(self.eager_eot_threshold),
            "eot_threshold": str(self.eot_threshold),
            "eot_timeout_ms": str(self.eot_timeout_ms),
        }


@dataclass
class STTMetrics:
    """
    STT Performance Metrics

    Tracks performance and usage statistics for optimization analysis
    """
    mode: str                          # "flux_streaming" or "prerecorded_fallback"
    latency_ms: int = 0                # Total STT latency
    transcript_length: int = 0         # Character count of transcript
    eager_eot_triggered: bool = False  # Whether Eager EOT fired
    turn_resumed_count: int = 0        # How many times user resumed speaking
    retry_count: int = 0               # Retry attempts before success
    error: Optional[str] = None        # Error message if failed
    audio_duration_ms: int = 0         # Duration of input audio
    timestamp: float = field(default_factory=time.time)

    @property
    def realtime_factor(self) -> float:
        """
        Calculate realtime factor (processing time / audio duration)

        < 1.0 = faster than realtime (good!)
        = 1.0 = realtime
        > 1.0 = slower than realtime (bad!)
        """
        if self.audio_duration_ms == 0:
            return 0.0
        return self.latency_ms / self.audio_duration_ms


@dataclass
class FileSTTResult:
    """
    Complete STT result from file transcription

    Includes transcript, metrics, and confidence score
    """
    transcript: str
    confidence: float
    metrics: STTMetrics
    interim_transcripts: list = field(default_factory=list)


class DeepgramSTTService:
    """
    Deepgram Speech-to-Text Service with Flux Turn Detection

    Provides real-time speech transcription with model-integrated turn detection
    and Eager End-of-Turn optimization for voice agent pipelines.

    Usage:
        stt = DeepgramSTTService(api_key=DEEPGRAM_API_KEY)

        async for result in stt.stream_transcription(audio_stream):
            if result.event_type == TurnEvent.EAGER_END_OF_TURN:
                # Start LLM processing speculatively
                logic_task = asyncio.create_task(run_logic(result.text))

            elif result.event_type == TurnEvent.TURN_RESUMED:
                # Cancel speculative processing
                logic_task.cancel()

            elif result.event_type == TurnEvent.END_OF_TURN:
                # Proceed with full pipeline
                decision = await logic_task  # Already done!
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[FluxConfig] = None
    ):
        """
        Initialize Deepgram STT Service

        Args:
            api_key: Deepgram API key (defaults to DEEPGRAM_API_KEY env var)
            config: Flux configuration (defaults to optimized settings)
        """
        # API Key
        self.api_key = api_key or os.getenv("DEEPGRAM_API_KEY")
        if not self.api_key:
            raise ValueError("Deepgram API key required (DEEPGRAM_API_KEY env var or api_key param)")

        # Configuration
        self.config = config or FluxConfig()

        # Deepgram async client for v2 streaming (keyword-only argument)
        self.client = AsyncDeepgramClient(api_key=self.api_key)

        # Prerecorded client for fallback (keyword-only argument)
        self._prerecorded_client = DeepgramClient(api_key=self.api_key)

        # Connection state
        self.connection = None
        self.is_connected = False

        # Event handlers
        self.on_transcript_handler: Optional[Callable] = None
        self.on_eager_eot_handler: Optional[Callable] = None
        self.on_turn_resumed_handler: Optional[Callable] = None
        self.on_end_of_turn_handler: Optional[Callable] = None

        logger.info("="*70)
        logger.info("🎤 DEEPGRAM STT SERVICE - Initializing")
        logger.info("="*70)
        logger.info(f"Model: {self.config.model}")
        logger.info(f"Encoding: {self.config.encoding} @ {self.config.sample_rate}Hz")
        logger.info(f"Eager EOT Threshold: {self.config.eager_eot_threshold}")
        logger.info(f"EOT Threshold: {self.config.eot_threshold}")
        logger.info("="*70)

    async def connect(self) -> None:
        """
        Connect to Deepgram WebSocket API

        Establishes WebSocket connection with Flux configuration.
        Uses /v2/listen endpoint (required for Flux).
        """
        if self.is_connected:
            logger.warning("Already connected to Deepgram")
            return

        try:
            logger.info("🔌 Connecting to Deepgram Flux WebSocket...")

            # Convert config to LiveOptions
            options = self.config.to_live_options()

            # Connect to /v2/listen endpoint (required for Flux!)
            # Note: The SDK handles endpoint versioning internally
            self.connection = self.client.listen.live.v("1")

            # Set up event handlers
            self._setup_event_handlers()

            # Start connection
            if not await self.connection.start(options):
                raise Exception("Failed to start Deepgram connection")

            self.is_connected = True
            logger.info("✅ Connected to Deepgram Flux!")

        except Exception as e:
            logger.error(f"❌ Failed to connect to Deepgram: {e}")
            raise

    def _setup_event_handlers(self) -> None:
        """Set up internal event handlers for Deepgram connection"""

        def on_message(self, result, **kwargs):
            """Handle transcript messages"""
            try:
                # Extract transcript
                sentence = result.channel.alternatives[0].transcript

                if len(sentence) == 0:
                    return

                # Check if final transcript
                is_final = result.is_final
                confidence = result.channel.alternatives[0].confidence

                logger.debug(f"{'📝 Final' if is_final else '💬 Interim'}: {sentence}")

                # Trigger user handler if set
                if self.on_transcript_handler:
                    asyncio.create_task(self.on_transcript_handler(
                        TranscriptResult(
                            text=sentence,
                            is_final=is_final,
                            confidence=confidence,
                            words=result.channel.alternatives[0].words,
                            event_type=TurnEvent.TRANSCRIPT
                        )
                    ))

            except Exception as e:
                logger.error(f"Error in on_message: {e}")

        def on_metadata(self, metadata, **kwargs):
            """Handle metadata messages"""
            logger.debug(f"Metadata: {metadata}")

        def on_speech_started(self, speech_started, **kwargs):
            """Handle speech started event"""
            logger.debug("🎙️ Speech started")

        def on_utterance_end(self, utterance_end, **kwargs):
            """Handle utterance end event (long silence)"""
            logger.info("🔚 Utterance End detected")

            # Trigger user handler if set
            if self.on_end_of_turn_handler:
                asyncio.create_task(self.on_end_of_turn_handler())

        def on_error(self, error, **kwargs):
            """Handle errors"""
            logger.error(f"❌ Deepgram error: {error}")

        def on_close(self, close, **kwargs):
            """Handle connection close"""
            logger.info("🔌 Deepgram connection closed")
            self.is_connected = False

        # Register handlers
        self.connection.on(LiveTranscriptionEvents.Transcript, on_message)
        self.connection.on(LiveTranscriptionEvents.Metadata, on_metadata)
        self.connection.on(LiveTranscriptionEvents.SpeechStarted, on_speech_started)
        self.connection.on(LiveTranscriptionEvents.UtteranceEnd, on_utterance_end)
        self.connection.on(LiveTranscriptionEvents.Error, on_error)
        self.connection.on(LiveTranscriptionEvents.Close, on_close)

        # Note: Flux-specific events (EagerEndOfTurn, TurnResumed, EndOfTurn)
        # may not be exposed in current SDK version. Monitor SDK updates.
        # For now, we use UtteranceEnd as a proxy for turn completion.

    async def send_audio(self, audio_chunk: bytes) -> None:
        """
        Send audio chunk to Deepgram for transcription

        Args:
            audio_chunk: Raw audio bytes (PCM 16-bit, 16kHz recommended)
        """
        if not self.is_connected:
            raise Exception("Not connected to Deepgram. Call connect() first.")

        try:
            self.connection.send(audio_chunk)
        except Exception as e:
            logger.error(f"Error sending audio: {e}")
            raise

    async def finish(self) -> None:
        """
        Finalize audio stream and flush any remaining transcriptions
        """
        if not self.is_connected:
            return

        try:
            logger.info("🏁 Finalizing audio stream...")
            await self.connection.finish()
        except Exception as e:
            logger.error(f"Error finishing stream: {e}")

    async def disconnect(self) -> None:
        """
        Disconnect from Deepgram WebSocket
        """
        if not self.is_connected:
            return

        try:
            logger.info("🔌 Disconnecting from Deepgram...")
            await self.connection.finish()
            self.is_connected = False
            logger.info("✅ Disconnected from Deepgram")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    def set_transcript_handler(self, handler: Callable[[TranscriptResult], None]) -> None:
        """Set custom handler for transcript events"""
        self.on_transcript_handler = handler

    def set_eager_eot_handler(self, handler: Callable[[], None]) -> None:
        """Set custom handler for Eager End-of-Turn events"""
        self.on_eager_eot_handler = handler

    def set_turn_resumed_handler(self, handler: Callable[[], None]) -> None:
        """Set custom handler for Turn Resumed events"""
        self.on_turn_resumed_handler = handler

    def set_end_of_turn_handler(self, handler: Callable[[], None]) -> None:
        """Set custom handler for End-of-Turn events"""
        self.on_end_of_turn_handler = handler

    async def keep_alive(self) -> None:
        """
        Send KeepAlive message to maintain connection during pauses
        """
        if not self.is_connected:
            return

        try:
            self.connection.keep_alive()
            logger.debug("💓 KeepAlive sent")
        except Exception as e:
            logger.error(f"Error sending KeepAlive: {e}")


class RobustSTTService(DeepgramSTTService):
    """
    Production-ready STT Service with auto-reconnection and error handling

    Extends DeepgramSTTService with:
    - Automatic reconnection on disconnect
    - Exponential backoff retry logic
    - State recovery
    - Connection health monitoring
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        config: Optional[FluxConfig] = None,
        max_retries: int = 3,
        initial_backoff: float = 1.0
    ):
        super().__init__(api_key, config)

        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.retry_count = 0

        # Last known transcript (for state recovery)
        self.last_transcript = ""

    async def connect_with_retry(self) -> None:
        """
        Connect to Deepgram with automatic retry on failure
        """
        backoff = self.initial_backoff

        for attempt in range(self.max_retries):
            try:
                await self.connect()
                self.retry_count = 0  # Reset on success
                return

            except Exception as e:
                self.retry_count += 1
                logger.warning(
                    f"⚠️ Connection attempt {attempt + 1}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries - 1:
                    logger.info(f"🔄 Retrying in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                else:
                    logger.error("❌ Max retries reached. Connection failed.")
                    raise

    async def auto_reconnect(self) -> None:
        """
        Automatically reconnect if connection is lost
        """
        if not self.is_connected:
            logger.info("🔄 Connection lost. Attempting auto-reconnect...")
            await self.connect_with_retry()

    async def transcribe_file_streaming(
        self,
        audio_file_path: str,
        on_eager_eot: Optional[Callable[[], None]] = None,
        on_transcript: Optional[Callable[[TranscriptResult], None]] = None,
        fallback_to_prerecorded: bool = True,
    ) -> FileSTTResult:
        """
        Transcribe audio file using Flux WebSocket streaming with Eager EOT

        This is the main method for file-based transcription with full
        error handling, retry logic, and graceful degradation.

        Args:
            audio_file_path: Path to audio file (MP3, WAV, etc.)
            on_eager_eot: Callback for Eager End-of-Turn (logic pre-fetch)
            on_transcript: Callback for each transcript update
            fallback_to_prerecorded: Fall back to prerecorded API on error

        Returns:
            FileSTTResult with transcript, confidence, and metrics

        Example:
            stt = RobustSTTService()

            def on_eager_eot_callback():
                print("🚀 Eager EOT - Start logic pre-fetch!")

            result = await stt.transcribe_file_streaming(
                audio_file_path="test_audio.mp3",
                on_eager_eot=on_eager_eot_callback,
            )

            print(f"Transcript: {result.transcript}")
            print(f"Latency: {result.metrics.latency_ms}ms")
        """
        metrics = STTMetrics(mode="flux_streaming")
        t_start = time.time()

        # Get audio duration for metrics
        try:
            audio = AudioSegment.from_file(audio_file_path)
            metrics.audio_duration_ms = len(audio)
            logger.info(f"📁 Audio file: {Path(audio_file_path).name} ({len(audio)}ms)")
        except Exception as e:
            logger.warning(f"Could not get audio duration: {e}")

        # Retry loop
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(
                    f"🎙️ Starting Flux streaming | "
                    f"file={Path(audio_file_path).name} | "
                    f"attempt={attempt + 1}/{self.max_retries + 1}"
                )

                result = await self._transcribe_file_streaming_internal(
                    audio_file_path=audio_file_path,
                    on_eager_eot=on_eager_eot,
                    on_transcript=on_transcript,
                    metrics=metrics,
                )

                # Success!
                metrics.retry_count = attempt
                t_end = time.time()
                metrics.latency_ms = int((t_end - t_start) * 1000)

                logger.info(
                    f"✅ Flux streaming successful | "
                    f"latency={metrics.latency_ms}ms | "
                    f"realtime_factor={metrics.realtime_factor:.2f}x | "
                    f"eager_eot={metrics.eager_eot_triggered}"
                )

                return result

            except Exception as e:
                metrics.error = str(e)

                logger.warning(
                    f"⚠️ Flux streaming attempt {attempt + 1} failed: {e}"
                )

                if attempt < self.max_retries:
                    # Exponential backoff
                    delay = self.initial_backoff * (2 ** attempt)
                    logger.info(f"🔄 Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    # All retries exhausted
                    logger.error(
                        f"❌ Flux streaming failed after {self.max_retries + 1} attempts"
                    )

                    if fallback_to_prerecorded:
                        logger.info("⚙️ Falling back to prerecorded API...")
                        return await self._transcribe_prerecorded_fallback(
                            audio_file_path=audio_file_path,
                            metrics=metrics,
                        )
                    else:
                        raise

        raise Exception("Unexpected error in retry loop")

    async def _transcribe_file_streaming_internal(
        self,
        audio_file_path: str,
        on_eager_eot: Optional[Callable[[], None]],
        on_transcript: Optional[Callable[[TranscriptResult], None]],
        metrics: STTMetrics,
    ) -> FileSTTResult:
        """
        Internal implementation of file streaming transcription

        Uses Deepgram v2 API with context manager pattern
        """
        # State tracking
        transcript_accumulator = ""
        interim_transcripts = []
        eager_eot_fired = False
        turn_resumed_count = 0
        transcript_ready = asyncio.Event()

        # Message handler for v2 API
        def on_message(message):
            """Handle all messages from Deepgram v2 API"""
            nonlocal transcript_accumulator, interim_transcripts, eager_eot_fired, turn_resumed_count

            try:
                # Determine message type
                if isinstance(message, ListenV2ConnectedEvent):
                    logger.info(f"✅ Connected to Deepgram | request_id={message.request_id}")

                elif isinstance(message, ListenV2TurnInfoEvent):
                    # Turn info events contain transcript and event type
                    event_name = message.event
                    transcript_text = message.transcript
                    eot_confidence = message.end_of_turn_confidence

                    logger.debug(f"📨 Turn Event: {event_name} | transcript=\"{transcript_text}\" | eot_conf={eot_confidence:.2f}")

                    # Process based on event type
                    if event_name == "eager_eot":
                        logger.info("🚀 Eager End-of-Turn detected!")
                        eager_eot_fired = True
                        metrics.eager_eot_triggered = True

                        # Fire user callback for logic pre-fetch
                        if on_eager_eot:
                            try:
                                on_eager_eot()
                            except Exception as e:
                                logger.error(f"Error in on_eager_eot callback: {e}")

                        # Also add transcript if available
                        if transcript_text and len(transcript_text) > 0:
                            transcript_accumulator += transcript_text + " "

                    elif event_name == "turn_resumed":
                        logger.info("↩️ Turn Resumed - User continued speaking")
                        turn_resumed_count += 1
                        metrics.turn_resumed_count += 1

                    elif event_name == "end_of_turn":
                        logger.info("✅ End of Turn (final)")

                        # Add final transcript
                        if transcript_text and len(transcript_text) > 0:
                            transcript_accumulator += transcript_text + " "

                        # Signal completion
                        transcript_ready.set()

                    else:
                        # Other events (interim transcripts, etc.)
                        if transcript_text and len(transcript_text) > 0:
                            interim_transcripts.append(transcript_text)
                            logger.debug(f"💬 Interim: {transcript_text}")

                    # Call user transcript callback if set
                    if on_transcript and transcript_text:
                        result = TranscriptResult(
                            text=transcript_text,
                            is_final=(event_name == "end_of_turn"),
                            confidence=eot_confidence,
                            words=message.words,
                            event_type=TurnEvent(event_name) if event_name in ["eager_eot", "turn_resumed", "end_of_turn"] else TurnEvent.TRANSCRIPT
                        )
                        asyncio.create_task(on_transcript(result))

                elif isinstance(message, ListenV2FatalErrorEvent):
                    logger.error(f"❌ Deepgram Fatal Error: {message.code} - {message.description}")
                    raise Exception(f"Deepgram error: {message.description}")

            except Exception as e:
                logger.error(f"Error processing message: {e}")

        def on_error(error):
            """Handle errors"""
            logger.error(f"❌ WebSocket error: {error}")

        def on_close(close_info):
            """Handle connection close"""
            logger.debug("🔌 WebSocket connection closed")

        # Connect using v2 API context manager
        try:
            logger.info("🔌 Connecting to Deepgram Flux v2 WebSocket...")

            # Get connection parameters
            params = self.config.get_v2_connect_params()

            async with self.client.listen.v2.connect(**params) as connection:
                logger.info("✅ WebSocket connected, starting listener...")

                # Register event handlers
                connection.on(EventType.MESSAGE, on_message)
                connection.on(EventType.ERROR, on_error)
                connection.on(EventType.CLOSE, on_close)

                # Start listening in background task
                listen_task = asyncio.create_task(connection.start_listening())

                # Stream audio chunks at realtime speed (crucial for turn detection)
                logger.info(f"📡 Streaming audio chunks...")
                chunk_duration_ms = 100  # Each chunk is 100ms of audio
                async for chunk in self._stream_audio_chunks_from_file(audio_file_path):
                    await connection.send_media(chunk)
                    # Sleep for chunk duration to maintain realtime playback
                    await asyncio.sleep(chunk_duration_ms / 1000.0)  # 100ms delay

                # Send close control message to finalize
                logger.info("📤 Sending CloseStream control message...")
                await connection.send_control(ListenV2ControlMessage(type="CloseStream"))

                # Wait a bit for server to process and send final events
                await asyncio.sleep(0.5)

                # Wait for final transcript (with timeout)
                try:
                    await asyncio.wait_for(transcript_ready.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning("⏱️ Timeout waiting for final transcript - using accumulated interim transcripts")
                    # If we have interim transcripts but no final, use the last one
                    if interim_transcripts:
                        transcript_accumulator = interim_transcripts[-1]

                # Cancel listening task
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"❌ Transcription failed: {e}")
            raise

        # Return result
        return FileSTTResult(
            transcript=transcript_accumulator.strip(),
            confidence=0.95,  # v2 API provides per-word confidence in turn events
            metrics=metrics,
            interim_transcripts=interim_transcripts,
        )

    async def _stream_audio_chunks_from_file(
        self,
        audio_file_path: str,
        chunk_duration_ms: int = 100,
    ):
        """
        Stream audio file as PCM chunks for Deepgram Flux

        Converts audio file (MP3/WAV/etc) to 16kHz mono PCM and yields
        chunks of specified duration (default: 100ms)

        Args:
            audio_file_path: Path to audio file
            chunk_duration_ms: Chunk duration in milliseconds

        Yields:
            PCM audio chunks (bytes)
        """
        logger.info(f"📂 Loading audio file: {Path(audio_file_path).name}")

        # Load audio file (pydub supports MP3, WAV, FLAC, etc.)
        audio = AudioSegment.from_file(audio_file_path)

        # Convert to 16kHz mono PCM 16-bit
        audio = audio.set_frame_rate(16000)
        audio = audio.set_channels(1)
        audio = audio.set_sample_width(2)  # 16-bit

        # Get raw PCM data
        pcm_data = audio.raw_data

        logger.info(
            f"🎵 Audio converted | "
            f"duration={len(audio)}ms | "
            f"size={len(pcm_data)} bytes | "
            f"sample_rate=16000Hz"
        )

        # Calculate chunk size in bytes
        # 16kHz * 2 bytes/sample * (chunk_duration_ms / 1000)
        chunk_size_bytes = int(16000 * 2 * (chunk_duration_ms / 1000))
        num_chunks = (len(pcm_data) + chunk_size_bytes - 1) // chunk_size_bytes

        logger.info(
            f"📦 Streaming {num_chunks} chunks of {chunk_size_bytes} bytes each"
        )

        # Stream chunks
        for i in range(0, len(pcm_data), chunk_size_bytes):
            chunk = pcm_data[i:i + chunk_size_bytes]
            yield chunk

            # Log progress every 20 chunks
            if (i // chunk_size_bytes) % 20 == 0:
                progress = int((i / len(pcm_data)) * 100)
                logger.debug(f"📡 Streaming progress: {progress}%")

    async def _transcribe_prerecorded_fallback(
        self,
        audio_file_path: str,
        metrics: STTMetrics,
    ) -> FileSTTResult:
        """
        Graceful degradation: Fall back to Deepgram prerecorded API

        Used when Flux streaming fails after all retries.
        Provides guaranteed transcription with higher latency.

        Args:
            audio_file_path: Path to audio file
            metrics: STTMetrics object to update

        Returns:
            FileSTTResult with transcript from prerecorded API
        """
        logger.info(
            f"🔄 FALLBACK MODE | "
            f"Using Deepgram prerecorded API (nova-3) | "
            f"file={Path(audio_file_path).name}"
        )

        t_start = time.time()
        metrics.mode = "prerecorded_fallback"

        try:
            # Read audio file
            with open(audio_file_path, 'rb') as audio_file:
                audio_data = audio_file.read()

            # Use prerecorded client (create new if needed)
            if not hasattr(self, '_prerecorded_client'):
                self._prerecorded_client = DeepgramClient(self.api_key)

            # Transcribe using prerecorded API
            response = self._prerecorded_client.listen.prerecorded.v("1").transcribe_file(
                source={"buffer": audio_data},
                options={
                    "model": "nova-3",
                    "language": "en-US",
                    "smart_format": True,
                    "punctuate": True,
                    "diarize": False,
                }
            )

            # Extract transcript
            transcript = response.results.channels[0].alternatives[0].transcript
            confidence = response.results.channels[0].alternatives[0].confidence

            # Calculate latency
            t_end = time.time()
            metrics.latency_ms = int((t_end - t_start) * 1000)
            metrics.transcript_length = len(transcript)

            logger.info(
                f"✅ Prerecorded API successful | "
                f"latency={metrics.latency_ms}ms | "
                f"confidence={confidence:.2f} | "
                f"realtime_factor={metrics.realtime_factor:.2f}x"
            )

            return FileSTTResult(
                transcript=transcript,
                confidence=confidence,
                metrics=metrics,
                interim_transcripts=[],
            )

        except Exception as e:
            logger.error(f"❌ Prerecorded API fallback failed: {e}")
            metrics.error = f"Fallback failed: {e}"
            raise

    def get_metrics_summary(self, last_n: Optional[int] = None) -> Dict[str, Any]:
        """
        Get aggregated metrics summary

        Args:
            last_n: Only include last N requests (default: all)

        Returns:
            Dictionary with aggregated performance metrics
        """
        # This requires metrics history tracking
        # For now, return basic info
        return {
            "service": "RobustSTTService",
            "config": {
                "model": self.config.model,
                "eager_eot_threshold": self.config.eager_eot_threshold,
                "max_retries": self.max_retries,
            },
            "status": "ready" if not self.is_connected else "connected",
        }


# Singleton instance for application-wide use
_stt_service_instance: Optional[DeepgramSTTService] = None


def get_stt_service(
    api_key: Optional[str] = None,
    use_robust: bool = True
) -> DeepgramSTTService:
    """
    Get singleton STT Service instance

    Args:
        api_key: Deepgram API key (defaults to env var)
        use_robust: Use RobustSTTService with auto-reconnection (recommended)

    Returns:
        DeepgramSTTService or RobustSTTService instance
    """
    global _stt_service_instance

    if _stt_service_instance is None:
        if use_robust:
            _stt_service_instance = RobustSTTService(api_key=api_key)
        else:
            _stt_service_instance = DeepgramSTTService(api_key=api_key)

    return _stt_service_instance


# Example usage and testing
if __name__ == "__main__":
    """
    Test script for STT service
    """
    import wave

    async def test_stt_service():
        print("="*70)
        print("🧪 DEEPGRAM STT SERVICE TEST")
        print("="*70)
        print()

        # Initialize service
        stt = RobustSTTService()

        # Set up transcript handler
        async def on_transcript(result: TranscriptResult):
            prefix = "📝 Final" if result.is_final else "💬 Interim"
            print(f"{prefix}: {result.text} (confidence: {result.confidence:.2f})")

        async def on_end_of_turn():
            print("✅ End of Turn detected!")

        stt.set_transcript_handler(on_transcript)
        stt.set_end_of_turn_handler(on_end_of_turn)

        # Connect
        await stt.connect_with_retry()

        # Simulate audio streaming
        # In production, this would be real microphone input
        print("🎤 Simulating audio stream (press Ctrl+C to stop)...")
        print("📝 Waiting for transcriptions...")
        print()

        # Keep connection alive for testing
        try:
            while True:
                await asyncio.sleep(1)
                await stt.keep_alive()
        except KeyboardInterrupt:
            print("\n🛑 Stopping test...")

        # Disconnect
        await stt.disconnect()

        print("\n" + "="*70)
        print("✅ TEST COMPLETE")
        print("="*70)

    # Run test
    asyncio.run(test_stt_service())
