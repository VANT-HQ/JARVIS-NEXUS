# app.py
"""
JARVIS - The Brain Orchestrator
================================

Main application file that coordinates all components:
- Ears, Mouth, Memory, Browser Agent
- Local LLM integration with tool calling (Offline Mode)
- Internal commands processing (Fallback Mode)
- State management
- Startup sequence with video (Parallel Initialization)
- Smart Follow-up Window (10s Continuous Listening)

Author: Hmody -> V.A.N.T. CEO & Founder
Version: 0.1 (Cleaned Duplications, Fixed Loop, Added System Control)
"""

import sys
import os
import json
import time
import threading
import requests  # Added for Local LLM API calls
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# =================================================================
# Imports
# =================================================================
from core.root.ears import Ears
from core.root.mouth import Mouth
from core.memory_manager import MemoryManager
from core.tools.browser_agent import BrowserAgent

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    print("⚠️ pygame not installed - video playback disabled")

# -----------------------------------------------------------------
# Configuration Integration (SQLite Supported)
# -----------------------------------------------------------------
try:
    from core.config import config
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False
    print("⚠️ core.config module not found. Using safe default runtime configurations.")

def get_setting(key: str, default_value):
    """Helper function to safely fetch settings from the database if available"""
    if CONFIG_AVAILABLE and hasattr(config, 'get'):
        val = config.get(key)
        return val if val is not None else default_value
    return default_value

def get_system_prompt() -> str:
    """Fetch system instructions either via the custom function or the default value"""
    base_prompt = ""
    if CONFIG_AVAILABLE and hasattr(config, 'get_full_prompt'):
        base_prompt = config.get_full_prompt()
    else:
        base_prompt = get_setting('system_prompt', "You are a helpful AI assistant with access to various tools.")
    
    # Injection: Rule for Memory Localization (Strictly English)
    language_rule = (
        "\nCRITICAL RULE FOR MEMORY: Whenever you use the 'remember_information' or 'create_task' tools, "
        "you MUST translate the content to ENGLISH before saving it, regardless of the language the user is speaking. "
        "The memory manager database strictly operates in English."
    )
    return base_prompt + language_rule


# =================================================================
# Video Player
# =================================================================
class VideoPlayer:
    """
    Advanced video player for JARVIS - Supports prestige mode and force kill
    """
    
    def __init__(self):
        if not PYGAME_AVAILABLE:
            self.available = False
            return
        
        self.available = True
        pygame.init()
        self.current_process = None
    
    def play_video(self, video_path: str, duration: Optional[float] = None, blocking: bool = True) -> bool:
        if not self.available:
            print(f"⚠️ Video playback not available: {video_path}")
            return False
        
        video_file = Path(video_path)
        if not video_file.exists():
            print(f"❌ Video file not found: {video_path}")
            return False
        
        absolute_path = str(video_file.resolve())
        
        try:
            import os
            import subprocess
            import platform
            
            system = platform.system()
            
            # --- 1. Play video (Professional fullscreen logic) ---
            if system == "Windows":
                vlc_path = next((p for p in [
                    os.path.join(os.environ.get('ProgramFiles', 'C:\\Program Files'), 'VideoLAN', 'VLC', 'vlc.exe'),
                    os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'VideoLAN', 'VLC', 'vlc.exe')
                ] if os.path.exists(p)), None)

                if vlc_path:
                    self.current_process = subprocess.Popen([
                        vlc_path, '--fullscreen', '--no-video-title-show', 
                        '--mouse-hide-timeout=0', '--play-and-exit', absolute_path
                    ])
                else:
                    wm_path = next((p for p in [
                        os.path.join(os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'), 'Windows Media Player', 'wmplayer.exe'),
                        os.path.join(os.environ.get('ProgramW6432', 'C:\\Program Files'), 'Windows Media Player', 'wmplayer.exe')
                    ] if os.path.exists(p)), None)
                    
                    if wm_path:
                        self.current_process = subprocess.Popen([wm_path, '/fullscreen', '/play', absolute_path])
                    else:
                        os.startfile(absolute_path)

            # --- 2. Time management and force kill (Sequence protection) ---
            if blocking:
                sleep_duration = duration if duration else 17.0
                if not duration:
                    try:
                        from tinytag import TinyTag
                        sleep_duration = TinyTag.get(absolute_path).duration or 17.0
                    except: pass

                print(f"⏳ Sequence active for {sleep_duration:.1f}s...")
                time.sleep(sleep_duration)

                if self.current_process:
                    self.current_process.kill()
                
                if system == "Windows":
                    os.system("taskkill /F /IM vlc.exe /T >nul 2>&1")
                    os.system("taskkill /F /IM wmplayer.exe /T >nul 2>&1")

            return True
            
        except Exception as e:
            print(f"❌ Error in visual sequence: {e}")
            return False

# =================================================================
# State Manager
# =================================================================
class StateManager:
    """
    System state management (Lifecycle is tied to the program runtime and cleared on exit)
    """
    
    def __init__(self):
        self.apache_mode = False
        self.language_mode = "english"  
        self.always_listening = False
        self.overthinking_mode = False  
        self.current_chat_history = []
        self.temp_memory = []  
        
        # Fetch location once on boot
        self.user_location = self._fetch_location()
    
    def _fetch_location(self) -> str:
        """
        Fetch location from the database, or fallback to IP (Country only)
        """
        # 1. Attempt from settings (Database)
        db_location = get_setting('user_location', '')
        if db_location:
            print(f"🌍 Location loaded from DB: {db_location}")
            return db_location
            
        # 2. Automatic fallback (Country only due to low city accuracy)
        import requests
        try:
            response = requests.get("http://ip-api.com/json/", timeout=3)
            if response.status_code == 200:
                data = response.json()
                country = data.get('country', 'Unknown Country')
                print(f"🌍 Auto-detected Location (Country Only): {country}")
                return country
        except Exception as e:
            print(f"⚠️ Could not auto-detect location: {e}")
        
        return "*sys coudnt get country*" # Absolute default

    def set_apache_mode(self, enabled: bool):
        self.apache_mode = enabled
        print(f"🔥 Apache Mode: {'ON' if enabled else 'OFF'}")
    
    def set_language_mode(self, mode: str):
        if mode.lower() in ["auto", "arabic", "english"]:
            self.language_mode = mode.lower()
            print(f"🌐 Language Mode: {mode}")
    
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
    
# =================================================================
# LLM Client (Strictly Local - Prompt Based Tool Calling)
# =================================================================
class LLMClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url  
        self.normal_model = None 
        self.overthink_model = None
        self._initialize_client()

    def _force_restart_ollama(self):
        import subprocess
        import platform
        print("🔪 Forcing Ollama restart (Killing zombie processes)...")
        try:
            if platform.system() == "Windows":
                subprocess.run("taskkill /F /IM ollama.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run("taskkill /F /IM ollama_llama_server.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["pkill", "-9", "-f", "ollama"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        time.sleep(1)
        try:
            subprocess.Popen(['ollama', 'serve'], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("⏳ Booting fresh Ollama instance...")
            time.sleep(4)
        except Exception as e:
            print(f"❌ Failed to start Ollama: {e}")

    def _initialize_client(self):
        import requests
        try:
            requests.get(self.base_url, timeout=2)
            print(f"✅ Local LLM server is running at: {self.base_url}")
        except requests.exceptions.ConnectionError:
            print("⚠️ Local LLM API not responding. Executing forced reboot protocol...")
            self._force_restart_ollama()
        self._ensure_model_exists()

    def _ensure_model_exists(self):
        import subprocess
        import os
        from pathlib import Path
        project_root = Path(__file__).resolve().parent
        llm_dir = project_root / "models" / "llm"
        
        if not llm_dir.exists():
            llm_dir.mkdir(parents=True, exist_ok=True)
            return

        gguf_files = list(llm_dir.glob("*.gguf"))
        if not gguf_files: return
        
        # 🚀 Model selection logic (1, 2, or 3+)
        gguf_files.sort(key=lambda x: os.path.getsize(x))
        
        if len(gguf_files) == 1:
            normal_file = gguf_files[0]
            overthink_file = gguf_files[0]
        else:
            # Smallest for normal, largest for Overthinking (ignores anything in between if present)
            normal_file = gguf_files[0]
            overthink_file = gguf_files[-1]

        self.normal_model = f"{normal_file.stem.lower()}-jarvis"
        self.overthink_model = f"{overthink_file.stem.lower()}-jarvis"
        
        required_models = {self.normal_model: normal_file, self.overthink_model: overthink_file}
        print(f"🔍 Active Models -> Normal: {self.normal_model} | Overthink: {self.overthink_model}")

        try:
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, check=True)
            installed_models = result.stdout.lower()
            
            # 🧹 Clean up old models named -jarvis that are not in the required list
            for line in installed_models.split('\n')[1:]:
                if not line.strip(): continue
                model_name = line.split()[0]
                if model_name.endswith('-jarvis') or model_name.endswith('-jarvis:latest'):
                    clean_name = model_name.replace(':latest', '')
                    if clean_name not in required_models:
                        print(f"🗑️ Removing old/unused system model: {clean_name}")
                        subprocess.run(['ollama', 'rm', clean_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # ⚙️ Install required models
            for mod_name, mod_file in required_models.items():
                if mod_name not in installed_models:
                    print(f"⚠️ Model '{mod_name}' not found. Starting Auto-Setup...")
                    modelfile_path = llm_dir / f"Modelfile_{mod_name}"
                    try:
                        with open(modelfile_path, "w", encoding="utf-8") as f:
                            f.write(f'FROM "{mod_file.resolve()}"\n')
                        subprocess.run(['ollama', 'create', mod_name, '-f', str(modelfile_path)], check=True)
                        print(f"✅ Model '{mod_name}' successfully integrated into Ollama!")
                    except Exception as e:
                        print(f"❌ Failed to build model {mod_name}. Error: {e}")
                    finally:
                        if modelfile_path.exists(): modelfile_path.unlink()
        except Exception as e:
            pass

    def generate_response(self, messages: List[Dict], is_overthinking: bool = False, tools: List[Dict] = None, temperature: float = 0.1) -> Dict:
        try: 
            target_model = self.overthink_model if is_overthinking else self.normal_model
            return self._local_generate(messages, target_model, temperature)
        except Exception as e: return {'success': False, 'error': str(e)}
    
    def _local_generate(self, messages, target_model, temperature):
        import requests
        endpoint = f"{self.base_url}/api/chat"
        if not target_model: raise Exception("Model name is not initialized.")

        payload = {
            "model": target_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": 150}
        }
        
        try:
            response = requests.post(endpoint, json=payload, timeout=60)
            if not response.ok: raise Exception(f"Ollama API Error ({response.status_code}): {response.text}")
            data = response.json()
            message = data.get('message', {})
            return {'success': True, 'text': message.get('content', ''), 'finish_reason': data.get('done_reason', 'stop')}
        except requests.exceptions.RequestException as req_err:
            raise Exception(f"Local Server Error: {req_err}")


# =================================================================
# Internal Command Processor
# =================================================================
class InternalCommandProcessor:
    """
    Internal Command Processor
    """
    
    def __init__(self, jarvis_core):
        self.jarvis = jarvis_core
        
        self.commands = {
            'jarvis start up': self._startup_video,
            'jarvis startup': self._startup_video,
            'start up': self._startup_video,
            'startup': self._startup_video,
            'introduce yourself': self._introduce_video,
            'jarvis introduce yourself': self._introduce_video,
            'apache mode on': lambda: self._set_apache(True),
            'apache mode off': lambda: self._set_apache(False),
            'language mode arabic': lambda: self._set_language('arabic'),
            'language mode english': lambda: self._set_language('english'),
            'language mode auto': lambda: self._set_language('auto'),
            'always listening on': lambda: self._set_always_listening(True),
            'always listening off': lambda: self._set_always_listening(False),
            'overthinking mode on': lambda: self._set_overthinking(True),
            'overthinking mode off': lambda: self._set_overthinking(False)
        }
    
    def process(self, command: str) -> Tuple[bool, Optional[str]]:
        command_lower = command.lower().strip()
        
        for cmd, handler in self.commands.items():
            if command_lower == cmd or command_lower.startswith(cmd):
                response = handler()
                return True, response
        
        if 'reply in arabic' in command_lower or 'respond in arabic' in command_lower:
            self.jarvis.state.add_temp_memory("reply_in_arabic: true")
            return True, "I will reply in Arabic."
        
        if 'reply in english' in command_lower or 'respond in english' in command_lower:
            self.jarvis.state.add_temp_memory("reply_in_english: true")
            return True, "Understood. I will reply in English."
        
        return False, None

    def _get_video_duration(self, path, default=17.0):
        import os
        if not os.path.exists(path): return 0.0
        try:
            from tinytag import TinyTag
            return TinyTag.get(path).duration or default
        except: return default

    def _startup_video(self):
        import time, re
        video_path = "media/Jarvis_startup.mp4"
        duration = self._get_video_duration(video_path, default=17.0)
        
        if duration > 0:
            print("🎬 [System] Playing startup video in background...")
            self.jarvis.video_player.play_video(video_path, duration=duration, blocking=False)
            if self.jarvis.ears: self.jarvis.ears.deafen_for(duration)
        
        start_time = time.time()
        print("🧠 [System] LLM generating post-video response in background...")
        
        messages = [{'role': 'system', 'content': 'The system has just booted up successfully. Give a very short, badass greeting to your creator. Do not use tools.'}]
        llm_response = self.jarvis.llm_client.generate_response(messages)
        reply = llm_response.get('text', 'Systems online. I am ready, sir.')
        
        reply = re.sub(r'@@TOOL:.*?@@', '', reply).strip()
        reply = re.sub(r'^Verbal:\s*', '', reply, flags=re.IGNORECASE).strip()
        reply = re.sub(r'Action:.*', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()
        
        elapsed = time.time() - start_time
        remaining = duration - elapsed
        if remaining > 0: time.sleep(remaining)
            
        return reply if reply else "Systems online."
    
    def _introduce_video(self):
        import time, re
        video_path = "media/Jarvis_introduce.mp4"
        duration = self._get_video_duration(video_path, default=10.0)
        
        if duration > 0:
            print("🎬 [System] Playing intro video in background...")
            self.jarvis.video_player.play_video(video_path, duration=duration, blocking=False)
            if self.jarvis.ears: self.jarvis.ears.deafen_for(duration)
        
        start_time = time.time()
        print("🧠 [System] LLM generating post-intro response in background...")
        
        messages = [{'role': 'system', 'content': 'You have just shown your visual introduction to the user. Give a brief, powerful verbal introduction of yourself as JARVIS. Do not use tools.'}]
        llm_response = self.jarvis.llm_client.generate_response(messages)
        reply = llm_response.get('text', 'I am JARVIS. At your service.')
        
        reply = re.sub(r'@@TOOL:.*?@@', '', reply).strip()
        reply = re.sub(r'^Verbal:\s*', '', reply, flags=re.IGNORECASE).strip()
        reply = re.sub(r'Action:.*', '', reply, flags=re.IGNORECASE | re.DOTALL).strip()
        
        elapsed = time.time() - start_time
        remaining = duration - elapsed
        if remaining > 0: time.sleep(remaining)
            
        return reply if reply else "Allow me to introduce myself. I am JARVIS."
    
    def _set_apache(self, enabled: bool):
        self.jarvis.state.set_apache_mode(enabled)
        return f"Apache mode {'activated' if enabled else 'deactivated'}."
    
    def _set_language(self, mode: str):
        self.jarvis.state.set_language_mode(mode)
        if hasattr(self.jarvis.ears, 'set_language_filter'):
            self.jarvis.ears.set_language_filter(mode)
        return f"Language mode set to {mode}."
    
    def _set_always_listening(self, enabled: bool):
        self.jarvis.state.set_always_listening(enabled)
        return f"Always listening mode {'enabled' if enabled else 'disabled'}."
    
    def _set_overthinking(self, enabled: bool):
        self.jarvis.state.overthinking_mode = enabled
        status = "ENABLED. I will now analyze and synthesize information deeply." if enabled else "DISABLED. Back to concise responses."
        return f"Overthinking mode {status}"

# =================================================================
# JARVIS Core
# =================================================================
class JARVISCore:
    """
    JARVIS Core - The Main Orchestrator
    """
    
    def __init__(self):
        print("\n" + "="*60)
        print("   🤖 JARVIS - Just A Rather Very Intelligent System")
        print("="*60)
        
        # Core components
        self.ears = None
        self.mouth = None
        self.memory = None
        self.browser = None
        self.video_player = VideoPlayer()
        self.state = StateManager()
        self.llm_client = None
        self.internal_commands = InternalCommandProcessor(self)
        
        # System state
        self.running = False
        self.initialization_complete = False
        
        # Chat history
        self.chat_history = []
        
        print("\n🔧 Initializing components...")
    
    def initialize(self):
        """
        Initialize all components concurrently (Parallel Initialization) to reduce load time.
        Includes a model Warm-up system during boot.
        """
        startup_show = get_setting('startup_show', True)
        local_api_url = get_setting('local_api_url', 'http://localhost:11434')

        video_path = "media/Jarvis_startup.mp4"
        video_duration = 17.0

        if startup_show and os.path.exists(video_path):
            try:
                from tinytag import TinyTag
                video_duration = TinyTag.get(video_path).duration or 17.0
            except: pass
            
            print(f"\n🎬 Booting Core Sequences (Parallel Mode) for {video_duration:.1f}s...")
            self.video_player.play_video(video_path, duration=video_duration, blocking=False)

        start_init_time = time.time()

        print("\n📡 Loading Ears (Speech Recognition)...")
        self.ears = Ears()
        
        # 🚀 First modification: Apply language filter from State Manager to Ears immediately
        if self.state.language_mode != "auto":
            self.ears.set_language_filter(self.state.language_mode)
        
        if startup_show:
            self.ears.deafen_for(video_duration)
        
        print("🔊 Loading Mouth (Text-to-Speech)...")
        self.mouth = Mouth()
        
        print("🧠 Loading Memory System...")
        self.memory = MemoryManager()
        
        print("🌐 Loading Browser Agent...")
        self.browser = BrowserAgent(memory_manager=self.memory)
        
        print("🤖 Loading Local LLM Client (Testing tools & connection)...")
        self.llm_client = LLMClient(base_url=local_api_url)
        
        self.initialization_complete = True
        
        if startup_show:
            elapsed_time = time.time() - start_init_time
            remaining_time = video_duration - elapsed_time
            
            if remaining_time > 0:
                print(f"⏳ Internal systems ready. Synchronizing visuals & Warming up LLM... ({remaining_time:.1f}s left)")
                
                def warmup_llm():
                    try:
                        self.llm_client.generate_response([{'role': 'user', 'content': 'Wake up'}])
                        print("   [System] 🔥 LLM Pre-ignition complete. VRAM loaded.")
                    except:
                        pass
                
                threading.Thread(target=warmup_llm, daemon=True).start()
                time.sleep(remaining_time)
            
            if self.video_player.current_process:
                try: self.video_player.current_process.kill()
                except: pass
            import platform
            if platform.system() == "Windows":
                os.system("taskkill /F /IM vlc.exe /T >nul 2>&1")
                os.system("taskkill /F /IM wmplayer.exe /T >nul 2>&1")

        print("\n✅ All systems online!")
        self.mouth.speak("Systems online. I am ready to assist you, sir.", lang='en')

    def get_available_tools(self) -> List[Dict]:
        """
        Get the list of available tools (for the LLM) in strict JSON Schema format.
        """
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_memory",
                    "description": "Search your long-term database to recall facts about the user, past events, or preferences.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The exact keyword or question to search for in memory."}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information when you need real-time data.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The exact search query."},
                            "max_results": {"type": "integer", "description": "Maximum number of results to fetch.", "default": 3}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "remember_information",
                    "description": "Save an event, thought, or note to episodic memory. MUST BE IN ENGLISH.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "description": "The full text to save."},
                            "title": {"type": "string", "description": "A brief title for this memory."},
                            "importance": {"type": "integer", "description": "Scale of 1-10 on how critical this is.", "default": 5}
                        },
                        "required": ["content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "store_knowledge",
                    "description": "Save factual data about entities (people, places, concepts).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entity": {"type": "string", "description": "Name of the entity."},
                            "entity_type": {"type": "string", "description": "Category (e.g., person, tech, project)."},
                            "attributes": {"type": "string", "description": "A valid JSON string mapping keys to facts."}
                        },
                        "required": ["entity", "entity_type", "attributes"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_task",
                    "description": "Create a new pending TODO task.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Task description/title."},
                            "priority": {"type": "integer", "description": "1=critical, 2=high, 3=normal, 4=low", "default": 3}
                        },
                        "required": ["title"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "complete_task",
                    "description": "Mark a task as completed using its ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_id": {"type": "integer", "description": "The ID of the task to complete"}
                        },
                        "required": ["task_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_website",
                    "description": "Opens a specific website URL or well-known site name in the browser.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "site_name": {"type": "string", "description": "Full URL (e.g., https://github.com/Hmody) or site name (e.g., youtube)."}
                        },
                        "required": ["site_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "auto_learn",
                    "description": "Learn autonomously about a specific topic, extract key facts, and save them directly to memory.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string", "description": "The specific subject or concept to learn about."}
                        },
                        "required": ["topic"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "deep_research",
                    "description": "Perform deep research on a complex question, analyzing multiple sources and comparing attributes.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "description": "The complex question to research."}
                        },
                        "required": ["question"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "open_application",
                    "description": "Opens a local Windows application or executable.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "app_name": {"type": "string", "description": "Name of the app to launch (e.g., calculator, notepad)."}
                        },
                        "required": ["app_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "system_control",
                    "description": "Control JARVIS internal settings (e.g., language mode english/arabic, apache mode on/off, always listening on/off, overthinking mode on/off, jarvis start up).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "The exact internal command to execute."}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "assistant_help",
                    "description": "INTERNAL TOOL: Call this ONLY if you are confused, forgot your prompt, or don't know how to fulfill the user's request. It will inject the full system manual into your context.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string", "description": "Why are you calling for help?"}
                        },
                        "required": ["reason"]
                    }
                }
            }
        ]
        return tools
    
    def execute_tool(self, tool_name: str, arguments: Dict) -> str:
        """Execute the tool and link it to subsystems"""
        try:
            import core.tools.os_actions as os_actions

            if tool_name == "search_memory":
                query = arguments.get('query', '')
                results = self.memory.recall_memory(query=query, limit=3)
                if not results:
                    return f"No memories found for '{query}'."
                formatted_results = []
                for r in results:
                    content = r.get('full_content', r.get('summary', ''))
                    formatted_results.append(f"- {content}")
                return "Found in memory:\n" + "\n".join(formatted_results)

            elif tool_name == "open_website":
                success, msg, _ = os_actions.open_website(arguments)
                return msg

            elif tool_name == "open_application":
                success, msg, _ = os_actions.open_application(arguments)
                return msg

            elif tool_name == "search_web":
                result = self.browser.quick_search(
                    query=arguments['query'],
                    max_results=arguments.get('max_results', 3)
                )
                return json.dumps(result)
            
            elif tool_name == "auto_learn":
                # Protection against sending variables incorrectly
                topic = arguments.get('topic') or arguments.get('query', '')
                if not topic: return "Error: Missing topic for auto_learn."
                
                result = self.browser.auto_learn(
                    topic=topic,
                    max_sources=3,
                    save_to_memory=True
                )
                return json.dumps(result)

            elif tool_name == "deep_research":
                # Protection against sending variables incorrectly
                question = arguments.get('question') or arguments.get('query', '')
                if not question: return "Error: Missing question for deep_research."
                
                result = self.browser.deep_research(
                    question=question,
                    max_sources=3
                )
                return json.dumps(result)

            elif tool_name == "remember_information":
                memory_id = self.memory.store_memory(
                    content=arguments['content'],
                    title=arguments.get('title', 'Untitled'),
                    importance=arguments.get('importance', 5),
                    memory_type='episodic'
                )
                return f"Memory stored successfully with ID: {memory_id}"
                
            elif tool_name == "store_knowledge":
                attrs = arguments.get('attributes', '{}')
                if isinstance(attrs, str):
                    try:
                        # Attempt to fix JSON if the model sent single quotes
                        cleaned_attrs = attrs.replace("'", '"')
                        attrs = json.loads(cleaned_attrs)
                    except:
                        # If it fails completely, save it as plain text inside a dictionary
                        attrs = {"info": str(attrs)}
                
                entity_id = self.memory.store_knowledge(
                    entity=arguments['entity'],
                    entity_type=arguments['entity_type'],
                    attributes=attrs
                )
                return f"Knowledge about '{arguments['entity']}' stored. ID: {entity_id}"

            elif tool_name == "create_task":
                task_id = self.memory.create_task(
                    title=arguments['title'],
                    priority=arguments.get('priority', 3)
                )
                return f"Task created successfully. Task ID: {task_id}"
                
            elif tool_name == "complete_task":
                success = self.memory.complete_task(arguments.get('task_id', 0))
                if success: return f"Task {arguments['task_id']} marked as completed."
                return f"Failed to complete task {arguments.get('task_id')}."
                
            elif tool_name == "system_control":
                cmd = arguments.get('command', '')
                is_internal, response = self.internal_commands.process(cmd)
                if is_internal:
                    return f"System executed: {response}"
                return f"Failed to execute internal command: {cmd}"

            else:
                return f"Unknown tool: {tool_name}"
                
        except Exception as e:
            return f"Error executing tool {tool_name}: {str(e)}"
        
    def build_messages(self, user_input: str) -> List[Dict]:
        """
        🚀 Build Messages: Smart assembly of prompts from the config file to form the integrated mind
        """
        from core.config import config, SYSTEM_PROMPT, TOOL_RULES
        
        messages = []
        
        # 1. Persona and Environmental Awareness (Added as the first message for roleplay)
        active_persona = config.get_active_persona()
        persona_prompt = active_persona.get('prompt', '')
        
        # Fetch the actual model name to enhance the system's awareness of its current state
        current_model_name = self.llm_client.overthink_model if self.state.overthinking_mode else self.llm_client.normal_model
        if not current_model_name:
            current_model_name = config.get("main_llm")
            
        environment_awareness = SYSTEM_PROMPT.format(model_name=current_model_name)
        
        base_setup = f"--- IDENTITY & ENVIRONMENT ---\n{environment_awareness}\n\n--- PERSONALITY GUIDELINES ---\n{persona_prompt}"
        messages.append({'role': 'system', 'content': base_setup})
        
        recalled_memory_text = ""
        # 2. Automatic Memory Search (Occurs only in Overthinking Mode)
        if self.state.overthinking_mode:
            try:
                memories = self.memory.recall_memory(query=user_input, limit=3, min_importance=0.0)
                memory_lines = []
                seen = set()
                for m in memories:
                    content = m.get('full_content', m.get('summary', ''))
                    if content and content not in seen:
                        memory_lines.append(f"- {content}")
                        seen.add(content)
                        
                if memory_lines:
                    recalled_memory_text = (
                        "\n[AUTO-RECALLED MEMORY]\n"
                        "CRITICAL RULE: The following facts are auto-retrieved from your database. Use them to answer the user.\n"
                        + "\n".join(memory_lines)
                    )
            except Exception as e:
                pass

        # 3. Real-time context and tool rules (Injected before the user's message to ensure model focus)
        current_time = datetime.now().strftime("%A, %B %d, %Y %I:%M %p")
        user_loc = self.state.user_location

        # Pass the user's location into tool examples dynamically
        formatted_tool_rules = TOOL_RULES.replace("{user_loc}", user_loc)

        system_content = (
            f"{formatted_tool_rules}\n\n"
            f"--- REAL-TIME CONTEXT ---\n"
            f"Current Time: {current_time}\n"
            f"User Location: {user_loc}\n"
        )
        
        pending_tasks = self.memory.get_tasks(status='pending', limit=2)
        if pending_tasks:
            tasks_text = "\n".join([f"- {t['title']}" for t in pending_tasks])
            system_content += f"\n\n[ACTIVE TASKS]\n{tasks_text}"

        temp_context = self.state.get_temp_memory_context()
        if temp_context: system_content += f"\n\n[CONTEXT]\n{temp_context}"
        if recalled_memory_text: system_content += f"\n{recalled_memory_text}"
        
        # 4. Insert chat history
        if len(self.chat_history) > 4: 
            messages.extend(self.chat_history[-4:])
        else: 
            messages.extend(self.chat_history)
            
        # 5. Inject real-time context and user message last
        messages.append({'role': 'system', 'content': system_content.strip()})
        messages.append({'role': 'user', 'content': user_input})
        
        return messages
    
    def process_command(self, command: str) -> str:
        """
        Process a user command using the Agentic Loop.
        The LLM thinks, uses a tool, observes the result, and decides if it needs another tool or gives the final response.
        """
        # 1. Check internal commands first (Dumb / Basic Mode Protocol)
        is_internal, response = self.internal_commands.process(command)
        
        if is_internal:
            if response == "HELP_COMMAND_TRIGGERED":
                sys_prompt = get_setting('system_prompt', "You are a helpful AI assistant.")
                pers_prompt = get_setting('personality_prompt', "You are JARVIS, an intelligent AI assistant.")
                
                help_prompt = f"""
    System Prompt:
    {sys_prompt}

    Personality:
    {pers_prompt}

    Available Tools:
    {json.dumps(self.get_available_tools(), indent=2)}

    Please explain my capabilities to the user.
    """
                messages = [{'role': 'user', 'content': help_prompt}]
                llm_response = self.llm_client.generate_response(messages)
                if not llm_response['success']:
                    return "I am JARVIS. Currently, my main LLM functions are offline, but I can perform basic commands."
                return llm_response.get('text', 'Help information sent.')
            
            return response
        
        # 2. Send to LLM and start thinking
        print(f"\n💭 User Command: {command}")
        
        messages = self.build_messages(command)
        tools = self.get_available_tools()
        
        # =================================================================
        # 🚀 THE AGENTIC LOOP (Reasoning & Acting)
        # =================================================================
        max_iterations = 4  # Maximum number of attempts to prevent infinite loops
        current_iteration = 0
        final_spoken_text = "Done."

        import re

        while current_iteration < max_iterations:
            current_iteration += 1
            print(f"🧠 [Agent Loop] Thinking... (Iteration {current_iteration}/{max_iterations})")
            
            llm_response = self.llm_client.generate_response(messages, is_overthinking=self.state.overthinking_mode, tools=tools)
            
            if not llm_response['success']:
                jarvis_fallback_quote = "Sir, I seem to have lost connection to the main processing mainframe. I am operating on basic protocols only."
                print(f"❌ LLM Error: {llm_response['error']}")
                return jarvis_fallback_quote
            
            response_text = llm_response.get('text', '')
            native_tools = llm_response.get('tool_calls', [])
            
            # 🚀 Extract all tools (maximum 3)
            tool_matches = list(re.finditer(r'@@TOOL:\s*(.*?)\s*\|\s*(.*?)@@', response_text))

            # Double Talk (Speaks only once for introduction)
            if (tool_matches or native_tools) and "Verbal:" in response_text:
                verbal_part = re.sub(r'Action:.*', '', response_text, flags=re.IGNORECASE | re.DOTALL)
                verbal_part = re.sub(r'^Verbal:\s*', '', verbal_part, flags=re.IGNORECASE).strip()
                if verbal_part and not getattr(self, '_is_currently_speaking_tool_intro', False):
                    print(f"🗣️ [Double Talk] Jarvis says: {verbal_part}")
                    self._is_currently_speaking_tool_intro = True
                    def speak_intro():
                        try:
                            self.mouth.speak(verbal_part, lang='en')
                        except: pass
                        finally:
                            self._is_currently_speaking_tool_intro = False
                    threading.Thread(target=speak_intro, daemon=True).start()

            # -------------------------------------------------------------
            # Case 1: The model didn't request any tools (Decided to answer finally)
            # -------------------------------------------------------------
            if not native_tools and not tool_matches:
                print("✅ [Agent Loop] LLM reached a conclusion.")
                final_spoken_text = response_text
                break  

            # -------------------------------------------------------------
            # Case 2: The model used hidden tools (Multi-Tool Support)
            # -------------------------------------------------------------
            if tool_matches:
                tool_results_combined = []
                silent_success_count = 0
                SILENT_TOOLS = ['open_website', 'open_application', 'system_control']
                
                # Execute tools in rapid succession
                for match in tool_matches[:3]:
                    tool_name = match.group(1).strip()
                    args_raw = match.group(2).strip() if match.lastindex >= 2 else ""
                    
                    print(f"🔧 [Hidden Tool Executing]: {tool_name} with args: {args_raw}")
                    
                    if tool_name == "assistant_help":
                        print("🔄 Injecting system manual and retrying...")
                        full_manual = json.dumps(self.get_available_tools(), indent=2)
                        tool_results_combined.append(f"SYSTEM MANUAL:\n{full_manual}\nNow fulfill the user request.")
                    else:
                        func_args = {}
                        if "=" in args_raw:
                            pairs = args_raw.split(',')
                            for pair in pairs:
                                if '=' in pair:
                                    k, v = pair.split('=', 1)
                                    func_args[k.strip()] = v.strip()
                        
                        result = self.execute_tool(tool_name, func_args)
                        tool_results_combined.append(f"Tool '{tool_name}' result:\n{result}")
                        
                        if tool_name in SILENT_TOOLS and "Error:" not in result and "Failed" not in result:
                            silent_success_count += 1

                messages.append({'role': 'assistant', 'content': response_text})
                messages.append({'role': 'system', 'content': "\n\n".join(tool_results_combined)})

                # If all requested tools succeed silently, break the loop
                if silent_success_count > 0 and silent_success_count == len(tool_matches[:3]):
                    print("✅ [Agent Loop] All requested actions completed silently. Breaking loop.")
                    final_spoken_text = "" 
                    break 

            # -------------------------------------------------------------
            # Case 3: The model used official tools (Native Tools)
            # -------------------------------------------------------------
            elif native_tools:
                messages.append({
                    'role': 'assistant',
                    'content': response_text,
                    'tool_calls': native_tools
                })
                
                for tool_call in native_tools[:3]: 
                    func_name = tool_call['function']['name']
                    func_args = json.loads(tool_call['function']['arguments'])
                    print(f"🔧 [Native Tool Executing]: {func_name}")
                    
                    result = self.execute_tool(func_name, func_args)
                    messages.append({
                        'role': 'tool',
                        'tool_call_id': tool_call.get('id', f'call_{current_iteration}_{func_name}'),
                        'content': str(result)
                    })
                print("⚙️ Native Actions Executed.")

        # =================================================================
        # End of loop - clean up text before speaking
        # =================================================================
        # If it consumes 4 attempts and doesn't stop, force a response
        if current_iteration >= max_iterations:
            print("⚠️ [Agent Loop] Max iterations reached. Forcing response.")
            final_spoken_text = response_text

        # 🚀 Keep the original response (with formatting) so the model doesn't lose its programming
        raw_history_text = response_text
        if "Action:" not in raw_history_text:
            raw_history_text += "\nAction: NONE"

        # Clean hidden tags (for final voice output)
        final_spoken_text = re.sub(r'@@TOOL:.*?@@', '', final_spoken_text).strip()
        final_spoken_text = re.sub(r'^Verbal:\s*', '', final_spoken_text, flags=re.IGNORECASE).strip()
        final_spoken_text = re.sub(r'Action:.*', '', final_spoken_text, flags=re.IGNORECASE | re.DOTALL).strip()
        
        if not final_spoken_text:
            final_spoken_text = "Task completed, sir."
        
        # 3. Update and store the conversation (store original format to continue calling tools)
        self.chat_history.append({'role': 'user', 'content': command})
        self.chat_history.append({'role': 'assistant', 'content': raw_history_text})
        
        max_history = get_setting('max_chat_history', 10)
        if len(self.chat_history) > max_history * 2:
            print("🗑️ Clearing old chat history...")
            self.chat_history = self.chat_history[-(max_history * 2):]
            self.state.clear_temp_memory()
        
        return final_spoken_text
    
    def run(self):
        """
        Run JARVIS in continuous smart listening mode (Continuous Streaming Logic)
        With a 10-second follow-up listening window
        """
        if not self.initialization_complete:
            self.initialize()
        
        self.running = True
        wake_word = get_setting('wake_word', 'jarvis').lower()
        
        print("\n" + "="*60)
        print(f"   🎙️ JARVIS IS LIVE")
        print(f"   🌐 Mode: {'Always Listening' if self.state.always_listening else 'Wake Word ('+wake_word+')'}")
        print("   🛑 Say 'exit' or 'shutdown' to stop")
        print("="*60 + "\n")
        
        import random
        
        pending_command = ""
        last_speech_time = 0.0 # 🚀 New counter for the 10 seconds

        while self.running:
            try:
                command = ""

                if pending_command:
                    command = pending_command
                    pending_command = "" 
                    print(f"\n⚡ [System] Resuming instantly with queued command...")
                    time.sleep(0.5) 
                else:
                    # 🚀 Most important modification: Check the window "before" listening!
                    is_in_window = (time.time() - last_speech_time) <= 12.0
                    
                    raw_text = self.ears.listen(timeout=5, phrase_time_limit=8)
                    if not raw_text:
                        continue

                    # 2. Command filtering logic
                    if self.state.always_listening or is_in_window:
                        if wake_word in raw_text.lower():
                            match_index = raw_text.lower().find(wake_word)
                            command = raw_text[match_index + len(wake_word):].strip(" ,.!?")
                            if not command:
                                greetings = ["Yes, sir?", "At your service.", "I am listening."]
                                self.mouth.speak(random.choice(greetings), lang='en')
                                command = self.ears.listen(timeout=5, phrase_time_limit=10)
                        else:
                            # If the target word isn't said, take the speech as is
                            command = raw_text
                    else:
                        if wake_word in raw_text.lower():
                            match_index = raw_text.lower().find(wake_word)
                            command = raw_text[match_index + len(wake_word):].strip(" ,.!?")
                            
                            if not command:
                                greetings = ["Yes, sir?", "At your service.", "I am listening."]
                                self.mouth.speak(random.choice(greetings), lang='en')
                                command = self.ears.listen(timeout=5, phrase_time_limit=10)
                        else:
                            # 🚀 The word that used to hide the text is now handled because we calculated the time correctly
                            continue

                # 3. Process the command
                if command:
                    if 'exit' in command.lower() or 'shutdown' in command.lower():
                        self.mouth.speak("Shutting down all systems. Goodbye sir.", lang='en')
                        self.running = False
                        break
                    
                    print(f"🚀 Executing: {command}")
                    response = self.process_command(command)
                    
                    # Speaking with interruption
                    def safe_speak():
                        try:
                            self.mouth.speak(response, lang='en')
                        except Exception as speak_err:
                            pass
                        finally:
                            self.mouth.is_speaking = False

                    self.mouth.is_speaking = True 
                    speak_thread = threading.Thread(target=safe_speak, daemon=True)
                    speak_thread.start()
                    
                    interrupted_cmd = self.ears.listen_with_interruption(self.mouth, timeout=120)
                    
                    speak_thread.join(timeout=2)
                    self.mouth.is_speaking = False 
                    
                    last_speech_time = time.time()
                    
                    if interrupted_cmd:
                        print(f"\n⚡ Smart Interruption Triggered! Queuing new command: {interrupted_cmd}")
                        pending_command = interrupted_cmd
                        if len(self.chat_history) >= 2:
                            self.chat_history = self.chat_history[:-2]
                    else:
                        print(f"\n✅ Task complete. Follow-up window active for 10s...")

            except KeyboardInterrupt:
                print("\n\n🛑 Interrupted by user.")
                self.running = False
                break
            except Exception as e:
                print(f"\n❌ Loop Error: {e}")
                time.sleep(1)

        print("\n✅ JARVIS shutdown complete.")


# =================================================================
# Entry Point
# =================================================================
def main():
    """
    Main entry point
    """
    jarvis = JARVISCore()
    
    try:
        jarvis.run()
    except Exception as e:
        print(f"\n❌ Fatal Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()