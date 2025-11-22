#!/usr/bin/env python3
"""
Test Query Generator - Emotional User Queries for Pipeline Testing

Generates realistic user queries with varying emotional intensities using Cartesia TTS.
These test queries simulate real customer service scenarios with different anger levels
to test the complete voice pipeline: STT → Emotion Detection → Filler Selection → TTS

Emotions Generated:
- Neutral: Calm, polite customer inquiries
- Angry Medium: Frustrated but controlled
- Angry High: Very upset, demanding immediate action

Output: Audio files saved to backend/test_audio/ for pipeline testing
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent / '.env')

try:
    from cartesia import Cartesia
except ImportError:
    print("❌ Cartesia SDK not installed!")
    print("📦 Installing cartesia package...")
    os.system("pip install cartesia")
    from cartesia import Cartesia

# Configuration
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
OUTPUT_DIR = Path(__file__).parent.parent / "test_audio"

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# Test Query Templates
# Designed to trigger different emotion detection levels
TEST_QUERIES = {
    # Neutral (anger < 0.3) - Calm, polite inquiries
    "neutral": [
        {
            "text": "Hi, I'm calling about a refund for order number 12345. "
                   "I received the wrong item and would like to return it. "
                   "Can you help me with this?",
            "scenario": "Wrong item received, polite tone",
            "expected_anger": 0.1,
            "voice_style": "calm",
        },
        {
            "text": "Hello, I ordered a product last week but it hasn't arrived yet. "
                   "Could you check the status of my delivery? "
                   "The order number is 67890.",
            "scenario": "Delayed delivery, patient inquiry",
            "expected_anger": 0.15,
            "voice_style": "friendly",
        },
        {
            "text": "Good morning, I'd like to request a refund for a purchase I made. "
                   "The product doesn't quite meet my needs. "
                   "What's the process for returning it?",
            "scenario": "Product doesn't fit needs, professional tone",
            "expected_anger": 0.05,
            "voice_style": "professional",
        },
    ],

    # Angry Medium (anger 0.3-0.7) - Frustrated but controlled
    "angry_medium": [
        {
            "text": "Look, I've been waiting three weeks for my refund and I still haven't received it. "
                   "This is getting really frustrating. "
                   "I was promised it would be processed within five business days. "
                   "Can someone please tell me what's going on?",
            "scenario": "Delayed refund, growing frustration",
            "expected_anger": 0.5,
            "voice_style": "frustrated",
        },
        {
            "text": "I'm pretty upset about this situation. "
                   "The item I received is damaged and I've already contacted support twice. "
                   "Nobody seems to be helping me. "
                   "I just want my money back or a replacement.",
            "scenario": "Damaged item, repeated contact attempts",
            "expected_anger": 0.55,
            "voice_style": "annoyed",
        },
        {
            "text": "This is the second time I'm calling about the same issue. "
                   "I was told last week that my refund would be processed, but nothing happened. "
                   "I'm starting to lose patience here. "
                   "When exactly will I get my refund?",
            "scenario": "Broken promise, escalating frustration",
            "expected_anger": 0.6,
            "voice_style": "impatient",
        },
    ],

    # Angry High (anger > 0.7) - Very upset, demanding immediate action
    "angry_high": [
        {
            "text": "This is absolutely unacceptable! "
                   "I've been waiting over a month for my refund and I keep getting the runaround! "
                   "Every time I call, I get a different excuse. "
                   "I want my money back RIGHT NOW or I'm filing a complaint with consumer protection!",
            "scenario": "Long delay, multiple broken promises",
            "expected_anger": 0.85,
            "voice_style": "angry",
        },
        {
            "text": "I am EXTREMELY frustrated with your service! "
                   "The product arrived broken, your support team has been completely unhelpful, "
                   "and now you're telling me I can't get a refund?! "
                   "This is ridiculous! I demand to speak to a manager immediately!",
            "scenario": "Broken product + poor service + refusal",
            "expected_anger": 0.9,
            "voice_style": "very_angry",
        },
        {
            "text": "I have had it with your company! "
                   "This is the FOURTH time I'm calling about this refund! "
                   "I've wasted hours on hold, been transferred multiple times, "
                   "and STILL no resolution! "
                   "Either you process my refund today or I'm taking legal action!",
            "scenario": "Multiple failed attempts, threatening escalation",
            "expected_anger": 0.95,
            "voice_style": "furious",
        },
    ],
}

# Voice Configuration per Emotion
# Cartesia supports emotional control through voice parameters
VOICE_CONFIGS = {
    "neutral": {
        "voice": {
            "mode": "id",
            "id": "a0e99841-438c-4a64-b679-ae501e7d6091"  # Default conversational voice
        },
        "model_id": "sonic-english",
        "language": "en",
        "output_format": {
            "container": "mp3",
            "encoding": "mp3",
            "sample_rate": 44100,
        },
        # Note: Emotional controls can be added here when supported
        # "emotion": "neutral",
        # "speed": 1.0,
        # "pitch": 0,
    },
    "angry_medium": {
        "voice": {
            "mode": "id",
            "id": "a0e99841-438c-4a64-b679-ae501e7d6091"
        },
        "model_id": "sonic-english",
        "language": "en",
        "output_format": {
            "container": "mp3",
            "encoding": "mp3",
            "sample_rate": 44100,
        },
        # "emotion": "frustrated",
        # "speed": 1.1,  # Slightly faster (frustrated people speak faster)
        # "pitch": 2,    # Slightly higher pitch (tension)
    },
    "angry_high": {
        "voice": {
            "mode": "id",
            "id": "a0e99841-438c-4a64-b679-ae501e7d6091"
        },
        "model_id": "sonic-english",
        "language": "en",
        "output_format": {
            "container": "mp3",
            "encoding": "mp3",
            "sample_rate": 44100,
        },
        # "emotion": "angry",
        # "speed": 1.2,  # Faster (angry people speak quickly)
        # "pitch": 4,    # Higher pitch (emotional intensity)
    },
}


def generate_test_query(
    client: Cartesia,
    text: str,
    emotion_category: str,
    output_path: Path,
    scenario: str,
    expected_anger: float
):
    """
    Generate a single test query audio file

    Args:
        client: Cartesia API client
        text: Query text to synthesize
        emotion_category: Emotion category (neutral, angry_medium, angry_high)
        output_path: Where to save the audio file
        scenario: Description of the scenario
        expected_anger: Expected anger score (0.0-1.0)
    """
    print(f"🎙️  Generating: {output_path.name}")
    print(f"   Emotion: {emotion_category} (expected anger: {expected_anger:.2f})")
    print(f"   Scenario: {scenario}")
    print(f"   Text: \"{text[:100]}...\"")

    try:
        # Get voice config for emotion category
        voice_config = VOICE_CONFIGS[emotion_category]

        # Generate audio using Cartesia API
        output = client.tts.bytes(
            model_id=voice_config["model_id"],
            transcript=text,
            voice=voice_config["voice"],
            language=voice_config["language"],
            output_format=voice_config["output_format"],
        )

        # Save audio file
        with open(output_path, "wb") as f:
            for chunk in output:
                f.write(chunk)

        file_size = output_path.stat().st_size / 1024  # KB
        print(f"   ✅ Saved: {file_size:.1f} KB")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        raise


def main():
    """Main script execution"""
    print("="*70)
    print("🎤 TEST QUERY GENERATOR - Emotional User Queries")
    print("="*70)
    print(f"📁 Output Directory: {OUTPUT_DIR}")
    print(f"🔑 Cartesia API Key: {'✅ Found' if CARTESIA_API_KEY else '❌ Missing'}")
    print()

    if not CARTESIA_API_KEY:
        print("❌ ERROR: CARTESIA_API_KEY not found in .env file!")
        print("   Please add: CARTESIA_API_KEY=your_key_here")
        sys.exit(1)

    # Initialize Cartesia client
    print("🔌 Connecting to Cartesia API...")
    client = Cartesia(api_key=CARTESIA_API_KEY)
    print("✅ Connected!\n")

    # Statistics
    total_files = 0
    total_size = 0

    # Generate test queries for each emotion category
    for emotion_category, queries in TEST_QUERIES.items():
        print(f"\n{'='*70}")
        print(f"📂 Category: {emotion_category.upper()}")
        print(f"{'='*70}")

        for idx, query_data in enumerate(queries, start=1):
            # Create filename: emotion_category_test_001.mp3
            filename = f"{emotion_category}_test_{idx:03d}.mp3"
            output_path = OUTPUT_DIR / filename

            # Generate audio
            generate_test_query(
                client=client,
                text=query_data["text"],
                emotion_category=emotion_category,
                output_path=output_path,
                scenario=query_data["scenario"],
                expected_anger=query_data["expected_anger"]
            )

            total_files += 1
            total_size += output_path.stat().st_size

            print()  # Blank line for readability

    # Summary
    print("\n" + "="*70)
    print("📊 GENERATION SUMMARY")
    print("="*70)
    print(f"✅ Total Test Queries Generated: {total_files}")
    print(f"📦 Total Size: {total_size / 1024:.1f} KB ({total_size / (1024*1024):.2f} MB)")
    print(f"📁 Location: {OUTPUT_DIR}")
    print()

    # List all generated files
    print("📋 Generated Test Queries:")
    for emotion_category in TEST_QUERIES.keys():
        category_files = sorted(OUTPUT_DIR.glob(f"{emotion_category}_test_*.mp3"))
        print(f"\n   {emotion_category.upper()}:")
        for i, file in enumerate(category_files, start=1):
            query_data = TEST_QUERIES[emotion_category][i-1]
            print(f"      {i}. {file.name}")
            print(f"         Scenario: {query_data['scenario']}")
            print(f"         Expected Anger: {query_data['expected_anger']:.2f}")

    print("\n" + "="*70)
    print("🎉 TEST QUERY GENERATION COMPLETE!")
    print("="*70)
    print()
    print("📝 Next Steps:")
    print("   1. Verify audio files in backend/test_audio/")
    print("   2. Test audio playback to verify emotional tone")
    print("   3. Use these files to test STT → Emotion → Filler pipeline")
    print("   4. Run pipeline tests with: python scripts/test_voice_pipeline.py")
    print()
    print("🧪 Testing Scenarios:")
    print("   - Play neutral queries → Should trigger 'calm' fillers")
    print("   - Play angry_medium queries → Should trigger 'angry_medium' fillers")
    print("   - Play angry_high queries → Should trigger 'angry_high' fillers")
    print()


if __name__ == "__main__":
    main()
