#!/usr/bin/env python3
"""
Voice Pipeline Test Script
Tests the complete voice pipeline: STT → Emotion Detection → Filler Selection → TTS

This script simulates the full voice agent flow using pre-generated test audio:
1. Load test audio file (simulated user query with emotion)
2. Transcribe using Deepgram STT
3. Detect emotion from transcript
4. Select appropriate filler based on emotion
5. Play filler audio
6. Run neuro-symbolic logic
7. Generate and synthesize response

Usage:
    python scripts/test_voice_pipeline.py
    python scripts/test_voice_pipeline.py --emotion angry_high
    python scripts/test_voice_pipeline.py --file test_audio/angry_high_test_001.mp3
"""

import os
import sys
import asyncio
import argparse
import time
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

# Import our services
from app.services.filler_loader import get_filler_loader
# Note: STT service would be imported here when ready
# from app.services.stt_service import get_stt_service

# Configuration
TEST_AUDIO_DIR = Path(__file__).parent.parent / "test_audio"
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")


class MockEmotionDetector:
    """
    Mock emotion detector for testing

    In production, this would analyze the transcript to detect emotion.
    For testing, we use the expected emotion from the test file metadata.
    """

    @staticmethod
    def detect_from_transcript(transcript: str) -> dict:
        """
        Detect emotion from transcript

        This is a simple keyword-based detector for testing.
        In production, this would use the actual empathy_engine.py
        """
        # Convert to lowercase for matching
        text_lower = transcript.lower()

        # High anger keywords
        high_anger_keywords = [
            "unacceptable", "extremely", "furious", "ridiculous",
            "demand", "complaint", "legal action", "manager",
            "had it", "fourth time", "right now"
        ]

        # Medium anger keywords
        medium_anger_keywords = [
            "frustrated", "upset", "losing patience", "still haven't",
            "promised", "second time", "pretty upset", "nobody seems"
        ]

        # Count keyword matches
        high_anger_count = sum(1 for keyword in high_anger_keywords if keyword in text_lower)
        medium_anger_count = sum(1 for keyword in medium_anger_keywords if keyword in text_lower)

        # Determine anger level
        if high_anger_count >= 2:
            anger = 0.85
            emotion = "angry_high"
        elif high_anger_count >= 1 or medium_anger_count >= 2:
            anger = 0.55
            emotion = "angry_medium"
        elif medium_anger_count >= 1:
            anger = 0.4
            emotion = "angry_medium"
        else:
            anger = 0.15
            emotion = "calm"

        return {
            "anger": anger,
            "emotion_category": emotion,
            "sentiment": "negative" if anger > 0.3 else "neutral"
        }


class MockDeepgramSTT:
    """
    Mock Deepgram STT for testing without API calls

    In production, this would be replaced with the real DeepgramSTTService.
    For testing, we return pre-defined transcripts based on the test file.
    """

    # Pre-defined transcripts for test files
    TRANSCRIPTS = {
        "neutral_test_001.mp3": "Hi, I'm calling about a refund for order number 12345. I received the wrong item and would like to return it. Can you help me with this?",
        "neutral_test_002.mp3": "Hello, I ordered a product last week but it hasn't arrived yet. Could you check the status of my delivery? The order number is 67890.",
        "neutral_test_003.mp3": "Good morning, I'd like to request a refund for a purchase I made. The product doesn't quite meet my needs. What's the process for returning it?",

        "angry_medium_test_001.mp3": "Look, I've been waiting three weeks for my refund and I still haven't received it. This is getting really frustrating. I was promised it would be processed within five business days. Can someone please tell me what's going on?",
        "angry_medium_test_002.mp3": "I'm pretty upset about this situation. The item I received is damaged and I've already contacted support twice. Nobody seems to be helping me. I just want my money back or a replacement.",
        "angry_medium_test_003.mp3": "This is the second time I'm calling about the same issue. I was told last week that my refund would be processed, but nothing happened. I'm starting to lose patience here. When exactly will I get my refund?",

        "angry_high_test_001.mp3": "This is absolutely unacceptable! I've been waiting over a month for my refund and I keep getting the runaround! Every time I call, I get a different excuse. I want my money back RIGHT NOW or I'm filing a complaint with consumer protection!",
        "angry_high_test_002.mp3": "I am EXTREMELY frustrated with your service! The product arrived broken, your support team has been completely unhelpful, and now you're telling me I can't get a refund?! This is ridiculous! I demand to speak to a manager immediately!",
        "angry_high_test_003.mp3": "I have had it with your company! This is the FOURTH time I'm calling about this refund! I've wasted hours on hold, been transferred multiple times, and STILL no resolution! Either you process my refund today or I'm taking legal action!",
    }

    @staticmethod
    async def transcribe(audio_file: Path) -> str:
        """
        Mock transcription - returns pre-defined transcript

        Args:
            audio_file: Path to audio file

        Returns:
            str: Transcript text
        """
        # Simulate STT latency
        await asyncio.sleep(0.3)  # 300ms (realistic STT latency)

        filename = audio_file.name
        transcript = MockDeepgramSTT.TRANSCRIPTS.get(
            filename,
            "This is a test query for the voice pipeline."
        )

        return transcript


async def test_voice_pipeline(audio_file: Path):
    """
    Test the complete voice pipeline

    Args:
        audio_file: Path to test audio file
    """
    print("="*70)
    print("🧪 VOICE PIPELINE TEST")
    print("="*70)
    print(f"📁 Test File: {audio_file.name}")
    print()

    # Track timing
    t_start = time.time()

    # PHASE 1: Speech-to-Text (STT)
    print("🎤 PHASE 1: Speech-to-Text")
    print("-" * 70)

    t_stt_start = time.time()
    transcript = await MockDeepgramSTT.transcribe(audio_file)
    t_stt_end = time.time()

    stt_latency = (t_stt_end - t_stt_start) * 1000
    print(f"📝 Transcript: \"{transcript}\"")
    print(f"⏱️  STT Latency: {stt_latency:.0f}ms")
    print()

    # PHASE 2: Emotion Detection
    print("😡 PHASE 2: Emotion Detection")
    print("-" * 70)

    t_emotion_start = time.time()
    emotion_data = MockEmotionDetector.detect_from_transcript(transcript)
    t_emotion_end = time.time()

    emotion_latency = (t_emotion_end - t_emotion_start) * 1000
    print(f"Detected Emotion: {emotion_data['emotion_category']}")
    print(f"Anger Score: {emotion_data['anger']:.2f}")
    print(f"Sentiment: {emotion_data['sentiment']}")
    print(f"⏱️  Emotion Detection: {emotion_latency:.0f}ms")
    print()

    # PHASE 3: Filler Selection
    print("🎵 PHASE 3: Filler Selection")
    print("-" * 70)

    t_filler_start = time.time()

    # Load filler loader (singleton)
    filler_loader = get_filler_loader()

    # Map emotion to filler category
    filler_category = emotion_data['emotion_category']

    # Get filler audio
    filler_audio = filler_loader.get_filler(filler_category)

    t_filler_end = time.time()

    filler_latency = (t_filler_end - t_filler_start) * 1000
    filler_size = len(filler_audio) / 1024

    print(f"Selected Filler Category: {filler_category}")
    print(f"Filler Audio Size: {filler_size:.1f} KB")
    print(f"⏱️  Filler Retrieval: {filler_latency:.2f}ms")
    print()

    # Calculate Time-To-Respond-Start (TTRS)
    t_ttrs = time.time()
    ttrs = (t_ttrs - t_start) * 1000

    print("🎯 TIME-TO-RESPOND-START (TTRS)")
    print("-" * 70)
    print(f"Total TTRS: {ttrs:.0f}ms")
    print(f"  ├─ STT: {stt_latency:.0f}ms")
    print(f"  ├─ Emotion Detection: {emotion_latency:.0f}ms")
    print(f"  └─ Filler Retrieval: {filler_latency:.2f}ms")
    print()

    if ttrs < 840:
        print(f"✅ TTRS Target Met! ({ttrs:.0f}ms < 840ms target)")
    else:
        print(f"⚠️  TTRS Above Target ({ttrs:.0f}ms > 840ms target)")
    print()

    # PHASE 4: Simulated Logic Execution (Parallel to Filler Playback)
    print("🧠 PHASE 4: Neuro-Symbolic Logic Execution")
    print("-" * 70)
    print("(Simulating logic execution during filler playback...)")

    t_logic_start = time.time()

    # Simulate logic execution (would be actual rules engine in production)
    await asyncio.sleep(0.093)  # 93ms (from our zero-latency tests)

    t_logic_end = time.time()

    logic_latency = (t_logic_end - t_logic_start) * 1000

    # Simulate logic result
    logic_result = {
        "refund_eligible": True,
        "refund_amount": 49.99,
        "reason": "Product defect within warranty period"
    }

    print(f"Logic Result: {logic_result}")
    print(f"⏱️  Logic Execution: {logic_latency:.0f}ms")
    print()

    # PHASE 5: Response Generation (would use LLM in production)
    print("💬 PHASE 5: Response Generation")
    print("-" * 70)

    # Mock response based on emotion and logic result
    if emotion_data['anger'] > 0.7:
        response = (
            f"I completely understand your frustration, and I sincerely apologize for the delay. "
            f"I've reviewed your case immediately, and I can confirm that you are eligible for a "
            f"full refund of ${logic_result['refund_amount']}. I'm processing this right away "
            f"and you'll see the refund in your account within 2-3 business days. "
            f"Is there anything else I can help you with today?"
        )
    elif emotion_data['anger'] > 0.3:
        response = (
            f"I understand your concern, and I appreciate your patience. "
            f"I've checked your order, and you are eligible for a refund of ${logic_result['refund_amount']}. "
            f"I'll process this for you right away. You should see the refund within 5 business days. "
            f"Is there anything else I can assist you with?"
        )
    else:
        response = (
            f"Thank you for contacting us. I've reviewed your request, and I can confirm that "
            f"you're eligible for a refund of ${logic_result['refund_amount']}. "
            f"I'll go ahead and process that for you. You can expect to see the refund "
            f"in your account within 5-7 business days. Is there anything else I can help with?"
        )

    print(f"Response: \"{response}\"")
    print()

    # Total Pipeline Time
    t_end = time.time()
    total_latency = (t_end - t_start) * 1000

    print("="*70)
    print("📊 PIPELINE PERFORMANCE SUMMARY")
    print("="*70)
    print(f"Time-To-Respond-Start (TTRS): {ttrs:.0f}ms")
    print(f"Logic Execution: {logic_latency:.0f}ms")
    print(f"Total Pipeline Latency: {total_latency:.0f}ms")
    print()

    print("🎯 Performance Targets:")
    ttrs_status = "✅ PASS" if ttrs < 840 else "❌ FAIL"
    logic_status = "✅ PASS" if logic_latency < 500 else "❌ FAIL"
    total_status = "✅ PASS" if total_latency < 5000 else "⚠️  SLOW"

    print(f"  TTRS < 840ms: {ttrs_status} ({ttrs:.0f}ms)")
    print(f"  Logic < 500ms: {logic_status} ({logic_latency:.0f}ms)")
    print(f"  Total < 5000ms: {total_status} ({total_latency:.0f}ms)")
    print()

    print("="*70)
    print("✅ PIPELINE TEST COMPLETE")
    print("="*70)
    print()


async def run_all_tests():
    """Run tests for all available test audio files"""
    print("="*70)
    print("🧪 RUNNING ALL PIPELINE TESTS")
    print("="*70)
    print()

    if not TEST_AUDIO_DIR.exists():
        print(f"❌ Test audio directory not found: {TEST_AUDIO_DIR}")
        print("📝 Please run: python scripts/generate_test_queries.py")
        return

    # Find all test audio files
    test_files = sorted(TEST_AUDIO_DIR.glob("*_test_*.mp3"))

    if not test_files:
        print(f"❌ No test audio files found in {TEST_AUDIO_DIR}")
        print("📝 Please run: python scripts/generate_test_queries.py")
        return

    print(f"Found {len(test_files)} test files")
    print()

    # Run test for each file
    for i, test_file in enumerate(test_files, start=1):
        print(f"\n{'='*70}")
        print(f"Test {i}/{len(test_files)}")
        print(f"{'='*70}\n")

        await test_voice_pipeline(test_file)

        # Pause between tests
        if i < len(test_files):
            await asyncio.sleep(1)

    print("\n" + "="*70)
    print("🎉 ALL PIPELINE TESTS COMPLETE")
    print("="*70)


def main():
    """Main script execution"""
    parser = argparse.ArgumentParser(
        description="Test the complete voice pipeline with simulated audio"
    )
    parser.add_argument(
        "--file",
        type=str,
        help="Specific test file to run (e.g., angry_high_test_001.mp3)"
    )
    parser.add_argument(
        "--emotion",
        type=str,
        choices=["neutral", "angry_medium", "angry_high"],
        help="Test all files of a specific emotion category"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all available tests"
    )

    args = parser.parse_args()

    # Ensure filler loader is initialized
    try:
        filler_loader = get_filler_loader()
        print(f"✅ Filler Loader initialized ({len(filler_loader.get_available_categories())} categories)")
        print()
    except Exception as e:
        print(f"❌ Failed to initialize Filler Loader: {e}")
        print("📝 Please ensure backend/fillers/ contains filler audio files")
        return

    # Determine which tests to run
    if args.all:
        asyncio.run(run_all_tests())
    elif args.file:
        test_file = TEST_AUDIO_DIR / args.file
        if not test_file.exists():
            print(f"❌ Test file not found: {test_file}")
            return
        asyncio.run(test_voice_pipeline(test_file))
    elif args.emotion:
        # Find all files for this emotion
        test_files = sorted(TEST_AUDIO_DIR.glob(f"{args.emotion}_test_*.mp3"))
        if not test_files:
            print(f"❌ No test files found for emotion: {args.emotion}")
            print(f"📝 Please run: python scripts/generate_test_queries.py")
            return

        for test_file in test_files:
            asyncio.run(test_voice_pipeline(test_file))
            print()
    else:
        # Default: run all tests
        asyncio.run(run_all_tests())


if __name__ == "__main__":
    main()
