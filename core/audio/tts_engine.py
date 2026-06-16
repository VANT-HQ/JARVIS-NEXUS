# core/audio/tts_engine.py

"""
JARVIS Text-to-Speech (TTS) Engine
==================================
A high-performance Piper-TTS engine featuring a Double-Queue (Producer-Consumer)
architecture for zero-latency, concurrent text synthesis and playback.
"""

import os
# Must be set before importing pygame to suppress the welcome prompt
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "1"

import sys
import glob
import logging
import json
import re
import platform
import threading
import wave
import time
import queue
import uuid
from pathlib import Path

import pygame

# =====================================================================
# Dynamic System Paths & Configuration
# =====================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.config import config, TTS_DIR, CACHE_DIR
except ImportError as e:
    raise RuntimeError(f"[Mouth] ❌ Fatal Error: Could not import config. {e}")

# --- PYINSTALLER DLL FIX FOR PIPER / ONNXRUNTIME --- #? (Hmody: 5days IN THAT HELL, blame it for the release delay)
# Pin onnxruntime.dll in memory from the correct path BEFORE import.
# Without this, ctranslate2's DLLs (loaded by faster_whisper) can
# pollute the process space and cause onnxruntime to crash.
if getattr(sys, 'frozen', False):
    bundle_dir = sys._MEIPASS
    os.environ['PATH'] = bundle_dir + os.pathsep + os.environ.get('PATH', '')
    if hasattr(os, 'add_dll_directory'):
        for _d in [
            os.path.join(bundle_dir, 'onnxruntime', 'capi'),
            os.path.join(bundle_dir, 'piper'),
            bundle_dir,
        ]:
            if os.path.isdir(_d):
                try:
                    os.add_dll_directory(_d)
                except Exception:
                    pass
    import ctypes
    _ort_dll = os.path.join(bundle_dir, 'onnxruntime', 'capi', 'onnxruntime.dll')
    if os.path.isfile(_ort_dll):
        try:
            ctypes.WinDLL(_ort_dll)
        except Exception:
            pass
# ---------------------------------------------------

try:
    from piper import PiperVoice
except ImportError as e:
    PiperVoice = None
    print(f"[Mouth] ❌ Fatal Error: piper-tts is not installed or failed to load. {e}")
    logging.error(f"[Mouth] Fatal Error: piper-tts is not installed or failed to load. {e}")


class Mouth:
    def __init__(self):
        # Centralized config variables (DRY Principle)
        self.assistant_name = config.get("assistant_name", "Jarvis")
        self.tts_dir = TTS_DIR
        self.cache_dir = CACHE_DIR
        
        # Ensure cache dir exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.voices = {} 
        self.sample_rates = {} 
        
        self.is_speaking = False
        self.is_synthesizing = False 
        self.spoken_history = []
        self.current_speaking_text = ""  
        self.current_lang = 'en' 
        
        # Pre-initialize interruption state variables
        self._last_interrupted_text = ""
        self._last_interrupted_history = []
        
        # 🚀 Double-Queue (Producer-Consumer) system to eliminate silence gaps
        self.speech_queue = queue.Queue()
        self.playback_queue = queue.Queue()
        self._stop_flag = False
        
        # Event-based signal replaces spin-lock polling
        self.speech_done_event = threading.Event()
        self.speech_done_event.set()  # Start in "not busy" state
        
        # Thread 1: Synthesizer
        self.synth_thread = threading.Thread(target=self._synth_worker, daemon=True)
        self.synth_thread.start()
        
        # Thread 2: Player
        self.play_thread = threading.Thread(target=self._play_worker, daemon=True)
        self.play_thread.start()
        
        # ==========================================================
        # ⚡ PRE-COMPILED REGEX OPTIMIZATION
        # ==========================================================
        self.PATTERN_CODE_BLOCK = re.compile(r'```.*?```', flags=re.DOTALL)
        self.PATTERN_INLINE_CODE = re.compile(r'`.*?`')
        self.PATTERN_WHITELIST = re.compile(r'[^a-zA-Z0-9\s.,!?\'"-]')
        self.PATTERN_SPACES = re.compile(r'\s+')

        raw_pronunciation_map = {
            # 1. Units & Symbols
            r'\b(?:kg|kgs)\b': 'kilograms',
            r'(?<=\d)kg\b': ' kilograms', 
            r'\b(?:km|kms)\b': 'kilometers',
            r'(?<=\d)km\b': ' kilometers',
            r'\b(?:cm|cms)\b': 'centimeters',
            r'(?<=\d)cm\b': ' centimeters',
            r'\b(?:mm|mms)\b': 'millimeters',
            r'(?<=\d)mm\b': ' millimeters',
            r'\b(?:mg|mgs)\b': 'milligrams',
            r'(?<=\d)mg\b': ' milligrams',
            r'\bmb\b': 'megabytes',
            r'(?<=\d)mb\b': ' megabytes',
            r'\bgb\b': 'gigabytes',
            r'(?<=\d)gb\b': ' gigabytes',
            r'\btb\b': 'terabytes',
            r'(?<=\d)tb\b': ' terabytes',
            r'%': ' percent ',
            r'\$': ' dollars ',
            r'&': ' and ',
            r'\+': ' plus ',
            r'=': ' equals ',
            r'/': ' per ',    
            r'@': ' at ',    

            # 2. Titles & Adjectives
            r'\bmr\.?\b': 'mister',
            r'\bmrs\.?\b': 'missus',
            r'\bms\.?\b': 'miss',
            r'\bdr\.?\b': 'doctor',
            r'\bprof\.?\b': 'professor',
            r'\bsr\.?\b': 'senior',
            r'\bjr\.?\b': 'junior',
            r'\bcapt\.?\b': 'captain',
            r'\bsgt\.?\b': 'sergeant',
            r'\blt\.?\b': 'lieutenant',
            r'\bgen\.?\b': 'general',
            r'\brev\.?\b': 'reverend',

            # 3. Additional Measurement Units
            r'\b(?:lb|lbs)\.?\b': 'pounds',
            r'(?<=\d)lb\b': ' pounds',
            r'(?<=\d)lbs\b': ' pounds',
            r'\boz\.?\b': 'ounces',
            r'(?<=\d)oz\b': ' ounces',
            r'(?<=\d)in\.?\b': ' inches',  
            r'(?<=\d)ft\.?\b': ' feet',
            r'(?<=\d)yd\.?\b': ' yards',
            r'(?<=\d)mi\.?\b': ' miles',
            r'\bmph\b': 'miles per hour',
            r'(?<=\d)mph\b': ' miles per hour',
            r'\bkph\b': 'kilometers per hour',
            r'\brpm\b': 'revolutions per minute',
            r'\bgal\.?\b': 'gallons',
            r'\btsp\.?\b': 'teaspoon',
            r'\btbsp\.?\b': 'tablespoon',

            # 4. Months & Days
            r'\bjan\.?\b': 'january',
            r'\bfeb\.?\b': 'february',
            r'\bmar\.?\b': 'march',
            r'\bapr\.?\b': 'april',
            r'\baug\.?\b': 'august',
            r'\bsept?\.?\b': 'september',
            r'\boct\.?\b': 'october',
            r'\bnov\.?\b': 'november',
            r'\bdec\.?\b': 'december',
            r'\bmon\.?\b': 'monday',
            r'\btue\.?\b': 'tuesday',
            r'\bwed\.?\b': 'wednesday',
            r'\bthu\.?\b': 'thursday',
            r'\bfri\.?\b': 'friday',
            r'\bsat\.?\b': 'saturday',
            r'\bsun\.?\b': 'sunday',

            # 5. Addresses & Places
            r'\bave\.?\b': 'avenue',
            r'\bblvd\.?\b': 'boulevard',
            r'\brd\.?\b': 'road',
            r'\bln\.?\b': 'lane',
            r'\bapt\.?\b': 'apartment',
            r'\bste\.?\b': 'suite',
            r'\bbldg\.?\b': 'building',

            # 6. Businesses & Institutions
            r'\binc\.?\b': 'incorporated',
            r'\bcorp\.?\b': 'corporation',
            r'\bllc\.?\b': 'limited liability company',
            r'\bltd\.?\b': 'limited',
            r'\bco\.?\b': 'company',
            r'\bdept\.?\b': 'department',
            r'\buniv\.?\b': 'university',

            # 7. Latin & General Abbreviations
            r'\bvs\.?\b': 'versus',
            r'\bv\.?\b': 'versus',
            r'\betc\.?\b': 'et cetera',
            r'\bi\.e\.?\b': 'that is',
            r'\be\.g\.?\b': 'for example',
            r'\bapprox\.?\b': 'approximately',
            r'\bfaq\.?\b': 'frequently asked questions',
            
            # 8. Time Abbreviations
            r'\bh\.?\b': 'hour',
            r'\bhr\.?\b': 'hour',
            r'\bhrs\.?\b': 'hours',
            r'\bsec\.?\b': 'seconds',
            r'\bsecs\.?\b': 'seconds',
            r'\bmins\.?\b': 'minutes',
            r'(?<=\d)min\.?\b': ' minutes'
        }
        
        self.COMPILED_PRONUNCIATION_MAP = [
            (re.compile(pattern, re.IGNORECASE), replacement) 
            for pattern, replacement in raw_pronunciation_map.items()
        ]
        
        print(f"🔊 Initializing {self.assistant_name.capitalize()}'s Mouth Engine (Piper Only)...")
            
        self._cleanup_temp_files() 
        self._load_piper_models()

    # Applied DRY principle by reusing self._safe_delete
    def _cleanup_temp_files(self):
        patterns = ["temp_speech_*.wav", "temp_speech.wav"]
        for pattern in patterns:
            search_path = str(self.cache_dir / pattern)
            for file_path in glob.glob(search_path):
                self._safe_delete(file_path)

    def _safe_delete(self, filepath):
        try:
            if os.path.exists(filepath): 
                os.remove(filepath)
        except OSError: 
            pass

    def _load_piper_models(self):
        if not PiperVoice: return

        while True:
            # Use centralized tts_dir
            search_pattern = str(self.tts_dir / "**" / "*.onnx")
            models = glob.glob(search_pattern, recursive=True)

            if not models:
                print(f"   [Mouth] ⚠️ No Piper .onnx models found in {self.tts_dir}.")
                from core.bootstrap.env_setup import safe_run_wizard
                safe_run_wizard()
                continue

            target_model = config.get("en_tts", "")
            loaded = False

            for model_path in models:
                parent_dir = os.path.basename(os.path.dirname(model_path))
                name = os.path.basename(model_path).replace('.onnx', '')
                
                if target_model and target_model not in (parent_dir, name):
                    continue

                config_path = f"{model_path}.json"
                
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            conf = json.load(f)
                            
                        sr = conf.get('audio', {}).get('sample_rate', 22050)
                        
                        try:
                            pygame.mixer.quit()
                            pygame.mixer.init(frequency=sr, size=-16, channels=1, buffer=512)
                            print(f"   [Mouth] ✅ pygame mixer initialized at {sr}Hz")
                        except Exception as e:
                            print(f"   [Mouth] ⚠️ pygame mixer failed: {e}")
                            logging.error(f"[Mouth] pygame mixer failed: {e}")

                        voice = PiperVoice.load(model_path, config_path=config_path)
                        
                        self.voices[self.current_lang] = voice
                        self.sample_rates[self.current_lang] = sr
                            
                        print(f"   [Mouth] ✅ Loaded Piper model: {name}")
                        loaded = True
                        break
                    except Exception as e:
                        print(f"   [Mouth] Error loading model {name}: {e}")
                        logging.error(f"[Mouth] Error loading model {name}: {e}")
            
            if not loaded:
                print(f"   [Mouth] ⚠️ Could not find selected model '{target_model}'.")
                logging.error(f"[Mouth] Could not find selected model '{target_model}'.")
                from core.bootstrap.env_setup import safe_run_wizard
                safe_run_wizard()
                continue
                
            break

    def _normalize_text_for_speech(self, text: str) -> str:
        clean_text = text

        clean_text = self.PATTERN_CODE_BLOCK.sub('', clean_text)
        clean_text = self.PATTERN_INLINE_CODE.sub('', clean_text)
        
        for pattern_obj, replacement in self.COMPILED_PRONUNCIATION_MAP:
            clean_text = pattern_obj.sub(replacement, clean_text)

        clean_text = self.PATTERN_WHITELIST.sub(' ', clean_text)
        clean_text = clean_text.replace(',', ' ')
        clean_text = self.PATTERN_SPACES.sub(' ', clean_text).strip()
        
        return clean_text

    def split_into_chunks(self, text: str) -> list:
        clean_text = self._normalize_text_for_speech(text)
        # Protects against failure if the original text is all emojis/symbols
        if not clean_text: return [] 
        
        chunks = re.split(r'[.!?]+(?:\s+|$)|\n+', clean_text)
        sentences = [chunk.strip() for chunk in chunks if chunk.strip()]
        return sentences

    def stop_speaking(self):
        # Capture interruption position BEFORE clearing state
        self._last_interrupted_text = self.current_speaking_text or ""
        self._last_interrupted_history = list(self.spoken_history[-3:]) if self.spoken_history else []
        
        self.is_speaking = False
        self._stop_flag = True
        
        # Flush both queues completely
        while not self.speech_queue.empty():
            try: 
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except queue.Empty: 
                break
            
        while not self.playback_queue.empty():
            try:
                wav_file, _ = self.playback_queue.get_nowait()
                self._safe_delete(wav_file)
                self.playback_queue.task_done()
            except queue.Empty: 
                break
        
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
    
    def get_interruption_context(self) -> dict:
        """Returns the speech position at the time of the last interruption."""
        return {
            "interrupted_text": self._last_interrupted_text,
            "recent_chunks": self._last_interrupted_history,
        }
    
    def is_busy(self) -> bool:
        """Checks if the engine is currently processing or playing audio."""
        is_playing = False
        if pygame.mixer.get_init():
            is_playing = pygame.mixer.music.get_busy()
            
        return (self.is_speaking or 
                self.is_synthesizing or # System is busy if currently rendering audio
                not self.speech_queue.empty() or 
                not self.playback_queue.empty() or 
                is_playing)
    
    def get_last_spoken_words(self, count=5) -> str:
        full_spoken_text = " ".join(self.spoken_history)
        if self.current_speaking_text:
             full_spoken_text += " " + self.current_speaking_text

        words = full_spoken_text.split()
        last_words = words[-count:] if len(words) >= count else words
        return " ".join(last_words)

    def speak(self, text: str):
        if not text or text.strip().upper() == "NONE":
            return
            
        self._stop_flag = False
        self.is_speaking = True # Instantly block listening/interruptions
        
        # Clear the event to signal "busy" state to any waiting threads
        self.speech_done_event.clear()
        self.speech_queue.put((text, self.current_lang))

    # =================================================================
    # Thread 1: Synthesizer Worker
    # =================================================================
    def _synth_worker(self):
        while True:
            task = self.speech_queue.get()
            if task is None: break
            
            self.is_synthesizing = True # Lock the busy state
            text, lang = task
            
            if not getattr(self, '_stop_flag', False):
                self._process_synth(text, lang)
                
            self.is_synthesizing = False # Unlock
            self.speech_queue.task_done()

    def _process_synth(self, text: str, lang: str):
        # Use centralized assistant name
        print(f"\n{self.assistant_name.capitalize()}: {text}")
        
        self.is_speaking = True
        chunks = self.split_into_chunks(text)
        
        if not chunks: return

        if lang not in self.voices:
            print(f"   [Mouth] ❌ Error: No Piper voice model loaded. Please check {self.tts_dir}.")
            logging.error(f"[Mouth] Error: No Piper voice model loaded. Please check {self.tts_dir}.")
            return

        voice = self.voices[lang]
        sr_rate = self.sample_rates[lang]

        for chunk in chunks:
            if getattr(self, '_stop_flag', False): break
            
            temp_file_name = f"temp_speech_{uuid.uuid4().hex[:8]}.wav"
            temp_wav = str(self.cache_dir / temp_file_name)
            
            try:
                audio_result = voice.synthesize(chunk)
                audio_bytes_list = []
                
                for c in audio_result:
                    if hasattr(c, 'audio_int16_bytes'): audio_bytes_list.append(c.audio_int16_bytes)
                    elif hasattr(c, 'audio'): audio_bytes_list.append(c.audio)
                    elif isinstance(c, bytes): audio_bytes_list.append(c)
                
                audio_bytes = b''.join(audio_bytes_list)
                if not audio_bytes: continue
                
                with wave.open(temp_wav, 'wb') as wav_file:
                    wav_file.setnchannels(1)       
                    wav_file.setsampwidth(2)       
                    wav_file.setframerate(sr_rate)      
                    wav_file.writeframes(audio_bytes)
                    
                # Push the ready file to the playback queue to be spoken immediately
                self.playback_queue.put((temp_wav, chunk))
                
            except Exception as e:
                print(f"   [Mouth] ❌ Piper synthesis failed: {e}")
                logging.error(f"[Mouth] Piper synthesis failed: {e}")
                self._safe_delete(temp_wav)

    # =================================================================
    # Thread 2: Playback Worker
    # =================================================================
    def _play_worker(self):
        while True:
            try:
                # Genius tweak: Use timeout to create a natural silence window (1 sec)
                # Prevents deadlocks and allows natural breathing room after speech
                task = self.playback_queue.get(timeout=1)
            except queue.Empty:
                # If queue is empty and no new audio arrives within 1 sec, and no synthesis is ongoing:
                if self.speech_queue.empty() and not self.is_synthesizing:
                    self.is_speaking = False
                    self.speech_done_event.set()
                continue
                
            if task is None: break
            temp_wav, chunk = task
            
            if getattr(self, '_stop_flag', False):
                self._safe_delete(temp_wav)
                self.playback_queue.task_done()
                continue
                
            self.current_speaking_text = chunk
            
            try:
                pygame.mixer.music.load(temp_wav)
                pygame.mixer.music.play()
                
                while pygame.mixer.music.get_busy():
                    if getattr(self, '_stop_flag', False):
                        pygame.mixer.music.stop()
                        break
                    time.sleep(0.01) 
                
                try: 
                    pygame.mixer.music.unload()
                except AttributeError: 
                    pass

            except Exception as e:
                print(f"   [Mouth] ❌ Playback error: {e}")
                logging.error(f"[Mouth] Playback error: {e}")
                
            self._safe_delete(temp_wav)
            self.current_speaking_text = ""
            self.spoken_history.append(chunk)
            
            # Cap spoken_history to prevent unbounded RAM growth over 24/7 uptime
            if len(self.spoken_history) > 20:
                self.spoken_history = self.spoken_history[-20:]
            
            self.playback_queue.task_done()