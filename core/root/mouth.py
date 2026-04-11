# core/root/mouth.py
import os
import glob
import json
import re
import platform
import threading
import wave
import time
import pyttsx3
import pygame 
from pathlib import Path
import asyncio
import queue
import uuid

# =================================================================
# Edge-TTS Integration (High-Quality Arabic Fallback)
# =================================================================
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

# =================================================================
# Dynamic System Paths
# =================================================================
import sys

# 1. Add Project Root to the Python path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 2. Import paths and settings directly from config
try:
    from core.config import config, TTS_DIR
except ImportError:
    print("   [Mouth] ⚠️ Warning: Could not import config properly.")

try:
    from piper import PiperVoice
except ImportError:
    PiperVoice = None

class Mouth:
    def __init__(self):
        self.voices = {} 
        self.sample_rates = {} 
        
        self.is_speaking = False
        self.spoken_history = []
        self.current_chunk = ""
        
        # 🚀 Queue system and background worker to prevent audio overlap
        self.speech_queue = queue.Queue()
        self._stop_flag = False
        self.worker_thread = threading.Thread(target=self._speech_worker, daemon=True)
        self.worker_thread.start()
        
        print("🔊 Initializing Mouth Engine with Queue System...")
        
        try:
            pygame.mixer.quit()
            pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=512)
            print("   [Mouth] ✅ pygame mixer initialized")
        except Exception as e:
            print(f"   [Mouth] ⚠️ pygame mixer failed: {e}")
            
        self._cleanup_temp_files() # Clean up previous remnants immediately upon starting the mouth
        self._load_piper_models()
        self._init_fallback_engine()

    def _cleanup_temp_files(self):
        """🧹 Clean up any lingering audio files from previous sessions or interruptions"""
        import glob
        # Search for all files starting with temp_speech or temp_edge
        patterns = ["temp_speech_*.wav", "temp_edge_*.mp3", "temp_speech.wav", "temp_edge.mp3"]
        for pattern in patterns:
            for file_path in glob.glob(os.path.join(os.path.dirname(__file__), pattern)):
                try:
                    os.remove(file_path)
                except OSError:
                    # If the file is currently locked (being played right now), leave it and delete it next time
                    pass

    def _init_fallback_engine(self):
        try:
            self.fallback_engine = pyttsx3.init()
            self.fallback_engine.setProperty('rate', 160) 
            print("   [Mouth] System Fallback Engine (pyttsx3) loaded.")
            if EDGE_TTS_AVAILABLE:
                print("   [Mouth] Arabic High-Quality Fallback (Edge-TTS) is AVAILABLE.")
        except Exception as e:
            print(f"   [Mouth] Warning: pyttsx3 failed to load. {e}")
            self.fallback_engine = None

    def _load_piper_models(self):
        if not PiperVoice:
            print("   [Mouth] ⚠️ Piper not installed. Will rely on fallback engines.")
            return

        search_pattern = str(TTS_DIR / "**" / "*.onnx")
        models = glob.glob(search_pattern, recursive=True)

        if not models:
            print(f"   [Mouth] ⚠️ No Piper .onnx models found in {TTS_DIR}. Using fallback engines.")
            return

        for model_path in models:
            filename = os.path.basename(model_path).lower()
            config_path = f"{model_path}.json"
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        conf = json.load(f)
                        
                    sr = conf.get('audio', {}).get('sample_rate', 22050)
                    lang_code = conf.get('language', {}).get('code', 'en').lower()
                    
                    lang_key = 'ar' if 'ar' in lang_code else 'en'
                    
                    voice = PiperVoice.load(model_path, config_path=config_path)
                    
                    self.voices[lang_key] = voice
                    self.sample_rates[lang_key] = sr
                        
                    print(f"   [Mouth] Loaded '{lang_key}' Piper model: {filename}")
                except Exception as e:
                    print(f"   [Mouth] Error loading model {filename}: {e}")

    def split_into_chunks(self, text: str) -> list:
        clean_text = re.sub(r'```.*?```', '', text, flags=re.DOTALL) 
        clean_text = re.sub(r'[{}[\]*#@_\\|<>":]+', '', clean_text)
        
        # 🚀 Remove commas (, ،) to reduce pauses in pronunciation
        chunks = re.split(r'([.!?؟\n]+)', clean_text)
        sentences = []
        for i in range(0, len(chunks) - 1, 2):
            sentence = (chunks[i] + chunks[i+1]).strip()
            if sentence:
                sentences.append(sentence)
        if len(chunks) % 2 != 0 and chunks[-1].strip():
            sentences.append(chunks[-1].strip())
        return sentences if sentences else [clean_text]

    def stop_speaking(self):
        """Stop speaking immediately and clear the queue"""
        self.is_speaking = False
        self._stop_flag = True
        
        # Clear the entire Queue
        while not self.speech_queue.empty():
            try:
                self.speech_queue.get_nowait()
                self.speech_queue.task_done()
            except queue.Empty:
                break
        
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            
        if self.fallback_engine:
            try:
                self.fallback_engine.stop()
            except Exception:
                pass

    def get_last_spoken_words(self, count=5) -> str:
        full_spoken_text = " ".join(self.spoken_history)
        if self.current_chunk:
             full_spoken_text += " " + self.current_chunk

        words = full_spoken_text.split()
        last_words = words[-count:] if len(words) >= count else words
        return " ".join(last_words)

    def speak(self, text: str, lang: str = 'en'):
        """Puts the text in the queue instead of playing it immediately to avoid Thread overlap"""
        self._stop_flag = False
        self.speech_queue.put((text, lang))

    def _speech_worker(self):
        """Background worker that pulls texts from the queue and speaks them sequentially"""
        while True:
            task = self.speech_queue.get()
            if task is None:
                break
            text, lang = task
            
            # Ensure no interruption was requested while waiting
            if not getattr(self, '_stop_flag', False):
                self._process_speak(text, lang)
                
            self.speech_queue.task_done()

    def _process_speak(self, text: str, lang: str):
        """The actual speaking function (operates only from within the queue)"""
        
        # 🧹 Clean up the previous sentence before speaking the new one to ensure files don't accumulate
        self._cleanup_temp_files()
        
        if platform.system() == 'Windows' and threading.current_thread() is not threading.main_thread():
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except ImportError:
                pass

        print(f"\nJarvis [{lang.upper()}]: {text}")
        
        self.is_speaking = True
        self.spoken_history = []
        self.current_chunk = ""
        
        chunks = self.split_into_chunks(text)
        use_piper = PiperVoice and lang in self.voices

        if not use_piper:
            if lang == 'ar':
                fallback_name = "Edge-TTS" if EDGE_TTS_AVAILABLE else "pyttsx3"
                print(f"   [Mouth] ⚠️ No Arabic Piper model found. Using {fallback_name} fallback.")
            elif lang == 'en':
                print(f"   [Mouth] ⚠️ No English Piper model found. Using pyttsx3 fallback.")

        for chunk in chunks:
            if getattr(self, '_stop_flag', False):
                print("   [Mouth] 🛑 Interrupted!")
                break
                
            self.current_chunk = chunk
            
            if use_piper:
                self._stream_piper(chunk, lang)
            else:
                if lang == 'ar' and EDGE_TTS_AVAILABLE:
                    self._stream_edge_tts(chunk)
                else:
                    self._stream_fallback(chunk, lang)
                
            if self.is_speaking:
                self.spoken_history.append(chunk)

        self.current_chunk = ""
        self.is_speaking = False

    def _stream_piper(self, text: str, lang: str):
        voice = self.voices[lang]
        sr = self.sample_rates[lang]
        
        # 🚀 Create a unique file for each process to avoid Permission Denied errors
        temp_file_name = f"temp_speech_{uuid.uuid4().hex[:8]}.wav"
        temp_wav = os.path.join(os.path.dirname(__file__), temp_file_name)
        
        try:
            audio_result = voice.synthesize(text)
            audio_bytes_list = []
            
            for chunk in audio_result:
                if hasattr(chunk, 'audio_int16_bytes'):
                    audio_bytes_list.append(chunk.audio_int16_bytes)
                elif hasattr(chunk, 'audio'):
                    audio_bytes_list.append(chunk.audio)
                elif isinstance(chunk, bytes):
                    audio_bytes_list.append(chunk)
                else:
                    raise TypeError(f"Unknown chunk type: {type(chunk)}")
            
            audio_bytes = b''.join(audio_bytes_list)
            
            if not audio_bytes:
                raise ValueError("No audio data extracted")
            
            with wave.open(temp_wav, 'wb') as wav_file:
                wav_file.setnchannels(1)       
                wav_file.setsampwidth(2)       
                wav_file.setframerate(sr)      
                wav_file.writeframes(audio_bytes)
                
        except Exception as e:
            print(f"   [Mouth] ❌ Piper failed: {e}")
            self._stream_fallback(text, lang)
            return
        
        if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) <= 44:
            print(f"   [Mouth] ❌ Invalid WAV file generated")
            self._stream_fallback(text, lang)
            return
        
        try:
            pygame.mixer.music.load(temp_wav)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                if getattr(self, '_stop_flag', False):
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.05)
            
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass
                
            # 🧹 Delete the file to free up space
            try:
                if os.path.exists(temp_wav):
                    os.remove(temp_wav)
            except OSError:
                pass
                
        except Exception as e:
            print(f"   [Mouth] ❌ Playback error: {e}")
            self._stream_fallback(text, lang)

    def _stream_edge_tts(self, text: str, voice: str = "ar-SA-HamedNeural"):
        temp_file_name = f"temp_edge_{uuid.uuid4().hex[:8]}.mp3"
        temp_mp3 = os.path.join(os.path.dirname(__file__), temp_file_name)
        
        try:
            communicate = edge_tts.Communicate(text, voice)
            asyncio.run(communicate.save(temp_mp3))
            
            pygame.mixer.music.load(temp_mp3)
            pygame.mixer.music.play()
            
            while pygame.mixer.music.get_busy():
                if getattr(self, '_stop_flag', False):
                    pygame.mixer.music.stop()
                    break
                time.sleep(0.05)
                
            try:
                pygame.mixer.music.unload()
            except AttributeError:
                pass
                
            # 🧹 Delete the file
            try:
                if os.path.exists(temp_mp3):
                    os.remove(temp_mp3)
            except OSError:
                pass
                
        except Exception as e:
            print(f"   [Mouth] ❌ Edge-TTS Error: {e}")
            self._stream_fallback(text, 'ar')

    def _stream_fallback(self, text: str, lang: str):
        if not self.fallback_engine or not text.strip():
            return
            
        try:
            voices = self.fallback_engine.getProperty('voices')
            voice_found = False
            
            for v in voices:
                v_name = v.name.lower()
                v_id = v.id.lower()
                
                if lang == 'ar':
                    if 'arabic' in v_name or 'ar' in v_id or 'hoda' in v_name:
                        self.fallback_engine.setProperty('voice', v.id)
                        voice_found = True
                        break
                elif lang == 'en':
                    if 'english' in v_name or 'en' in v_id or 'david' in v_name or 'zira' in v_name:
                        self.fallback_engine.setProperty('voice', v.id)
                        voice_found = True
                        break
            
            if lang == 'ar' and not voice_found:
                print("   [Mouth] ⚠️ OS Warning: No Arabic Voice Pack found in Windows!")
                    
            self.fallback_engine.say(text)
            self.fallback_engine.runAndWait()
            
        except RuntimeError as e:
            if "run loop already started" in str(e):
                try:
                    self.fallback_engine.say(text)
                except:
                    pass
            else:
                print(f"   [Mouth] Fallback Error (Runtime): {e}")
        except Exception as e:
            print(f"   [Mouth] Unexpected Fallback Error: {e}")

# =================================================================
# System Testing
# =================================================================
if __name__ == "__main__":
    mouth = Mouth()
    
    # English Test (Piper Model)
    print("\n=== English Test (Piper Model) ===")
    test_text_en = "Hello sir! Systems are online. This is the ultimate test."
    mouth.speak(test_text_en, lang='en')
    
    # Arabic Test (Edge-TTS or Fallback)
    print("\n=== Arabic Test (Edge-TTS or Fallback) ===")
    test_text_ar = "مرحباً يا سيدي! جارفيس جاهز للعمل."
    mouth.speak(test_text_ar, lang='ar')
    
    # Interruption Test
    print("\n=== Interruption Test ===")
    test_text_interrupt = "I am going to speak a very long sentence now to test if you can interrupt me correctly while I am talking."
    speak_thread = threading.Thread(target=mouth.speak, args=(test_text_interrupt, 'en'))
    speak_thread.start()
    
    time.sleep(1.5) 
    mouth.stop_speaking()
    speak_thread.join()
    
    last_words = mouth.get_last_spoken_words(count=5)
    print(f"\n🧠 Last spoken words: '{last_words}'")