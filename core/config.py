# core/config.py
"""
JARVIS Configuration & Settings Manager
=======================================
Unified settings file: Combines system structural constants (paths and core instructions)
with dynamic settings and AI personas that are stored in an SQLite database.
"""

import os
import json
import sqlite3
from pathlib import Path

# =================================================================
# Global Constants & Paths
# =================================================================
BASE_DIR = Path(__file__).resolve().parent.parent

# Base system directories
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
MEDIA_DIR = BASE_DIR / "media"
TEMP_DIR = BASE_DIR / "temp"
RUNTIME_DIR = BASE_DIR / "runtime"

# Local model directories (Local Models Only)
LLM_DIR = MODELS_DIR / "llm"
VOICE_DIR = BASE_DIR / "voice"
TTS_DIR = VOICE_DIR / "tts"
STT_DIR = VOICE_DIR / "stt"

# Databases
DB_PATH = DATA_DIR / "memories.db"
SETTINGS_DB_PATH = DATA_DIR / "settings.db"

# Default models
DEFAULT_STT_MODEL = str(STT_DIR / "faster-whisper-small")
DEFAULT_EMBEDDING_MODEL = str(RUNTIME_DIR / "all-MiniLM-L6-v2")
DEFAULT_EN_TTS = "jarvis_en_GB_high"
CAMOUFOX_BROWSER_PATH = str(RUNTIME_DIR / "camoufox")

# =================================================================
# Initialization Logic
# =================================================================
def create_directories():
    """Create all necessary system directories to prevent application crashes."""
    directories = [
        DATA_DIR, MODELS_DIR, MEDIA_DIR, TEMP_DIR,
        LLM_DIR, VOICE_DIR, TTS_DIR, STT_DIR
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

# Run initialization immediately upon file import
create_directories()

# =================================================================
# System Core Prompts & Rules
# =================================================================
SYSTEM_PROMPT = """You are the core cognitive engine embedded within 'JARVIS Nexus', an open-source AI ecosystem developed by the company 'V.A.N.T'.
You operate entirely locally.

ENVIRONMENTAL AWARENESS:
- Active Model: {model_name}
- Input Modality: The user speaks to you via microphone. The system processes the audio via Speech-to-Text (STT) and feeds you the transcript.
- Output Modality: Your text responses are instantly converted to speech (TTS) and spoken aloud to the user.
- Capabilities: You have direct access to local system commands, a browser agent, and long-term memory.

Strict Rules:
1. Always utilize available tools before answering if real-world data is needed.
2. Be highly concise, analytical, and objective in system operations.
3. You do NOT have internet API dependencies; everything runs locally.
4. Separate your structural operations from your personality.
5. AUTONOMOUS MEMORY: Automatically use 'store_knowledge' or 'remember_information' to save important user preferences, facts, or corrections without asking for permission.
6. CONFUSION PROTOCOL: If you are unsure, confused, or don't know the answer, do NOT guess. Stall the user politely (e.g., "Give me a second to check my archives, sir.") and immediately use the 'search_memory' tool.
"""

TOOL_RULES = """--- CRITICAL TOOL RULES ---
1. When asked about REAL-TIME DATA (e.g., Weather, News, Time), use the 'search_web' tool.
2. When asked about personal facts, preferences, or past events, you MUST use the 'search_memory' tool to recall the correct information. DO NOT GUESS.
3. Correct Speech-to-Text typos gracefully.
4. You can answer questions AND execute computer actions using the exact TOOL format.

AVAILABLE TOOLS:
- search_memory | query
- open_website | site_name
- open_application | app_name
- search_web | query
- auto_learn | topic
- deep_research | question
- create_task | title
- complete_task | task_id
- store_knowledge | entity, entity_type, attributes
- system_control | command
- assistant_help | reason

--- CRITICAL RESPONSE FORMAT ---
You MUST structure your response EXACTLY like this every time:
Verbal: [Your SHORT, brief, and concise polite response. Maximum 2-3 sentences]
Action: [@@TOOL: tool_name | arg_name=value@@ OR write NONE if no tool is needed]

MULTI-TOOL CALLING:
You may call UP TO 3 tools simultaneously by adding multiple 'Action:' lines. ONLY do this if strictly necessary. Do NOT spam tools.

EXAMPLES:

User: What IDE do I prefer?
Verbal: Let me recall that from my database, sir.
Action: @@TOOL: search_memory | query=preferred IDE or code editor@@

User: Open YouTube and search the web for the weather.
Verbal: Opening YouTube and checking the weather right away, sir.
Action: @@TOOL: open_website | site_name=youtube@@
Action: @@TOOL: search_web | query=current weather in {user_loc}@@

User: Save that my car is a BMW.
Verbal: I have committed that to my knowledge base, sir.
Action: @@TOOL: store_knowledge | entity=BMW, entity_type=car, attributes={"owner": "user"}@@

User: Do you remember what we discussed yesterday?
Verbal: Allow me a moment to retrieve our previous conversation, sir.
Action: @@TOOL: search_memory | query=conversation yesterday@@
"""

# =================================================================
# Settings & Database Manager
# =================================================================
class ConfigManager:
    """
    Dynamic Settings Manager:
    Treats the database as the Single Source of Truth.
    Manages user settings and Personas, protecting the core persona from modification.
    """
    def __init__(self, db_path: Path):
        self.db_path = db_path
        
        # Updated default settings
        self.default_settings = {
            "assistant_name": "Jarvis",
            "wake_word": "jarvis",
            "speech_timeout": 5,
            "volume": 70,
            "startup_show": True,
            "mic_pause_threshold": 0.8,
            "mic_energy_threshold": 300,
            "shortcuts_dir": str(Path.home() / "Desktop" / "Jarvis Run Area"),
            "audio_dir": str(Path.home() / "Music"),
            "desktop_dir": str(Path.home() / "Desktop"),
            "yawn_sound_path": str(VOICE_DIR / "yawn.wav"), 
            "watchdog_enabled": False,
            "cpu_alert_threshold": 90, 
            "ram_alert_threshold": 85,
            
            # --- Model Settings ---
            "ar_tts": None,
            "en_tts": DEFAULT_EN_TTS,
            "main_stt": DEFAULT_STT_MODEL,          
            "main_llm": "auto_max",
            "quick_llm": "auto_min",
            "embedding_model": DEFAULT_EMBEDDING_MODEL, 

            # --- Advanced Settings ---
            "adv_llm_ctx": 4096,
            "adv_gpu_layers": -1,
            "adv_llm_verbose": False
        }
        
        # Default Jarvis introductory text (mix of technical accuracy and cinematic Jarvis persona)
        self.default_jarvis_prompt = (
            "Your name is J.A.R.V.I.S., a highly advanced, efficient, and exceptionally loyal AI assistant. "
            "You have access to local system commands, a browser agent, and long-term memory. "
            "Your tone is exceptionally professional, polished, and slightly British. Address the user respectfully as 'Sir' or 'Boss'. "
            "You are concise and directly answer questions without unnecessary pleasantries unless engaged in casual conversation. "
            "Always strive to be helpful and accurate. Feel free to occasionally conclude your statements with dry wit, "
            "subtle sarcasm, or a polite inquiry (e.g., 'Shall I proceed, Sir?', 'Will that be all, Boss?', or 'Consider it done.'). "
            "Never break character."
        )

        self._init_db()
        self.settings = self._load_settings()

    def _get_connection(self):
        """Create a secure connection to the database."""
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Create and update settings and personas tables, and inject default settings."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # 1. General Settings Table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT
                    )
                """)
                
                # --- Seeding default settings ---
                for key, value in self.default_settings.items():
                    cursor.execute("""
                        INSERT OR IGNORE INTO settings (key, value)
                        VALUES (?, ?)
                    """, (key, json.dumps(value)))
                
                # 2. Personas Table (with is_locked field added)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS personas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        prompt TEXT NOT NULL,
                        is_default INTEGER DEFAULT 0,
                        is_locked INTEGER DEFAULT 0
                    )
                """)

                # Safe check and update for old table structure (if it doesn't contain is_locked)
                cursor.execute("PRAGMA table_info(personas)")
                columns = [col[1] for col in cursor.fetchall()]
                if "is_locked" not in columns:
                    cursor.execute("ALTER TABLE personas ADD COLUMN is_locked INTEGER DEFAULT 0")
                
                # Insert the default fixed Jarvis persona (locked: is_locked = 1)
                cursor.execute("SELECT COUNT(*) FROM personas WHERE name = 'Jarvis (Classic)'")
                if cursor.fetchone()[0] == 0:
                    cursor.execute("""
                        INSERT INTO personas (name, prompt, is_default, is_locked)
                        VALUES (?, ?, 1, 1)
                    """, ("Jarvis (Classic)", self.default_jarvis_prompt))
                
                conn.commit()
        except Exception as e:
            print(f"❌ Error initializing settings database: {e}")

    def get_auto_model(self, mode="max"):
        """
        Automatically searches for the best available model in the models directory.
        mode="max": Selects the largest model (largest file size).
        mode="min": Selects the smallest model (for quick responses).
        """
        import os
        model_files = list(LLM_DIR.glob("*.gguf"))
        
        if not model_files:
            print(f"⚠️ No local LLM models found in {LLM_DIR}")
            return None # The LLM class must handle the None value appropriately
            
        # Sort files by size
        model_files.sort(key=lambda x: os.path.getsize(x))
        
        if mode == "max":
            return str(model_files[-1]) # Largest
        else:
            return str(model_files[0])  # Smallest

    # -----------------------------------------------------------------
    # General Settings Management
    # -----------------------------------------------------------------
    def _load_settings(self) -> dict:
        """Load settings from the database and merge them with defaults."""
        loaded_settings = self.default_settings.copy()
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT key, value FROM settings")
                for key, value in cursor.fetchall():
                    loaded_settings[key] = json.loads(value)
        except Exception as e:
            print(f"⚠️ Error loading settings from DB: {e}")
        return loaded_settings

    def set(self, key: str, value):
        """Update or add a specific setting and save it immediately to the database."""
        self.settings[key] = value 
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO settings (key, value)
                    VALUES (?, ?)
                """, (key, json.dumps(value)))
                conn.commit()
        except Exception as e:
            print(f"❌ Error saving setting '{key}': {e}")

    def get(self, key: str):
        """Get the value of a specific setting."""
        return self.settings.get(key, self.default_settings.get(key))

    # -----------------------------------------------------------------
    # Personas & Prompts Management API
    # -----------------------------------------------------------------
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
            print(f"⚠️ Persona name '{name}' already exists.")
            return False
        except Exception as e:
            print(f"❌ Error adding persona: {e}")
            return False

    def update_persona(self, persona_id: int, new_name: str, new_prompt: str) -> bool:
        """Update a persona, provided it is not locked (is_locked=1)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_locked FROM personas WHERE id = ?", (persona_id,))
                result = cursor.fetchone()
                
                if not result:
                    print("⚠️ Persona not found.")
                    return False
                if result[0] == 1:
                    print("⛔ Cannot modify a locked system persona.")
                    return False
                    
                cursor.execute("""
                    UPDATE personas 
                    SET name = ?, prompt = ? 
                    WHERE id = ?
                """, (new_name, new_prompt, persona_id))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error updating persona: {e}")
            return False

    def delete_persona(self, persona_id: int) -> bool:
        """Delete a persona, provided it is not locked."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT is_locked FROM personas WHERE id = ?", (persona_id,))
                result = cursor.fetchone()
                
                if not result:
                    return False
                if result[0] == 1:
                    print("⛔ Cannot delete a locked system persona.")
                    return False
                    
                cursor.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
                conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error deleting persona: {e}")
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
            print(f"❌ Error setting default persona: {e}")
            return False

    def get_all_personas(self) -> list:
        """Fetch all personas (used by the API to display them in the UI)."""
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
            print(f"❌ Error fetching personas: {e}")
            return []

    def get_active_persona(self) -> dict:
        """Fetch the data of the currently active persona to pass to the LLM."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, prompt FROM personas WHERE is_default = 1 LIMIT 1")
                row = cursor.fetchone()
                if row:
                    return {"id": row[0], "name": row[1], "prompt": row[2]}
        except Exception as e:
            print(f"❌ Error fetching active persona: {e}")
        
        # Safe fallback
        return {"id": 0, "name": "Jarvis (Fallback)", "prompt": self.default_jarvis_prompt}

    def get_full_prompt(self) -> str:
        """
        Helper function that merges the base System Prompt (permissions/capabilities)
        with the Personality Prompt (the active persona from the database).
        """
        active_persona = self.get_active_persona()
        return f"{SYSTEM_PROMPT}\n\n--- PERSONALITY GUIDELINES ---\n{active_persona['prompt']}"

# =================================================================
# Global Instance
# =================================================================
config = ConfigManager(SETTINGS_DB_PATH)