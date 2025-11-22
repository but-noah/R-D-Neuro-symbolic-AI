"""
Test Voice Pipeline WebSocket Endpoint
Real-time voice pipeline testing with live updates

This endpoint enables testing the complete voice pipeline with:
- Mock STT (realistic delays, pre-defined transcripts)
- REAL Emotion Detection (OpenAI API)
- REAL Filler Selection (memory-cached audio)
- REAL Rules Engine (test orders database)
- REAL Response Generation (OpenAI API)

Flow:
1. Client selects test audio file
2. Server streams updates for each phase:
   - STT transcript
   - Emotion detection
   - Filler selection
   - Logic execution
   - Response generation
   - Performance metrics
"""

import os
import asyncio
import time
import base64
import re
from typing import Dict, Any
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from openai import AsyncOpenAI

# Import our services
from app.services.filler_loader import get_filler_loader
from app.services.rules_engine import check_refund_eligibility_with_order_id

router = APIRouter()

# Initialize OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# Pre-defined transcripts for test files (from generate_test_queries.py)
MOCK_TRANSCRIPTS = {
    "neutral_test_001.mp3": "Hi, I'm calling about a refund for order number 12345. I received the wrong item and would like to return it. Can you help me with this?",
    "neutral_test_002.mp3": "Hello, I ordered a product last week but it hasn't arrived yet. Could you check the status of my delivery? The order number is 67890.",
    "neutral_test_003.mp3": "Good morning, I'd like to request a refund for a purchase I made. The product doesn't quite meet my needs. What's the process for returning it?",

    "angry_medium_test_001.mp3": "Look, I've been waiting three weeks for my refund for order 12345 and I still haven't received it. This is getting really frustrating. I was promised it would be processed within five business days. Can someone please tell me what's going on?",
    "angry_medium_test_002.mp3": "I'm pretty upset about this situation with order 67890. The item I received is damaged and I've already contacted support twice. Nobody seems to be helping me. I just want my money back or a replacement.",
    "angry_medium_test_003.mp3": "This is the second time I'm calling about order 11111. I was told last week that my refund would be processed, but nothing happened. I'm starting to lose patience here. When exactly will I get my refund?",

    "angry_high_test_001.mp3": "This is absolutely unacceptable! I've been waiting over a month for my refund for order 12345 and I keep getting the runaround! Every time I call, I get a different excuse. I want my money back RIGHT NOW or I'm filing a complaint with consumer protection!",
    "angry_high_test_002.mp3": "I am EXTREMELY frustrated with your service! The product from order 22222 arrived broken, your support team has been completely unhelpful, and now you're telling me I can't get a refund?! This is ridiculous! I demand to speak to a manager immediately!",
    "angry_high_test_003.mp3": "I have had it with your company! This is the FOURTH time I'm calling about this refund for order 77777! I've wasted hours on hold, been transferred multiple times, and STILL no resolution! Either you process my refund today or I'm taking legal action!",
}


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
        order_details = decision.get("order_details", {})
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
    order_details = decision.get("order_details", {})
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
            # PHASE 1: Speech-to-Text (Mock with realistic delay)
            # ================================================================
            print("  Phase 1: STT...")
            t_stt_start = time.time()

            # Simulate STT latency (300ms realistic for Deepgram)
            await asyncio.sleep(0.3)

            # Get transcript from mock database
            transcript = MOCK_TRANSCRIPTS.get(
                audio_file,
                "Test query for voice pipeline testing."
            )

            t_stt_end = time.time()
            stt_latency = int((t_stt_end - t_stt_start) * 1000)

            # Send STT result with timing
            await websocket.send_json({
                "type": "stt",
                "transcript": transcript,
                "latency": stt_latency,
                "method": "mock_realistic",
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
                "type": "response",
                **response,
                "timestamp": t_response_end,
                "emotion_used": emotion_for_response["method"]
            })

            # ================================================================
            # PHASE 6: Performance Metrics
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
