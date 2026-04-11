#!/usr/bin/env python3
"""
JARVIS Setup Script
Downloads required models and dependencies
"""

import os
import sys
import urllib.request
import zipfile
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "models" / "llm"
VOICE_TTS_DIR = BASE_DIR / "voice" / "tts"
VOICE_STT_DIR = BASE_DIR / "voice" / "stt"
RUNTIME_DIR = BASE_DIR / "runtime"

def download_file(url, destination, description):
    """Download with progress"""
    print(f"\n📥 Downloading {description}...")
    print(f"   URL: {url}")
    print(f"   Destination: {destination}")
    
    def report_progress(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, downloaded * 100 / total_size)
        print(f"\r   Progress: {percent:.1f}%", end="", flush=True)
    
    try:
        urllib.request.urlretrieve(url, destination, reporthook=report_progress)
        print("\n   ✅ Complete")
        return True
    except Exception as e:
        print(f"\n   ❌ Error: {e}")
        return False

def setup_directories():
    """Create necessary directories"""
    dirs = [
        MODELS_DIR, VOICE_TTS_DIR, VOICE_STT_DIR,
        RUNTIME_DIR, BASE_DIR / "data", BASE_DIR / "media",
        BASE_DIR / "temp"
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch(exist_ok=True)
    print("✅ Directories created")

def download_sample_models():
    """Download small sample models for testing"""
    
    # Example: Download a small whisper model
    stt_url = "https://huggingface.co/Systran/faster-whisper-small/resolve/main/model.bin"
    stt_dir = VOICE_STT_DIR / "faster-whisper-small"
    stt_dir.mkdir(exist_ok=True)
    
    if not (stt_dir / "model.bin").exists():
        download_file(
            stt_url, 
            stt_dir / "model.bin",
            "STT Model (Small)"
        )
    else:
        print("✅ STT Model already exists")

def main():
    print("=" * 60)
    print("🤖 JARVIS Setup Assistant")
    print("=" * 60)
    
    setup_directories()
    
    print("\n⚠️  Manual downloads required for:")
    print("   1. LLM Models (.gguf files) -> models/llm/")
    print("   2. Camoufox Browser -> runtime/camoufox/")
    print("   3. TTS Voice Models -> voice/tts/")
    print("   4. Media files (videos) -> media/")
    
    choice = input("\nDownload small STT model now? (y/n): ").lower()
    if choice == 'y':
        download_sample_models()
    
    print("\n✅ Setup complete!")
    print("Next steps:")
    print("1. Place your LLM .gguf files in models/llm/")
    print("2. Install Camoufox from https://github.com/daijro/camoufox")
    print("3. Run: python app.py")

if __name__ == "__main__":
    main()