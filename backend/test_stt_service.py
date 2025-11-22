#!/usr/bin/env python3
"""
Test Script for Deepgram Flux STT Service

Tests the new STT service implementation with:
- File-based streaming transcription
- Eager End-of-Turn callback
- Metrics tracking
- Graceful degradation (optional)

Usage:
    python test_stt_service.py

Expected Results:
- STT Latency: 300-400ms (vs 1275ms baseline) = 68-75% reduction
- Eager EOT: Should trigger for natural speech pauses
- Graceful Degradation: Falls back to prerecorded on error
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("⚠️ python-dotenv not installed, environment variables may not be loaded")

from app.services.stt_service import RobustSTTService, FileSTTResult, TranscriptResult


async def test_flux_streaming():
    """Test Deepgram Flux streaming with file-based audio"""
    print("="*80)
    print("🧪 DEEPGRAM FLUX STT SERVICE TEST")
    print("="*80)
    print()

    # Initialize service
    print("📝 Initializing RobustSTTService...")
    stt = RobustSTTService()
    print(f"   Model: {stt.config.model}")
    print(f"   Eager EOT Threshold: {stt.config.eager_eot_threshold}")
    print(f"   Max Retries: {stt.max_retries}")
    print()

    # Test audio file
    test_audio_file = "test_audio/neutral_test_002.mp3"
    if not os.path.exists(test_audio_file):
        print(f"❌ Test audio file not found: {test_audio_file}")
        return

    print(f"🎵 Test Audio: {test_audio_file}")
    print()

    # Setup callbacks
    eager_eot_fired = False
    transcript_updates = []

    def on_eager_eot_callback():
        nonlocal eager_eot_fired
        eager_eot_fired = True
        print("   🚀 EAGER EOT TRIGGERED - Logic can pre-fetch now!")

    async def on_transcript_callback(result: TranscriptResult):
        transcript_updates.append(result)
        status = "FINAL" if result.is_final else "INTERIM"
        print(f"   [{status}] {result.text}")

    # Run transcription
    print("🎙️ Starting Flux streaming transcription...")
    print()

    try:
        result: FileSTTResult = await stt.transcribe_file_streaming(
            audio_file_path=test_audio_file,
            on_eager_eot=on_eager_eot_callback,
            on_transcript=on_transcript_callback,
            fallback_to_prerecorded=True,
        )

        print()
        print("="*80)
        print("✅ TRANSCRIPTION COMPLETE")
        print("="*80)
        print()

        # Display results
        print(f"📝 Transcript:")
        print(f"   \"{result.transcript}\"")
        print()

        print(f"📊 Metrics:")
        print(f"   Mode:                {result.metrics.mode}")
        print(f"   Latency:             {result.metrics.latency_ms}ms")
        print(f"   Audio Duration:      {result.metrics.audio_duration_ms}ms")
        print(f"   Realtime Factor:     {result.metrics.realtime_factor:.2f}x")
        print(f"   Transcript Length:   {result.metrics.transcript_length} chars")
        print(f"   Eager EOT Triggered: {result.metrics.eager_eot_triggered}")
        print(f"   Turn Resumed Count:  {result.metrics.turn_resumed_count}")
        print(f"   Retry Count:         {result.metrics.retry_count}")
        print(f"   Confidence:          {result.confidence:.2f}")
        print()

        # Performance analysis
        if result.metrics.mode == "flux_streaming":
            baseline_latency = 1275  # ms (from analysis)
            improvement = ((baseline_latency - result.metrics.latency_ms) / baseline_latency) * 100

            print(f"🚀 Performance Improvement:")
            print(f"   Baseline (Nova-3 Prerecorded): {baseline_latency}ms")
            print(f"   Flux Streaming:                {result.metrics.latency_ms}ms")
            print(f"   Improvement:                   {improvement:.1f}% faster")
            print()

            if result.metrics.latency_ms < 500:
                print("   ✅ MEETS TTRS TARGET (< 500ms)!")
            elif result.metrics.latency_ms < 840:
                print("   ✅ MEETS TTRS TARGET (< 840ms)!")
            else:
                print("   ⚠️ ABOVE TTRS TARGET (< 840ms)")
            print()

        # Eager EOT analysis
        if eager_eot_fired:
            print("🎯 Eager EOT Analysis:")
            print("   ✅ Eager EOT successfully triggered")
            print("   💡 Logic can pre-fetch during user's final words")
            print("   ⏱️ Expected savings: 150-250ms")
        else:
            print("ℹ️ Eager EOT did not trigger (this is OK for short audio)")
        print()

        # Transcript updates
        print(f"📊 Transcript Updates: {len(transcript_updates)} total")
        final_count = sum(1 for t in transcript_updates if t.is_final)
        interim_count = sum(1 for t in transcript_updates if not t.is_final)
        print(f"   Final:   {final_count}")
        print(f"   Interim: {interim_count}")
        print()

    except Exception as e:
        print()
        print("="*80)
        print(f"❌ TEST FAILED: {e}")
        print("="*80)
        import traceback
        traceback.print_exc()


async def test_multiple_files():
    """Test with all available test audio files"""
    print("="*80)
    print("🧪 MULTIPLE FILES TEST")
    print("="*80)
    print()

    stt = RobustSTTService()

    test_files = [
        "test_audio/neutral_test_001.mp3",
        "test_audio/neutral_test_002.mp3",
        "test_audio/angry_medium_test_001.mp3",
    ]

    results = []

    for test_file in test_files:
        if not os.path.exists(test_file):
            print(f"⚠️ Skipping {test_file} (not found)")
            continue

        print(f"📁 Testing: {Path(test_file).name}")

        try:
            result = await stt.transcribe_file_streaming(
                audio_file_path=test_file,
                fallback_to_prerecorded=True,
            )

            results.append({
                "file": Path(test_file).name,
                "latency": result.metrics.latency_ms,
                "mode": result.metrics.mode,
                "realtime_factor": result.metrics.realtime_factor,
                "eager_eot": result.metrics.eager_eot_triggered,
            })

            print(f"   ✅ Latency: {result.metrics.latency_ms}ms | Mode: {result.metrics.mode}")

        except Exception as e:
            print(f"   ❌ Failed: {e}")

        print()

    # Summary
    if results:
        print("="*80)
        print("📊 SUMMARY")
        print("="*80)
        print()

        flux_results = [r for r in results if r["mode"] == "flux_streaming"]
        fallback_results = [r for r in results if r["mode"] == "prerecorded_fallback"]

        if flux_results:
            avg_latency = sum(r["latency"] for r in flux_results) / len(flux_results)
            avg_rtf = sum(r["realtime_factor"] for r in flux_results) / len(flux_results)
            eager_eot_rate = sum(1 for r in flux_results if r["eager_eot"]) / len(flux_results)

            print(f"Flux Streaming Results ({len(flux_results)} files):")
            print(f"   Avg Latency:        {avg_latency:.0f}ms")
            print(f"   Avg Realtime Factor: {avg_rtf:.2f}x")
            print(f"   Eager EOT Rate:     {eager_eot_rate * 100:.0f}%")
            print()

        if fallback_results:
            print(f"Fallback Results ({len(fallback_results)} files):")
            for r in fallback_results:
                print(f"   {r['file']}: {r['latency']}ms")
            print()


async def main():
    """Run all tests"""
    # Test 1: Single file with detailed output
    await test_flux_streaming()

    print("\n" + "="*80 + "\n")

    # Test 2: Multiple files
    # await test_multiple_files()


if __name__ == "__main__":
    asyncio.run(main())
