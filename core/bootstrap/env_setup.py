# core/bootstrap/env_setup.py
"""
JARVIS NEXUS — First-Run Setup Wizard (Premium Gold Theme)
==========================================================
Stable logic merged with Gold/Amber premium design.
All original functionality preserved; only visual layer updated.
"""

import sys
import os
import json
import threading
import subprocess
import platform
import urllib.request
import shutil
import webview
import logging
from pathlib import Path

try:
    _temp_root = str(Path(__file__).resolve().parent.parent.parent)
    if _temp_root not in sys.path:
        sys.path.insert(0, _temp_root)
    from core.config import (
        config, BASE_DIR,
        LLM_DIR, STT_DIR, TTS_DIR,
        DEFAULT_STT_MODEL, DEFAULT_EMBEDDING_MODEL, DEFAULT_EN_TTS,
        STARTUP_VIDEO_PATH, INTRO_VIDEO_PATH, PROCESSING_SOUND, LISTENING_SOUND, BEEP_SOUND,
        TRAY_ICON_PATH, BIN_DIR,
    )
except ImportError as e:
    print(f"❌  Cannot load core/config.py\n{e}")
    logging.error(f"Cannot load core/config.py: {e}")
    sys.exit(1)


# ╔══════════════════════════════════════════════════════════════╗
# ║                     COMPONENT DEFINITIONS                    ║
# ╚══════════════════════════════════════════════════════════════╝
OS = platform.system()   # "Windows" or "Linux" or "Darwin"

# Ollama install URLs
OLLAMA_URLS = {
    "Windows": "https://ollama.com/download/OllamaSetup.exe",
    "Linux":   "https://ollama.com/download/ollama-linux-amd64",
    "Darwin":  "https://ollama.com/download/Ollama-darwin.zip",
}

# Recommended LLM
RECOMMENDED_LLM_NAME = "Qwen3-4B-Instruct-2507-Q5_K_M.gguf"
RECOMMENDED_LLM_URL  = (
    "https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/main"
    "Qwen3-4B-Instruct-2507-Q5_K_M.gguf"
)

# STT model — faster-whisper-small.en
STT_FOLDER   = Path(DEFAULT_STT_MODEL)   # e.g. models/stt/faster-whisper-small.en
STT_REQUIRED = ["config.json", "model.bin", "tokenizer.json", "vocabulary.txt"]
STT_HF_BASE  = (
    "https://huggingface.co/guillaumekln/faster-whisper-small.en/resolve/main/"
)
STT_FILES = {
    "config.json":    STT_HF_BASE + "config.json",
    "model.bin":      STT_HF_BASE + "model.bin",
    "tokenizer.json": STT_HF_BASE + "tokenizer.json",
    "vocabulary.txt": STT_HF_BASE + "vocabulary.txt",
}

# TTS — jarvis_en_GB_high
TTS_FOLDER   = TTS_DIR / DEFAULT_EN_TTS
TTS_REQUIRED = [f"{DEFAULT_EN_TTS}.onnx", f"{DEFAULT_EN_TTS}.onnx.json"]
TTS_HF_REPO  = "https://huggingface.co/rhasspy/piper-voices/tree/main/en"

JARVIS_VOICE_FILES = {
    "jarvis-high.onnx": "https://huggingface.co/datasets/VANT-HQ/JARVIS-PIPER-Voices/resolve/main/jarvis_en_GB_high/jarvis-high.onnx",
    "jarvis-high.onnx.json": "https://huggingface.co/datasets/VANT-HQ/JARVIS-PIPER-Voices/resolve/main/jarvis_en_GB_high/jarvis-high.onnx.json"
}

# Embeddings — via Ollama (OPTIONAL)

# System Files (Assets)
SYSFILES_REQUIRED = [
    Path(STARTUP_VIDEO_PATH),
    Path(INTRO_VIDEO_PATH),
    Path(PROCESSING_SOUND),
    Path(LISTENING_SOUND),
    Path(BEEP_SOUND),
    Path(TRAY_ICON_PATH)
]
SYSFILES_BASE = "https://raw.githubusercontent.com/VANT-HQ/JARVIS-NEXUS/main/assets/"
SYSFILES_DL = {
    Path(STARTUP_VIDEO_PATH).name: (SYSFILES_BASE + "videos/" + Path(STARTUP_VIDEO_PATH).name, Path(STARTUP_VIDEO_PATH)),
    Path(INTRO_VIDEO_PATH).name: (SYSFILES_BASE + "videos/" + Path(INTRO_VIDEO_PATH).name, Path(INTRO_VIDEO_PATH)),
    Path(PROCESSING_SOUND).name: (SYSFILES_BASE + "sounds/" + Path(PROCESSING_SOUND).name, Path(PROCESSING_SOUND)),
    Path(LISTENING_SOUND).name: (SYSFILES_BASE + "sounds/" + Path(LISTENING_SOUND).name, Path(LISTENING_SOUND)),
    Path(BEEP_SOUND).name: (SYSFILES_BASE + "sounds/" + Path(BEEP_SOUND).name, Path(BEEP_SOUND)),
    Path(TRAY_ICON_PATH).name: (SYSFILES_BASE + "icons/" + Path(TRAY_ICON_PATH).name, Path(TRAY_ICON_PATH)),
}


# ╔══════════════════════════════════════════════════════════════╗
# ║                     CHECKER FUNCTIONS                        ║
# ╚══════════════════════════════════════════════════════════════╝
def check_ollama() -> dict:
    """Check if ollama is installed and reachable."""
    try:
        flags = subprocess.CREATE_NO_WINDOW if OS == "Windows" else 0
        result = subprocess.run(
            ["ollama", "--version"],
            capture_output=True, text=True, timeout=5,
            stdin=subprocess.DEVNULL,
            creationflags=flags
        )
        if result.returncode == 0:
            ver = result.stdout.strip() or result.stderr.strip()
            return {"ok": True, "detail": ver}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {"ok": False, "detail": "Not installed"}


def check_llm() -> dict:
    """Check if at least one .gguf model exists in LLM_DIR."""
    models = list(LLM_DIR.glob("*.gguf"))
    main_llm = config.get("main_llm", "auto_max")
    quick_llm = config.get("quick_llm", "auto_min")
    if models:
        names = [m.name for m in models]
        main_name = Path(main_llm).name if main_llm.endswith(".gguf") else main_llm
        quick_name = Path(quick_llm).name if quick_llm.endswith(".gguf") else quick_llm
        active_info = f"Main: {main_name} | Quick: {quick_name}"
        return {"ok": True, "detail": active_info, "models": names}
    return {"ok": False, "detail": "No .gguf models found", "models": []}


def check_stt() -> dict:
    """Check required STT files based on config."""
    active_stt = config.get("main_stt", DEFAULT_STT_MODEL)
    stt_folder = STT_DIR / active_stt
    missing = [f for f in STT_REQUIRED if not (stt_folder / f).exists()]
    if not missing:
        return {"ok": True, "detail": f"Active: {stt_folder.name}"}
    return {"ok": False, "detail": f"Missing files in {stt_folder.name}", "missing": missing}


def check_tts() -> dict:
    """Check required TTS files based on config."""
    active_tts = config.get("en_tts", DEFAULT_EN_TTS)
    tts_folder = TTS_DIR / active_tts
    
    found_onnx = None
    if tts_folder.exists() and tts_folder.is_dir():
        for file in tts_folder.glob("*.onnx"):
            if (tts_folder / f"{file.name}.json").exists():
                found_onnx = file
                break
                
    if found_onnx:
        found_files = [found_onnx.name, f"{found_onnx.name}.json"]
        return {"ok": True, "detail": f"Active: {active_tts}", "required": found_files, "active": active_tts}
        
    expected = [f"{active_tts}.onnx", f"{active_tts}.onnx.json"]
    return {"ok": False, "detail": f"Missing files in {active_tts}", "missing": expected, "required": expected, "active": active_tts}


def check_embeddings() -> dict:
    """Check optional embeddings model via HuggingFace Hub locally."""
    model = config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
    
    try:
        from huggingface_hub import snapshot_download
        models_to_try = [model]
        if "/" not in model:
            models_to_try.append(f"sentence-transformers/{model}")
            
        for m in models_to_try:
            try:
                snapshot_download(m, local_files_only=True)
                return {"ok": True,  "detail": f"Active Local: {m}", "optional": True}
            except Exception:
                pass
    except Exception:
        pass
    return {"ok": False, "detail": f"Missing {model} Locally", "missing": [], "optional": True}

def check_sysfiles() -> dict:
    """Check required system files (videos and sounds)."""
    missing = [f.name for f in SYSFILES_REQUIRED if not f.exists()]
    if not missing:
        return {"ok": True, "detail": "All assets present", "required": [f.name for f in SYSFILES_REQUIRED]}
    return {"ok": False, "detail": "Missing media assets", "missing": missing, "required": [f.name for f in SYSFILES_REQUIRED]}

def check_mpv() -> dict:
    """Check if mpv player is available."""
    if OS == "Windows":
        if (BIN_DIR / "mpv.exe").exists():
            return {"ok": True, "detail": "Found mpv.exe in bin"}
        return {"ok": False, "detail": "Missing mpv.exe in bin"}
    else:
        try:
            flags = subprocess.CREATE_NO_WINDOW if OS == "Windows" else 0
            subprocess.run(
                ["mpv", "--version"], 
                capture_output=True, timeout=5,
                stdin=subprocess.DEVNULL,
                creationflags=flags
            )
            return {"ok": True, "detail": "Installed"}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {"ok": False, "detail": "Not installed"}

def get_vram_gb():
    """Attempt to get total VRAM in GB for NVIDIA GPUs without external libraries."""
    try:
        if OS == "Windows":
            flags = subprocess.CREATE_NO_WINDOW
            res = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"], capture_output=True, text=True, creationflags=flags)
            if res.returncode == 0:
                return round(int(res.stdout.strip()) / 1024, 1)
    except Exception:
        pass
    return None

def run_all_checks() -> dict:
    print("[DEBUG] check_ollama starting")
    ollama_res = check_ollama()
    print("[DEBUG] check_llm starting")
    llm_res = check_llm()
    print("[DEBUG] check_stt starting")
    stt_res = check_stt()
    print("[DEBUG] check_tts starting")
    tts_res = check_tts()
    print("[DEBUG] check_embeddings starting")
    emb_res = check_embeddings()
    print("[DEBUG] check_sysfiles starting")
    sys_res = check_sysfiles()
    print("[DEBUG] check_mpv starting")
    mpv_res = check_mpv()
    print("[DEBUG] run_all_checks finished")
    return {
        "os":         {"name": OS, "ok": True, "detail": platform.version()[:60]},
        "vram_gb":    get_vram_gb(),
        "ollama":     ollama_res,
        "llm":        llm_res,
        "stt":        stt_res,
        "tts":        tts_res,
        "embeddings": emb_res,
        "sysfiles":   sys_res,
        "mpv":        mpv_res,
    }


def is_setup_complete() -> bool:
    """Returns False if any NON-optional component is missing."""
    checks = run_all_checks()
    critical = ["ollama", "llm", "stt", "tts", "sysfiles", "mpv"]
    return all(checks[k]["ok"] for k in critical)


# ╔══════════════════════════════════════════════════════════════╗
# ║                      DOWNLOADER                              ║
# ╚══════════════════════════════════════════════════════════════╝
class Downloader:
    """Background download engine with progress callbacks."""

    def __init__(self, progress_cb, done_cb, error_cb):
        self._progress = progress_cb   # (percent: int, speed_str: str, label: str)
        self._done     = done_cb       # (component: str)
        self._error    = error_cb      # (component: str, msg: str)
        self._cancel   = False
        self._thread: threading.Thread | None = None

    def cancel(self):
        self._cancel = True

    def _download_file(self, url: str, dest: Path, label=""):
        """Download a single file with progress reporting."""
        import time
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")

        try:
            req = urllib.request.urlopen(url, timeout=30)
            total = int(req.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 1024 * 64   # 64 KB
            t0 = time.time()
            speed_str = "—"

            with open(tmp, "wb") as f:
                while True:
                    if self._cancel:
                        break
                    buf = req.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    downloaded += len(buf)
                    elapsed = time.time() - t0 or 0.001
                    speed = downloaded / elapsed
                    speed_str = (f"{speed/1_048_576:.1f} MB/s"
                                 if speed > 1_048_576
                                 else f"{speed/1024:.0f} KB/s")
                    pct = int(downloaded * 100 / total) if total else 0
                    self._progress(pct, speed_str, label)

            if self._cancel:
                tmp.unlink(missing_ok=True)
                return False

            tmp.rename(dest)
            return True

        except Exception as e:
            try:
                if tmp.exists():
                    tmp.unlink(missing_ok=True)
            except Exception:
                pass
            raise e

    # ── Public download triggers ───────────────────────────────
    def download_ollama(self):
        url = OLLAMA_URLS.get(OS, OLLAMA_URLS["Linux"])
        ext = ".exe" if OS == "Windows" else ""
        dest = Path.home() / f"OllamaInstaller{ext}"
        self._thread = threading.Thread(
            target=self._task_ollama, args=(url, dest), daemon=True)
        self._thread.start()

    def _task_ollama(self, url, dest):
        try:
            self._download_file(url, dest, "Ollama Installer")
            # NEW: robust auto-launch installer after download
            if OS == "Windows":
                os.startfile(str(dest)) # MODIFIED: os.startfile is more robust for EXEs than Popen
            else:
                dest.chmod(0o755)
                subprocess.Popen(["bash", "-c",
                    f'curl -fsSL https://ollama.com/install.sh | sh'])
            self._done("ollama")
        except Exception as e:
            self._error("ollama", str(e))

    def download_llm(self):
        dest = LLM_DIR / RECOMMENDED_LLM_NAME
        self._thread = threading.Thread(
            target=self._task_single,
            args=(RECOMMENDED_LLM_URL, dest, "LLM Model", "llm"),
            daemon=True)
        self._thread.start()

    def download_stt(self):
        active_stt = config.get("main_stt", DEFAULT_STT_MODEL)
        self._thread = threading.Thread(
            target=self._task_multi,
            args=(STT_FILES, STT_DIR / active_stt, "STT Model", "stt"),
            daemon=True)
        self._thread.start()

    def download_tts(self):
        """TTS is manual — just open the HuggingFace page."""
        import webbrowser
        webbrowser.open(TTS_HF_REPO)

    def download_jarvis_voice(self):
        dest_folder = TTS_DIR / "jarvis_en_GB_high"
        dest_folder.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(
            target=self._task_multi,
            args=(JARVIS_VOICE_FILES, dest_folder, "Jarvis Voice", "tts"),
            daemon=True)
        self._thread.start()

    def download_embeddings(self):
        def _pull_model():
            try:
                model = config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
                models_to_try = [model]
                if "/" not in model:
                    models_to_try.append(f"sentence-transformers/{model}")
                    
                from huggingface_hub import snapshot_download
                success = False
                last_error = ""
                for m in models_to_try:
                    try:
                        self._progress(50, f"Downloading {m}...", "Embeddings")
                        snapshot_download(m)
                        success = True
                        break
                    except Exception as e:
                        last_error = str(e)
                        
                if success:
                    self._done("embeddings")
                else:
                    self._error("embeddings", last_error)
            except Exception as e:
                self._error("embeddings", str(e))
                
        self._thread = threading.Thread(target=_pull_model, daemon=True)
        self._thread.start()

    def download_sysfiles(self):
        self._thread = threading.Thread(
            target=self._task_sysfiles,
            daemon=True)
        self._thread.start()

    def _task_sysfiles(self):
        try:
            total = len(SYSFILES_DL)
            for i, (name, (url, dest)) in enumerate(SYSFILES_DL.items(), 1):
                lbl = f"System Files ({i}/{total}): {name}"
                self._download_file(url, dest, lbl)
                if self._cancel:
                    self._error("sysfiles", "Cancelled")
                    return
            self._done("sysfiles")
        except Exception as e:
            self._error("sysfiles", str(e))

    def download_mpv(self):
        self._thread = threading.Thread(target=self._task_mpv, daemon=True)
        self._thread.start()

    def _task_mpv(self):
        import urllib.request, json, subprocess
        try:
            if OS != "Windows":
                self._error("mpv", "Auto-download is only supported on Windows.")
                return
            
            self._progress(10, "Fetching info...", "MPV Player")
            res = urllib.request.urlopen("https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest", timeout=15)
            data = json.loads(res.read())
            url = next(a['browser_download_url'] for a in data['assets'] if a['name'].startswith('mpv-x86_64-') and 'v3' not in a['name'] and 'dev' not in a['name'])
            
            BIN_DIR.mkdir(parents=True, exist_ok=True)
            seven_z_path = BIN_DIR / "7zr.exe"
            if not seven_z_path.exists():
                self._download_file("https://www.7-zip.org/a/7zr.exe", seven_z_path, "7-Zip Extractor")
                if self._cancel:
                    self._error("mpv", "Cancelled")
                    return
            
            mpv_7z_path = BIN_DIR / "mpv_temp.7z"
            self._download_file(url, mpv_7z_path, "MPV Archive")
            if self._cancel:
                self._error("mpv", "Cancelled")
                return
            
            self._progress(90, "Extracting...", "MPV Player")
            # CREATE_NO_WINDOW = 0x08000000
            subprocess.run([str(seven_z_path), "x", "-y", f"-o{BIN_DIR}", str(mpv_7z_path)], check=True, creationflags=0x08000000)
            
            mpv_7z_path.unlink(missing_ok=True)
            self._done("mpv")
        except Exception as e:
            self._error("mpv", str(e))

    def _task_single(self, url, dest, label, component):
        try:
            self._download_file(url, dest, label)
            self._done(component)
        except Exception as e:
            self._error(component, str(e))

    def _task_multi(self, files: dict, folder: Path, label: str, component: str):
        try:
            total = len(files)
            for i, (name, url) in enumerate(files.items(), 1):
                dest = folder / name
                lbl  = f"{label} ({i}/{total}): {name}"
                self._download_file(url, dest, lbl)
                if self._cancel:
                    self._error(component, "Cancelled")
                    return
            self._done(component)
        except Exception as e:
            self._error(component, str(e))


# ╔══════════════════════════════════════════════════════════════╗
# ║                    PYTHON ↔ JS BRIDGE                        ║
# ╚══════════════════════════════════════════════════════════════╝
class WizardAPI:
    def __init__(self):
        self._dls = {}  # type: dict[str, Downloader]
        self._window = None          # set after window creation
        self._download_queue = []  # not included in windows production v1.3 
        self._active_downloads = set()

    def set_window(self, w):
        self._window = w

    def _js(self, js_code: str):
        if not self._window:
            return
        try:
            self._window.evaluate_js(js_code)
        except Exception as e:
            logging.debug(f"JS eval skipped (window gone): {e}")

    # ── Checks ────────────────────────────────────────────────
    def get_status(self):
        return json.dumps(run_all_checks())

    def open_url(self, url: str):
        import webbrowser
        webbrowser.open(url)

    # NEW: ── Open Directory Logic ─────────────────────────────
    def open_folder(self, component: str):
        """Opens the correct local folder based on the component clicked."""
        paths = {
            "llm": LLM_DIR,
            "stt": STT_DIR,
            "tts": TTS_DIR,
            "bin": BIN_DIR,
        }
        
        folder = paths.get(component)
        if not folder:
            return json.dumps({"ok": False})
            
        folder.mkdir(parents=True, exist_ok=True)
        
        try:
            if OS == "Windows":
                os.startfile(folder)
            elif OS == "Darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
            return json.dumps({"ok": True})
        except Exception as e:
            print(f"Error opening folder: {e}")
            logging.error(f"Error opening folder: {e}")
            return json.dumps({"ok": False})

    # ── Downloads ─────────────────────────────────────────────
    def start_download(self, component: str):
        # Prevent re-downloading if already exists (skip this check for jarvis_voice as it is an explicit extra download)
        if component != "jarvis_voice":
            checks = run_all_checks()
            if checks.get(component, {}).get("ok"):
                return json.dumps({"ok": False, "reason": "Already Existed"})

        if component in self._dls or component in self._download_queue:
            return json.dumps({"ok": False, "reason": "Already downloading"})

        self._download_queue.append(component)
        self._js(f"onProgress('{component}', 0, 'Queued', 'Waiting for slot...')")
        self._process_queue()
        return json.dumps({"ok": True})

    def _process_queue(self):
        while len(self._active_downloads) < 2 and self._download_queue:
            component = self._download_queue.pop(0)
            self._active_downloads.add(component)
            self._start_download_task(component)

    def _start_download_task(self, component: str):
        def on_progress(pct, speed, label):
            safe_label = label.replace("'", "\\'")
            self._js(f"onProgress('{component}',{pct},'{speed}','{safe_label}')")

        def on_done(comp):
            self._dls.pop(comp, None)
            self._active_downloads.discard(comp)
            self._js(f"onDone('{comp}')")
            self._process_queue()

        def on_error(comp, msg):
            self._dls.pop(comp, None)
            self._active_downloads.discard(comp)
            safe_msg = msg.replace("'", "\\'")[:120]
            self._js(f"onError('{comp}','{safe_msg}')")

        dl = Downloader(on_progress, on_done, on_error)
        self._dls[component] = dl

        actions = {
            "ollama":     dl.download_ollama,
            "llm":        dl.download_llm,
            "stt":        dl.download_stt,
            "tts":        dl.download_tts,
            "jarvis_voice": dl.download_jarvis_voice,
            "embeddings": dl.download_embeddings,
            "sysfiles":   dl.download_sysfiles,
            "mpv":        dl.download_mpv,
        }
        fn = actions.get(component)
        if fn:
            fn()
        else:
            on_error(component, "Unknown component")
        return json.dumps({"ok": bool(fn)})

    def cancel_download(self):
        self._download_queue.clear()
        for dl in self._dls.values():
            dl.cancel()
        self._dls.clear()
        self._active_downloads.clear()
        return json.dumps({"ok": True})

    def cancel_task(self, component: str):
        if component in self._download_queue:
            self._download_queue.remove(component)
            self._js(f"onError('{component}','Cancelled')")
            return json.dumps({"ok": True})
            
        dl = self._dls.pop(component, None)
        if dl:
            dl.cancel()
            self._active_downloads.discard(component)
            self._process_queue()
            return json.dumps({"ok": True})
        return json.dumps({"ok": False, "reason": "Not downloading"})

    def mark_setup_complete(self):
        config.set("setup_complete", True)
        return json.dumps({"ok": True})

    def recheck(self):
        return json.dumps(run_all_checks())

    def open_settings(self):
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--settings"])
            elif "__compiled__" in globals():
                subprocess.Popen([sys.argv[0], "--settings"])
            else:
                settings_script = BASE_DIR / "core" / "ui" / "settings_panel.py"
                subprocess.Popen([sys.executable, str(settings_script)])
            return json.dumps({"ok": True})
        except Exception as e:
            print(f"Error opening settings: {e}")
            logging.error(f"Error opening settings: {e}")
            return json.dumps({"ok": False})

    def launch_jarvis(self):
        """Close wizard — main app will continue."""
        config.set("setup_complete", True)
        if self._window:
            self._window.destroy()


# ╔══════════════════════════════════════════════════════════════╗
# ║              PREMIUM HTML / UI (GOLD THEME MERGED)           ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>JARVIS NEXUS · Setup Wizard</title>
<style>
/* ═══════════════════════════════════════════════════════════════
   JARVIS NEXUS Design System v2.0 – Premium Gold/Amber Theme
   ═══════════════════════════════════════════════════════════════ */
:root{
  --gold:           #C9A227;
  --gold-light:     #E8D5A3;
  --gold-dark:      #8B6914;
  --gold-glow:      rgba(201, 162, 39, 0.15);
  --gold-glow-strong:rgba(201, 162, 39, 0.3);
  --bg:             #0a0e14;
  --surface-1:      #0d1117;
  --surface-2:      #131820;
  --surface-3:      #1a1f2a;
  --surface-4:      #222836;
  --surface-hover:  #2a3040;
  --border-subtle:  rgba(255,255,255,0.04);
  --border-default: rgba(255,255,255,0.08);
  --border-active:  rgba(201, 162, 39, 0.4);
  --border-gold:    rgba(201, 162, 39, 0.25);
  --txt-primary:    #f0f4f8;
  --txt-secondary:  #94a3b8;
  --txt-muted:      #64748b;
  --txt-gold:       #E8D5A3;
  --accent:         var(--gold);
  --accent-h:       var(--gold-light);
  --green:          #22c55e;
  --green-dim:      #16a34a;
  --red:            #ef4444;
  --red-dim:        #dc2626;
  --yellow:         #eab308;
  --cyan:           #06b6d4;
  --shadow-sm:      0 1px 2px rgba(0,0,0,0.3);
  --shadow-md:      0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg:      0 8px 32px rgba(0,0,0,0.5);
  --shadow-gold:    0 0 20px rgba(201, 162, 39, 0.1);
  --ease-out:       cubic-bezier(0.16, 1, 0.3, 1);
  --ease-spring:    cubic-bezier(0.34, 1.56, 0.64, 1);
  --trans-fast:     0.15s var(--ease-out);
  --trans-normal:   0.25s var(--ease-out);
  --trans-slow:     0.4s var(--ease-out);
  --radius-sm:      6px;
  --radius-md:      10px;
  --radius-lg:      14px;
  --radius-xl:      20px;
}

*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html,body{
  height:100%;
  font-family:"Inter","Segoe UI",system-ui,-apple-system,sans-serif;
  background:var(--bg);
  color:var(--txt-primary);
  font-size:14px;
  overflow:hidden;
  -webkit-font-smoothing:antialiased;
}

::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:10px}
::-webkit-scrollbar-thumb:hover{background:rgba(201,162,39,0.3)}

#app{display:flex;flex-direction:column;height:100vh;position:relative}
#app::before{
  content:'';position:fixed;inset:0;
  background-image:
    linear-gradient(rgba(201,162,39,0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(201,162,39,0.03) 1px, transparent 1px);
  background-size:50px 50px;
  pointer-events:none;z-index:0;
  mask-image:radial-gradient(ellipse at center, black 40%, transparent 80%);
}

/* ── Header ─────────────────────────────────────────────── */
#header{
  background:linear-gradient(180deg, var(--surface-1) 0%, var(--surface-2) 100%);
  border-bottom:1px solid var(--border-default);
  padding:18px 32px;display:flex;align-items:center;gap:16px;flex-shrink:0;
  position:relative;z-index:10;
}
#header::after{
  content:'';position:absolute;bottom:-1px;left:0;right:0;
  height:1px;background:linear-gradient(90deg, transparent, var(--gold-glow-strong), transparent);
}

.logo-wrap{display:flex;align-items:center;gap:14px}
.logo-icon{
  width:36px;height:36px;border-radius:10px;
  background:linear-gradient(135deg, var(--gold-dark), var(--gold));
  display:flex;align-items:center;justify-content:center;
  box-shadow:0 0 15px rgba(201,162,39,0.3), inset 0 1px 0 rgba(255,255,255,0.2);
  font-size:18px;color:#0a0e14;font-weight:700;
}
.logo-text{line-height:1.2}
.logo-main{font-size:17px;font-weight:700;letter-spacing:0.5px;color:var(--txt-primary)}
.logo-main span{color:var(--gold);font-weight:800}
.logo-sub{font-size:11px;color:var(--txt-muted);font-weight:500;letter-spacing:0.3px}

.os-badge{
  margin-left:auto;
  background:rgba(201,162,39,0.1);
  border:1px solid var(--border-gold);
  color:var(--gold-light);
  font-size:11px;font-weight:700;
  padding:4px 12px;border-radius:20px;
  letter-spacing:0.5px;
}
.os-badge:empty{display:none}

/* ── Body ───────────────────────────────────────────────── */
#body{
  flex:1;overflow-y:auto;padding:24px 32px;display:flex;flex-direction:column;gap:16px;
  position:relative;z-index:1;
}

/* ── Summary Bar ────────────────────────────────────────── */
#summary{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);padding:14px 20px;
  display:flex;align-items:center;gap:16px;
  flex-shrink:0;
  box-shadow:var(--shadow-md);
}
#summary .s-item{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--txt-secondary);}
#summary .s-dot{width:8px;height:8px;border-radius:50%;}

/* ── Component Card ─────────────────────────────────────── */
.comp-card{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);
  overflow:hidden;
  transition:all var(--trans-normal);
  flex-shrink:0;
}
.comp-card:hover{
  border-color:var(--border-active);
  box-shadow:var(--shadow-gold);
}
.comp-card.ok{border-color:rgba(34,197,94,0.3);}
.comp-card.warn{border-color:rgba(234,179,8,0.3);}
.comp-card.error{border-color:rgba(239,68,68,0.3);}
.comp-card.optional{opacity:0.9;}

.card-top{
  display:flex;align-items:center;gap:14px;padding:16px 20px;cursor:pointer;
  user-select:none;
  transition:background var(--trans-fast);
}
.card-top:hover{background:rgba(255,255,255,0.02);}

.status-dot{
  width:10px;height:10px;border-radius:50%;flex-shrink:0;
  transition:background var(--trans-fast);
}
.dot-ok    {background:var(--green); box-shadow:0 0 8px var(--green);}
.dot-error {background:var(--red); box-shadow:0 0 8px rgba(239,68,68,0.4);}
.dot-warn  {background:var(--yellow); box-shadow:0 0 8px rgba(234,179,8,0.4);}
.dot-spin  {
  background:transparent;border:2px solid var(--gold);
  border-top-color:transparent;
  animation:spin .7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}

.comp-icon{font-size:20px;width:30px;text-align:center;flex-shrink:0;color:var(--gold);}
.comp-info{flex:1;min-width:0}
.comp-name{font-size:15px;font-weight:600;color:var(--txt-primary);}
.comp-detail{font-size:13px;color:var(--txt-muted);margin-top:4px;line-height:1.4;}

.quick-actions{display:flex;gap:8px;align-items:center;margin-right:12px;}
.opt-tag{
  font-size:10px;padding:2px 8px;border-radius:10px;
  background:rgba(201,162,39,0.1);color:var(--gold-light);
  border:1px solid var(--border-gold);
  flex-shrink:0;
}
.chevron{color:var(--txt-muted);font-size:12px;transition:transform var(--trans-fast);}
.card-top.expanded .chevron{transform:rotate(180deg);}

.card-body{
  display:none;padding:0 20px 16px;border-top:1px solid var(--border-default);
}
.card-body.open{display:block;}

.desc{
  font-size:12px;color:var(--txt-secondary);line-height:1.6;
  padding:12px 0 14px;
}
.desc strong{color:var(--txt-primary);}
.desc code{
  background:var(--surface-1);padding:1px 6px;border-radius:4px;
  font-family:monospace;font-size:11px;color:var(--gold-light);
}

.file-list{
  display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;
}
.file-pill{
  font-size:11px;padding:3px 10px;border-radius:20px;
  font-family:monospace;
}
.file-ok   {background:rgba(34,197,94,0.1);color:var(--green);border:1px solid rgba(34,197,94,0.2);}
.file-miss {background:rgba(239,68,68,0.1);color:var(--red);border:1px solid rgba(239,68,68,0.2);}

.action-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}

/* ── Progress bar ────────────────────────────────────────── */
.progress-wrap{margin-top:12px;display:none;}
.progress-wrap.show{display:block}
.progress-top{display:flex;justify-content:space-between;font-size:11px;color:var(--txt-muted);margin-bottom:6px}
.progress-bar-bg{
  height:6px;background:var(--surface-4);border-radius:3px;overflow:hidden;
}
.progress-bar{
  height:100%;background:linear-gradient(90deg, var(--gold-dark), var(--gold));
  border-radius:3px;width:0%;transition:width .3s;
}
.progress-label{font-size:11px;color:var(--txt-muted);margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* ── Buttons (Premium) ──────────────────────────────────── */
button{
  display:inline-flex;align-items:center;gap:6px;
  padding:8px 16px;border-radius:var(--radius-md);border:none;
  font-size:12px;font-weight:600;cursor:pointer;
  transition:all var(--trans-fast);font-family:inherit;
  position:relative;overflow:hidden;
}
button::before{
  content:'';position:absolute;inset:0;
  background:linear-gradient(180deg, rgba(255,255,255,0.1), transparent);
  opacity:0;transition:opacity var(--trans-fast);
}
button:hover::before{opacity:1}
button:active{transform:scale(0.97)}
button:disabled{opacity:.4;cursor:not-allowed}

.btn-primary{
  background:linear-gradient(135deg, var(--gold), var(--gold-dark));
  color:#0a0e14;box-shadow:0 4px 15px rgba(201,162,39,0.25);
}
.btn-primary:hover:not(:disabled){
  box-shadow:0 6px 20px rgba(201,162,39,0.4);
  transform:translateY(-1px);
}

.btn-ghost{
  background:var(--surface-3);
  color:var(--txt-secondary);
  border:1px solid var(--border-default);
}
.btn-ghost:hover:not(:disabled){
  background:var(--surface-4);color:var(--txt-primary);
  border-color:var(--border-active);
}

.btn-success{
  background:rgba(34,197,94,0.08);
  color:var(--green);
  border:1px solid rgba(34,197,94,0.2);
}
.btn-success:hover:not(:disabled){
  background:rgba(34,197,94,0.15);border-color:rgba(34,197,94,0.4);
}

.btn-danger{
  background:rgba(239,68,68,0.08);
  color:var(--red);
  border:1px solid rgba(239,68,68,0.2);
}
.btn-danger:hover:not(:disabled){
  background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.4);
}

.btn-warn{
  background:rgba(234,179,8,0.08);
  color:var(--yellow);
  border:1px solid rgba(234,179,8,0.2);
}
.btn-warn:hover:not(:disabled){
  background:rgba(234,179,8,0.15);border-color:rgba(234,179,8,0.4);
}

.btn-launch{
  background:linear-gradient(135deg, var(--gold), var(--gold-dark));
  color:#0a0e14;padding:11px 28px;font-size:14px;
  box-shadow:0 0 20px rgba(201,162,39,0.3);
}
.btn-launch:hover:not(:disabled){
  box-shadow:0 0 30px rgba(201,162,39,0.5);
  transform:translateY(-1px);
}
.btn-launch:disabled{
  background:var(--surface-4);color:var(--txt-muted);box-shadow:none;
}

/* ── Footer ─────────────────────────────────────────────── */
#footer{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-1));
  border-top:1px solid var(--border-default);
  padding:14px 32px;display:flex;align-items:center;gap:12px;flex-shrink:0;
  position:relative;z-index:10;
}
#footer::before{
  content:'';position:absolute;top:-1px;left:0;right:0;
  height:1px;background:linear-gradient(90deg, transparent, var(--gold-glow-strong), transparent);
}
#footer .info{flex:1;font-size:12px;color:var(--txt-muted);}

/* ── Toast ───────────────────────────────────────────────── */
#toast{
  position:fixed;bottom:80px;right:28px;
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);padding:14px 24px;
  font-size:13px;color:var(--txt-primary);font-weight:500;
  box-shadow:var(--shadow-lg), 0 0 30px rgba(0,0,0,0.3);
  transform:translateY(20px) scale(0.95);opacity:0;
  transition:all .3s var(--ease-spring);
  pointer-events:none;z-index:999;
  display:flex;align-items:center;gap:10px;
}
#toast.show{transform:translateY(0) scale(1);opacity:1}
#toast.ok{border-color:rgba(34,197,94,0.3);color:var(--green);}
#toast.err{border-color:rgba(239,68,68,0.3);color:var(--red);}
#toast.warn{border-color:rgba(234,179,8,0.3);color:var(--yellow);}

/* ── SVG Icons ─────────────────────────────────────────── */
svg { vertical-align: middle; }
button svg { margin-top: -1px; width: 1.1em; height: 1.1em; }
.comp-icon svg { width: 1.2em; height: 1.2em; color: var(--gold); }
.logo-icon svg { width: 22px; height: 22px; color: #0a0e14; }
.quick-actions button svg { width: 1.2em; height: 1.2em; }
.chevron { display: flex; align-items: center; justify-content: center; }
.chevron svg { width: 1.2em; height: 1.2em; transition: transform var(--trans-fast); }
.card-top.expanded .chevron svg { transform: rotate(180deg); }
</style>
</head>
<body>
<div id="app">

<div id="header">
  <div class="logo-wrap">
    <div class="logo-icon">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <polygon points="12 2 20.66 7 20.66 17 12 22 3.34 17 3.34 7"></polygon>
        <circle cx="12" cy="12" r="3.5"></circle>
        <line x1="12" y1="2" x2="12" y2="8.5"></line>
        <line x1="12" y1="22" x2="12" y2="15.5"></line>
        <line x1="20.66" y1="7" x2="15.03" y2="10.25"></line>
        <line x1="20.66" y1="17" x2="15.03" y2="13.75"></line>
        <line x1="3.34" y1="7" x2="8.97" y2="10.25"></line>
        <line x1="3.34" y1="17" x2="8.97" y2="13.75"></line>
        <circle cx="12" cy="2" r="1.5" fill="currentColor" stroke="none"></circle>
        <circle cx="20.66" cy="7" r="1.5" fill="currentColor" stroke="none"></circle>
        <circle cx="20.66" cy="17" r="1.5" fill="currentColor" stroke="none"></circle>
        <circle cx="12" cy="22" r="1.5" fill="currentColor" stroke="none"></circle>
        <circle cx="3.34" cy="17" r="1.5" fill="currentColor" stroke="none"></circle>
        <circle cx="3.34" cy="7" r="1.5" fill="currentColor" stroke="none"></circle>
      </svg>
    </div>
    <div class="logo-text">
      <div class="logo-main">JARVIS <span>Setup</span></div>
      <div class="logo-sub">First-Run Configuration Wizard</div>
    </div>
  </div>
  <div class="os-badge" id="vram-badge" style="display:none; font-weight:bold;"></div>
  <div class="os-badge" id="os-badge" style="margin-left:8px;">Detecting OS...</div>
  <div class="os-badge" id="version-badge" style="margin-left:8px;">v__APP_VERSION__</div>
</div>

<div id="body">

  <div id="summary">
    <span style="font-size:12px;color:var(--txt-muted);font-weight:600;">STATUS:</span>
    <div class="s-item"><div class="s-dot" id="sum-ollama" style="background:var(--txt-muted)"></div><span>Ollama</span></div>
    <div class="s-item"><div class="s-dot" id="sum-llm"    style="background:var(--txt-muted)"></div><span>LLM</span></div>
    <div class="s-item"><div class="s-dot" id="sum-stt"    style="background:var(--txt-muted)"></div><span>STT</span></div>
    <div class="s-item"><div class="s-dot" id="sum-tts"    style="background:var(--txt-muted)"></div><span>TTS</span></div>
    <div class="s-item"><div class="s-dot" id="sum-emb"    style="background:var(--txt-muted)"></div><span style="color:var(--txt-muted)">Embeddings (opt)</span></div>
    <div class="s-item"><div class="s-dot" id="sum-sysfiles" style="background:var(--txt-muted)"></div><span>SysFiles</span></div>
    <div class="s-item"><div class="s-dot" id="sum-mpv" style="background:var(--txt-muted)"></div><span>MPV</span></div>
    <button class="btn-ghost" style="margin-left:auto;padding:5px 12px;font-size:11px;"
            onclick="recheck()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg> Re-check</button>
  </div>

  <!-- Ollama Card -->
  <div class="comp-card" id="card-ollama">
    <div class="card-top" onclick="toggle('ollama')">
      <div class="status-dot" id="dot-ollama"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg></div>
      <div class="comp-info">
        <div class="comp-name">Ollama</div>
        <div class="comp-detail" id="detail-ollama">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" id="icon-dl-ollama" onclick="doDownload('ollama')" title="Download"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></button>
        <button class="btn-ghost btn-sm" id="icon-cancel-ollama" onclick="doCancel('ollama')" title="Cancel" style="display:none"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
      </div>
      <span class="chevron" id="chev-ollama"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-ollama">
      <div class="desc">
        <strong>Ollama</strong> is the local model runtime that powers JARVIS's brain.
        It manages downloading, loading, and serving LLM models on your machine.<br><br>
        Detected OS: <code id="os-label">—</code>
      </div>
      <div class="action-row">
        <button class="btn-primary" id="btn-dl-ollama" onclick="doDownload('ollama')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download Ollama Installer
        </button>
        <button class="btn-danger" id="btn-cancel-ollama" onclick="doCancel('ollama')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_url('https://ollama.com')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> ollama.com
        </button>
      </div>
      <div class="progress-wrap" id="prog-ollama">
        <div class="progress-top">
          <span id="prog-ollama-speed">—</span>
          <span id="prog-ollama-pct">0%</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar" id="bar-ollama"></div></div>
        <div class="progress-label" id="lbl-ollama"></div>
      </div>
    </div>
  </div>

  <!-- LLM Card -->
  <div class="comp-card" id="card-llm">
    <div class="card-top" onclick="toggle('llm')">
      <div class="status-dot" id="dot-llm"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg></div>
      <div class="comp-info">
        <div class="comp-name">LLM Model</div>
        <div class="comp-detail" id="detail-llm">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" id="icon-dl-llm" onclick="doDownload('llm')" title="Download"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></button>
        <button class="btn-ghost btn-sm" id="icon-cancel-llm" onclick="doCancel('llm')" title="Cancel" style="display:none"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
        <button class="btn-ghost btn-sm" onclick="pywebview.api.open_folder('llm')" title="Open Folder"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg></button>
      </div>
      <span class="chevron" id="chev-llm"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-llm">
      <div class="desc">
        The <strong>Large Language Model</strong> is JARVIS's reasoning core — it understands
        your commands and generates intelligent responses.<br><br>
        We strongly recommend <code>Qwen3-4B-Instruct-2507-Q5_K_M.gguf</code> —
        exceptional performance at ~3.5 GB, great Ollama/GGUF compatibility,
        and the best results with JARVIS's tool-calling system.<br><br>
        Place any <code>.gguf</code> file inside <code>models/llm/</code> and it will be auto-detected.
      </div>
      <div class="file-list" id="files-llm"></div>
      <div class="action-row">
        <button class="btn-primary" id="btn-dl-llm" onclick="doDownload('llm')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download Qwen3-4B (Recommended)
        </button>
        <button class="btn-danger" id="btn-cancel-llm" onclick="doCancel('llm')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('llm')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> Open LLM Folder
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://huggingface.co/Qwen/Qwen3-4B-Instruct-GGUF')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> HuggingFace Repo
        </button>
      </div>
      <div class="progress-wrap" id="prog-llm">
        <div class="progress-top">
          <span id="prog-llm-speed">—</span>
          <span id="prog-llm-pct">0%</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar" id="bar-llm"></div></div>
        <div class="progress-label" id="lbl-llm"></div>
      </div>
    </div>
  </div>

  <!-- STT Card -->
  <div class="comp-card" id="card-stt">
    <div class="card-top" onclick="toggle('stt')">
      <div class="status-dot" id="dot-stt"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg></div>
      <div class="comp-info">
        <div class="comp-name">Speech-to-Text Model</div>
        <div class="comp-detail" id="detail-stt">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" id="icon-dl-stt" onclick="doDownload('stt')" title="Download"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></button>
        <button class="btn-ghost btn-sm" id="icon-cancel-stt" onclick="doCancel('stt')" title="Cancel" style="display:none"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
        <button class="btn-ghost btn-sm" onclick="pywebview.api.open_folder('stt')" title="Open Folder"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg></button>
      </div>
      <span class="chevron" id="chev-stt"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-stt">
      <div class="desc">
        <strong>faster-whisper-small.en</strong> — JARVIS's ears.
        Converts your voice to text locally with low latency.
        Required files:
      </div>
      <div class="file-list" id="files-stt"></div>
      <div class="action-row">
        <button class="btn-primary" id="btn-dl-stt" onclick="doDownload('stt')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download STT Model
        </button>
        <button class="btn-danger" id="btn-cancel-stt" onclick="doCancel('stt')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('stt')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> Open STT Folder
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://huggingface.co/guillaumekln/faster-whisper-small.en')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> HuggingFace Repo
        </button>
      </div>
      <div class="progress-wrap" id="prog-stt">
        <div class="progress-top">
          <span id="prog-stt-speed">—</span>
          <span id="prog-stt-pct">0%</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar" id="bar-stt"></div></div>
        <div class="progress-label" id="lbl-stt"></div>
      </div>
    </div>
  </div>

  <!-- TTS Card -->
  <div class="comp-card" id="card-tts">
    <div class="card-top" onclick="toggle('tts')">
      <div class="status-dot" id="dot-tts"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg></div>
      <div class="comp-info">
        <div class="comp-name">TTS Voice Files</div>
        <div class="comp-detail" id="detail-tts">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" onclick="pywebview.api.open_url('https://huggingface.co/rhasspy/piper-voices/tree/main/en')" title="Browse HF"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg></button>
        <button class="btn-ghost btn-sm" onclick="pywebview.api.open_folder('tts')" title="Open Folder"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg></button>
      </div>
      <span class="chevron" id="chev-tts"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-tts">
      <div class="desc" id="desc-tts">
        <strong>Piper TTS</strong> — JARVIS's voice engine.
        The system checks for the active TTS model configured in settings.<br><br>
        Required files inside your configured <code>assets/tts/</code> folder:<br>
        <code>[model_name].onnx</code> &nbsp;+&nbsp; <code>[model_name].onnx.json</code><br><br>
        Want a different voice? Browse all English Piper voices on HuggingFace and
        drop the files in the same folder structure.
      </div>
      <div class="file-list" id="files-tts"></div>
      <div class="action-row">
        <button class="btn-primary" onclick="doDownload('jarvis_voice')" id="btn-dl-tts">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download Original Jarvis Voice
        </button>
        <button class="btn-danger" id="btn-cancel-tts" onclick="doCancel('jarvis_voice')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
        <button class="btn-warn"
                onclick="pywebview.api.open_url('https://huggingface.co/rhasspy/piper-voices/tree/main/en')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> Browse Piper Voices (English)
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('tts')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> Open TTS Folder
        </button>
        <div style="font-size:11px;color:var(--txt-muted);max-width:320px;line-height:1.5">
          Download the <code>.onnx</code> + <code>.onnx.json</code> files and place them
          in <code>assets/tts/jarvis_en_GB_high/</code> — then re-check.
        </div>
      </div>
    </div>
  </div>

  <!-- Embeddings Card -->
  <div class="comp-card optional" id="card-embeddings">
    <div class="card-top" onclick="toggle('embeddings')">
      <div class="status-dot" id="dot-embeddings"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg></div>
      <div class="comp-info">
        <div class="comp-name">Embeddings Model</div>
        <div class="comp-detail" id="detail-embeddings">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" id="icon-dl-embeddings" onclick="doDownload('embeddings')" title="Download Model"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></button>
        <button class="btn-ghost btn-sm" id="icon-cancel-embeddings" onclick="doCancel('embeddings')" title="Cancel" style="display:none"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
      </div>
      <span class="opt-tag">Optional</span>
      <span class="chevron" id="chev-embeddings"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-embeddings">
      <div class="desc">
        <strong>Embeddings Model</strong> — Used for semantic memory search.
        Enables JARVIS to find relevant memories by meaning, not just keywords.
        <strong>Not required for basic operation</strong> — skip if you just want to get started.<br><br>
        <em>Note: This model is downloaded and loaded locally using SentenceTransformers.</em>
      </div>
      <div class="action-row">
        <button class="btn-ghost" id="btn-dl-embeddings" onclick="doDownload('embeddings')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download Model
        </button>
        <button class="btn-danger" id="btn-cancel-embeddings" onclick="doCancel('embeddings')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> HuggingFace Page
        </button>
      </div>
      <div class="progress-wrap" id="prog-embeddings">
        <div class="progress-top">
          <span id="prog-embeddings-speed">—</span>
          <span id="prog-embeddings-pct">0%</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar" id="bar-embeddings"></div></div>
        <div class="progress-label" id="lbl-embeddings"></div>
      </div>
    </div>
  </div>

  <!-- Sysfiles Card -->
  <div class="comp-card" id="card-sysfiles">
    <div class="card-top" onclick="toggle('sysfiles')">
      <div class="status-dot" id="dot-sysfiles"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 12 15 2 8.5 12 2"></polygon><polyline points="2 12.5 12 19 22 12.5"></polyline><polyline points="2 16.5 12 23 22 16.5"></polyline></svg></div>
      <div class="comp-info">
        <div class="comp-name">System Files</div>
        <div class="comp-detail" id="detail-sysfiles">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" id="icon-dl-sysfiles" onclick="doDownload('sysfiles')" title="Download"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg></button>
        <button class="btn-ghost btn-sm" id="icon-cancel-sysfiles" onclick="doCancel('sysfiles')" title="Cancel" style="display:none"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
      </div>
      <span class="chevron" id="chev-sysfiles"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-sysfiles">
      <div class="desc">
        <strong>Assets</strong> — Video and sound effects required for the system interface.
      </div>
      <div class="file-list" id="files-sysfiles"></div>
      <div class="action-row">
        <button class="btn-primary" id="btn-dl-sysfiles" onclick="doDownload('sysfiles')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download Missing Assets
        </button>
        <button class="btn-danger" id="btn-cancel-sysfiles" onclick="doCancel('sysfiles')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
      </div>
      <div class="progress-wrap" id="prog-sysfiles">
        <div class="progress-top">
          <span id="prog-sysfiles-speed">—</span>
          <span id="prog-sysfiles-pct">0%</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar" id="bar-sysfiles"></div></div>
        <div class="progress-label" id="lbl-sysfiles"></div>
      </div>
    </div>
  </div>

  <!-- MPV Card -->
  <div class="comp-card" id="card-mpv">
    <div class="card-top" onclick="toggle('mpv')">
      <div class="status-dot" id="dot-mpv"></div>
      <div class="comp-icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="23 7 16 12 23 17 23 7"></polygon><rect x="1" y="5" width="15" height="14" rx="2" ry="2"></rect></svg></div>
      <div class="comp-info">
        <div class="comp-name">MPV Player</div>
        <div class="comp-detail" id="detail-mpv">Checking...</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-sm" onclick="pywebview.api.open_folder('bin')" title="Open Folder"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg></button>
      </div>
      <span class="chevron" id="chev-mpv"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg></span>
    </div>
    <div class="card-body" id="body-mpv">
      <div class="desc">
        <strong>MPV Video Player</strong> — Required for Jarvis visual sequences.
        <br><br>
        <span id="mpv-desc-win" style="display:none">
          Windows Build: You need to download the Portable version from the official mpv website (or from authorized GitHub releases for Windows). Extract only the <code>mpv.exe</code> file and place it in the <code>bin</code> folder.
        </span>
        <span id="mpv-desc-lin" style="display:none">
          Linux Build: Run the following command in your terminal:<br>
          <code>sudo apt install mpv</code>
        </span>
      </div>
      <div class="action-row">
        <button class="btn-primary" id="btn-dl-mpv" onclick="doDownload('mpv')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg> Download & Install MPV
        </button>
        <button class="btn-danger" id="btn-cancel-mpv" onclick="doCancel('mpv')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel Download
        </button>
        <button class="btn-primary" id="btn-info-mpv" onclick="pywebview.api.open_url('https://mpv.io/installation/')" style="display:none">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg> Instructions for Linux
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('bin')">
          <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg> Open bin Folder
        </button>
      </div>
      <div class="progress-wrap" id="prog-mpv">
        <div class="progress-top">
          <span id="prog-mpv-speed">—</span>
          <span id="prog-mpv-pct">0%</span>
        </div>
        <div class="progress-bar-bg"><div class="progress-bar" id="bar-mpv"></div></div>
        <div class="progress-label" id="lbl-mpv"></div>
      </div>
    </div>
  </div>

</div>

<div id="footer">
  <div class="info" id="footer-info">Checking components...</div>
  <button class="btn-ghost" onclick="openSettings()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg> Settings</button>
  <button class="btn-ghost" onclick="recheck()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg> Re-check All</button>
  <button class="btn-launch" id="btn-launch" disabled onclick="launchJarvis()">
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg> Launch JARVIS
  </button>
</div>

</div><div id="toast"></div>

<script>
// ╔══════════════════════════════════════════════════════════════╗
// ║                        STATE                                 ║
// ╚══════════════════════════════════════════════════════════════╝
let STATUS = {};
const REQUIRED = ['ollama','llm','stt','tts','sysfiles','mpv'];

// ╔══════════════════════════════════════════════════════════════╗
// ║                         BOOT                                 ║
// ╚══════════════════════════════════════════════════════════════╝
window.addEventListener('pywebviewready', async () => {
  await recheck();
});

// ╔══════════════════════════════════════════════════════════════╗
// ║                       RECHECK                                ║
// ╚══════════════════════════════════════════════════════════════╝
async function recheck() {
  document.getElementById('footer-info').textContent = 'Re-checking...';
  const raw = await pywebview.api.get_status();
  STATUS = JSON.parse(raw);
  renderAll();
  
  if (!window._auto_downloaded_sysfiles && STATUS.sysfiles && !STATUS.sysfiles.ok) {
    window._auto_downloaded_sysfiles = true;
    doDownload('sysfiles');
  }
}

async function openSettings() {
  await pywebview.api.open_settings();
}

function renderAll() {
  const os = STATUS.os;
  document.getElementById('os-badge').textContent = `${os.name} detected`;
  document.getElementById('os-label').textContent = os.name;

  const vramBadge = document.getElementById('vram-badge');
  if (STATUS.vram_gb !== null && STATUS.vram_gb !== undefined) {
      vramBadge.style.display = 'block';
      if (STATUS.vram_gb < 4) {
          vramBadge.style.color = 'var(--red)';
          vramBadge.style.borderColor = 'var(--red)';
          vramBadge.textContent = `⚠ VRAM: ${STATUS.vram_gb} GB (Min 4GB required)`;
      } else {
          vramBadge.style.color = 'var(--txt-muted)';
          vramBadge.style.borderColor = 'var(--border-default)';
          vramBadge.textContent = `VRAM: ${STATUS.vram_gb} GB`;
      }
  } else {
      vramBadge.style.display = 'none';
  }

  renderComp('ollama',     STATUS.ollama,     false);
  renderComp('llm',        STATUS.llm,        false);
  renderComp('stt',        STATUS.stt,        false);
  renderComp('tts',        STATUS.tts,        false);
  renderComp('embeddings', STATUS.embeddings, true);
  renderComp('sysfiles',   STATUS.sysfiles,   false);
  renderComp('mpv',        STATUS.mpv,        false);

  if (STATUS.os.name === 'Windows') {
    document.getElementById('mpv-desc-win').style.display = 'inline';
    if (STATUS.mpv && !STATUS.mpv.ok) {
        document.getElementById('btn-dl-mpv').style.display = 'inline-flex';
    }
  } else {
    document.getElementById('mpv-desc-lin').style.display = 'inline';
    document.getElementById('btn-info-mpv').style.display = 'inline-flex';
  }

  renderFiles('stt',        ['config.json','model.bin','tokenizer.json','vocabulary.txt'],
              STATUS.stt?.missing || []);
  renderFiles('tts',        STATUS.tts?.required || ['model.onnx','model.onnx.json'],
              STATUS.tts?.missing || []);
  renderFiles('embeddings', ['config.json','tokenizer.json','tokenizer_config.json',
                              'vocab.txt','model.safetensors'],
              STATUS.embeddings?.missing || []);
  renderFiles('sysfiles',   STATUS.sysfiles?.required || [],
              STATUS.sysfiles?.missing || []);

  const llmList = document.getElementById('files-llm');
  llmList.innerHTML = '';
  if (STATUS.llm?.models?.length) {
    STATUS.llm.models.forEach(m => {
      const p = document.createElement('span');
      p.className = 'file-pill file-ok';
      p.textContent = m;
      llmList.appendChild(p);
    });
  }

  const dotMap = {
    'sum-ollama': STATUS.ollama,
    'sum-llm':    STATUS.llm,
    'sum-stt':    STATUS.stt,
    'sum-tts':    STATUS.tts,
    'sum-emb':    STATUS.embeddings,
    'sum-sysfiles': STATUS.sysfiles,
    'sum-mpv':    STATUS.mpv,
  };
  Object.entries(dotMap).forEach(([id, s]) => {
    document.getElementById(id).style.background =
      s.ok ? 'var(--green)' : (s.optional ? 'var(--yellow)' : 'var(--red)');
  });

  const allOk = REQUIRED.every(k => STATUS[k]?.ok);
  const btn = document.getElementById('btn-launch');
  btn.disabled = !allOk;
  document.getElementById('footer-info').textContent = allOk
    ? '✔ All required components are ready — you\'re good to go!'
    : `Missing: ${REQUIRED.filter(k=>!STATUS[k]?.ok).join(', ')}`;
}

function renderComp(id, s, optional) {
  if (!s) return;
  const card   = document.getElementById(`card-${id}`);
  const dot    = document.getElementById(`dot-${id}`);
  const detail = document.getElementById(`detail-${id}`);

  dot.className    = 'status-dot ' + (s.ok ? 'dot-ok' : (optional ? 'dot-warn' : 'dot-error'));
  detail.textContent = s.detail || '';
  card.className   = 'comp-card' + (s.ok ? ' ok' : (optional ? ' warn' : ' error'))
                     + (optional ? ' optional' : '');

  const iconDl = document.getElementById(`icon-dl-${id}`);
  const btnDl = document.getElementById(`btn-dl-${id}`);
  
  if (s.ok) {
    if (iconDl) iconDl.style.display = 'none';
    if (btnDl) btnDl.style.display = 'none';
  } else {
    const progWrap = document.getElementById(`prog-${id}`);
    const isDownloading = progWrap && progWrap.classList.contains('show');
    if (!isDownloading) {
      if (iconDl) iconDl.style.display = '';
      if (btnDl) {
        if (id === 'mpv' && STATUS.os && STATUS.os.name !== 'Windows') {
          btnDl.style.display = 'none';
        } else {
          btnDl.style.display = (id === 'mpv' ? 'inline-flex' : '');
        }
      }
    }
  }
}

function renderFiles(id, required, missing) {
  const el = document.getElementById(`files-${id}`);
  if (!el) return;
  el.innerHTML = '';
  required.forEach(f => {
    const p = document.createElement('span');
    p.className = 'file-pill ' + (missing.includes(f) ? 'file-miss' : 'file-ok');
    p.textContent = f;
    el.appendChild(p);
  });
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                      ACCORDION                               ║
// ╚══════════════════════════════════════════════════════════════╝
function toggle(id) {
  const body  = document.getElementById(`body-${id}`);
  const top   = document.querySelector(`#card-${id} .card-top`);
  const chev  = document.getElementById(`chev-${id}`);
  const open  = body.classList.toggle('open');
  top.classList.toggle('expanded', open);
}

// ║                      DOWNLOADS                               ║
async function doDownload(comp) {
  showProg(comp, true);
  const resStr = await pywebview.api.start_download(comp);
  const res = JSON.parse(resStr);
  if (!res.ok) {
      showProg(comp, false);
      if (res.reason === "Already Existed") {
          toast('Already Existed', 'warn');
      } else if (res.reason !== "Already downloading") {
          toast(res.reason || 'Failed to start', 'err');
      }
  }
}

async function doCancel(comp) {
  const resStr = await pywebview.api.cancel_task(comp);
  const res = JSON.parse(resStr);
  if (res.ok) {
      showProg(comp, false);
      toast(`Cancelled ${comp}`, 'warn');
  }
}

function showProg(comp, show) {
  const uiComp = comp === 'jarvis_voice' ? 'tts' : comp;
  const btnComp = uiComp;
  
  const el = document.getElementById(`prog-${uiComp}`);
  if (el) el.classList.toggle('show', show);
  
  const iconDl = document.getElementById(`icon-dl-${btnComp}`);
  const btnDl = document.getElementById(`btn-dl-${btnComp}`);
  const iconCancel = document.getElementById(`icon-cancel-${btnComp}`);
  const btnCancel = document.getElementById(`btn-cancel-${btnComp}`);
  
  if (show) {
    if (iconDl) iconDl.style.display = 'none';
    if (btnDl) btnDl.style.display = 'none';
    if (iconCancel) iconCancel.style.display = '';
    if (btnCancel) btnCancel.style.display = '';
  } else {
    if (iconCancel) iconCancel.style.display = 'none';
    if (btnCancel) btnCancel.style.display = 'none';
    const isOk = STATUS[uiComp] && STATUS[uiComp].ok;
    if (!isOk) {
      if (iconDl) iconDl.style.display = '';
      if (btnDl) btnDl.style.display = (btnComp === 'mpv' && STATUS.os && STATUS.os.name !== 'Windows') ? 'none' : '';
    }
  }
}

// Called from Python via evaluate_js
function onProgress(comp, pct, speed, label) {
  const bar   = document.getElementById(`bar-${comp}`);
  const pctEl = document.getElementById(`prog-${comp}-pct`);
  const spdEl = document.getElementById(`prog-${comp}-speed`);
  const lblEl = document.getElementById(`lbl-${comp}`);
  if (bar)   bar.style.width   = pct + '%';
  if (pctEl) pctEl.textContent = pct + '%';
  if (spdEl) spdEl.textContent = speed;
  if (lblEl) lblEl.textContent = label;

  const dot = document.getElementById(`dot-${comp}`);
  if (dot) dot.className = 'status-dot dot-spin';
}

async function onDone(comp) {
  showProg(comp, false);
  toast(`\u2714 ${comp.toUpperCase()} ready!`, 'ok');
  await recheck();
}

function onError(comp, msg) {
  showProg(comp, false);
  toast(`\u2716 ${comp}: ${msg}`, 'err');
  const dot = document.getElementById(`dot-${comp}`);
  if (dot) dot.className = 'status-dot dot-error';
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                       LAUNCH                                 ║
// ╚══════════════════════════════════════════════════════════════╝
async function launchJarvis() {
  await pywebview.api.mark_setup_complete();
  await pywebview.api.launch_jarvis();
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                        TOAST                                 ║
// ╚══════════════════════════════════════════════════════════════╝
let _tt;
function toast(msg, type='ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(_tt);
  _tt = setTimeout(() => el.className = '', 3500);
}
</script>
</body>
</html>
"""


# ╔══════════════════════════════════════════════════════════════╗
# ║                  TRIGGER LOGIC (Entry Points)                ║
# ╚══════════════════════════════════════════════════════════════╝
def should_show_wizard() -> bool:
    """
    Returns True if the wizard should open.
    Conditions (any one is enough):
      - setup_complete flag is missing/False in config DB
      - LLM folder is empty
      - STT folder is missing required files
      - TTS folder is missing required files
      - System files missing
    """
    if not config.get("setup_complete", False):
        return True

    checks = run_all_checks()
    critical = ["llm", "stt", "tts", "sysfiles", "mpv"]
    if any(not checks[k]["ok"] for k in critical):
        return True

    return False


def launch_wizard(block=True):
    """Open the setup wizard window."""
    from core.bootstrap.utils import enforce_single_instance
    if not enforce_single_instance("JARVIS_Wizard_Mutex", "JARVIS NEXUS — Setup Wizard"):
        print("Setup Wizard is already open.")
        return

    import os
    os.environ.setdefault(
        'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS',
        '--disable-background-networking --disable-component-update --disable-domain-reliability'
    )

    api = WizardAPI()

    from core.config import APP_VERSION
    html_content = HTML.replace('v__APP_VERSION__', f'v{APP_VERSION}')

    window = webview.create_window(
        title            = "JARVIS NEXUS · Setup Wizard",
        html             = html_content,
        js_api           = api,
        width            = 1150, 
        height           = 850,
        min_size         = (1000, 750),
        resizable        = True,
        background_color = "#0a0e14",
    )
    api.set_window(window)
    webview.start(debug=False, icon=TRAY_ICON_PATH)


_WIZARD_LOCK = threading.Lock()

def safe_run_wizard():
    """
    Thread-safe way to launch the wizard from anywhere if components are missing.
    Blocks until the user clicks 'Launch JARVIS'.
    Only one window will be shown even if multiple threads hit this at the same time.
    """
    with _WIZARD_LOCK:
        if not is_setup_complete():
            print("\n🚀 [Bootstrap] Component missing! Launching Setup Wizard...")
            launch_wizard()

def check_and_run_wizard():
    """
    Call this at the very start of app.py / main.py.
    Blocks until the wizard is closed if setup is incomplete.
    Returns True if JARVIS should continue launching normally.
    """
    if should_show_wizard():
        safe_run_wizard()
        return is_setup_complete()
    return True


if __name__ == "__main__":
    launch_wizard()