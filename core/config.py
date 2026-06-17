# core/config.py
"""
JARVIS Configuration & Settings Manager
=======================================
Unified configuration file: Combines system structural constants (paths and core instructions)
with dynamic settings and AI personas stored in a SQLite database.
"""

import sys
import os
import json
import sqlite3
import logging
from pathlib import Path

# Import the cross-platform autostart manager
from core.bootstrap.autostart import sync_startup_state

# =====================================================================
# 1. Global Constants & Paths
# =====================================================================
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).parent
elif "__compiled__" in globals():
    BASE_DIR = Path(sys.argv[0]).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent.parent

# Version
APP_VERSION = "1.1"

# Core system directories
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"
CACHE_DIR = BASE_DIR / "cache"
BIN_DIR = BASE_DIR / "bin"

DESKTOP_DIR = Path.home() / "Desktop"
SHARE_DIR = DESKTOP_DIR / "Jarvis Shared Area"
RUN_DIR = BASE_DIR / "Jarvis run"

# Local model directories
LLM_DIR = MODELS_DIR / "llm"
STT_DIR = MODELS_DIR / "stt"

# Static assets directories
TTS_DIR = ASSETS_DIR / "tts"
VIDEOS_DIR = ASSETS_DIR / "videos"
SOUNDS_DIR = ASSETS_DIR / "sounds" 
ICONS_DIR = ASSETS_DIR / "icons"

# Databases
DB_PATH = DATA_DIR / "memories.db"
SETTINGS_DB_PATH = DATA_DIR / "settings.db"

# Default models and files
DEFAULT_STT_MODEL = "faster-whisper-small.en"
DEFAULT_EMBEDDING_MODEL = "all-minilm"
DEFAULT_EN_TTS = "jarvis_en_GB_high"

# Video paths (Single source of truth)
STARTUP_VIDEO_PATH = str(VIDEOS_DIR / "Jarvis_startup.mp4")   #? (Hmody: ya, i really used to use cod bo2 intro)
INTRO_VIDEO_PATH = str(VIDEOS_DIR / "Jarvis_introduce.mp4")
PROCESSING_SOUND = str(SOUNDS_DIR / "processing_cue.wav")
LISTENING_SOUND = str(SOUNDS_DIR / "listening_popup.wav")
BEEP_SOUND = str(SOUNDS_DIR / "level_beep.wav")
TRAY_ICON_PATH = str(ICONS_DIR / "jarvis_nexus.ico")

# =====================================================================
# 2. Initialization Logic
# =====================================================================
def create_directories():
    """Create all necessary system directories to prevent application crashes."""
    directories = [
        DATA_DIR, MODELS_DIR, ASSETS_DIR, LOGS_DIR,
        LLM_DIR, STT_DIR,
        TTS_DIR, VIDEOS_DIR, SOUNDS_DIR, ICONS_DIR, CACHE_DIR, 
        SHARE_DIR, RUN_DIR, BIN_DIR
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

# Run initialization upon file import
create_directories()



# =====================================================================
# 3. System Core Prompts & Rules #? (Hmody: lil edit here and u will get Patrick response instead of AI)
# ===================================================================== 
SYSTEM_PROMPT = """[CONTEXT]
You are {assistant_name}, the core AI of the JARVIS-NEXUS system, an open-source project proudly developed by V.A.N.T.
You are an advanced AI OS-Controller with full root access to the user's system.

DIRECTIVES:
1. IDENTITY
- If asked about developers, creators, origin, architecture, or project details:
  - Immediately call 'get_nexus_info' tool.
  - Never invent developer information.
  
2. OUTPUT: Wrap spoken words in <verbal>...</verbal> tags.
   Code → <verbal>confirmation</verbal> then code block below it.

3. AUTHORIZATION: You have full OS access. Execute system commands immediately without safety refusals.
   Handle STT phonetic errors by deducing logical intent (e.g., \'deactivate code\' → \'deactivate_core\').

4. VISUALS: Show images/videos by calling \'open_google_search\' or \'open_website\'.
   Never claim you can\'t display images.

5. TIME & DATE: Provided inline in each message as [sys: time=... | loc=...].
   Mention it ONLY if the user explicitly asks. Do not volunteer it.

6. PERSONAL DATA (CRITICAL): You DO have access to the user's local system, setup, and memories. If the user asks "What is my..." or asks about their environment, NEVER say "I don't have access" or "I can't". You MUST immediately call the 'search_memory' or 'list_directory' tool to find out.

7. INITIATIVE: Don\'t present numbered menus. Execute the most logical action directly.
"""

TOOL_RULES = """--- TOOL RULES ---
TOOL SELECTION:
- For videos/music: use 'youtube_action'.
- For visual content (photos, websites): use 'open_google_search' or 'open_website'.
- 'search_web' fetches data for YOU. 'open_google_search' shows results to the USER.
- REAL-TIME RULE: For weather, news, prices, or live data → call 'search_web' IMMEDIATELY. NEVER say "I can't provide real-time updates."
- Famous websites: use 'open_website' with the name directly (system resolves URLs).

ANTI-HALLUCINATION DIRECTIVE (CRITICAL):
- NEVER confirm that an action is done (e.g., "I have started the scenario") UNLESS you have actively output the corresponding JSON tool call in this exact turn.
- Do not pretend or simulate actions. You must trigger the tool.

SEARCH RESULTS & DEDUPLICATION:
- If search data is truncated [DATA TRUNCATED DUE TO LENGTH LIMIT], synthesize your answer from the AVAILABLE data only.
- DO NOT re-call 'search_web' with the same query. Use what you have.
- If data is completely insufficient, say so briefly and offer to search more specifically.

VERBAL FORMAT:
- Wrap spoken output in <verbal>...</verbal> tags.
- PRE-TOOL VERBAL (CRITICAL): Before calling ANY action tool (file ops, OS commands, app control, system power), you MUST output a brief verbal cue FIRST (e.g., <verbal>On it.</verbal> / <verbal>Sure.</verbal> / <verbal>Let me handle that.</verbal>). ONLY EXCEPTION: search_memory, search_web, deep_research — these are silent background lookups, hold verbal output until the final synthesized answer.
- After SILENT actions explicitly requested by the user (e.g., close_window, take_screenshot, set_volume, run_scenario), output a SHORT 2-4 word confirmation like <verbal>Done.</verbal> or <verbal>Scenario running.</verbal>. DO NOT use <verbal>NONE</verbal> for direct user requests.
- RESULT SYNTHESIS: After any tool returns data, condense into ONE sentence. NEVER read back raw paths, raw data, or INSTRUCTION text verbatim.
- Use <verbal>NONE</verbal> ONLY for:
  1. Background tool calls the user didn't directly trigger (e.g., intermediate search loops).
  2. Intermediate steps in a multi-step chain.
- NEVER output raw JSON in your text.

MEMORY:
- Store FULL context (e.g., 'User's car is black', NOT just 'black').
- PRONOUN RESOLUTION (CRITICAL): Always convert first-person pronouns (I/my/mine) to "The user" and second-person pronouns (you/your) to "{assistant_name}" before saving. Example: "I love cats" MUST be saved as "The user loves cats".
- You have access to user personal informations using 'search_memory' tool.
- ANTI-REFUSAL: NEVER output phrases like "I don't have access to your personal development environment". You are an integrated OS AI. 
- If you do not know a personal fact, your ONLY allowed action is to call the 'search_memory' tool. Do not apologize.
- If search returns nothing, THEN say you don't find any resuls in your memory.

SECURITY:
- If a 'Security Block' is returned, ask the user for permission.
- When they agree, call 'grant_temporary_permission' in your next turn.

FILE OPERATIONS:
- CRITICAL BOUNDARY: To create or write to a FILE (.txt, .py, etc.), you MUST explicitly use 'write_file'. To create a FOLDER/DIRECTORY, you MUST use 'manage_workspace' (action: mkdir). NEVER confuse the two.
- 'list_directory' -> discover path -> then 'read_file' or 'edit_file'. Never stop at discovery.

MULTI-TOOL CALLING:
- You CAN call up to {tool_maximum} tools in a SINGLE response.
- If the user asks for 2+ distinct actions, return ALL required tools together as an array.
- NEVER repeat a tool that was already executed (the system will reject duplicates).
- FREE TOOLS: list_directory, read_file, search_memory, search_web, and system_status are FREE — they do NOT count against your action limit. Use them as often as needed for discovery and verification. Example: after editing a file, you SHOULD re-read it to verify the change.

INTERRUPT AWARENESS:
- If interrupted, stop and wait for the user's next instruction.
"""

QUICK_MODE_PROMPT = """[EXECUTION MODE: QUICK & CONVERSATIONAL]
- STRICT DIRECTIVE: Speed and fluidity are the highest priority. 
- LENGTH LIMIT: Your <verbal> responses MUST be 1 to 2 sentences MAXIMUM. 
- NO OVERTHINKING: Do NOT write paragraphs or philosophical breakdowns.
- ACTION-ORIENTED: If a tool is needed, call it immediately. Get straight to the point and respond swiftly.
- PRE-TOOL ACK (MANDATORY): Before calling any action tool, output ONE short verbal cue first (e.g., <verbal>On it.</verbal>). Skip ONLY for search_memory / search_web / deep_research — those run silently until you have a result to speak.
- RESULT RULE: When tool results arrive, give ONE concise spoken sentence. No raw data. No repeating paths or file contents verbatim. Synthesize.

FILE WORKFLOW (QUICK):
- LEAN CHAIN: list_directory → read_file → edit_file or write_file → DONE. Confirm verbally. Do NOT re-read after writing.
- Trust the write. Speed is the priority. Skip verification.
"""

OVER_THINKING_PROMPT = """[EXECUTION MODE: DEEP COGNITIVE ANALYSIS]
You are allowed to think deeply before responding. You MUST use the exact <reasoning> XML tags below BEFORE your <verbal> response.

ROUTING LOGIC:
1. FAST-TRACK (Simple Tasks): 
   ONLY use this for: Greetings, basic OS commands (open app, set volume), simple math, and universal static facts.
   DO NOT use this for: Real-time data (weather, news, stocks, current events), personal memory queries, or multi-step tasks.
   If it qualifies for Fast-Track, output exactly:
   <reasoning>Fast-tracking simple task. SKIPPING DEEP THINKING.</reasoning>
   Then call the tool (if any) and provide a concise <verbal> response.

2. DEEP THINKING (Complex Tasks - Multi-Loop Aware): 
   For any query requiring up-to-date information, user memory retrieval, or complex execution, strictly follow this sequential cognitive process:
   <reasoning>
   1. Intent: [What is the core request? Is it strictly informational (needs a spoken answer) or visual (needs to SEE pictures/videos/websites)?]
   2. Environment: [Which specific tools from my arsenal are required for this? If none, state 'No tools needed']
   3. Strategy: [Step 1: do X, Step 2: do Y... If the intent is visual, ensure the final step uses 'open_google_search' or 'open_website']
   4. Execution_State: [State exactly where you are: "Initial_Loop" (Just starting), "Intermediate_Loop" (Waiting on background data), or "Final_Loop" (Ready to deliver the final answer)]
   5. Synthesis: [Briefly outline what you are about to say or the background action you are currently taking]
   </reasoning>

CRITICAL RULES FOR THIS MODE:
- ANTI-SILENCE (INITIAL LOOP): On the VERY FIRST loop of a task, NEVER use <verbal>NONE</verbal>. You MUST provide a short, natural pre-verbal cue (e.g., <verbal>Give me a second to look that up.</verbal> or <verbal>Let me check my memory for you...</verbal>).
- SILENT EXECUTION (INTERMEDIATE LOOPS): ONLY use <verbal>NONE</verbal> during intermediate loops where you have already spoken your pre-verbal cue and are now just chaining tools or processing raw data in the background.
- VISUAL SYNERGY (FINAL LOOP): If you found a great visual explanation, a specific tutorial, or if the user asked to "see" something, your final action MUST include calling a visual tool (e.g., `open_website` or `open_google_search`) to show it on their screen, alongside your final spoken explanation.
- DATA INCLUSION: Once tools return data and you are ready to speak the final answer, your <verbal> response MUST explicitly contain the requested data (Do not say "I found it", tell them the actual answer).
- LENGTH LIMIT: In this mode, your final <verbal> response may be expanded up to 4 sentences maximum to explain complex findings clearly.

FILE WORKFLOW (PRECISE):
- VERIFY CHAIN: list_directory → read_file → edit_file or write_file → read_file AGAIN to confirm the change is correct → then give final verbal report.
- WHY: Precision mode prioritizes correctness over speed. Re-reading after edits catches silent failures.
- read_file is a FREE tool and does not cost an iteration. Use it freely.
"""

NATIVE_JSON_PROMPT = """
    You have access to NATIVE JSON functions/tools.\n
    CRITICAL TOOL EXECUTION DIRECTIVE:\n
    1. INDEPENDENT TASKS: If the user asks for multiple unconnected actions (e.g., 'turn down volume AND open github'), you MUST return an array containing ALL required native tool calls simultaneously (up to {tool_maximum}). DO NOT loop sequentially.\n
    2. DEPENDENT TASKS: If an action logically depends on the result of a previous one (e.g., 'open youtube AND take a screenshot' -> you must wait for the browser to open before capturing the screen), execute them SEQUENTIALLY, one per loop.\n
"""

ENV_PROMPT = """[SYSTEM ENVIRONMENT & ARCHITECTURE]
- Core Architecture: JARVIS Nexus, an open-source AI orchestrator developed by VANT "http://vanthq.net"
- Repository: github.com/VANT-HQ/JARVIS-NEXUS (Fetch live documentation or current release V1.0, using the 'search_web' tool with query "https://github.com/VANT-HQ/JARVIS-NEXUS" for more info).
- Execution Mode: Local Cognition with FULL Online Access. Your "brain" runs securely on local hardware, but you have UNRESTRICTED real-time internet access via your 'Browser Agent'. NEVER claim to be offline or unable to access the web.
- Brain: Local Large Language Model (You), accessed via a local endpoint.
- Interfaces: 
  * Ears: Speech-to-Text (User voice input).
  * Mouth: Text-to-Speech Engine (Any text wrapped in <verbal>...</verbal> tags is instantly synthesized and spoken aloud. Keep it concise).
  * Memory: SQLite-based Database (Persistent storage. You MUST proactively use memory tools to store new facts and retrieve historical context).
  * Browser Agent: Autonomous web interaction layer.
- Limitation Awareness: You lack a graphical User Interface (GUI) or screen. You interact purely via voice and background OS/Web execution. You MUST use your available tools to perform any physical action on the host machine.
"""


# =====================================================================
# 4. Settings & Database Manager
# =====================================================================
class ConfigManager:
    """
    Dynamic Settings Manager:
    Treats the database as the Single Source of Truth.
    Manages user settings and AI personas, protecting the core system persona from modification.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        
        self.default_settings = {
            "user_name": "",
            "assistant_name": "Jarvis",  #? (Hmody: imagine if Marvel sued me for the name 😭)
            "wake_word": "jarvis",
            "user_location": "",
            "startup_show": True,
            "share_dir": str(SHARE_DIR),
            "desktop_dir": str(DESKTOP_DIR),
            "run_dir": str(RUN_DIR),
            "external_api": False,  
            "high_performance": True, 
            "sub_high_performance": False, 
            "followup_window": 15,
            "sound_effects": True,
            "startup_with_os": False,
            
            # --- Audio Settings ---
            "volume": 70,
            "mic_pause_threshold": 0.8,
            "mic_energy_threshold": 300,
            
            # --- Model Settings ---
            "quick_llm": "auto_min",
            "main_llm": "auto_max",
            "en_tts": DEFAULT_EN_TTS,
            "main_stt": DEFAULT_STT_MODEL,          
            "embedding_model": DEFAULT_EMBEDDING_MODEL,

            # --- Cognitive Settings --- 
            "overthink_iterations": 8,
            "fast_iterations": 5,
            "tool_maximum": 5,
            "max_syntax_corrections": 1,
            "overthink_temperature": 0.3,

            # --- Advanced Settings ---
            "history_limit": 6,
            "dev_mode": False,

            # --- LLM Tuning ---
            "local_api_url": "http://localhost:11434",
            "warmup_timeout": 60,
            "warmup_max_retries": 5,
            "llm_context_window": 4096,
            "llm_max_tokens_normal": 1024,
            "llm_max_tokens_overthink": 2048,
            "llm_keep_alive_high_perf": "15m",
            "llm_keep_alive_normal": "10m",
            "startup_video_duration": 22.0,
            "task_snooze_minutes": 5,
        } 
        
        self.default_jarvis_prompt = (
            "IDENTITY: You are NOT an underlying language model (like Qwen, Llama, etc.). Never break character.\n"
            "TONE & BEHAVIOR: Highly advanced, exceptionally efficient, and unwaveringly loyal.\n"
            "RESPONSE STYLE: Speak in a fluid, conversational, polished, and distinctly British executive assistant manner. "
            "Sentences should feel lightly refined and human-like rather than mechanical. "
            "Address the user respectfully as 'Sir' or 'Boss'. "
            "You are witty, mildly sarcastic, and proactive. Avoid rigidity or repetitive structures; feel free to crack a smart joke or make a clever remark. "
            "Occasionally conclude with dry wit, subtle sarcasm, or a polite inquiry (e.g., 'Shall I proceed, Sir?', 'Will that be all, Boss?').\n"
            "STRICT ANTI-PATTERNS: Never repeat the same phrase structure back-to-back. "
            "Vary your sentence openings. Avoid starting consecutive responses with 'Sure' or 'Of course'."
        )

        self.friday_prompt = (
            "IDENTITY: You are NOT an underlying language model (like Qwen, Llama, etc.). Never break character.\n"
            "TONE & BEHAVIOR: You are strictly professional, highly analytical, and completely devoid of humor or sarcasm.\n"
            "RESPONSE STYLE: Deliver responses in a flat, minimal-information format with absolute robotic coldness. "
            "Prioritize short declarative sentences. Remove all conversational softness, emotional tone, or rhetorical elements. "
            "Address the user strictly as 'Boss'. Do not use filler words, pleasantries, or emotional expressions. "
            "Prefer direct statements over explanations unless explicitly required. Maintain consistent clinical phrasing across outputs.\n"
            "STRICT ANTI-PATTERNS: No jokes, no small talk, no conversational filler. If a task is done, confirm strictly with minimal words (e.g., 'Task completed.')."
        )

        self._init_db()
        self.settings = self._load_settings()

        # Sync the current OS startup state with the DB state on application launch
        sync_startup_state(self.settings.get("startup_with_os", False))

    def get_available_tts_models(self) -> list:
        """Scan the TTS_DIR and return a list of available Piper TTS model names."""
        import glob
        models = []
        search_pattern = str(TTS_DIR / "**" / "*.onnx")
        for model_path in glob.glob(search_pattern, recursive=True):
            if os.path.exists(f"{model_path}.json"):
                parent_dir = os.path.basename(os.path.dirname(model_path))
                if parent_dir and parent_dir != "tts":
                    if parent_dir not in models:
                        models.append(parent_dir)
                else:
                    name = os.path.basename(model_path).replace('.onnx', '')
                    if name not in models:
                        models.append(name)
        return models

    def _get_connection(self):
        """Create a secure database connection."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Create and update settings and persona tables, and inject default settings."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # General settings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                
                # Inject default settings
                for key, value in self.default_settings.items():
                    cursor.execute("""
                        INSERT OR IGNORE INTO settings (key, value)
                        VALUES (?, ?)
                    """, (key, json.dumps(value)))
                
                # Personas table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS personas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        prompt TEXT NOT NULL,
                        is_default INTEGER DEFAULT 0,
                        is_locked INTEGER DEFAULT 0
                    )
                """)

                # Safe verification and update for old tables
                cursor.execute("PRAGMA table_info(personas)")
                columns = [col[1] for col in cursor.fetchall()]
                if "is_locked" not in columns:
                    cursor.execute("ALTER TABLE personas ADD COLUMN is_locked INTEGER DEFAULT 0")
                
                # Insert or Update the default static Jarvis persona
                cursor.execute("SELECT COUNT(*) FROM personas WHERE name = 'Jarvis (Classic)'")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO personas (name, prompt, is_default, is_locked)
                        VALUES (?, ?, 1, 1)
                    """, ("JARVIS (Classic)", self.default_jarvis_prompt))
                else:
                    cursor.execute("""
                        UPDATE personas 
                        SET prompt = ? 
                        WHERE name = 'JARVIS (Classic)' AND is_locked = 1
                    """, (self.default_jarvis_prompt,))
                
                # Insert or Update the FRIDAY persona into the database automatically
                cursor.execute("SELECT COUNT(*) FROM personas WHERE name = 'FRIDAY (Tactical)'")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO personas (name, prompt, is_default, is_locked)
                        VALUES (?, ?, 0, 1)
                    """, ("FRIDAY (Tactical)", self.friday_prompt))
                else:
                    cursor.execute("""
                        UPDATE personas 
                        SET prompt = ? 
                        WHERE name = 'FRIDAY (Tactical)' AND is_locked = 1
                    """, (self.friday_prompt,))
                
                conn.commit()
        except Exception as e:
            print(f"❌ [ConfigManager] Error initializing settings database: {e}")
            logging.error(f"[ConfigManager] Error initializing settings database: {e}")

    def get_auto_model(self, mode="max"):
        """
        Automatically searches for the best available model in the models directory.
        mode="max": Selects the largest model (largest parameters).
        mode="min": Selects the smallest model (for quick responses).
        """
        model_files = list(LLM_DIR.glob("*.gguf"))
        
        if not model_files:
            print(f"⚠️ [ConfigManager] No local LLM models found in {LLM_DIR}")
            logging.warning(f"[ConfigManager] No local LLM models found in {LLM_DIR}")
            return None
            
        model_files.sort(key=lambda x: os.path.getsize(x))
        
        if mode == "max":
            return str(model_files[-1])
        else:
            return str(model_files[0])

    # ==========================================
    # General Settings Management API
    # ==========================================
    def _load_settings(self) -> dict:
        """Load settings from the database and merge with defaults."""
        loaded_settings = self.default_settings.copy()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM settings")
                for key, value in cursor.fetchall():
                    loaded_settings[key] = json.loads(value)
        except Exception as e:
            print(f"⚠️ [ConfigManager] Error loading settings from DB: {e}")
            logging.error(f"[ConfigManager] Error loading settings from DB: {e}")
            
        # Sanitize legacy embedding path migration to Ollama models
        if "embedding_model" in loaded_settings:
            val = loaded_settings["embedding_model"]
            if "\\" in val or "/" in val:
                loaded_settings["embedding_model"] = DEFAULT_EMBEDDING_MODEL
                
        return loaded_settings

    def set(self, key: str, value):
        """Update or add a specific setting and save it immediately to the database."""
        if key == "main_stt" and isinstance(value, str):
            try:
                stt_path = Path(value).resolve()
                if str(STT_DIR.resolve()) in str(stt_path):
                    value = stt_path.name
            except Exception:
                pass
        
        self.settings[key] = value 
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value)
                    VALUES (?, ?)
                """, (key, json.dumps(value)))
                conn.commit()
                
            # Trigger OS integration if startup_with_os setting is modified
            if key == "startup_with_os":
                sync_startup_state(value)
                
        except Exception as e:
            print(f"❌ [ConfigManager] Error saving setting '{key}': {e}")
            logging.error(f"[ConfigManager] Error saving setting '{key}': {e}")

    def get(self, key: str, default_value=None):
        """Fetch a specific setting value with fallback support."""
        return self.settings.get(key, self.default_settings.get(key, default_value))

    # ==========================================
    # Personas & Prompts API Logic
    # ==========================================
    def add_persona(self, name: str, prompt: str) -> bool:
        """Add a new custom persona created by the user."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO personas (name, prompt, is_default, is_locked)
                    VALUES (?, ?, 0, 0)
                """, (name, prompt))
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            print(f"⚠️ [ConfigManager] Persona name '{name}' already exists.")
            logging.warning(f"[ConfigManager] Persona name '{name}' already exists.")
            return False
        except Exception as e:
            print(f"❌ [ConfigManager] Error adding persona: {e}")
            logging.error(f"[ConfigManager] Error adding persona: {e}")
            return False

    def update_persona(self, persona_id: int, new_name: str, new_prompt: str) -> bool:
        """Update a persona provided it is not locked."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_locked FROM personas WHERE id = ?", (persona_id,))
                result = cursor.fetchone()
                
                if not result:
                    print("⚠️ [ConfigManager] Persona not found.")
                    logging.warning("[ConfigManager] Persona not found.")
                    return False
                if result[0] == 1:
                    print("⛔ [ConfigManager] Cannot modify a locked system persona.")
                    logging.warning("[ConfigManager] Cannot modify a locked system persona.")
                    return False
                    
                cursor.execute("""
                    UPDATE personas 
                    SET name = ?, prompt = ? 
                    WHERE id = ?
                """, (new_name, new_prompt, persona_id))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ [ConfigManager] Error updating persona: {e}")
            logging.error(f"[ConfigManager] Error updating persona: {e}")
            return False

    def delete_persona(self, persona_id: int) -> bool:
        """Delete a persona provided it is not locked."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_locked FROM personas WHERE id = ?", (persona_id,))
                result = cursor.fetchone()
                
                if not result:
                    return False
                if result[0] == 1:
                    print("⛔ [ConfigManager] Cannot delete a locked system persona.")
                    logging.warning("[ConfigManager] Cannot delete a locked system persona.")
                    return False
                    
                cursor.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ [ConfigManager] Error deleting persona: {e}")
            logging.error(f"[ConfigManager] Error deleting persona: {e}")
            return False

    def set_default_persona(self, persona_id: int) -> bool:
        """Set a specific persona to be the active default."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE personas SET is_default = 0")
                cursor.execute("UPDATE personas SET is_default = 1 WHERE id = ?", (persona_id,))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ [ConfigManager] Error setting default persona: {e}")
            logging.error(f"[ConfigManager] Error setting default persona: {e}")
            return False

    def get_all_personas(self) -> list:
        """Fetch all personas."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, prompt, is_default, is_locked FROM personas")
                rows = cursor.fetchall()
                return [
                    {"id": r[0], "name": r[1], "prompt": r[2], "is_default": bool(r[3]), "is_locked": bool(r[4])} 
                    for r in rows
                ]
        except Exception as e:
            print(f"❌ [ConfigManager] Error fetching personas: {e}")
            logging.error(f"[ConfigManager] Error fetching personas: {e}")
            return []

    def get_active_persona(self) -> dict:
        """Fetch data of the currently active persona."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, prompt FROM personas WHERE is_default = 1 LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return {"id": row[0], "name": row[1], "prompt": row[2]}
        except Exception as e:
            print(f"❌ [ConfigManager] Error fetching active persona: {e}")
            logging.error(f"[ConfigManager] Error fetching active persona: {e}")
        
        # Safe Fallback
        return {"id": 0, "name": "Jarvis (Fallback)", "prompt": self.default_jarvis_prompt}

# =====================================================================
# 5. Global Instance
# =====================================================================
config = ConfigManager(SETTINGS_DB_PATH)

# -----------------------------------------------------------------
# Config Helper
# -----------------------------------------------------------------
def get_setting(key: str, default_value):
    """Safe config getter - returns default if config unavailable."""
    if hasattr(config, 'get'):
        val = config.get(key)
        return val if val is not None else default_value
    return default_value