# core/jarvis_engine.py  #? (Hmody: what a pice of art)

"""
JARVIS Core Engine
==================
The main autonomous engine handling LLM invocation, tool dispatching, 
audio pipelines, and system state management.
"""

import os
import re
import json
import time
import random
import threading
import platform
import requests
import difflib 
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from thefuzz import process, fuzz

logger = logging.getLogger(__name__)

# --- Internal Components ---
from core.tools.registry import ToolRegistry
from core.audio.stt_engine import Ears
from core.audio.tts_engine import Mouth
from core.memory import MemoryManager
from core.tools.browsing_tool import BrowsingTool
from core.config import config, STARTUP_VIDEO_PATH, INTRO_VIDEO_PATH, PROCESSING_SOUND, LISTENING_SOUND, get_setting
from core.llm_client import LLMClient  # Transport & I/O layer

# --- Decoupled Modules ---
from core.ui.video_player import VideoPlayer
from core.tools.default_tools import register_all_tools, SILENT_TOOLS, FREE_TOOLS

# =================================================================
# Interrupt State Machine
# =================================================================
class InterruptState:
    """
    Formal interrupt states for the realtime voice agent architecture.
    Priority: User Interrupt > Safety > Tool Execution > Quality > Completeness
    """
    IDLE = "idle"                        # No active processing
    PROCESSING = "processing"            # LLM is generating (State 1: Thinking Interrupt territory)
    SPEAKING = "speaking"                # TTS is outputting (State 2: Speech Interrupt territory)
    FOLLOW_UP = "follow_up"              # Waiting for user input after interrupt/completion
    INTERRUPTED_THINKING = "int_think"   # Aborted during LLM generation
    INTERRUPTED_SPEECH = "int_speech"    # Aborted during TTS output


# =================================================================
# State Manager
# =================================================================
class StateManager:
    """
    Runtime state container (lives only while the program runs).
    Manages language mode, listening flags, temp memory, user location,
    and the formal interrupt state machine.
    """

    def __init__(self):
        self.always_listening  = False
        self.overthinking_mode = False
        self.root_mode         = False   # Bypasses all permission checks when True
        self.current_chat_history = []
        self.temp_memory       = []
        self.active_permissions = {}
        
        # Queue to hold a blocked tool call for auto-resuming
        self.pending_tool_call = None 

        # Tracks last successfully accessed file workspace (e.g. "desktop/", "shared_area/Projects/")
        self.last_file_path = ""

        # Formal Interrupt State Machine
        self.interrupt_state = InterruptState.IDLE
        self.interrupted_position = ""      # Last spoken text before mid-speech interrupt
        self.interrupted_context = {}       # Preserved context for optional resume
        self.pending_resume_data = None     # Stored interrupted task data if user wants to continue

        # Fetch location once at boot
        self.user_location = self._fetch_location()
        self.user_name = get_setting('user_name', '')
        self.os_type       = platform.system().lower()
        print(f"💻 OS Detected: {self.os_type.capitalize()}")
        
        # Cached persona at boot
        self._cached_persona = None
        self._cached_overthinking = None
        self._static_system_content = None

    def _fetch_location(self) -> str:
        """DB first, then optional IP-API fallback."""
        db_location = get_setting('user_location', '')
        if db_location:
            print(f"🌍 Location loaded from DB: {db_location}")
            return db_location

        allow_api = get_setting('external_api', False)
        if allow_api:
            try:
                response = requests.get("http://ip-api.com/json/", timeout=3)
                if response.status_code == 200:
                    data    = response.json()
                    country = data.get('country', 'Unknown Country')
                    print(f"🌍 Auto-detected Location (Country Only): {country}")
                    return country
            except Exception as e:
                print(f"⚠️ Could not auto-detect location: {e}")
                logger.warning(f"Could not auto-detect location: {e}")
        else:
            print("🔒 External location API blocked by privacy settings.")

        return (
            "Unknown (Location auto-detection is off. If you need the user's location for "
            "weather or local queries, politely ask them for it. NOTE: Your internet, "
            "browsing, and YouTube tools are STILL FULLY ACTIVE and functional)."
        )
    
    def grant_permission(self, action: str, minutes: int = 10):
        self.active_permissions[action.lower().strip()] = time.time() + (minutes * 60)
        print(f"🔑 [Security] Permission granted for '{action}' ({minutes}m).")

    def get_permissions_context(self) -> str:
        current_time = time.time()
        expired = [k for k, v in self.active_permissions.items() if current_time > v]
        for k in expired:
            del self.active_permissions[k]
            print(f"🔒 [Security] Permission expired for '{k}'.")
            
        if not self.active_permissions:
            return ""
        
        valid = list(self.active_permissions.keys())
        return "ACTIVE PERMISSIONS: " + ", ".join(valid)

    def set_always_listening(self, enabled: bool):
        self.always_listening = enabled
        print(f"👂 Always Listening: {'ON' if enabled else 'OFF'}")

    def add_temp_memory(self, item: str):
        self.temp_memory.append(item)
        print(f"💾 Temp Memory: {item}")

    def clear_temp_memory(self):
        self.temp_memory = []
        print("🗑️ Temp Memory cleared")

    def get_temp_memory_context(self) -> str:
        if not self.temp_memory:
            return ""
        return "Temporary Context:\n" + "\n".join(self.temp_memory)

    # ------------------------------------------------------------------
    # Interrupt State Machine Transitions
    # ------------------------------------------------------------------
    def transition_to(self, new_state: str):
        """Formal state transition with logging."""
        old = self.interrupt_state
        self.interrupt_state = new_state
        if old != new_state:
            print(f"\n   🔄 [State] {old} → {new_state}")

    def handle_thinking_interrupt(self):
        """State 1: Abort during LLM generation. Clears all pending context."""
        self.transition_to(InterruptState.INTERRUPTED_THINKING)
        self.interrupted_context = {}
        self.pending_resume_data = None
        print("   ⚡ [Interrupt] Thinking aborted — entering follow-up window")
        self.transition_to(InterruptState.FOLLOW_UP)

    def handle_speech_interrupt(self, position_text: str, context: dict = None):
        """State 2: Abort during TTS output. Preserves interrupted position for optional resume."""
        self.transition_to(InterruptState.INTERRUPTED_SPEECH)
        self.interrupted_position = position_text
        self.interrupted_context = context or {}
        print(f"   ⚡ [Interrupt] Speech aborted at: \"...{position_text[-40:]}\"")
        self.transition_to(InterruptState.FOLLOW_UP)

    def enter_follow_up(self):
        """Natural completion — enter follow-up window without interrupt markers."""
        self.transition_to(InterruptState.FOLLOW_UP)

    def reset_interrupt(self):
        """Clear all interrupt state when starting a new command."""
        self.interrupt_state = InterruptState.IDLE
        self.interrupted_position = ""
        self.interrupted_context = {}


# =================================================================
# Internal Command Processor
# =================================================================
class InternalCommandProcessor:
    """
    Handles hardcoded shortcut commands (startup video, language mode, etc.)
    before the LLM even sees the input. Acts as a pre-filter.
    """

    def __init__(self, jarvis_core):
        self.jarvis = jarvis_core

        self.commands = {
            'jarvis start up':           self._startup_video,
            'jarvis startup':            self._startup_video,
            'start up':                  self._startup_video,
            'startup':                   self._startup_video,
            'introduce yourself':        self._introduce_video,
            'jarvis introduce yourself': self._introduce_video,
            
            # --- Settings Panel ---
            'nexus panel':               self._open_settings,
            'settings panel':            self._open_settings,
            'show settings':       self._open_settings,
            'show panel':                self._open_settings,
            
            # --- Always Listening Synonyms ---
            'always listening on':       lambda: self._set_always_listening(True),
            'enable always listening':   lambda: self._set_always_listening(True),
            'activate always listening': lambda: self._set_always_listening(True),
            'turn on always listening':  lambda: self._set_always_listening(True),
            
            'always listening off':      lambda: self._set_always_listening(False),
            'disable always listening':  lambda: self._set_always_listening(False),
            'turn off always listening': lambda: self._set_always_listening(False),

            # --- Root Mode Synonyms ---
            'root mode on':               lambda: self._set_root_mode(True),
            'root access on':             lambda: self._set_root_mode(True),
            'enable root mode':           lambda: self._set_root_mode(True),
            'enable root access':         lambda: self._set_root_mode(True),
            'activate root mode':         lambda: self._set_root_mode(True),
            'turn on root mode':          lambda: self._set_root_mode(True),
            
            'root mode off':              lambda: self._set_root_mode(False),
            'root access off':            lambda: self._set_root_mode(False),
            'disable root mode':          lambda: self._set_root_mode(False),
            'disable root access':        lambda: self._set_root_mode(False),
            'deactivate root mode':       lambda: self._set_root_mode(False),
            'turn off root mode':         lambda: self._set_root_mode(False),
            
            # --- Overthinking Mode Synonyms ---
            'overthinking mode on':       lambda: self._set_overthinking(True),
            'enable overthinking mode':   lambda: self._set_overthinking(True),
            'activate overthinking mode': lambda: self._set_overthinking(True),
            'turn on overthinking mode':  lambda: self._set_overthinking(True),
            
            'overthinking mode off':      lambda: self._set_overthinking(False),
            'disable overthinking mode':  lambda: self._set_overthinking(False),
            'turn off overthinking mode': lambda: self._set_overthinking(False),
        }

    def process(self, command: str) -> Tuple[bool, Optional[str]]:
        command_lower = command.lower().strip()

        # 1. New Guard: Ignore common short greetings from fuzzy matching
        ignore_keywords = ['hello', 'hi', 'hey']
        if any(command_lower == kw or command_lower == f"{kw} jarvis" for kw in ignore_keywords):
            return False, None

        # 2. Strict Fuzzy matching
        try:
            available_commands = list(self.commands.keys())
            
            # Use token_sort_ratio: compares word sets regardless of order, but very strict on word identity
            best_match, score = process.extractOne(
                command_lower, 
                available_commands, 
                scorer=fuzz.token_sort_ratio
            )
            
            if score >= 85:
                print(f"🪄 [System] Strict Fuzzy matched: '{best_match}' (Confidence: {score}%)")
                return True, self.commands[best_match]()
        except ImportError:
            pass

        return False, None

    def _run_video_only(self, video_path: str, reply_text: str = "") -> str:
        """Plays the video naturally (blocking) and handles mic state without hardcoded durations."""
        print(f"🎬 [System] Playing sequence: {video_path}")
        
        if self.jarvis.ears:
            if hasattr(self.jarvis.ears, 'stop_background_listening'):
                self.jarvis.ears.stop_background_listening()
            print(" 🔇 [Ears] Mic paused. Waiting for visual sequence to finish naturally...")
            
        # Execute and wait until the video closes naturally
        self.jarvis.video_player.play_video(video_path, blocking=True)

        print(" 🔊 [Ears] Visual sequence finished. Mic is ready.")

        return reply_text

    def _startup_video(self) -> str:
        return self._run_video_only(
            video_path = STARTUP_VIDEO_PATH,
            reply_text = ""
        )

    def _introduce_video(self) -> str:
        return self._run_video_only(
            video_path = INTRO_VIDEO_PATH,
            reply_text = ""
        )

    def _set_always_listening(self, enabled: bool) -> str:
        self.jarvis.state.set_always_listening(enabled)
        return f"Always listening mode {'enabled' if enabled else 'disabled'}."

    def _set_root_mode(self, enabled: bool) -> str:
        """Toggle root mode: bypasses ALL permission/security checks on protected tools."""
        self.jarvis.state.root_mode = enabled
        if enabled:
            print("🔓 [Security] ROOT MODE ACTIVATED — All permission gates bypassed.")
            return "Root mode ENABLED. All actions will execute directly without permission prompts."
        else:
            print("🔒 [Security] ROOT MODE DEACTIVATED — Normal permission gates restored.")
            return "Root mode DISABLED. Standard security prompts are back in effect."

    def _set_overthinking(self, enabled: bool) -> str:
        self.jarvis.state.overthinking_mode = enabled
        status = (
            "ENABLED. I will now analyze and synthesize information deeply."
            if enabled else
            "DISABLED. Back to concise responses."
        )
        return f"Overthinking mode {status}"

    def _open_settings(self) -> str:
        print("⚙️ [System] Launching Settings Panel...")
        try:
            import subprocess
            import sys
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--settings"])
            else:
                subprocess.Popen([sys.executable, "app.py", "--settings"])
        except Exception as e:
            print(f"❌ [System] Error launching settings panel: {e}")
            logger.error(f"[System] Error launching settings panel: {e}")
            
        return "Opening settings panel."

# =================================================================
# JARVIS Core (Orchestrator)
# =================================================================
class JARVISCore:
    """
    The top-level coordinator.
    Owns the Agentic Loop, tool dispatch, TTS/STT lifecycle, and chat history.
    """

    def __init__(self):
        self.assistant_name = get_setting('assistant_name', 'Jarvis')

        print("\n" + "=" * 60)
        print(f"   🤖 {self.assistant_name.upper()} - Core System Online")
        print("=" * 60)

        # Component placeholders (filled during initialize())
        self.ears         = None
        self.mouth        = None
        self.memory       = None
        self.browser      = None
        self.llm_client   = None

        # Always-available subsystems
        self.video_player      = VideoPlayer()
        self.state             = StateManager()
        self.internal_commands = InternalCommandProcessor(self)
        self.tool_registry     = ToolRegistry()

        # Runtime flags
        self.running                               = False
        self.initialization_complete               = False
        self.chat_history                          = []
        self._is_currently_speaking_tool_intro     = False
        self.last_speech_time                      = 0.0
        self.pending_command                       = ""

        # Tracked by WatchDog for Golden Opportunity pre-generation
        self._llm_busy = False
        self._llm_free_event = threading.Event()
        self._llm_free_event.set()  # Free by default

        print("\n🔧 Initializing components...")

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------
    def initialize(self):
        # FAST PRE-CHECK: If any required component is missing, run the wizard immediately and block.
        from core.bootstrap.env_setup import check_and_run_wizard
        if not check_and_run_wizard():
            print("❌ [Bootstrap] Setup incomplete or wizard was closed without fixing. Terminating system.")
            logger.critical("[Bootstrap] Setup incomplete or wizard was closed without fixing. Terminating system.")
            import sys
            sys.exit(1)
            
        startup_show  = get_setting('startup_show', True)
        local_api_url = get_setting('local_api_url', 'http://localhost:11434')

        video_path     = STARTUP_VIDEO_PATH
        video_duration = get_setting('startup_video_duration', 17.0)

        if startup_show and os.path.exists(video_path):
            print(f"\n🎬 Booting Core Sequences (Parallel Mode)...")
            self.video_player.play_video(video_path, duration=video_duration, blocking=False)

        print("📦 Registering Internal Tools...")
        register_all_tools(self)

        # ---------------------------------------------------------
        # The Master Boot Thread (LLM + Warmup)
        # ---------------------------------------------------------
        llm_ready_event = threading.Event()

        def async_llm_boot_and_warmup():
            """
            ==============================================================================
            [ARCHITECTURAL NOTE: THE KV-CACHE PREFIX MATCHING EQUATION]
            If UI Video is enabled: We build the heavy Static Data (System Prompt + Tools) 
            in this background thread while the video plays (takes ~15s masked by 17s video).
            
            Even if disabled, we force this warmup before saying "Systems Online".
            When the user speaks their FIRST_MESSAGE, we send Static + Flex Data.
            Ollama's Prefix Caching will recognize the Static part is identical, 
            skip rebuilding it entirely, and ONLY compute the new Flex Data. 
            Result: Near-instant Time-To-First-Token (TTFT) on the very first interaction!
            ==============================================================================
            """
            try:
                print("🤖 Booting Local LLM Engine in background...")
                # 1. Initialize the heavy LLM Client (Loads model into RAM)
                self.llm_client = LLMClient(base_url=local_api_url)
                
                print("⏳ Warming up LLM and building KV-Cache...")
                max_retries = get_setting('warmup_max_retries', 5)
                
                # 2. Build exact tools schema for perfect Hash Matching
                warmup_tools = self._get_minified_tools()

                # 3. Inject into Cache
                for attempt in range(max_retries):
                    try:
                        print(f"   [System] 🔥 Injecting Core System into VRAM & KV-Cache (Attempt {attempt+1}/{max_retries})...")
                        
                        # Native tool support was already determined in _ensure_model_exists()
                        static_sys, test_messages = self.build_messages("System check.")
                        
                        warmup_messages = list(test_messages)
                        warmup_system = static_sys

                        test_payload = {
                            "model": self.llm_client.normal_model,
                            "messages": warmup_messages,
                            "stream": False,  #? (Hmody: change it and u will regret it)    *it taked from me 3h to discover what happend 
                            "keep_alive": get_setting('llm_keep_alive_high_perf', '15m'),
                            # Only send tools schema if the model supports native tool calling
                            "tools": warmup_tools if self.llm_client.supports_native_tools else None,
                            "options": {
                                "temperature": 0.1,
                                "num_predict": 1,
                                "num_ctx": get_setting('llm_context_window', 4096)
                            }
                        }
                        if warmup_system:
                            test_payload["system"] = warmup_system
                        
                        response = requests.post(
                            f"{self.llm_client.base_url}/api/chat", 
                            json=test_payload, 
                            timeout=get_setting('warmup_timeout', 60)
                        )
                        
                        if response.ok:
                            print("   [System] 🔥 LLM Pre-ignition & Immutable Cache complete. Ready for instant replies.")
                            # Cache Key generation for warmup debugging
                            import hashlib
                            sys_hash = hashlib.md5(static_sys.encode()).hexdigest()[:8]
                            tools_hash = hashlib.md5(json.dumps(warmup_tools, sort_keys=True).encode()).hexdigest()[:8] if warmup_tools else "none"
                            print(f"   🔑 [Cache Key - Warmup] sys={sys_hash} tools={tools_hash}")
                            break 
                    except Exception as e:
                        if attempt < max_retries - 1:
                            time.sleep(2) 
                        else:
                            print(f"   [System] ❌ Warmup failed: {e}")
                            logger.error(f"[System] Warmup failed: {e}")
                            # Warmup is a KV-Cache optimization; its failure must not cripple tool calling.
            except Exception as e:
                print(f"   [System] ❌ Fatal error in LLM Boot Thread: {e}")
                logger.critical(f"[System] Fatal error in LLM Boot Thread: {e}")
            finally:
                llm_ready_event.set()

        # 🚀 START THE HEAVY LIFTING IMMEDIATELY IN PARALLEL
        threading.Thread(target=async_llm_boot_and_warmup, daemon=True).start()

        # ---------------------------------------------------------
        # Main Thread: Load lightweight local components
        # ---------------------------------------------------------
        print("\n📡 Loading Ears (Speech Recognition)...")
        self.ears = Ears()
        if hasattr(self.ears, 'set_language'):
            self.ears.set_language('en')
        if startup_show:
            self.ears.deafen_for(video_duration)

        print("🔊 Loading Mouth (Text-to-Speech)...")
        self.mouth = Mouth()

        print("🧠 Loading Memory System...")
        self.memory = MemoryManager()

        print("🌐 Loading Browsing Tool...")
        self.browser = BrowsingTool(memory_manager=self.memory)

        from core.watch_dog import WatchDog
        self.watch_dog = WatchDog(self)
        self.watch_dog.start()

        # ---------------------------------------------------------
        # Sync Point: Wait for LLM Boot & Video to finish
        # ---------------------------------------------------------
        if not llm_ready_event.wait(timeout=60):
            print("⚠️ [System] LLM Boot Thread timed out. Proceeding with caution.")
            logger.warning("[System] LLM Boot Thread timed out. Proceeding with caution.")

        # Ensure the video process finishes naturally before we declare "Systems Online"
        if startup_show and hasattr(self.video_player, 'current_process') and self.video_player.current_process:
            if getattr(self.video_player.current_process, 'poll', None) and self.video_player.current_process.poll() is None:
                print("🎬 Waiting for visual sequence to conclude...")
                self.video_player.current_process.wait()

        self.initialization_complete = True

        print("\n✅ All systems online!")
        self.mouth.speak("Systems online. I am ready to assist you, sir.")
        self.mouth.speech_done_event.wait(timeout=15)

        self.last_speech_time = time.time()

    # ------------------------------------------------------------------
    # Tool Execution Helpers
    # ------------------------------------------------------------------
    def get_available_tools(self) -> List[Dict]:
        return self.tool_registry.get_all_schemas()

    def execute_tool(self, tool_name: str, arguments: Dict) -> str:
        success, result_message = self.tool_registry.execute_tool(tool_name, arguments)
        return result_message

    def _get_minified_tools(self) -> list:
        """Single source of truth for minified tool schemas."""
        if not hasattr(self, '_cached_minified_tools') or self._cached_minified_tools is None:
            raw_tools = self.get_available_tools()
            minified = []
            for schema in raw_tools:
                clean = json.loads(json.dumps(schema))
                try:
                    props = clean.get("function", {}).get("parameters", {}).get("properties", {})
                    for _, details in list(props.items()):
                        if "description" in details:
                            desc = details["description"]
                            if "CRITICAL" not in desc and "Required" not in desc:
                                del details["description"]
                except Exception:
                    pass
                minified.append(clean)
            self._cached_minified_tools = minified
        return self._cached_minified_tools

    # =================================================================
    # Audio Cues & Background Generation Methods
    # =================================================================
    def _play_audio_cue(self, cue_path: str):
        """Helper to run non-blocking audio cues based on the OS."""
        if not config.get('sound_effects', True):
            return
        if not cue_path or not os.path.exists(cue_path):
            return
            
        def _play():
            try:
                if self.state.os_type == 'windows':
                    import winsound
                    winsound.PlaySound(cue_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    import subprocess
                    subprocess.Popen(['aplay', cue_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:
                print(f"⚠️ [Cue] Audio playback failed for {cue_path}: {e}")
                logger.warning(f"[Cue] Audio playback failed for {cue_path}: {e}")
                
        threading.Thread(target=_play, daemon=True).start()

    def play_processing_cue(self):
        """Runs non-blocking whenever a request is sent to the LLM."""
        self._play_audio_cue(PROCESSING_SOUND)

    def play_listening_cue(self):
        """Runs non-blocking when the follow-up window starts."""
        self._play_audio_cue(LISTENING_SOUND)

    def pregenerate_text(self, prompt: str) -> str:
        """
        Invoked by WatchDog during Golden Opportunity. 
        Independent LLM call — does not affect the main conversation's KV Cache.
        """
        if not self.llm_client or not self._llm_free_event.is_set():
            return ""

        self.play_processing_cue()

        system = (
            "You are a concise voice assistant. "
            "Output ONE plain spoken sentence only. "
            "No XML tags, no <verbal>, no preamble. Just the sentence."
        )
        messages = [{'role': 'user', 'content': prompt}]

        try:
            self._llm_busy = True
            self._llm_free_event.clear()

            response = self.llm_client.generate_response(
                messages,
                system_prompt=system,
                is_overthinking=False,
                tools=None,
                temperature=0.1
            )

            text = response.get('text', '').strip()
            # Clean up any accidental leftover tags
            text = re.sub(r'(?i)</?verbal>', '', text).strip()
            text = re.sub(r'(?si)<reasoning>.*?</reasoning>', '', text).strip()
            return text

        except Exception as e:
            print(f"❌ [Pregenerate] LLM call failed: {e}")
            logger.error(f"[Pregenerate] LLM call failed: {e}")
            return ""
        finally:
            self._llm_busy = False
            self._llm_free_event.set()

    # =================================================================
    # Message Builder (KV-Cache Prefix Matching Optimized) #? (Hmody: look how beauty it looks)
    # =================================================================
    def build_messages(self, user_input: str) -> Tuple[str, List[Dict]]:
        from core.config import config, SYSTEM_PROMPT, TOOL_RULES, OVER_THINKING_PROMPT, QUICK_MODE_PROMPT, NATIVE_JSON_PROMPT
        from datetime import datetime

        current_assistant_name = config.get('assistant_name', 'Jarvis')
        current_tool_maximum = config.get('tool_maximum', 3)
        
        # Cache persona lookup - only re-fetch from DB when explicitly changed
        active_persona = self.state._cached_persona
        if active_persona is None:
            active_persona = config.get_active_persona()
            self.state._cached_persona = active_persona
        
        current_overthinking = self.state.overthinking_mode
        
        # =================================================================
        # 🟢 THE IMMUTABLE LAYER (Role: System)
        # =================================================================
        # Only rebuild the system prompt when overthinking_mode, persona, or tool_maximum change
        if (self.state._static_system_content is None 
            or self.state._cached_overthinking != current_overthinking
            or getattr(self.state, '_cached_tool_maximum', None) != current_tool_maximum):
            
            self.state._cached_overthinking = current_overthinking
            self.state._cached_tool_maximum = current_tool_maximum 
            immutable_parts = []
            
            # 1. System Prompt
            immutable_parts.append(SYSTEM_PROMPT.format(assistant_name=current_assistant_name))
            
            # 2. Tool Rules 
            tool_rules_clean = TOOL_RULES.replace("{user_loc}", "Check Dynamic Context for Location")
            tool_rules_clean = tool_rules_clean.replace("{tool_maximum}", str(current_tool_maximum))
            immutable_parts.append(tool_rules_clean)
            
            # 3. Active Persona
            immutable_parts.append(f"--- PERSONALITY GUIDELINES ---\n{active_persona.get('prompt', '')}")
            
            # 4. NATIVE Instructions
            native_clean = NATIVE_JSON_PROMPT.replace("{tool_maximum}", str(current_tool_maximum))
            immutable_parts.append(native_clean)
                
            # 5. Cognitive Mode (Overthinking vs Quick Mode)
            if current_overthinking:
                immutable_parts.append(OVER_THINKING_PROMPT)
            else:
                immutable_parts.append(QUICK_MODE_PROMPT)
                
            # 6. System Info
            immutable_parts.append(
                "[SYSTEM INFO]\n"
                "Architecture: JARVIS NEXUS, developed by VANT company, and open source community\n"
                f"OS Environment: {self.state.os_type}\n"
                f"Location: {self.state.user_location}"
            )

            self.state._static_system_content = "\n\n".join(immutable_parts)

        static_system_content = self.state._static_system_content

        # =================================================================
        # 🟡 THE HISTORICAL LAYER (Roles: User / Assistant)
        # =================================================================
        messages = []

        # A. Fetch previous Chat History
        history_limit = get_setting('history_limit', 6)
        if len(self.chat_history) > history_limit:
            messages.extend(self.chat_history[-history_limit:])
        else:
            messages.extend(self.chat_history)

        # B. Build Dynamic Context
        dynamic_context = []
        
        if temp_ctx := self.state.get_temp_memory_context():
            dynamic_context.append(f"Temp Memory:\n{temp_ctx}")
            
        if self.memory:
            time_aware_context = self.memory.get_time_aware_context()
            if time_aware_context:
                dynamic_context.append(f"Retrieved Memory:\n{time_aware_context}")
            
        if perms_ctx := self.state.get_permissions_context():
            dynamic_context.append(f"Security Context:\n{perms_ctx}")

        # Only create a header if there is actually dynamic data
        dynamic_header = ""
        if dynamic_context:
            dynamic_header = "--- SYSTEM DYNAMIC CONTEXT ---\n" + "\n".join(dynamic_context) + "\n\n"

        current_time = datetime.now().strftime('%A, %B %d, %Y %I:%M %p')
        
        # Small 4B LLMs ignore the static SYSTEM_PROMPT, so we inject it HERE where attention is highest.
        user_location = getattr(self.state, 'user_location', 'Unknown')

        raw_user_name = getattr(self.state, 'user_name', '').strip()
        safe_user_name = raw_user_name if raw_user_name else "Unknown (Address as Sir or Boss)"
        
        # Safe Path Extraction for Spatial Awareness
        _last_path_str = ""
        _last_path = getattr(self.state, 'last_file_path', '')
        
        if _last_path:
            try:
                _path_obj = Path(_last_path)
                _target_file = _path_obj.name
                _parent_dir = _path_obj.parent
                _active_dir = str(_parent_dir).replace('\\', '/')
                
                if _active_dir in (".", "/"):
                    _active_dir = "shared_area"
                    
                _last_path_str = f" | active_dir={_active_dir} | target_file={_target_file}"
            except Exception:
                _last_path_filename = _last_path.rstrip('/').split('/')[-1] if _last_path else ""
                _last_path_str = f" | target_file={_last_path_filename}" if _last_path_filename else ""

        final_user_content = (
            f"{dynamic_header}"
            f"--- USER MESSAGE ---\n{user_input}\n"
            f"[sys: time={current_time} | loc={user_location}{_last_path_str} | user={safe_user_name} | "
            f"use time/loc/user ONLY if user explicitly asks, do NOT volunteer it]"
        )
        
        messages.append({'role': 'user', 'content': final_user_content})

        return static_system_content, messages

    # ------------------------------------------------------------------
    # Process Command (Interrupt-Aware Agentic Loop)
    # ------------------------------------------------------------------
    def process_command(self, command: str) -> str:
        # Reset interrupt state at the start of every new command cycle
        self.state.reset_interrupt()
        
        is_internal, response = self.internal_commands.process(command)
        if is_internal:
            return response

        # Engine-Level Permission Auto-Grant
        _AFFIRMATIVE = {'yes', 'yeah', 'yep', 'sure', 'go on', 'go ahead', 'do it', 'proceed',
                        'approved', 'granted', 'permission granted', 'you have my permission',
                        'u have my permission', 'i agree', 'ok', 'okay', 'confirm', 'confirmed',
                        'allow', 'allow it', 'accept'}
        cmd_clean = command.lower().strip(' ,.!?')
        
        auto_resume_feedback = ""
        
        if self.state.pending_tool_call and any(af in cmd_clean for af in _AFFIRMATIVE):
            pending = self.state.pending_tool_call
            tool_name = pending['name']
            tool_args = pending['args']
            self.state.pending_tool_call = None
            
            # Auto-grant permission for this tool (and its group siblings)
            from core.tools.default_tools import _handle_grant_permission
            _handle_grant_permission({'tool_name': tool_name, 'minutes': 10}, self)
            print(f"🔑 [Engine] Auto-granted permission for '{tool_name}' and auto-resuming...")
            result = self.execute_tool(tool_name, tool_args)
            
            auto_resume_feedback = f"[SYSTEM: User granted permission. Tool '{tool_name}' was automatically executed. Result:\n{result}\nINSTRUCTION: Formulate a natural response based ONLY on this result.]"

        static_system_payload, messages = self.build_messages(command)
        
        if auto_resume_feedback:
            messages.append({'role': 'user', 'content': auto_resume_feedback})

        tools_payload = None
        if self.llm_client.supports_native_tools:
            tools_payload = self._get_minified_tools()

        # Cache Hash printing for Live Request debugging
        _sys_hash = hashlib.md5(static_system_payload.encode()).hexdigest()[:8]
        _tools_hash = hashlib.md5(json.dumps(tools_payload, sort_keys=True).encode()).hexdigest()[:8] if tools_payload else "none"
        print(f"   🔑 [Cache Key - Request] sys={_sys_hash} tools={_tools_hash}")
        
        # Dynamic limits configuration
        overthink_iters = get_setting('overthink_iterations', 5)
        fast_iters = get_setting('fast_iterations', 3)
        tool_max = get_setting('tool_maximum', 3)
        
        max_iterations = overthink_iters if self.state.overthinking_mode else fast_iters
        final_unspoken_text = ""

        try:
            # LLM Busy Flag + Processing Cue 
            self._llm_busy = True
            self._llm_free_event.clear()
            self.play_processing_cue()

            _tool_announced = threading.Event()

            def _build_announcement(tool_calls_raw: list) -> str:
                phrases = []
                for tc in tool_calls_raw:
                    if isinstance(tc, dict):
                        name = tc.get("function", {}).get("name", tc.get("name", ""))
                        if name and not any(name == ex_name for ex_name, _ in _executed_tool_signatures):
                            tool_spec = self.tool_registry.get_tool(name)
                            if tool_spec and tool_spec.announcement:
                                phrases.append(tool_spec.announcement)
            
                if not phrases: return "" 
                if len(phrases) == 1: return f"{phrases[0]}"
                return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"

            def on_tool_start(tool_calls_raw: list):
                if _tool_announced.is_set():
                    return
                _tool_announced.set()
                
                announcement = _build_announcement(tool_calls_raw)
                if not announcement: 
                    return
                
                if get_setting('dev_mode', False):
                    print(f"🎙️ [Acoustic ACK]: {announcement}")
                    self.state.transition_to(InterruptState.SPEAKING)
                    self.mouth.speak(announcement)

            instant_spoken_chunks = []
            _error_retry_budget = {}

            def stream_interpreter(chunk: str):
                chunk_clean = chunk.strip()
                if not chunk_clean: return
                
                if bool(re.search(r'(?i)^<reasoning|^<tool_call|^\{', chunk_clean)):
                    return

                speak_text = re.sub(r'(?i)</?verbal>', '', chunk_clean).strip()

                if speak_text and speak_text.upper() != "NONE":
                    instant_spoken_chunks.append(speak_text)
                    self.state.transition_to(InterruptState.SPEAKING)
                    self._is_currently_speaking_tool_intro = True
                    self.mouth.speak(speak_text)
                    self._is_currently_speaking_tool_intro = False

            _current_iter_idx = 0  
            _executed_tool_signatures = set() 

            while _current_iter_idx < max_iterations:
                _current_iter_idx += 1
                current_iteration = _current_iter_idx  

                _tool_announced.clear()
                _loop_label = f"[LOOP {_current_iter_idx}/{max_iterations}]"
                abort_event = threading.Event()

                def on_background_speech(audio_np):
                    text = self.ears.transcribe(audio_np, initial_prompt="Listen carefully.")
                    if not text: return
                    
                    cleaned_text = text.lower().strip(" ,.!?")
                    
                    # Check for trigger word FIRST (before anti-echo)
                    has_trigger = self.ears.trigger_word.lower() in text.lower()
                    
                    # Smart Anti-Echo Filter for Background Listening
                    recent_history = getattr(self.mouth, 'spoken_history', [])[-3:]
                    current_tts = getattr(self.mouth, 'current_speaking_text', '')
                    if current_tts:
                        recent_history.append(current_tts)
                    combined_tts = " ".join(recent_history).lower()
                    
                    if combined_tts:
                        # Near-exact echo → always block (even if wake word is in the TTS itself)
                        if cleaned_text in combined_tts or difflib.SequenceMatcher(None, cleaned_text, combined_tts).ratio() > 0.85:
                            return
                        # Partial echo → block ONLY if user did NOT say the trigger word
                        if not has_trigger and difflib.SequenceMatcher(None, cleaned_text, combined_tts).ratio() > 0.40:
                            return

                    if has_trigger:
                        abort_event.set()
                        self.mouth.stop_speaking()
                        
                        match = self.ears.wake_word_pattern.search(text)
                        if match:
                            remainder = text[match.end():].strip(" ,.!?")
                            if len(remainder) > 2:
                                self.pending_command = remainder
                            else:
                                self.pending_command = "SYSTEM_WAKE"

                def delayed_listener_start():
                    abort_event.wait(timeout=0.5)
                    if not abort_event.is_set():
                        self.ears.start_background_listening(on_background_speech)
                
                listener_thread = threading.Thread(target=delayed_listener_start, daemon=True)
                listener_thread.start()

                _ttft_anchor = time.time()
                self.state.transition_to(InterruptState.PROCESSING)

                _active_temperature = (
                    get_setting('overthink_temperature', 0.3)
                    if self.state.overthinking_mode else 0.1
                )

                llm_response = self.llm_client.generate_response(
                    messages,
                    system_prompt=static_system_payload,
                    is_overthinking=self.state.overthinking_mode,
                    tools=tools_payload,
                    temperature=_active_temperature,
                    line_callback=stream_interpreter,
                    abort_event=abort_event,
                    on_tool_start_callback=on_tool_start,
                    ttft_anchor=_ttft_anchor
                )

                self.ears.stop_background_listening()

                if llm_response.get('aborted'):
                    current_state = self.state.interrupt_state
                    if current_state == InterruptState.SPEAKING:
                        ctx = self.mouth.get_interruption_context()
                        self.state.handle_speech_interrupt(
                            position_text=ctx.get('interrupted_text', ''),
                            context={'chat_history': list(self.chat_history), 'command': command}
                        )
                    else:
                        self.state.handle_thinking_interrupt()
                    # Capture partial response for history, then exit loop cleanly
                    clean_text = llm_response.get('text', '')
                    unified_tools = llm_response.get('tools', [])
                    final_unspoken_text = ""  # Don't speak anything more after interrupt
                    break

                if not llm_response.get('success'):
                    if not (llm_response.get('tools') and not llm_response.get('text')):
                        return "Connection to mainframe lost. Operating on basic protocols."

                clean_text = llm_response.get('text', '')
                unified_tools = llm_response.get('tools', [])

                remainder_text = clean_text
                for chunk in instant_spoken_chunks:
                    remainder_text = remainder_text.replace(chunk, "", 1)
                
                remainder_text = re.sub(r'(?i)</?verbal>', '', remainder_text).strip()
                
                if remainder_text and remainder_text.upper() != "NONE":
                    final_unspoken_text = remainder_text 
                else:
                    final_unspoken_text = ""

                if not unified_tools:
                    _intent_signals = ['i am executing:', 'executing:', 'i am executing the', 'calling tool', 'i will now execute']
                    _text_lower = clean_text.lower()
                    _is_intent_only = (
                        clean_text
                        and any(sig in _text_lower for sig in _intent_signals)
                        and current_iteration < max_iterations
                    )
                    if _is_intent_only:
                        _announced_tool = ""
                        for sig in _intent_signals:
                            if sig in _text_lower:
                                _after = _text_lower.split(sig, 1)[-1].strip().split()[0].rstrip('.,')
                                if _after:
                                    _announced_tool = _after
                                break
                        _feedback_hint = (
                            f"Call the '{_announced_tool}' tool NOW."
                            if _announced_tool else
                            "Call the correct tool NOW."
                        )
                        messages.append({'role': 'assistant', 'content': clean_text.strip()})
                        messages.append({'role': 'user', 'content': (
                            f"[SYSTEM FEEDBACK]\\n"
                            f"System: You announced intent but emitted NO tool call. {_feedback_hint} "
                            f"Do NOT repeat your announcement text."
                        )})
                        continue
                    break

                tool_results_combined = []
                silent_success_count = 0
                _skipped_duplicates = 0

                for idx, tool in enumerate(unified_tools[:tool_max]):
                    tool_name = tool.get('name', '')
                    func_args = tool.get('arguments', {})
                    
                    if isinstance(func_args, str):
                        try:
                            func_args = json.loads(func_args)
                        except (json.JSONDecodeError, TypeError):
                            func_args = {}
                    if not isinstance(func_args, dict):
                        func_args = {}
                    tool['arguments'] = func_args 
                    
                    _sig = (tool_name, json.dumps(func_args, sort_keys=True))
                    if _sig in _executed_tool_signatures:
                        print(f"   ⚠️ [Dedup] Skipped duplicate call: {tool_name}({func_args})")
                        logger.warning(f"[Dedup] Skipped duplicate call: {tool_name}({func_args})")
                        _skipped_duplicates += 1
                        continue
                    _executed_tool_signatures.add(_sig)
                    
                    try:
                        result = self.execute_tool(tool_name, func_args)
                        
                        if tool_name == 'grant_temporary_permission' and "granted" in str(result).lower() and self.state.pending_tool_call:
                            tool_results_combined.append(f"System: Tool '{tool_name}' executed. Result:\n{result}")
                            auto_name = self.state.pending_tool_call['name']
                            auto_args = self.state.pending_tool_call['args']
                            self.state.pending_tool_call = None
                            auto_res = self.execute_tool(auto_name, auto_args)
                            tool_results_combined.append(f"System: Auto-resumed blocked Tool '{auto_name}' seamlessly. Result:\n{auto_res}")
                            continue
                        
                        if isinstance(result, str) and "Security Block" in result:
                            self.state.pending_tool_call = {'name': tool_name, 'args': func_args}
                            result = f"Security Block: Action '{tool_name}' requires permission. Ask the user. If they agree, you MUST call 'grant_temporary_permission' in your NEXT turn to auto-resume."
                        
                        if isinstance(result, str) and len(result) > 800:
                            result = result[:800] + "\n... [DATA TRUNCATED DUE TO LENGTH LIMIT]"
                    except Exception as e:
                        result = f"Error executing '{tool_name}': {str(e)}."

                    tool_results_combined.append(f"System: Tool '{tool_name}' executed. Result:\n{result}")

                    if tool_name in SILENT_TOOLS and "Error:" not in result and "Failed" not in result and "Security Block" not in result:
                        silent_success_count += 1

                _executed_names = [
                    t.get('name', '') for t in unified_tools[:tool_max]
                    if (t.get('name', ''), json.dumps(t.get('arguments', {}), sort_keys=True)) in _executed_tool_signatures
                ]
                _all_free = (
                    bool(_executed_names)
                    and all(n in FREE_TOOLS for n in _executed_names)
                )

                _all_errors = tool_results_combined and all(
                    any(marker in res for marker in ("Error", "Failed", "Security Block"))
                    for res in tool_results_combined
                )
                if _all_errors:
                    _errored_tools = [t.get('name', '') for t in unified_tools[:tool_max]]
                    _has_retry_budget = False
                    for _et in _errored_tools:
                        if _error_retry_budget.get(_et, 0) < 1:
                            _error_retry_budget[_et] = _error_retry_budget.get(_et, 0) + 1
                            _has_retry_budget = True
                    if _has_retry_budget:
                        _all_free = True  

                if _all_free and _current_iter_idx > 0:
                    _current_iter_idx -= 1  
                    print(f"   🔄 [Free Iteration] Read-only/error tools only — iteration not consumed ({_current_iter_idx}/{max_iterations})")

                if _skipped_duplicates > 0 and not tool_results_combined:
                    _done_list = ', '.join(sorted(set(n for n, _ in _executed_tool_signatures)))
                    messages.append({'role': 'assistant', 'content': f"I am executing: {_done_list}"})
                    messages.append({'role': 'user', 'content': (
                        f"[SYSTEM FEEDBACK]\n"
                        f"System: Tools already completed: {_done_list}.\n"
                        f"The user's ORIGINAL command was: \"{command}\"\n"
                        f"Call the REMAINING tool(s) for the parts NOT yet handled. Do NOT repeat {_done_list}."
                    )})
                    continue

                assistant_msg = clean_text.strip()
                if not assistant_msg:
                    tool_names = [t.get('name', 'Unknown') for t in unified_tools]
                    assistant_msg = f"I am executing: {', '.join(tool_names)}"
                    
                messages.append({'role': 'assistant', 'content': assistant_msg})
                
                _done_names = [t.get('name','') for t in unified_tools[:tool_max] if (t.get('name',''), json.dumps(t.get('arguments',{}), sort_keys=True)) in _executed_tool_signatures]
                _remaining_hint = ""
                
                if current_iteration < max_iterations:
                    _remaining_hint = f"\n\nIMPORTANT: The user's ORIGINAL command was: \"{command}\"\n"
                    if _done_names:
                        _remaining_hint += f"Tools COMPLETED so far: {', '.join(_done_names)}.\n"
                        _remaining_hint += "If there are REMAINING actions from the original command, call the appropriate tool NOW. Do NOT repeat any tool listed above."
                    else:
                        _remaining_hint += "No tools have been successfully executed yet. Call the correct tool NOW."
                    
                    if current_iteration == max_iterations - 1:
                        _remaining_hint += "\nCRITICAL WARNING: Your loop iterations are almost exhausted (Next loop is the LAST). You MUST finalize your task now and provide a spoken <verbal> final answer."
                    else:
                        _remaining_hint += " If all actions are complete, give a natural, very short spoken confirmation or following up question."

                if silent_success_count > 0 and silent_success_count == len(tool_results_combined):
                    feedback_content = (
                        f"[SYSTEM FEEDBACK] {_loop_label}\n" + "\n\n".join(tool_results_combined) + 
                        "\n\nSystem: Action completed. If the user asked a question, answer it in ONE short sentence. If there are remaining actions, call the next tool. Otherwise, give a SHORT confirmation like <verbal>Done.</verbal>."
                        + _remaining_hint
                    )
                    messages.append({'role': 'user', 'content': feedback_content})
                    final_unspoken_text = "" 
                    continue 
                else:
                    feedback_content = f"[SYSTEM FEEDBACK] {_loop_label}\n" + "\n\n".join(tool_results_combined) + "\n\nProvide the final response directly based on these results." + _remaining_hint
                    messages.append({'role': 'user', 'content': feedback_content})

                if _current_iter_idx >= max_iterations and clean_text:
                    _verbal_matches = re.findall(r'(?si)<verbal>(.*?)</verbal>', clean_text)
                    if _verbal_matches:
                        _last_verbal = _verbal_matches[-1].strip()
                        if _last_verbal and _last_verbal.upper() != "NONE":
                            if _last_verbal not in " ".join(instant_spoken_chunks):
                                final_unspoken_text = _last_verbal
                                print(f"   🎯 [Last Verbal] Extracted final <verbal> from {_current_iter_idx}/{max_iterations}: '{_last_verbal[:60]}...'")

            # ==========================================
            # History Compression
            # ==========================================
            if not clean_text.strip() and unified_tools:
                tool_names = ", ".join([t.get('name', 'Unknown') for t in unified_tools])
                compressed_response = f"[System: For user request '{command[:60]}', executed tools -> {tool_names}]"
            else:
                words = clean_text.split()
                compressed_response = " ".join(words[:80]) + ("..." if len(words) > 120 else "")
            
            self.chat_history.append({'role': 'user', 'content': command})
            self.chat_history.append({'role': 'assistant', 'content': compressed_response})

            history_limit = get_setting('history_limit', 6)
            if len(self.chat_history) > history_limit:
                self.chat_history = self.chat_history[-history_limit:]
                self.state.clear_temp_memory()

            if final_unspoken_text:
                self.state.transition_to(InterruptState.SPEAKING)
                self.mouth.speak(final_unspoken_text)

            return ""
            
        finally:
            self._llm_busy = False
            self._llm_free_event.set()
    
    # ------------------------------------------------------------------
    # Wake-Word Handler (DRY — shared by both branches in run())
    # ------------------------------------------------------------------
    def _handle_wake_word(self, raw_text: str, wake_word: str):
        """
        Processes a detected wake-word utterance:
        - If the user said ONLY the wake word → greet and listen for a follow-up command.
        - If additional text follows the wake word → use that as the command directly.
        Returns the command string (may be empty if listen() times out).
        """
        clean_check = re.sub(rf'(?i)\b{wake_word}\b', '', raw_text).strip(" ,.!?")
        print(f"💡 [System] Woken Up via wake word: {wake_word}")
        
        if not clean_check:
            greetings = ["Yes, sir?", "At your service.", "I am listening.", "What can I do for you?", 
            "Ready for your command.", "Yes?", "How can I help?", "Go ahead.", "I'm here."]
            self.mouth.speak(random.choice(greetings))
            # Force the system to wait for speech to finish before opening the mic to prevent self-hearing.
            self.mouth.speech_done_event.wait(timeout=5)
            self.last_speech_time = time.time()
            return self.ears.listen()
        else:
            return raw_text.strip()

    # ------------------------------------------------------------------
    # Main Loop
    # ------------------------------------------------------------------
    def run(self):
        """
        Continuous listening loop with:
        - Wake-word detection
        - 10s follow-up window
        - Interruption injection
        - Pending command queue
        """
        if not self.initialization_complete:
            self.initialize()

        self.running = True

        raw_wake_word = get_setting('wake_word', 'jarvis').lower()
        wake_words = [w.strip() for w in raw_wake_word.split(',') if w.strip()]
        if not wake_words:
            wake_words = ["jarvis"] # Ultimate fallback

        print("\n" + "=" * 60)
        print(f"   🎙️ {self.assistant_name.upper()} IS LIVE")
        print(f"   🌐 Mode: {'Always Listening' if self.state.always_listening else f'Wake Words ({", ".join(wake_words)})'}")
        print("   🛑 Say 'exit' or 'shutdown' to stop")
        print("=" * 60 + "\n")
        
        while self.running:
            try:
                command = ""

                if self.pending_command:
                    if self.pending_command == "SYSTEM_WAKE":
                        self.pending_command = ""
                        print("💡 [System] Woken Up via interrupt wake word.")
                        greetings = ["Yes, sir?", "At your service.", "I am listening.", "what is your command sir?", "wating for you command", "always here for you sir"]
                        self.mouth.speak(random.choice(greetings))
                        self.mouth.speech_done_event.wait(timeout=5)
                        continue

                    command              = self.pending_command
                    self.pending_command = ""
                    print(f"\n⚡ [System] Resuming instantly with queued command...")
                    if self.state.interrupt_state == InterruptState.FOLLOW_UP:
                        if self.state.interrupted_position:
                            self.state.add_temp_memory(
                                f"[System: Previous response was interrupted at: \"{self.state.interrupted_position[-60:]}\"]"
                            )
                else:
                    window_limit = get_setting('followup_window', 10)
                    is_in_window = (time.time() - self.last_speech_time) <= window_limit

                    raw_text = self.ears.listen()
                    if not raw_text:
                        continue

                    matched_ww = next((w for w in wake_words if w in raw_text.lower()), None)

                    if self.state.always_listening or is_in_window:
                        if matched_ww:
                            command = self._handle_wake_word(raw_text, matched_ww)
                        else:
                            command = raw_text
                    else:
                        if matched_ww:
                            command = self._handle_wake_word(raw_text, matched_ww)
                        else:
                            continue

                # immediately kill for emergency shutdown
                if command:
                    cmd_lower = command.lower().strip(" .!?")
                    targets = ["immediately deactivate", "immediately shutdown"]
                    is_kill = any(t in cmd_lower or difflib.SequenceMatcher(None, t, cmd_lower).ratio() > 0.85 for t in targets)
                    if is_kill:
                        self.mouth.speak("Shutting down all systems. Goodbye sir.")
                        print("\n⏳ [Emergency Shutdown] 7 seconds given for cinematic goodbye...")
                        time.sleep(7)
                        try:
                            base_url = getattr(self.llm_client, 'base_url', "http://localhost:11434")
                            models_to_unload = set([getattr(self.llm_client, 'normal_model', None), getattr(self.llm_client, 'overthink_model', None)])
                            for model in models_to_unload:
                                if model:
                                    requests.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=3)
                                    print(f"🧹 Unloaded model '{model}' from RAM.")
                        except Exception as e:
                            print(f"⚠️ Failed to unload Ollama models: {e}")
                        self.running = False
                        break

                    print(f"🚀 Executing: {command}")
                    self._is_currently_speaking_tool_intro = False

                    response = self.process_command(command)
                    if response:
                        self.mouth.speak(response)

                    interrupted_cmd = ""
                    if self.mouth.is_busy():
                        interrupted_cmd = self.ears.listen_with_interruption(self.mouth, timeout=120)
                    
                    self.last_speech_time = time.time()
                    
                    if interrupted_cmd:
                        print(f"\n⚡ Smart Interruption Triggered! Queuing: {interrupted_cmd}")
                        self.pending_command = interrupted_cmd

                        ctx = self.mouth.get_interruption_context()
                        self.state.handle_speech_interrupt(
                            position_text=ctx.get('interrupted_text', ''),
                            context={'command': command}
                        )

                        if self.chat_history and self.chat_history[-1]['role'] == 'assistant':
                            last_spoken_chunk = getattr(self.mouth, 'current_speaking_text', '')
                            words_list        = str(last_spoken_chunk).split()
                            last_3_words      = (
                                " ".join(words_list[-3:]) if len(words_list) >= 3
                                else last_spoken_chunk
                            )
                            note = (
                                f"\n\n[System Note: You were interrupted at \"...{last_3_words}\"]"
                                if last_3_words.strip()
                                else "\n\n[System Note: You were interrupted before finishing your sentence.]"
                            )
                            self.chat_history[-1]['content'] += note
                            print(f"💉 Context Injected: {note.strip()}")
                    else:
                        self.mouth.speech_done_event.wait(timeout=30)
                        self.state.enter_follow_up()
                        
                        self.play_listening_cue()  
                        
                        print(f"\n✅ Task complete. Follow-up window active for {get_setting('followup_window', 10)}s...")
                        self.state.clear_temp_memory()

            except KeyboardInterrupt:
                print("\n\n🛑 Interrupted by user.")
                try:
                    if hasattr(self, 'llm_client') and self.llm_client:
                        base_url = getattr(self.llm_client, 'base_url', "http://localhost:11434")
                        models_to_unload = set([getattr(self.llm_client, 'normal_model', None), getattr(self.llm_client, 'overthink_model', None)])
                        for model in models_to_unload:
                            if model:
                                requests.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=3)
                                print(f"🧹 Unloaded model '{model}' from RAM.")
                except Exception as e:
                    print(f"⚠️ Failed to unload Ollama models: {e}")
                self.running = False
                break
            except Exception as e:
                print(f"\n❌ Loop Error: {e}")
                logger.error(f"Loop Error: {e}")
                time.sleep(1)

        self.watch_dog.stop()
        print(f"\n✅ {self.assistant_name.upper()} shutdown complete.")

