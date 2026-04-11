# core/root/ears.py
import os
import sys
import re
import threading
import time
import numpy as np 
import speech_recognition as sr
from faster_whisper import WhisperModel
from pathlib import Path

# =================================================================
# Dynamic System Paths
# =================================================================
# 1. Add Project Root to the Python path so it can read the core directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 2. Import dynamic paths and settings from the unified config
try:
    from core.config import config, STT_DIR
except ImportError as e:
    print(f"   [Ears] ❌ Fatal Error: Could not import config. {e}")
    sys.exit(1)

class Ears:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.is_cpu_mode = False
        self.mic = None
        self.mic_lock = threading.Lock() 
        
        self.wakeup_time = 0.0
        self.language_filter = None # 🚀 Variable for forced language control (None means Auto)
        
        self._initialize_microphone()
            
        self.recognizer.pause_threshold = config.get("mic_pause_threshold")
        energy_thresh = config.get("mic_energy_threshold")
        
        if energy_thresh:
            self.recognizer.energy_threshold = energy_thresh
            print(f"   [Ears] 🎚️ Using static energy threshold: {energy_thresh}")
        else:
            print("   [Ears] 🔊 Calibrating ambient noise...")
            with self.mic as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=2.0)
            print(f"   [Ears] ✅ Calibration complete. Threshold: {self.recognizer.energy_threshold}")

        self.main_stt = self.find_local_model()
        print(f"👂 Loading Offline Hearing Model from: {self.main_stt}...")
        
        configurations = [
            {"device": "cuda", "compute_type": "float16", "desc": "GPU (High Performance)"},
            {"device": "cuda", "compute_type": "int8_float16", "desc": "GPU (Balanced Memory)"},
            {"device": "cuda", "compute_type": "int8", "desc": "GPU (Low VRAM)"},
            {"device": "cuda", "compute_type": "float32", "desc": "GPU (Legacy/Maxwell Fallback)"},
            {"device": "cpu", "compute_type": "int8", "desc": "CPU (Optimized)"},
            {"device": "cpu", "compute_type": "float32", "desc": "CPU (Ultimate Fallback)"}
        ]
        
        model_loaded = False
        for cfg in configurations:
            try:
                self.model = WhisperModel(
                    self.main_stt, 
                    device=cfg['device'], 
                    compute_type=cfg['compute_type'], 
                    local_files_only=True
                )
                dummy_audio = np.zeros(16000, dtype=np.float32)
                self.model.transcribe(dummy_audio, vad_filter=False)
                self.is_cpu_mode = (cfg['device'] == "cpu")
                print(f"   [Ears] ✅ Whisper Model loaded via {cfg['desc']}.")
                model_loaded = True
                break  
            except Exception as e:
                pass
                
        if not model_loaded:
            print("   [Ears] ❌ FATAL ERROR: Could not load Whisper model.")
            sys.exit(1)

        wake_word_val = config.get("wake_word")
        trigger = str(wake_word_val) if wake_word_val is not None else "jarvis"
        self.wake_words = [trigger, trigger.capitalize(), trigger.lower()]
        self.wake_word_pattern = re.compile("|".join(self.wake_words), re.IGNORECASE)
        
        self.is_listening = False
        self.interrupt_callback = None
        self.background_listener = None

    def deafen_for(self, seconds: float):
        self.wakeup_time = time.time() + seconds
        print(f"   [Ears] 🔇 System deafened for {seconds}s.")

    def set_language_filter(self, mode: str):
        """🚀 New function: Called from app.py to force the Ears to a specific language constraint"""
        if mode == 'english':
            self.language_filter = 'en'
        elif mode == 'arabic':
            self.language_filter = 'ar'
        else:
            self.language_filter = None
        print(f"   [Ears] 🌐 Language constraint set to: {mode.upper()}")

    def _initialize_microphone(self):
        try:
            self.mic = sr.Microphone()
            print("   [Ears] ✅ Microphone detected.")
        except OSError as e:
            print(f"   [Ears] ❌ Microphone Error: {e}")
            sys.exit(1)

    def _reconnect_mic(self):
        try:
            time.sleep(1) 
            self.mic = sr.Microphone()
            return True
        except Exception:
            return False

    def find_local_model(self): 
        main_stt = str(config.get("main_stt"))
        if not os.path.exists(os.path.join(main_stt, "model.bin")):
            sys.exit(1)
        return main_stt

    def _audio_to_numpy(self, audio_data: sr.AudioData) -> np.ndarray:
        wav_bytes = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
        return np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    def transcribe(self, audio_input, initial_prompt=None) -> str:
        try:
            dynamic_beam_size = 1 if self.is_cpu_mode else 5
            
            # 🚀 Second Modification: Removed "Jarvis" from the Prompt to prevent hallucination and self-interruption!
            hybrid_prompt = initial_prompt if initial_prompt else "Listen carefully."
            hybrid_prompt += " English text. نص عربي واضح."

            segments, info = self.model.transcribe(
                audio_input, 
                language=self.language_filter, # The mandatory language will be applied correctly here
                beam_size=dynamic_beam_size,
                vad_filter=True, 
                vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=400),
                condition_on_previous_text=False, 
                initial_prompt=hybrid_prompt,
                temperature=0.0 # 🚀 Fix for the freezing issue
            )
            
            # 🚀 Third Modification: Aggressive filtering for noise/silence hallucinations
            valid_text = ""
            for segment in segments:
                # If the probability of noise/silence is over 70%, ignore it immediately
                if hasattr(segment, 'no_speech_prob') and segment.no_speech_prob > 0.7:
                    continue
                valid_text += segment.text

            valid_text = valid_text.strip()
            
            if not self.language_filter:
                # Ignore foreign languages in Auto mode
                if info.language not in ['en', 'ar']:
                    print(f"   [Ears] 🗑️ Ignored background noise (Detected: {info.language})")
                    return ""
                    
            # If the text is empty after filtering or less than 2 characters (transient noise)
            if not valid_text or len(valid_text) < 2:
                return ""
                
            return valid_text
            
        except Exception as e:
            print(f"   [Ears] Transcription Error: {e}")
            return ""

    def listen(self, timeout=5, phrase_time_limit=10) -> str:
        if time.time() < self.wakeup_time:
            time.sleep(self.wakeup_time - time.time())

        if not self.mic: self._reconnect_mic()

        with self.mic_lock:
            try:
                with self.mic as source:
                    audio_data = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError: return ""
            except OSError: self._reconnect_mic(); return ""
            except Exception: return ""
            
        audio_np = self._audio_to_numpy(audio_data)
        text = self.transcribe(audio_np, initial_prompt="Jarvis, listen.")
        if text: print(f"   [Heard]: {text}")
        return text

    def wait_for_wake_word(self) -> str:
        print("\n🔵 JARVIS is in standby mode. Say 'Jarvis' to wake him up...")
        if not self.mic: self._reconnect_mic()

        while True:
            if time.time() < self.wakeup_time:
                time.sleep(0.5); continue

            with self.mic_lock:
                try:
                    with self.mic as source:
                        audio_data = self.recognizer.listen(source, timeout=None, phrase_time_limit=5)
                except OSError: self._reconnect_mic(); continue
                except Exception: time.sleep(0.5); continue
                
            audio_np = self._audio_to_numpy(audio_data)
            text = self.transcribe(audio_np, initial_prompt="Jarvis.")
            
            if not text: continue
            match = self.wake_word_pattern.search(text)
            if match:
                command_part = text[match.end():].strip(" ,.!?\n-")
                return command_part if command_part else ""

    def start_background_listening(self, on_speech_callback):
        if self.is_listening: return
        self.is_listening = True
        self.interrupt_callback = on_speech_callback
        self.background_listener = threading.Thread(target=self._background_listen_loop, daemon=True)
        self.background_listener.start()

    def stop_background_listening(self):
        self.is_listening = False
        if self.background_listener:
            self.background_listener.join(timeout=1)

    def _background_listen_loop(self):
        if not self.mic and not self._reconnect_mic(): return

        while self.is_listening:
            if time.time() < self.wakeup_time:
                time.sleep(0.5); continue

            with self.mic_lock:
                try:
                    with self.mic as source:
                        audio_data = self.recognizer.listen(source, timeout=1, phrase_time_limit=3)
                except (sr.WaitTimeoutError, Exception): 
                    continue
                    
            if self.is_listening and self.interrupt_callback:
                audio_np = self._audio_to_numpy(audio_data)
                self.interrupt_callback(audio_np)

    def listen_with_interruption(self, mouth_instance, timeout=120):
        interrupted = False
        final_command = ""
        
        def on_interrupt(audio_np):
            nonlocal interrupted, final_command
            text = self.transcribe(audio_np, initial_prompt="Jarvis.")
            if not text: return
            
            match = self.wake_word_pattern.search(text)
            if match:
                if getattr(mouth_instance, 'is_speaking', False):
                    print(f"\n   [Ears] 🛑 Wake word detected! Stopping speech...")
                    mouth_instance.stop_speaking()
                    interrupted = True
                
                command_part = text[match.end():].strip(" ,.!?\n-")
                final_command = command_part if command_part else "stop"
        
        self.start_background_listening(on_interrupt)
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            if interrupted or not getattr(mouth_instance, 'is_speaking', False): break
            time.sleep(0.1)
        
        self.stop_background_listening()
        return final_command if interrupted else ""
    
# =================================================================
# System Testing
# =================================================================
if __name__ == "__main__":
    ears = Ears()
    
    print("\n=== Test 0: Deafen Mode ===")
    ears.deafen_for(3) # Deafen audio for 3 seconds
    print("Testing deafen mode (Wait for 3 seconds...)")
    
    print("\n=== Test 1: Wake Word Detection ===")
    ears.wait_for_wake_word()
    
    print("\n=== Test 2: Command Listening ===")
    print("  (Listening for your command...)")
    command = ears.listen(phrase_time_limit=15)
    print(f"✅ Final Command Received: {command}")
    
    print("\n=== Test 3: Interruption System ===")
    print("Testing background listening (say anything to interrupt)...")
    
    class MockMouth:
        def __init__(self):
            self.is_speaking = True
        
        def stop_speaking(self):
            self.is_speaking = False
            print("   [MockMouth] Speech stopped!")
    
    mock_mouth = MockMouth()
    
    interrupted_command = ears.listen_with_interruption(mock_mouth, timeout=10)
    
    if interrupted_command:
        print(f"✅ Interruption successful! Command: {interrupted_command}")
    else:
        print("⏱️ No interruption detected within timeout")