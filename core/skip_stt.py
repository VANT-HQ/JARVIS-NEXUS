# core/skip_stt.py
"""
Terminal-Only Test Harness (No Audio)
=====================================

Inherits core logic from JARVISCore, overriding only:
  - initialize() -> Skips real Ears/Mouth and injects stubs.
  - run()        -> Uses terminal input() instead of microphone listening.

All other mechanisms (tool dispatch, memory, agentic loop, LLM context)
remain identical to the main production engine.
"""

import os
import re
import sys
import json
import time
import random
import threading
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.jarvis_engine import (
    JARVISCore, StateManager, InternalCommandProcessor,
    InterruptState
)
from core.config import config, STARTUP_VIDEO_PATH, get_setting
from core.memory import MemoryManager
from core.tools.browsing_tool import BrowsingTool
from core.llm_client import LLMClient


# =================================================================
# Stub: Terminal Mouth (TTS Replacement)
# =================================================================
class StubMouth:
    """Replaces real TTS with terminal print, featuring a streaming effect."""

    def __init__(self):
        self.speech_done_event = threading.Event()
        self.speech_done_event.set()
        self.spoken_history = []
        self.current_speaking_text = ""
        self._is_mid_sentence = False  # Tracks if we are streaming the same line

    def speak(self, text: str):
        """Prints to terminal with a natural typing/streaming effect."""
        if not text or text.strip().upper() == "NONE":
            return
            
        self.current_speaking_text = text
        self.spoken_history.append(text)
        if len(self.spoken_history) > 10:
            self.spoken_history = self.spoken_history[-10:]
        
        # Format the output to look like a continuous stream
        if not self._is_mid_sentence:
            sys.stdout.write("  🔊 [JARVIS]: ")
            
        for char in text:
            sys.stdout.write(char)
            sys.stdout.flush()
            time.sleep(0.015)  # 15ms delay per character for a typing feel
            
        # If the chunk ends with a sentence breaker, start a new line next time
        if text.strip().endswith(('.', '!', '?', '</verbal>')):
            sys.stdout.write("\n")
            self._is_mid_sentence = False
        else:
            sys.stdout.write(" ")  # Add space between chunks
            self._is_mid_sentence = True
            
        self.speech_done_event.set()

    def stop_speaking(self):
        """No-op stub matching the original interface."""
        pass

    def is_busy(self):
        """Always False since terminal print is instant."""
        return False

    def get_interruption_context(self):
        """Returns the interrupted text context."""
        return {'interrupted_text': self.current_speaking_text}


# =================================================================
# Stub: Terminal Ears (STT Replacement)
# =================================================================
class StubEars:
    """Replaces real STT. All listening methods are bypassed."""

    def __init__(self):
        self.trigger_word = get_setting('wake_word', 'jarvis')
        self.wake_word_pattern = re.compile(
            rf'\b{re.escape(self.trigger_word)}\b', re.IGNORECASE
        )
        self.is_actively_listening = False  # Required for WatchDog monitoring

    def set_language(self, lang):
        pass

    def deafen_for(self, duration):
        pass

    def listen(self):
        return ""

    def transcribe(self, audio_np, initial_prompt=""):
        return ""

    def start_background_listening(self, callback):
        pass

    def stop_background_listening(self):
        pass

    def listen_with_interruption(self, mouth_instance, timeout=120):
        return ""


# =================================================================
# SkipSTT Core Engine
# =================================================================
class SkipSTTCore(JARVISCore):
    """
    Terminal Test Harness subclassing JARVISCore.
    Provides a text-only interface to interact with the agentic loop.
    """

    def play_processing_cue(self):
        """Override: Silent in terminal mode."""
        pass

    def play_listening_cue(self):
        """Override: Silent in terminal mode."""
        pass

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def initialize(self):
        """
        Boots LLM, Memory, Tools, and WatchDog, but replaces 
        hardware audio components with terminal stubs.
        """
        local_api_url = get_setting('local_api_url', 'http://localhost:11434')

        print("\n🎬 [SkipSTT] Startup video SKIPPED (terminal mode)")

        print("📡 [SkipSTT] Ears SKIPPED -> using terminal input()")
        self.ears = StubEars()

        print("🔊 [SkipSTT] Mouth SKIPPED -> using print()")
        self.mouth = StubMouth()

        print("🧠 Loading Memory System...")
        self.memory = MemoryManager()

        print("🌐 Loading Browsing Tool...")
        self.browser = BrowsingTool(memory_manager=self.memory)

        print("📦 Registering Internal Tools...")
        from core.tools.default_tools import register_all_tools
        register_all_tools(self)

        print("🤖 Booting Local LLM Engine...")
        try:
            self.llm_client = LLMClient(base_url=local_api_url)
        except Exception as e:
            print(f"   ❌ LLM Boot failed: {e}")
            logger.error(f"LLM Boot failed: {e}")

        print("⏳ Warming up LLM and building KV-Cache...")
        max_retries = get_setting('warmup_max_retries', 5)
        warmup_tools = self._get_minified_tools()

        for attempt in range(max_retries):
            try:
                print(f"   [System] 🔥 Injecting Core System into VRAM & KV-Cache (Attempt {attempt+1}/{max_retries})...")

                static_sys, test_messages = self.build_messages("System check.")
                
                warmup_messages = list(test_messages)
                warmup_system = static_sys

                test_payload = {
                    "model": self.llm_client.normal_model,
                    "messages": warmup_messages,
                    "stream": False,
                    "keep_alive": get_setting('llm_keep_alive_high_perf', '15m'),
                    "tools": warmup_tools if self.llm_client.supports_native_tools else None,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 1,
                        "num_ctx": get_setting('llm_context_window', 4096)
                    }
                }
                if warmup_system:
                    test_payload["system"] = warmup_system

                import requests
                response = requests.post(
                    f"{self.llm_client.base_url}/api/chat",
                    json=test_payload,
                    timeout=get_setting('warmup_timeout', 60)
                )

                if response.ok:
                    print("   [System] 🔥 LLM Pre-ignition & Immutable Cache complete. Ready for instant replies.")
                    break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    print(f"   [System] ❌ Warmup failed: {e}")
                    logger.error(f"[System] Warmup failed: {e}")
                    print("   [System] ⚠️ KV-Cache warmup failed, but native tool support is preserved.")
                    logger.warning("[System] KV-Cache warmup failed, but native tool support is preserved.")

        # Initialize WatchDog Background Daemon
        from core.watch_dog import WatchDog
        self.watch_dog = WatchDog(self)
        self.watch_dog.start()

        self.initialization_complete = True
        print("\n✅ All systems online! (Terminal Mode — type commands below)")
        print("   💡 Type 'exit' or 'shutdown' to quit.\n")

    # ------------------------------------------------------------------
    # Execution Loop
    # ------------------------------------------------------------------
    def run(self):
        """
        Replaces the mic-based wake-word loop with a terminal input stream.
        """
        if not self.initialization_complete:
            self.initialize()

        self.running = True

        print("=" * 60)
        print(f"   ⌨️  {self.assistant_name.upper()} — TERMINAL MODE")
        print("   🛑 Type 'exit' or 'shutdown' to stop")
        print("=" * 60 + "\n")

        while self.running:
            try:
                command = input(f"  [{self.assistant_name}] You: ").strip()

                if not command:
                    continue

                if command.lower() in ('exit', 'shutdown'):
                    print(f"  🔊 [JARVIS]: Shutting down all systems. Goodbye sir.")
                    self.running = False
                    break

                print(f"\n🚀 Executing: {command}")
                self._is_currently_speaking_tool_intro = False

                response = self.process_command(command)
                if response:
                    self.mouth.speak(response)

                self.last_speech_time = time.time()
                self.state.enter_follow_up()
                
                self.play_listening_cue() 
                self.state.clear_temp_memory()
                print()

            except KeyboardInterrupt:
                print("\n\n🛑 Interrupted by user (Ctrl+C).")
                self.running = False
                break
            except EOFError:
                print("\n\n🛑 EOF — exiting.")
                self.running = False
                break
            except Exception as e:
                print(f"\n❌ Loop Error: {e}")
                logger.error(f"Loop Error: {e}")

        self.watch_dog.stop()
        print(f"\n✅ {self.assistant_name.upper()} shutdown complete.")