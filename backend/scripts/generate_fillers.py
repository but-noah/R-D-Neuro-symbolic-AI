#!/usr/bin/env python3
"""
Filler Audio Generation Script
Generates pre-cached filler audio files using Cartesia TTS API

This script implements the "Progressive Audio Enhancement" strategy (Proposal 4)
by pre-generating emotionally-appropriate filler responses that can be played
instantly (< 840ms Time-to-Respond-Start) while logic executes in the background.
"""

import os
import sys
from pathlib import Path
import asyncio
from dotenv import load_dotenv

# Add parent directory to path to import cartesia
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
OUTPUT_DIR = Path(__file__).parent.parent / "fillers"

# Ensure output directory exists
OUTPUT_DIR.mkdir(exist_ok=True)

# Filler Templates
# Organized by emotion category to match our empathy engine
FILLER_TEMPLATES = {
    # Neutral - Default for standard interactions
    "neutral": [
        "Thank you for reaching out, I'm reviewing your request.",
        "I understand, let me take a moment to check that for you.",
        "Let me pull up your account details.",
    ],

    # High Anger (> 0.7) - De-escalation focus
    "angry_high": [
        "I understand your frustration, let me review this immediately.",
        "I hear you, let me get this sorted out right away.",
        "I completely understand, give me just a moment to help.",
    ],

    # Medium Anger (0.3-0.7) - Professional but empathetic
    "angry_medium": [
        "I understand your concern, let me check on that.",
        "I hear what you're saying, let me look into this.",
        "I appreciate you reaching out, let me review the details.",
    ],

    # Low Anger (< 0.3) - Friendly and warm
    "calm": [
        "Of course! Let me take a look at that for you.",
        "Absolutely, let me check on that right away.",
        "Sure thing! Give me just a moment to review your account.",
    ],

    # Frustrated (specific tone)
    "frustrated": [
        "I can imagine how frustrating this is, let me help right away.",
        "I understand the inconvenience, let me look into this for you.",
        "I know this isn't ideal, let me see what I can do.",
    ],
}

# Voice Configuration
# Cartesia voice IDs - you can customize these
# See: https://docs.cartesia.ai/api-reference/voices
VOICE_CONFIG = {
    "voice": {
        "mode": "id",
        "id": "a0e99841-438c-4a64-b679-ae501e7d6091"  # Cartesia default conversational voice
    },
    "model_id": "sonic-english",  # Sonic model for ultra-low latency
    "language": "en",  # English
    "output_format": {
        "container": "mp3",  # MP3 for compatibility
        "encoding": "mp3",
        "sample_rate": 44100,  # High quality
    }
}


def generate_filler_audio(client: Cartesia, text: str, output_path: Path, emotion_category: str):
    """
    Generate a single filler audio file using Cartesia TTS.

    Args:
        client: Cartesia API client
        text: Filler text to synthesize
        output_path: Where to save the audio file
        emotion_category: Emotion category for voice customization
    """
    print(f"🎙️  Generating: {output_path.name}")
    print(f"   Text: \"{text}\"")
    print(f"   Emotion: {emotion_category}")

    try:
        # Generate audio using Cartesia API
        # Note: Cartesia supports emotional control - we can adjust this per category
        output = client.tts.bytes(
            model_id=VOICE_CONFIG["model_id"],
            transcript=text,
            voice=VOICE_CONFIG["voice"],
            language=VOICE_CONFIG["language"],
            output_format=VOICE_CONFIG["output_format"],
        )

        # Save audio file
        # The bytes() method returns an iterator of audio chunks
        with open(output_path, "wb") as f:
            for chunk in output:
                f.write(chunk)

        file_size = output_path.stat().st_size / 1024  # KB
        print(f"   ✅ Saved: {file_size:.1f} KB")

    except Exception as e:
        print(f"   ❌ Error: {e}")
        raise


def main():
    """Main script execution."""
    print("="*70)
    print("🎤 FILLER AUDIO GENERATION SCRIPT")
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

    # Generate fillers for each emotion category
    for emotion_category, texts in FILLER_TEMPLATES.items():
        print(f"\n{'='*70}")
        print(f"📂 Category: {emotion_category.upper()}")
        print(f"{'='*70}")

        for idx, text in enumerate(texts, start=1):
            # Create filename: emotion_category_001.mp3
            filename = f"{emotion_category}_{idx:03d}.mp3"
            output_path = OUTPUT_DIR / filename

            # Generate audio
            generate_filler_audio(client, text, output_path, emotion_category)

            total_files += 1
            total_size += output_path.stat().st_size

            print()  # Blank line for readability

    # Summary
    print("\n" + "="*70)
    print("📊 GENERATION SUMMARY")
    print("="*70)
    print(f"✅ Total Files Generated: {total_files}")
    print(f"📦 Total Size: {total_size / 1024:.1f} KB ({total_size / (1024*1024):.2f} MB)")
    print(f"📁 Location: {OUTPUT_DIR}")
    print()

    # List all generated files
    print("📋 Generated Files:")
    for emotion_category in FILLER_TEMPLATES.keys():
        category_files = sorted(OUTPUT_DIR.glob(f"{emotion_category}_*.mp3"))
        print(f"   {emotion_category}: {len(category_files)} files")
        for file in category_files:
            print(f"      - {file.name}")

    print("\n" + "="*70)
    print("🎉 FILLER GENERATION COMPLETE!")
    print("="*70)
    print()
    print("📝 Next Steps:")
    print("   1. Verify audio files in backend/fillers/")
    print("   2. Test playback to ensure quality")
    print("   3. Integrate filler loader into voice pipeline")
    print("   4. Map emotion detection to filler categories")
    print()


if __name__ == "__main__":
    main()
