"""
Test Voice Pipeline WebSocket Endpoint
Real-time voice pipeline testing with live updates

This endpoint enables testing the complete voice pipeline with:
- REAL Deepgram STT (pre-recorded test audio files)
- REAL Emotion Detection (hybrid: fast keyword + parallel LLM)
- REAL Filler Selection (memory-cached audio)
- REAL Rules Engine (test orders database)
- REAL Response Generation (OpenAI API)
- REAL Cartesia TTS (text-to-speech)

Flow:
1. Client selects test audio file
2. Server loads MP3 and sends to Deepgram for transcription
3. Partial results trigger pipeline early
4. Server streams updates for each phase:
   - STT transcript (partial + final)
   - Emotion detection (fast + LLM)
   - Filler selection + audio
   - Logic execution
   - Response generation + TTS audio
   - Performance metrics
"""

import os
import asyncio
import time
import base64
import re
import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI
from deepgram import DeepgramClient
from cartesia import AsyncCartesia

# Import our services
from app.services.filler_loader import get_filler_loader
from app.services.rules_engine import check_refund_eligibility_with_order_id
from app.services.stt_service import RobustSTTService, FileSTTResult

router = APIRouter()

# Initialize API clients
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None
deepgram_client = DeepgramClient(api_key=DEEPGRAM_API_KEY) if DEEPGRAM_API_KEY else None  # Keep for fallback (keyword arg!)
cartesia_client = AsyncCartesia(api_key=CARTESIA_API_KEY) if CARTESIA_API_KEY else None

# Initialize Flux STT service (v2 streaming with Eager EOT)
flux_stt_service = RobustSTTService() if DEEPGRAM_API_KEY else None

# Cartesia voice configuration
CARTESIA_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"  # Conversational English voice
CARTESIA_MODEL = "sonic-english"

# Cartesia WebSocket connection (reusable)
cartesia_ws = None

# Test audio directory
TEST_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "test_audio")


async def detect_emotion_real(transcript: str) -> Dict[str, Any]:
    """
    REAL emotion detection using OpenAI API

    Args:
        transcript: User transcript to analyze

    Returns:
        Dict with anger score and emotion category
    """
    if not openai_client:
        # Fallback to keyword-based if no API key
        return detect_emotion_mock(transcript)

    t_start = time.time()

    try:
        # Call OpenAI API for sentiment analysis
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": """You are an emotion detection system for customer service.
                    Analyze the customer's message and determine their anger level on a scale from 0.0 to 1.0.

                    Anger levels:
                    - 0.0-0.3: Calm, polite, neutral
                    - 0.3-0.7: Frustrated, annoyed, impatient
                    - 0.7-1.0: Very angry, furious, threatening

                    Respond with ONLY a JSON object in this exact format:
                    {"anger": 0.85, "sentiment": "negative", "keywords": ["unacceptable", "frustrated"]}
                    """
                },
                {
                    "role": "user",
                    "content": f"Analyze this customer message:\n\n{transcript}"
                }
            ],
            temperature=0.0,
        )

        # Parse response
        import json
        result_text = response.choices[0].message.content.strip()

        # Extract JSON if wrapped in markdown
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0].strip()

        result = json.loads(result_text)

        anger = result.get("anger", 0.5)
        sentiment = result.get("sentiment", "neutral")

        # Map anger to emotion category
        if anger > 0.7:
            category = "angry_high"
        elif anger >= 0.3:
            category = "angry_medium"
        else:
            category = "calm"

        t_end = time.time()
        latency = int((t_end - t_start) * 1000)

        return {
            "anger": anger,
            "sentiment": sentiment,
            "category": category,
            "keywords": result.get("keywords", []),
            "latency": latency,
            "method": "openai_gpt4_mini"
        }

    except Exception as e:
        print(f"Error in emotion detection: {e}")
        # Fallback to mock
        return detect_emotion_mock(transcript)


def detect_emotion_keyword(transcript: str) -> Dict[str, Any]:
    """
    FAST keyword-based emotion detection for TTRS optimization

    This is used for immediate filler selection to meet TTRS < 840ms target.
    Achieves < 1ms latency with ~75-80% accuracy.

    A more accurate LLM-based emotion detection runs in parallel for
    response generation quality.
    """
    t_start = time.time()
    text_lower = transcript.lower()

    # High anger keywords (very upset, threatening, demanding)
    high_anger_keywords = [
        "unacceptable", "extremely", "furious", "ridiculous", "disgusted",
        "demand", "complaint", "legal action", "manager", "supervisor",
        "had it", "fourth time", "right now", "immediately", "absolutely",
        "worst", "terrible", "horrible", "pathetic", "incompetent"
    ]

    # Medium anger keywords (frustrated, annoyed, impatient)
    medium_anger_keywords = [
        "frustrated", "upset", "annoyed", "disappointed", "unhappy",
        "losing patience", "still haven't", "waiting", "weeks",
        "promised", "second time", "third time", "pretty upset",
        "nobody seems", "not helping", "no response", "ignored"
    ]

    # Calm/neutral keywords (positive indicators)
    calm_keywords = [
        "please", "thank you", "could you", "would you", "help",
        "appreciate", "understand", "sorry", "excuse me"
    ]

    # Count keyword matches
    high_anger_count = sum(1 for keyword in high_anger_keywords if keyword in text_lower)
    medium_anger_count = sum(1 for keyword in medium_anger_keywords if keyword in text_lower)
    calm_count = sum(1 for keyword in calm_keywords if keyword in text_lower)

    # Determine anger level with refined thresholds
    if high_anger_count >= 2:
        anger = 0.85
        category = "angry_high"
    elif high_anger_count >= 1:
        anger = 0.75
        category = "angry_high"
    elif medium_anger_count >= 3:
        anger = 0.65
        category = "angry_medium"
    elif medium_anger_count >= 1:
        anger = 0.45
        category = "angry_medium"
    elif calm_count >= 2:
        anger = 0.1
        category = "calm"
    else:
        anger = 0.2
        category = "calm"

    t_end = time.time()
    latency = int((t_end - t_start) * 1000)

    return {
        "anger": anger,
        "sentiment": "negative" if anger > 0.3 else "neutral",
        "category": category,
        "keywords": [],
        "latency": latency,
        "method": "keyword_fast"
    }


def extract_order_id(transcript: str) -> str | None:
    """
    Extract order ID from transcript

    Looks for patterns like:
    - "order number 12345"
    - "order 12345"
    - "order ID 12345"
    """
    # Pattern: "order (number|id)? 12345"
    patterns = [
        r"order\s+(?:number|id|#)?\s*(\d+)",
        r"order\s+(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, transcript, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


async def generate_response_real(
    transcript: str,
    decision: Dict[str, Any],
    emotion: Dict[str, Any]
) -> Dict[str, Any]:
    """
    REAL response generation using OpenAI API

    Args:
        transcript: Original user query
        decision: Refund decision from rules engine
        emotion: Emotion detection results

    Returns:
        Dict with generated response text and latency
    """
    if not openai_client:
        # Fallback to mock
        return generate_response_mock(decision, emotion)

    t_start = time.time()

    try:
        # Build system prompt based on emotion
        if emotion["anger"] > 0.7:
            tone = "extremely empathetic and apologetic, focused on immediate de-escalation"
        elif emotion["anger"] > 0.3:
            tone = "empathetic and professional, acknowledging frustration"
        else:
            tone = "friendly and helpful"

        # Build context
        order_details = decision.get("order_details") or {}
        product_name = order_details.get("product_name", "your order")

        system_prompt = f"""You are a customer service agent for an e-commerce company.
        The customer's tone is {tone}.

        IMPORTANT RULES:
        1. Be {tone} in your response
        2. Address the customer's specific situation
        3. Clearly state the refund decision
        4. If approved: explain next steps and timeline
        5. If denied: explain why and offer alternatives
        6. Keep response concise (3-4 sentences max)
        7. Never make promises you can't keep
        """

        # Build user prompt
        user_prompt = f"""Customer message: "{transcript}"

        Refund Decision:
        - Approved: {decision['allowed']}
        - Amount: ${decision['amount']:.2f}
        - Reason: {decision['reason']}
        - Product: {product_name}

        Generate a response to the customer."""

        # Call OpenAI API
        response = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=200,
        )

        response_text = response.choices[0].message.content.strip()

        t_end = time.time()
        latency = int((t_end - t_start) * 1000)

        return {
            "text": response_text,
            "latency": latency,
            "method": "openai_gpt4_mini"
        }

    except Exception as e:
        print(f"Error in response generation: {e}")
        # Fallback to mock
        return generate_response_mock(decision, emotion)


def generate_response_mock(decision: Dict[str, Any], emotion: Dict[str, Any]) -> Dict[str, Any]:
    """Mock response generation (fallback)"""
    order_details = decision.get("order_details") or {}
    product_name = order_details.get("product_name", "your product")
    amount = decision["amount"]

    if decision["allowed"]:
        if emotion["anger"] > 0.7:
            text = f"I completely understand your frustration, and I sincerely apologize for the delay. I've reviewed your case immediately, and I can confirm that you are eligible for a full refund of ${amount:.2f}. I'm processing this right away and you'll see the refund in your account within 2-3 business days."
        elif emotion["anger"] > 0.3:
            text = f"I understand your concern, and I appreciate your patience. I've checked your order, and you are eligible for a refund of ${amount:.2f}. I'll process this for you right away. You should see the refund within 5 business days."
        else:
            text = f"Thank you for contacting us. I've reviewed your request, and I can confirm that you're eligible for a refund of ${amount:.2f}. I'll go ahead and process that for you. You can expect to see the refund in your account within 5-7 business days."
    else:
        text = f"I understand your situation. Unfortunately, {decision['reason']}. I apologize for any inconvenience. Is there anything else I can help you with today?"

    return {
        "text": text,
        "latency": 1,
        "method": "template_mock"
    }


async def transcribe_audio_file(
    audio_file_path: str,
    websocket: Optional[WebSocket] = None
) -> Dict[str, Any]:
    """
    Transcribe audio file using Deepgram Flux Streaming API

    Now uses Flux v2 streaming with Eager End-of-Turn for ultra-low latency.
    Expected latency: 300-400ms (vs 1275ms with Nova-3 prerecorded)

    Args:
        audio_file_path: Path to audio file (MP3)
        websocket: Optional WebSocket for streaming interim transcripts

    Returns:
        Dict with transcript and latency
    """
    if not flux_stt_service:
        return {
            "transcript": "",
            "latency": 0,
            "method": "unavailable",
            "error": "Flux STT service not available"
        }

    t_start = time.time()

    try:
        # Interim transcript callback for WebSocket streaming
        async def on_interim_transcript(result):
            if websocket and not result.is_final:
                await websocket.send_json({
                    "type": "stt_interim",
                    "transcript": result.text,
                    "confidence": result.confidence,
                    "timestamp": time.time()
                })

        # Transcribe using Flux streaming
        result: FileSTTResult = await flux_stt_service.transcribe_file_streaming(
            audio_file_path=audio_file_path,
            on_transcript=on_interim_transcript,
            fallback_to_prerecorded=True,  # Graceful degradation to Nova-3
        )

        t_end = time.time()

        # Note: result.metrics.latency_ms includes full streaming time
        # For pipeline integration, we use actual wall-clock time
        actual_latency = int((t_end - t_start) * 1000)

        print(f"  ✅ Flux STT: '{result.transcript}' ({actual_latency}ms, mode={result.metrics.mode})")

        return {
            "transcript": result.transcript,
            "latency": actual_latency,
            "method": f"deepgram_{result.metrics.mode}",
            "confidence": result.confidence,
            "metrics": {
                "mode": result.metrics.mode,
                "eager_eot_triggered": result.metrics.eager_eot_triggered,
                "turn_resumed_count": result.metrics.turn_resumed_count,
                "realtime_factor": result.metrics.realtime_factor,
                "audio_duration_ms": result.metrics.audio_duration_ms,
            }
        }

    except Exception as e:
        print(f"❌ Error in Flux STT transcription: {e}")
        import traceback
        traceback.print_exc()
        return {
            "transcript": "",
            "latency": 0,
            "method": "error",
            "error": str(e)
        }


async def synthesize_speech_streaming(text: str, websocket: WebSocket, emotion_category: str):
    """
    Convert text to speech using Cartesia WebSocket TTS with real-time streaming

    Args:
        text: Text to synthesize
        websocket: WebSocket connection to stream audio chunks
        emotion_category: "calm", "angry_medium", or "angry_high"
    """
    if not cartesia_client:
        print("⚠️  Cartesia client not available")
        await websocket.send_json({
            "type": "tts_error",
            "error": "Cartesia client not available"
        })
        return

    t_start = time.time()
    first_chunk_time = None
    chunk_count = 0
    total_bytes = 0

    try:
        print(f"  📡 Starting Cartesia WebSocket TTS stream...", flush=True)

        # Initialize WebSocket connection (await the coroutine)
        ws = await cartesia_client.tts.websocket()

        # Send TTS request and get the streaming generator
        output_generate = await ws.send(
            model_id=CARTESIA_MODEL,
            transcript=text,
            voice={"mode": "id", "id": CARTESIA_VOICE_ID},
            stream=True,
            output_format={
                "container": "raw",
                "encoding": "pcm_s16le",  # 16-bit PCM
                "sample_rate": 22050,
            },
            language="en",
        )

        # Stream audio chunks
        async for chunk in output_generate:
            if chunk_count == 0:
                first_chunk_time = time.time()
                ttfb = int((first_chunk_time - t_start) * 1000)
                print(f"  ⚡ First chunk received: {ttfb}ms (TTFB)", flush=True)

            # Get audio data from chunk
            audio_data = chunk.get("audio") if isinstance(chunk, dict) else getattr(chunk, "audio", None)

            if audio_data:
                chunk_bytes = len(audio_data)
                total_bytes += chunk_bytes
                chunk_count += 1

                # Convert raw PCM bytes to base64 for transmission
                audio_b64 = base64.b64encode(audio_data).decode('utf-8')

                # Stream chunk to frontend
                await websocket.send_json({
                    "type": "tts_chunk",
                    "audio_b64": audio_b64,
                    "chunk_number": chunk_count,
                    "chunk_size": chunk_bytes,
                    "encoding": "pcm_s16le",
                    "sample_rate": 22050,
                })

        # Close the Cartesia WebSocket
        ws.close()

        t_end = time.time()
        total_latency = int((t_end - t_start) * 1000)
        ttfb = int((first_chunk_time - t_start) * 1000) if first_chunk_time else 0

        print(f"  ✅ TTS stream complete: {chunk_count} chunks, {total_bytes} bytes", flush=True)
        print(f"     TTFB: {ttfb}ms, Total: {total_latency}ms", flush=True)

        # Send completion signal
        await websocket.send_json({
            "type": "tts_complete",
            "chunk_count": chunk_count,
            "total_bytes": total_bytes,
            "ttfb": ttfb,
            "total_latency": total_latency,
        })

        # Return latency metrics for pipeline metrics tracking
        return total_latency

    except Exception as e:
        print(f"  ❌ Error in TTS streaming: {e}", flush=True)
        import traceback
        traceback.print_exc()
        await websocket.send_json({
            "type": "tts_error",
            "error": str(e)
        })
        return 0  # Return 0 on error


@router.websocket("/ws/test-voice")
async def test_voice_websocket(websocket: WebSocket):
    """
    Test Voice Pipeline WebSocket Endpoint

    Protocol:
    1. Client sends: {"audio_file": "angry_high_test_001.mp3"}
    2. Server streams JSON updates:
       - {"type": "stt", "transcript": "...", "latency": 301}
       - {"type": "emotion", "anger": 0.85, "category": "angry_high", ...}
       - {"type": "filler", "category": "angry_high", "audio_b64": "...", ...}
       - {"type": "logic", "order": {...}, "decision": {...}, ...}
       - {"type": "response", "text": "...", ...}
       - {"type": "metrics", "ttrs": 305, "total": 2134, ...}
    """
    await websocket.accept()
    print("🔌 Test voice client connected")

    try:
        while True:
            # Receive request from client
            data = await websocket.receive_json()
            audio_file = data.get("audio_file")

            if not audio_file:
                await websocket.send_json({
                    "type": "error",
                    "message": "No audio_file specified"
                })
                continue

            print(f"🎤 Testing pipeline with: {audio_file}")

            # Track overall timing
            t_pipeline_start = time.time()
            t_ttrs_start = t_pipeline_start

            # ================================================================
            # PHASE 1: Speech-to-Text (REAL Deepgram!)
            # ================================================================
            print("  Phase 1: STT (Deepgram)...")
            t_stt_start = time.time()

            # Build path to audio file
            audio_file_path = os.path.join(TEST_AUDIO_DIR, audio_file)

            if not os.path.exists(audio_file_path):
                await websocket.send_json({
                    "type": "error",
                    "message": f"Audio file not found: {audio_file}"
                })
                continue

            # Transcribe with Deepgram Flux (with interim transcript streaming)
            stt_result = await transcribe_audio_file(audio_file_path, websocket=websocket)

            if stt_result.get("error"):
                await websocket.send_json({
                    "type": "error",
                    "message": f"STT error: {stt_result['error']}"
                })
                continue

            transcript = stt_result["transcript"]
            stt_latency = stt_result["latency"]

            # Send STT result with timing and Flux metrics
            await websocket.send_json({
                "type": "stt",
                "transcript": transcript,
                "latency": stt_latency,
                "method": stt_result["method"],
                "confidence": stt_result.get("confidence", 0),
                "metrics": stt_result.get("metrics", {}),  # Flux metrics (EOT, mode, etc.)
                "timestamp": time.time()
            })

            # ================================================================
            # PHASE 2A: FAST Emotion Detection (Keyword-based for TTRS!)
            # ================================================================
            print("  Phase 2A: FAST Emotion Detection (Keyword)...")
            t_emotion_fast_start = time.time()

            emotion_fast = detect_emotion_keyword(transcript)

            t_emotion_fast_end = time.time()

            # Send fast emotion result
            await websocket.send_json({
                "type": "emotion",
                **emotion_fast,
                "timestamp": t_emotion_fast_end,
                "note": "Fast keyword-based for TTRS optimization"
            })

            # ================================================================
            # PHASE 2B: ACCURATE Emotion Detection (LLM - Parallel!)
            # ================================================================
            print("  Phase 2B: Starting LLM Emotion Detection (Parallel)...")
            # Start LLM emotion detection in background (don't await yet!)
            emotion_llm_task = asyncio.create_task(detect_emotion_real(transcript))

            # ================================================================
            # PHASE 3: Filler Selection (REAL - Memory cached!)
            # ================================================================
            print("  Phase 3: Filler Selection (REAL)...")
            t_filler_start = time.time()

            filler_loader = get_filler_loader()
            filler_category = emotion_fast["category"]  # Use FAST emotion!
            filler_audio = filler_loader.get_filler(filler_category)

            t_filler_end = time.time()
            filler_latency = (t_filler_end - t_filler_start) * 1000

            # Encode audio as base64 for transmission
            filler_b64 = base64.b64encode(filler_audio).decode('utf-8')

            await websocket.send_json({
                "type": "filler",
                "category": filler_category,
                "audio_b64": filler_b64,
                "size_kb": len(filler_audio) / 1024,
                "latency": filler_latency,
                "timestamp": t_filler_end
            })

            # Calculate TTRS (Time-To-Respond-Start)
            t_ttrs = time.time()
            ttrs = int((t_ttrs - t_ttrs_start) * 1000)

            # Send TTRS update
            await websocket.send_json({
                "type": "ttrs_update",
                "ttrs": ttrs,
                "ttrs_met": ttrs < 840,
                "timestamp": t_ttrs
            })

            # ================================================================
            # PHASE 4: Logic Execution (REAL - Rules Engine!)
            # ================================================================
            print("  Phase 4: Logic Execution (REAL)...")
            t_logic_start = time.time()

            # Extract order ID from transcript
            order_id = extract_order_id(transcript)

            if order_id:
                # Check refund eligibility with test orders
                decision = check_refund_eligibility_with_order_id(order_id, "defective")
            else:
                decision = {
                    "allowed": False,
                    "amount": 0.0,
                    "reason": "Could not identify order number in transcript",
                    "order_details": None
                }

            t_logic_end = time.time()
            logic_latency = int((t_logic_end - t_logic_start) * 1000)

            await websocket.send_json({
                "type": "logic",
                "decision": {
                    "allowed": decision["allowed"],
                    "amount": decision["amount"],
                    "reason": decision["reason"]
                },
                "order_details": decision["order_details"],
                "latency": logic_latency,
                "timestamp": t_logic_end
            })

            # ================================================================
            # PHASE 5: Response Generation (REAL - OpenAI API!)
            # ================================================================
            print("  Phase 5: Response Generation (REAL)...")
            t_response_start = time.time()

            # Wait for LLM emotion detection to complete (runs during logic phase!)
            print("  Waiting for LLM emotion detection to complete...")
            try:
                emotion_llm = await asyncio.wait_for(emotion_llm_task, timeout=5.0)
                print(f"  ✅ Using LLM emotion (anger: {emotion_llm['anger']:.2f})")
                emotion_for_response = emotion_llm

                # Send LLM emotion update (for frontend display)
                await websocket.send_json({
                    "type": "emotion_llm_update",
                    **emotion_llm,
                    "note": "Accurate LLM-based emotion (used for response)"
                })
            except asyncio.TimeoutError:
                print("  ⚠️  LLM emotion timeout, using keyword emotion")
                emotion_for_response = emotion_fast

            # Generate response with best available emotion
            response = await generate_response_real(transcript, decision, emotion_for_response)

            t_response_end = time.time()

            await websocket.send_json({
                "type": "response_text",
                **response,
                "timestamp": t_response_end,
                "emotion_used": emotion_for_response["method"]
            })

            # ================================================================
            # PHASE 6: Text-to-Speech (REAL - Cartesia WebSocket Streaming!)
            # ================================================================
            print("  Phase 6: Text-to-Speech (Cartesia WebSocket Streaming)...", flush=True)

            # Stream TTS audio in real-time and capture latency
            tts_latency = await synthesize_speech_streaming(
                response["text"],
                websocket,
                emotion_for_response["category"]
            )

            # ================================================================
            # PHASE 7: Performance Metrics
            # ================================================================
            t_pipeline_end = time.time()
            total_latency = int((t_pipeline_end - t_pipeline_start) * 1000)

            await websocket.send_json({
                "type": "metrics",
                "ttrs": ttrs,
                "stt_latency": stt_latency,
                "emotion_latency": emotion_fast["latency"],
                "filler_latency": round(filler_latency, 2),
                "logic_latency": logic_latency,
                "response_latency": response["latency"],
                "tts_latency": tts_latency,
                "total_latency": total_latency,
                "ttrs_target": 840,
                "ttrs_met": ttrs < 840
            })

            print(f"  ✅ Pipeline complete: TTRS={ttrs}ms, Total={total_latency}ms")

    except WebSocketDisconnect:
        print("🔌 Test voice client disconnected")
    except Exception as e:
        print(f"❌ Error in test voice pipeline: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
