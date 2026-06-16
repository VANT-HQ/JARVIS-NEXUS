# core/audio/stt_engine.py

"""
JARVIS Speech-to-Text (STT) Engine
==================================
Handles real-time audio capture, wake-word detection, and Whisper-based
offline transcription with advanced noise-filtering and anti-hallucination logic.
"""

import os
import sys
import re
import logging
import threading
import time
import difflib
import queue
import numpy as np 
import speech_recognition as sr
from faster_whisper import WhisperModel
from pathlib import Path

# =====================================================================
# Dynamic System Paths
# =====================================================================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from core.config import config, STT_DIR
except ImportError as e:
    print(f"   [Ears] ❌ Fatal Error: Could not import config. {e}")
    logging.error(f"[Ears] Fatal Error: Could not import config. {e}")
    sys.exit(1)

class Ears:
    def __init__(self):
        self.recognizer = sr.Recognizer()
        self.is_cpu_mode = False
        self.mic = sr.Microphone() 
        self.overlap_buffer = np.array([], dtype=np.float32)
        
        # Production Audio Pipeline variables
        self.audio_queue = queue.Queue()
        self.run_hardware_thread = True
        self.route_to_queue = False
        
        self.followup_window = float(config.get("followup_window", 10.0))
        self.dynamic_phrase_limit = self.followup_window
        
        self.wakeup_time = 0.0
        self.current_lang = 'en'
        
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
        
        is_high_perf = config.get("sub_high_performance", False)
        
        if is_high_perf:
            print("   [Ears] 🚀 Sub High Performance Mode: Prioritizing GPU for STT...")
            configurations = [
                {"device": "cuda", "compute_type": "float16", "desc": "GPU (High Performance)"},
                {"device": "cuda", "compute_type": "int8_float16", "desc": "GPU (Balanced Memory)"},
                {"device": "cuda", "compute_type": "int8", "desc": "GPU (Low VRAM)"},
                {"device": "cpu", "compute_type": "int8", "desc": "CPU (Optimized)"},
                {"device": "cpu", "compute_type": "float32", "desc": "CPU (Ultimate Fallback)"}
            ]
        else:
            print("   [Ears] 🛡️ Standard Mode: Prioritizing CPU for STT to save VRAM...")
            configurations = [
                {"device": "cpu", "compute_type": "int8", "desc": "CPU (Optimized)"},
                {"device": "cpu", "compute_type": "float32", "desc": "CPU (Ultimate Fallback)"},
                {"device": "cuda", "compute_type": "float16", "desc": "GPU (High Performance)"},
                {"device": "cuda", "compute_type": "int8_float16", "desc": "GPU (Balanced Memory)"},
                {"device": "cuda", "compute_type": "int8", "desc": "GPU (Low VRAM)"}
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
            except Exception:
                pass
                
        if not model_loaded:
            print("   [Ears] ❌ FATAL ERROR: Could not load Whisper model.")
            logging.error("[Ears] FATAL ERROR: Could not load Whisper model.")
            sys.exit(1)

        self.assistant_name = str(config.get("assistant_name", "Assistant"))
        wake_word_val = config.get("wake_word")
        
        if wake_word_val:
            self.trigger_words = [w.strip().lower() for w in str(wake_word_val).split(',') if w.strip()]
        else:
            self.trigger_words = [self.assistant_name.lower()]
            
        self.trigger_word = self.trigger_words[0] 
        
        self.wake_words = []
        for w in self.trigger_words:
            self.wake_words.extend([w, w.capitalize(), w.lower()])
            
        self.wake_word_pattern = re.compile(r'\b(?:' + "|".join(set(self.wake_words)) + r')\b', re.IGNORECASE)
        
        self.is_listening = False
        self.is_actively_listening = False
        self.interrupt_callback = None
        self.background_listener = None

        self.pipeline_thread = threading.Thread(target=self._hardware_audio_pipeline, daemon=True)
        self.pipeline_thread.start()

    def deafen_for(self, seconds: float):
        self.wakeup_time = time.time() + seconds
        print(f"   [Ears] 🔇 System deafened for {seconds}s.")

    def set_language(self, lang_code: str):
        """Currently supports English only due to the underlying model limitations."""
        supported_langs = ['en'] 
        if lang_code in supported_langs:
            self.current_lang = lang_code
            print(f"   [Ears] 🌐 Language set to: {self.current_lang.upper()}")
        else:
            print(f"   [Ears] ⚠️ Model only supports English. Ignored setting language to: {lang_code}")

    def _hardware_audio_pipeline(self):
        """Continuous Producer Thread: Keeps OS stream open and routes audio chunks safely."""
        print("   [Ears] 🎤 Hardware Audio Pipeline initialized (Always-ON).")
        while self.run_hardware_thread:
            try:
                with self.mic as source:
                    print("   [Ears] ✅ Pipeline Ready. Routing audio chunks natively...")
                    while self.run_hardware_thread:
                        
                        # 1. Gate Closed (Sleep/Deafened state)
                        if time.time() < self.wakeup_time or (not self.route_to_queue and not self.is_listening):
                            try:
                                self.recognizer.record(source, duration=0.2) # Fast Drain
                            except Exception:
                                pass
                            continue

                        # 2. Snapshot Intent
                        intended_for_queue = self.route_to_queue
                        intended_for_bg = self.is_listening

                        try:
                            # record(duration=1.5) was causing continuous Whisper
                            # transcription during LLM generation, stealing CPU and adding
                            # ~3s to TTFT. Silence-gated listen() only fires on real speech,
                            # keeping CPU free for LLM token generation.
                            audio_data = self.recognizer.listen(
                                source, timeout=0.5, phrase_time_limit=self.dynamic_phrase_limit
                            )
                            
                            # 3. Gatekeeper Check
                            if intended_for_queue and self.route_to_queue:
                                self.audio_queue.put(audio_data)
                                
                            if intended_for_bg and self.is_listening and self.interrupt_callback:
                                audio_np = self._audio_to_numpy(audio_data)
                                threading.Thread(
                                    target=self.interrupt_callback, 
                                    args=(audio_np,), 
                                    daemon=True
                                ).start()

                        except sr.WaitTimeoutError:
                            continue 
                        except Exception as e:
                            print(f"   [Ears] ⚠️ Pipeline loop inner error: {e}")
                            logging.error(f"[Ears] Pipeline loop inner error: {e}")
                            break 
            except Exception as e:
                print(f"   [Ears] ❌ Fatal Pipeline Error: {e}. OS blocked Mic? Reconnecting in 2s...")
                logging.error(f"[Ears] Fatal Pipeline Error: {e}. OS blocked Mic? Reconnecting in 2s...")
                time.sleep(2)

    def flush_mic(self):
        """Logical Flush: Empties software queue instantly without touching hardware."""
        flushed_count = 0
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
                flushed_count += 1
            except queue.Empty:
                break
        if flushed_count > 0:
            print(f"   [Ears] 🧹 Software buffer flushed ({flushed_count} stale chunks purged).")

    def find_local_model(self): 
        while True:
            active_stt = str(config.get("main_stt", "faster-whisper-small.en"))
            main_stt = str(STT_DIR / active_stt)
            if not os.path.exists(os.path.join(main_stt, "model.bin")):
                print(f"\n   [Ears] ❌ FATAL ERROR: STT Model missing!")
                print(f"   [Ears] Expected to find 'model.bin' inside: {main_stt}")
                logging.error(f"[Ears] FATAL ERROR: STT Model missing! Expected to find 'model.bin' inside: {main_stt}")
                from core.bootstrap.env_setup import safe_run_wizard
                safe_run_wizard()
                continue
            return main_stt

    def _audio_to_numpy(self, audio_data: sr.AudioData) -> np.ndarray:
        wav_bytes = audio_data.get_raw_data(convert_rate=16000, convert_width=2)
        return np.frombuffer(wav_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    def transcribe(self, audio_input, initial_prompt=None) -> str:
        try:
            dynamic_beam_size = 1 if self.is_cpu_mode else 5
            hybrid_prompt = initial_prompt if initial_prompt else "Listen carefully."

            segments, info = self.model.transcribe(
                audio_input, 
                language=self.current_lang,
                beam_size=dynamic_beam_size,
                vad_filter=True, 
                vad_parameters=dict(min_silence_duration_ms=500, speech_pad_ms=200, min_speech_duration_ms=150),
                condition_on_previous_text=False, 
                initial_prompt=hybrid_prompt,
                temperature=0.0,
                no_speech_threshold=0.75 
            )
            
            valid_text = ""
            for segment in segments:
                if hasattr(segment, 'no_speech_prob') and segment.no_speech_prob > 0.75:
                    continue
                valid_text += segment.text

            valid_text = re.sub(r'[^a-zA-Z0-9\s.,!?\'"]', '', valid_text).strip()
            
            if info.language != self.current_lang:
                return ""
                    
            if not valid_text or len(valid_text) < 3:
                return ""
                
            # ALGORITHMIC HALLUCINATION FILTER
            words = valid_text.lower().replace('.', '').replace(',', '').split()
            word_count = len(words)
            
            if word_count >= 6:
                unique_words = len(set(words))
                uniqueness_ratio = unique_words / word_count
                
                is_repeating_loop = bool(re.search(r'\b(.+?)(?:\s+\1\b){4,}', valid_text, flags=re.IGNORECASE))
                
                if uniqueness_ratio < 0.35 or is_repeating_loop:
                    print(f"   [Ears] 🛡️ Dynamic Filter Blocked Hallucination (Ratio: {uniqueness_ratio:.2f}): {valid_text[:40]}...")
                    return ""

            return valid_text
            
        except Exception as e:
            print(f"   [Ears] Transcription Error: {e}")
            logging.error(f"[Ears] Transcription Error: {e}")
            return ""

    def listen(self) -> str:
        if time.time() < self.wakeup_time:
            time.sleep(max(0, self.wakeup_time - time.time()))

        self.dynamic_phrase_limit = self.followup_window

        time.sleep(0.2) 
        self.flush_mic() 
        self.is_actively_listening = True 
        self.route_to_queue = True # OPEN GATE
        
        try:
            audio_data = self.audio_queue.get(timeout=self.followup_window)
            audio_np = self._audio_to_numpy(audio_data)
            text = self.transcribe(audio_np, initial_prompt=f"{self.assistant_name}, listen.")
            if text: print(f"   [Heard]: {text}")
            return text
        except queue.Empty:
            return "" 
        except Exception as e:
            print(f"   [Ears] ⚠️ Listen Error: {e}")
            logging.error(f"[Ears] Listen Error: {e}")
            return ""
        finally:
            self.route_to_queue = False # CLOSE GATE
            self.is_actively_listening = False

    def wait_for_wake_word(self) -> str:
        print(f"\n🔵 {self.assistant_name.upper()} is in standby mode. Say '{self.trigger_word}' to wake up...")
        
        self.dynamic_phrase_limit = 10.0 
        time.sleep(0.2)
        self.flush_mic() 
        self.route_to_queue = True # OPEN GATE

        try:
            while True:
                if time.time() < self.wakeup_time:
                    time.sleep(0.5); continue

                try:
                    audio_data = self.audio_queue.get(timeout=2.0)
                    audio_np = self._audio_to_numpy(audio_data)
                    text = self.transcribe(audio_np, initial_prompt=f"{self.assistant_name}.")
                    
                    if not text: continue
                    match = self.wake_word_pattern.search(text)
                    if match:
                        command_part = text[match.end():].strip(" ,.!?\n-")
                        return command_part if command_part else ""
                except queue.Empty:
                    continue 
        finally:
            self.route_to_queue = False # CLOSE GATE

    def start_background_listening(self, on_speech_callback):
        if self.is_listening: return
        self.overlap_buffer = np.array([], dtype=np.float32) 
        self.is_listening = True
        self.interrupt_callback = on_speech_callback

    def stop_background_listening(self):
        self.is_listening = False
        self.interrupt_callback = None
        self.overlap_buffer = np.array([], dtype=np.float32)

    def listen_with_interruption(self, mouth_instance, timeout=120) -> str:
        if not mouth_instance.is_busy():
            return ""
        interrupted = False
        final_command = ""
        transcribe_lock = threading.Lock()
        
        def on_interrupt(audio_np):
            nonlocal interrupted, final_command
            if not mouth_instance.is_busy() or interrupted:
                return
            
            if not transcribe_lock.acquire(blocking=False):
                return
                
            try:
                # 1. Merge buffers
                if self.overlap_buffer.size > 0:
                    combined_audio = np.concatenate((self.overlap_buffer, audio_np))
                else:
                    combined_audio = audio_np

                # 2. Transcribe
                text = self.transcribe(combined_audio, initial_prompt="Listen carefully.") 
                
                # 3. Update overlap buffer (last ~300ms)
                overlap_samples = 3200 
                self.overlap_buffer = audio_np[-overlap_samples:] if audio_np.size > overlap_samples else audio_np

                if not text: return
                
                cleaned_text = text.lower().strip(" ,.!?")
                
                recent_history = getattr(mouth_instance, 'spoken_history', [])[-3:]
                current_tts = getattr(mouth_instance, 'current_speaking_text', '')
                if current_tts:
                    recent_history.append(current_tts)

                combined_tts = " ".join(recent_history).lower()
                
                words = cleaned_text.split()
                trigger_hit = False
                matched_word = "" 
                
                for word in words:
                    for ww in self.trigger_words:
                        sim = difflib.SequenceMatcher(None, ww, word).ratio()
                        if (sim >= 0.85 and len(word) >= 4) or ww == word: 
                            trigger_hit = True
                            matched_word = word 
                            break
                    if trigger_hit:
                        break
                        
                # Smart Anti-Echo Filter
                if combined_tts:
                    # If it's an exact or near-exact echo, block it (even if wake word is present in TTS)
                    if cleaned_text in combined_tts or difflib.SequenceMatcher(None, cleaned_text, combined_tts).ratio() > 0.85:
                        return
                    # If it's a partial match, block it ONLY if no wake word was explicitly heard
                    if not trigger_hit and difflib.SequenceMatcher(None, cleaned_text, combined_tts).ratio() > 0.40:
                        return

                # Check if system is requesting input/permission
                is_question = False
                if current_tts and ('?' in current_tts or 'yes" or "no."' in current_tts.lower() or 'permission' in current_tts.lower()):
                    is_question = True

                # Allow interruption via wake word or immediate response to a question
                if trigger_hit or (is_question and len(words) >= 1):
                    self.overlap_buffer = np.array([], dtype=np.float32)
                    
                    if is_question and not trigger_hit:
                        print(f"\n   [Ears] 🛑 Contextual Interruption Detected ('{text}')! Halting speech...")
                    else:
                        print(f"\n   [Ears] 🛑 Wake Word Detected ('{text}')! Halting speech...")
                        
                    if mouth_instance.is_busy():
                        mouth_instance.stop_speaking()
                    interrupted = True
                    
                    exact_match = self.wake_word_pattern.search(text)
                    if exact_match:
                        remainder = text[exact_match.end():].strip(" ,.!?")
                    else:
                        if trigger_hit:
                            idx = text.lower().find(matched_word)
                            if idx != -1:
                                remainder = text[idx + len(matched_word):].strip(" ,.!?")
                            else:
                                remainder = ""
                        else:
                            remainder = text.strip(" ,.!?")
                            
                    if len(remainder) > 2:
                        final_command = remainder
            finally:
                transcribe_lock.release()

        self.start_background_listening(on_interrupt)
        start_time = time.time()
        
        while (time.time() - start_time) < timeout:
            if interrupted or not mouth_instance.is_busy(): 
                break
            time.sleep(0.1)
            
        self.stop_background_listening()
        
        if interrupted:
            self.flush_mic()
            if final_command:
                print(f"   [Ears] ⚡ Captured inline command: {final_command}")
                return final_command
            else:
                print("   [Ears] 🟢 Ready. Listening for your command...")
                command = self.listen()
                return command if command else "stop"
                
        return final_command