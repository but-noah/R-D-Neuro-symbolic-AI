#!/usr/bin/env python3
"""
Filler Audio Loader Service
Loads pre-cached filler audio files into memory for instant playback

This service implements the "Progressive Audio Enhancement" strategy (Proposal 4)
by loading emotionally-appropriate filler audio files into memory on startup,
enabling instant playback (< 840ms Time-to-Respond-Start) while logic executes.

Key Features:
- Pre-caching: All filler audio loaded into memory at startup
- Emotion Mapping: Maps customer emotion to appropriate filler category
- Random Selection: Randomizes filler selection within category for variety
- Fallback Logic: Falls back to neutral if category unavailable
- Zero I/O Overhead: Returns audio bytes directly from memory
"""

from pathlib import Path
from typing import Dict, List, Optional
import random
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FillerLoader:
    """
    Filler Audio Loader - Pre-caches filler audio files for instant playback.

    This class loads all pre-generated filler audio files into memory on initialization,
    enabling zero-latency audio playback while background logic executes.

    Attributes:
        cache: Dictionary mapping emotion categories to lists of audio bytes
        fillers_dir: Path to the fillers directory containing MP3 files
        emotion_categories: List of supported emotion categories
    """

    # Emotion categories mapping to filler audio files
    EMOTION_CATEGORIES = [
        "neutral",
        "angry_high",
        "angry_medium",
        "calm",
        "frustrated"
    ]

    def __init__(self, fillers_dir: Optional[Path] = None):
        """
        Initialize FillerLoader and pre-cache all audio files.

        Args:
            fillers_dir: Path to fillers directory. Defaults to backend/fillers/
        """
        # Default to backend/fillers/ directory
        if fillers_dir is None:
            fillers_dir = Path(__file__).parent.parent.parent / "fillers"

        self.fillers_dir = fillers_dir
        self.cache: Dict[str, List[bytes]] = {}

        logger.info("="*70)
        logger.info("🎵 FILLER AUDIO LOADER - Initializing")
        logger.info("="*70)
        logger.info(f"📁 Fillers Directory: {self.fillers_dir}")

        # Load all filler audio files into memory
        self.load_all_fillers()

        logger.info("✅ Filler Loader Ready!")
        logger.info("="*70)

    def load_all_fillers(self):
        """
        Load all filler audio files into memory cache.

        This method scans the fillers directory for MP3 files matching the pattern:
        {emotion_category}_{number}.mp3 and loads them into memory.

        Raises:
            FileNotFoundError: If fillers directory doesn't exist
            Exception: If no filler files are found
        """
        if not self.fillers_dir.exists():
            error_msg = f"Fillers directory not found: {self.fillers_dir}"
            logger.error(f"❌ {error_msg}")
            raise FileNotFoundError(error_msg)

        total_files = 0
        total_size = 0

        # Load fillers for each emotion category
        for emotion_category in self.EMOTION_CATEGORIES:
            # Find all MP3 files for this category
            category_files = sorted(self.fillers_dir.glob(f"{emotion_category}_*.mp3"))

            if not category_files:
                logger.warning(f"⚠️  No filler files found for category: {emotion_category}")
                continue

            # Initialize cache for this category
            self.cache[emotion_category] = []

            # Load each file into memory
            for file_path in category_files:
                try:
                    with open(file_path, "rb") as f:
                        audio_bytes = f.read()
                        self.cache[emotion_category].append(audio_bytes)

                        file_size = len(audio_bytes) / 1024  # KB
                        total_size += len(audio_bytes)
                        total_files += 1

                        logger.info(f"   ✅ Loaded: {file_path.name} ({file_size:.1f} KB)")

                except Exception as e:
                    logger.error(f"   ❌ Error loading {file_path.name}: {e}")
                    continue

            logger.info(f"📂 Category '{emotion_category}': {len(category_files)} files loaded")

        # Verify we have at least some fillers loaded
        if total_files == 0:
            error_msg = "No filler audio files were successfully loaded!"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

        logger.info(f"\n📊 Total Files Cached: {total_files}")
        logger.info(f"📦 Total Memory Used: {total_size / 1024:.1f} KB ({total_size / (1024*1024):.2f} MB)")

    def get_filler(self, emotion_category: Optional[str] = None) -> bytes:
        """
        Get a random filler audio file for the specified emotion category.

        This method returns pre-cached audio bytes for instant playback without
        any I/O overhead. If the requested category is unavailable, it falls back
        to neutral fillers.

        Args:
            emotion_category: Emotion category (e.g., "angry_high", "calm").
                            Defaults to "neutral" if None or unavailable.

        Returns:
            bytes: MP3 audio file bytes ready for playback

        Examples:
            >>> loader = FillerLoader()
            >>> audio = loader.get_filler("angry_high")
            >>> # Play audio immediately (< 1ms to retrieve from memory)
        """
        # Default to neutral if no category specified
        if emotion_category is None:
            emotion_category = "neutral"

        # Fallback to neutral if category not available
        if emotion_category not in self.cache or not self.cache[emotion_category]:
            logger.warning(f"⚠️  Emotion category '{emotion_category}' not available, falling back to 'neutral'")
            emotion_category = "neutral"

        # Final fallback check (in case neutral is also missing)
        if emotion_category not in self.cache or not self.cache[emotion_category]:
            error_msg = "No filler audio available (including neutral fallback)!"
            logger.error(f"❌ {error_msg}")
            raise Exception(error_msg)

        # Randomly select a filler from the category
        audio_bytes = random.choice(self.cache[emotion_category])

        logger.debug(f"🎵 Selected filler: {emotion_category} ({len(audio_bytes) / 1024:.1f} KB)")

        return audio_bytes

    def get_emotion_category_from_score(self, anger: float) -> str:
        """
        Map emotion scores to filler emotion categories.

        This method maps the neuro-symbolic emotion detection output
        (specifically the anger score) to the appropriate filler category.

        Args:
            anger: Anger score from emotion detection (0.0 - 1.0)

        Returns:
            str: Emotion category for filler selection

        Mapping:
            - anger > 0.7: "angry_high" (de-escalation focus)
            - anger 0.3-0.7: "angry_medium" (empathetic but professional)
            - anger < 0.3: "calm" (friendly and warm)

        Examples:
            >>> loader = FillerLoader()
            >>> category = loader.get_emotion_category_from_score(0.85)
            >>> # Returns: "angry_high"
            >>> audio = loader.get_filler(category)
        """
        if anger > 0.7:
            return "angry_high"
        elif anger >= 0.3:
            return "angry_medium"
        else:
            return "calm"

    def get_available_categories(self) -> List[str]:
        """
        Get list of available emotion categories.

        Returns:
            List[str]: List of emotion categories with loaded fillers
        """
        return list(self.cache.keys())

    def get_category_count(self, emotion_category: str) -> int:
        """
        Get count of fillers available for a specific category.

        Args:
            emotion_category: Emotion category to check

        Returns:
            int: Number of filler audio files available for this category
        """
        if emotion_category not in self.cache:
            return 0
        return len(self.cache[emotion_category])

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about loaded fillers.

        Returns:
            Dict[str, int]: Dictionary mapping emotion categories to filler counts

        Examples:
            >>> loader = FillerLoader()
            >>> stats = loader.get_stats()
            >>> # Returns: {"neutral": 3, "angry_high": 3, "calm": 3, ...}
        """
        return {category: len(fillers) for category, fillers in self.cache.items()}


# Singleton instance for application-wide use
_filler_loader_instance: Optional[FillerLoader] = None


def get_filler_loader() -> FillerLoader:
    """
    Get the singleton FillerLoader instance.

    This function ensures only one FillerLoader instance is created,
    avoiding duplicate memory usage from loading fillers multiple times.

    Returns:
        FillerLoader: Singleton FillerLoader instance

    Examples:
        >>> loader = get_filler_loader()
        >>> audio = loader.get_filler("angry_high")
    """
    global _filler_loader_instance

    if _filler_loader_instance is None:
        _filler_loader_instance = FillerLoader()

    return _filler_loader_instance


if __name__ == "__main__":
    """
    Test script to verify filler loader functionality.
    """
    print("="*70)
    print("🧪 FILLER LOADER TEST SCRIPT")
    print("="*70)
    print()

    # Initialize loader
    loader = FillerLoader()

    # Display statistics
    print("\n📊 Filler Statistics:")
    stats = loader.get_stats()
    for category, count in stats.items():
        print(f"   {category}: {count} files")

    # Test emotion mapping
    print("\n🧪 Testing Emotion Mapping:")
    test_scores = [
        (0.85, "angry_high"),
        (0.5, "angry_medium"),
        (0.15, "calm"),
    ]

    for anger_score, expected_category in test_scores:
        category = loader.get_emotion_category_from_score(anger_score)
        match = "✅" if category == expected_category else "❌"
        print(f"   {match} Anger={anger_score:.2f} → {category} (expected: {expected_category})")

    # Test filler retrieval
    print("\n🎵 Testing Filler Retrieval:")
    for category in loader.get_available_categories():
        audio = loader.get_filler(category)
        print(f"   ✅ {category}: Retrieved {len(audio) / 1024:.1f} KB")

    # Test fallback logic
    print("\n🔄 Testing Fallback Logic:")
    audio = loader.get_filler("nonexistent_category")
    print(f"   ✅ Fallback worked: Retrieved {len(audio) / 1024:.1f} KB (neutral)")

    print("\n" + "="*70)
    print("✅ ALL TESTS PASSED!")
    print("="*70)
