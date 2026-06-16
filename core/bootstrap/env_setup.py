# core/bootstrap/env_setup.py  #? (Hmody: 5% me, 95% AI in the UI files fells like: https://share.google/016aSjT68zvqT55Sq)
"""
JARVIS NEXUS — First-Run Setup Wizard
======================================
Checks all required components and guides the user to install missing ones.
Triggered automatically when critical components are missing.
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
    """Check optional embeddings model via Ollama."""
    model = config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
    import tempfile
    try:
        flags = subprocess.CREATE_NO_WINDOW if OS == "Windows" else 0
        # CRITICAL FIX: Do NOT use capture_output=True or stdout=subprocess.PIPE.
        # 'ollama list' might start the ollama daemon in the background. The daemon
        # inherits the pipe, causing subprocess.run to hang forever waiting for EOF.
        # Using a TemporaryFile completely bypasses the pipe freeze.
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as temp_out:
            subprocess.run(
                ["ollama", "list"], 
                stdout=temp_out, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                timeout=5, creationflags=flags
            )
            temp_out.seek(0)
            output = temp_out.read()
            if model in output:
                return {"ok": True,  "detail": f"Active in Ollama: {model}", "optional": True}
    except Exception:
        pass
    return {"ok": False, "detail": f"Missing {model} in Ollama", "missing": [], "optional": True}

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
                        tmp.unlink(missing_ok=True)
                        return False
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

            tmp.rename(dest)
            return True

        except Exception as e:
            tmp.unlink(missing_ok=True)
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
        def _pull_ollama_model():
            try:
                model = config.get("embedding_model", DEFAULT_EMBEDDING_MODEL)
                # Fake progress to show it's doing something
                self._progress(50, "Pulling via Ollama...", "Embeddings")
                subprocess.run(["ollama", "pull", model], check=True)
                self._done("embeddings")
            except Exception as e:
                self._error("embeddings", str(e))
                
        self._thread = threading.Thread(target=_pull_ollama_model, daemon=True)
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
        self._dl: Downloader | None = None
        self._window = None          # set after window creation

    def set_window(self, w):
        self._window = w

    def _js(self, js_code: str):
        if self._window:
            self._window.evaluate_js(js_code)

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

        if self._dl:
            self._dl.cancel()

        def on_progress(pct, speed, label):
            safe_label = label.replace("'", "\\'")
            self._js(f"onProgress('{component}',{pct},'{speed}','{safe_label}')")

        def on_done(comp):
            self._js(f"onDone('{comp}')")

        def on_error(comp, msg):
            safe_msg = msg.replace("'", "\\'")[:120]
            self._js(f"onError('{comp}','{safe_msg}')")

        self._dl = Downloader(on_progress, on_done, on_error)

        actions = {
            "ollama":     self._dl.download_ollama,
            "llm":        self._dl.download_llm,
            "stt":        self._dl.download_stt,
            "tts":        self._dl.download_tts,
            "jarvis_voice": self._dl.download_jarvis_voice,
            "embeddings": self._dl.download_embeddings,
            "sysfiles":   self._dl.download_sysfiles,
            "mpv":        self._dl.download_mpv,
        }
        fn = actions.get(component)
        if fn:
            fn()
        return json.dumps({"ok": bool(fn)})

    def cancel_download(self):
        if self._dl:
            self._dl.cancel()
        return json.dumps({"ok": True})

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
# ║                          HTML / UI                           ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<title>JARVIS · Setup</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--card:#1c2128;--input:#21262d;
  --border:#30363d;--accent:#58a6ff;--accent-h:#388bfd;
  --green:#3fb950;--red:#f85149;--yellow:#d29922;--purple:#bc8cff;
  --txt:#e6edf3;--sub:#8b949e;--mute:#484f58;
  --r:10px;--rs:6px;--t:.18s ease;
}
html,body{
  height:100%;font-family:"Segoe UI",system-ui,sans-serif;
  background:var(--bg);color:var(--txt);font-size:14px;overflow:hidden;
}

/* ── Layout ─────────────────────────────────────────────── */
#app{display:flex;flex-direction:column;height:100vh}

/* header */
#header{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:18px 32px;display:flex;align-items:center;gap:16px;flex-shrink:0;
}
.logo-icon{font-size:32px;line-height:1}
.logo-text .title{font-size:20px;font-weight:700;letter-spacing:.3px}
.logo-text .title span{color:var(--accent)}
.logo-text .sub{font-size:12px;color:var(--sub);margin-top:3px}
.os-badge{
  margin-left:auto;background:var(--input);border:1px solid var(--border);
  border-radius:20px;padding:5px 14px;font-size:12px;color:var(--sub);
}

/* body */
#body{flex:1;overflow-y:auto;padding:28px 32px;display:flex;flex-direction:column;gap:16px}
#body::-webkit-scrollbar{width:6px}
#body::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* footer */
#footer{
  background:var(--surface);border-top:1px solid var(--border);
  padding:14px 32px;display:flex;align-items:center;gap:12px;flex-shrink:0;
}
#footer .info{flex:1;font-size:12px;color:var(--sub)}

/* ── Component Card ─────────────────────────────────────── */
.comp-card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);overflow:hidden;
  transition:border-color var(--t);
  flex-shrink: 0; /* MODIFIED: Prevents squishing when others expand */
}
.comp-card.ok{border-color:#238636}
.comp-card.warn{border-color:#9e6a03}
.comp-card.error{border-color:#da3633}
.comp-card.optional{opacity:.85}

.card-top{
  display:flex;align-items:center;gap:14px;padding:16px 20px;cursor:pointer;
  user-select:none;
}
.card-top:hover{background:#ffffff08}

.status-dot{
  width:10px;height:10px;border-radius:50%;flex-shrink:0;
  transition:background var(--t);
}
.dot-ok    {background:var(--green)}
.dot-error {background:var(--red);box-shadow:0 0 8px var(--red)44}
.dot-warn  {background:var(--yellow)}
.dot-spin  {
  background:transparent;border:2px solid var(--accent);
  border-top-color:transparent;
  animation:spin .7s linear infinite;
}
@keyframes spin{to{transform:rotate(360deg)}}

.comp-icon{font-size:22px;width:30px;text-align:center;flex-shrink:0}
.comp-info{flex:1;min-width:0}
.comp-name{font-size:15px;font-weight:600;color:var(--txt)}
.comp-detail{font-size:13px;color:var(--sub);margin-top:4px;
             line-height:1.4}

/* NEW: Quick Actions Container */
.quick-actions {
  display: flex; gap: 8px; align-items: center; margin-right: 12px;
}
.btn-icon {
  padding: 5px 10px; font-size: 11px; border-radius: 4px;
}

.opt-tag{
  font-size:10px;padding:2px 8px;border-radius:10px;
  background:#21262d;color:var(--sub);border:1px solid var(--border);
  flex-shrink:0;
}
.chevron{color:var(--mute);font-size:12px;transition:transform var(--t)}
.card-top.expanded .chevron{transform:rotate(180deg)}

/* expanded body */
.card-body{
  display:none;padding:0 20px 16px;border-top:1px solid var(--border);
}
.card-body.open{display:block}

.desc{
  font-size:12px;color:var(--sub);line-height:1.6;
  padding:12px 0 14px;
}
.desc strong{color:var(--txt)}
.desc code{
  background:var(--input);padding:1px 6px;border-radius:4px;
  font-family:monospace;font-size:11px;color:var(--accent);
}

/* file list */
.file-list{
  display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px;
}
.file-pill{
  font-size:11px;padding:3px 10px;border-radius:20px;
  font-family:monospace;
}
.file-ok   {background:#1b2d1b;color:var(--green);border:1px solid #238636}
.file-miss {background:#2d1b1b;color:var(--red);border:1px solid #da3633}

/* action row */
.action-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}

/* ── Progress bar ────────────────────────────────────────── */
.progress-wrap{
  margin-top:12px;display:none;
}
.progress-wrap.show{display:block}
.progress-top{display:flex;justify-content:space-between;
              font-size:11px;color:var(--sub);margin-bottom:6px}
.progress-bar-bg{
  height:6px;background:var(--input);border-radius:3px;overflow:hidden;
}
.progress-bar{
  height:100%;background:var(--accent);border-radius:3px;
  width:0%;transition:width .3s;
}
.progress-label{font-size:11px;color:var(--sub);margin-top:5px;
                white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

/* ── Buttons ─────────────────────────────────────────────── */
button{
  display:inline-flex;align-items:center;gap:6px;
  padding:8px 16px;border-radius:var(--rs);border:none;
  font-size:12px;font-weight:600;cursor:pointer;
  font-family:inherit;transition:all var(--t);
}
button:active{transform:scale(.97)}
button:disabled{opacity:.4;cursor:not-allowed}
.btn-primary{background:var(--accent);color:#000}
.btn-primary:hover:not(:disabled){background:var(--accent-h)}
.btn-ghost{background:var(--input);color:var(--txt);border:1px solid var(--border)}
.btn-ghost:hover:not(:disabled){background:#30363d}
.btn-success{background:#238636;color:#fff}
.btn-success:hover:not(:disabled){background:#2ea043}
.btn-danger{background:#2d1b1b;color:var(--red);border:1px solid #da3633}
.btn-danger:hover:not(:disabled){background:#3d2020}
.btn-warn{background:#2a2010;color:var(--yellow);border:1px solid #9e6a03}
.btn-warn:hover:not(:disabled){background:#3a3010}
.btn-launch{
  background:linear-gradient(135deg,#238636,#2ea043);
  color:#fff;padding:11px 28px;font-size:14px;
  box-shadow:0 0 20px #23863644;
}
.btn-launch:hover:not(:disabled){
  box-shadow:0 0 30px #23863666;transform:translateY(-1px)
}
.btn-launch:disabled{
  background:var(--input);color:var(--mute);box-shadow:none;
}

/* ── Summary bar ─────────────────────────────────────────── */
#summary{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);padding:14px 20px;
  display:flex;align-items:center;gap:16px;
  flex-shrink: 0;
}
#summary .s-item{display:flex;align-items:center;gap:6px;font-size:12px}
#summary .s-dot{width:8px;height:8px;border-radius:50%}

/* ── Toast ───────────────────────────────────────────────── */
#toast{
  position:fixed;bottom:80px;right:24px;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:10px 18px;font-size:12px;
  box-shadow:0 8px 32px #0008;
  transform:translateY(10px);opacity:0;
  transition:all .22s;pointer-events:none;z-index:999;
}
#toast.show{transform:translateY(0);opacity:1}
#toast.ok{border-color:var(--green);color:var(--green)}
#toast.err{border-color:var(--red);color:var(--red)}
#toast.warn {border-color:var(--yellow);color:var(--yellow)}
</style>
</head>
<body>
<div id="app">

<div id="header">
  <div class="logo-icon">🤖</div>
  <div class="logo-text">
    <div class="title">JARVIS <span>NEXUS</span> — Setup Wizard</div>
    <div class="sub">Check and install all required components before first launch</div>
  </div>
  <div class="os-badge" id="os-badge">Detecting OS…</div>
  <div class="os-badge" id="vram-badge" style="display:none; margin-left:8px; font-weight: bold;"></div>
</div>

<div id="body">

  <div id="summary">
    <span style="font-size:12px;color:var(--sub);font-weight:600">STATUS:</span>
    <div class="s-item"><div class="s-dot" id="sum-ollama" style="background:var(--mute)"></div><span>Ollama</span></div>
    <div class="s-item"><div class="s-dot" id="sum-llm"    style="background:var(--mute)"></div><span>LLM</span></div>
    <div class="s-item"><div class="s-dot" id="sum-stt"    style="background:var(--mute)"></div><span>STT</span></div>
    <div class="s-item"><div class="s-dot" id="sum-tts"    style="background:var(--mute)"></div><span>TTS</span></div>
    <div class="s-item"><div class="s-dot" id="sum-emb"    style="background:var(--mute)"></div><span style="color:var(--sub)">Embeddings (opt)</span></div>
    <div class="s-item"><div class="s-dot" id="sum-sysfiles" style="background:var(--mute)"></div><span>SysFiles</span></div>
    <div class="s-item"><div class="s-dot" id="sum-mpv" style="background:var(--mute)"></div><span>MPV</span></div>
    <button class="btn-ghost" style="margin-left:auto;padding:5px 12px;font-size:11px"
            onclick="recheck()">🔄 Re-check</button>
  </div>

  <div class="comp-card" id="card-ollama">
    <div class="card-top" onclick="toggle('ollama')">
      <div class="status-dot" id="dot-ollama"></div>
      <div class="comp-icon">🦙</div>
      <div class="comp-info">
        <div class="comp-name">Ollama</div>
        <div class="comp-detail" id="detail-ollama">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="doDownload('ollama')" title="Download">⬇️</button>
      </div>
      <span class="chevron" id="chev-ollama">▼</span>
    </div>
    <div class="card-body" id="body-ollama">
      <div class="desc">
        <strong>Ollama</strong> is the local model runtime that powers JARVIS's brain.
        It manages downloading, loading, and serving LLM models on your machine.<br><br>
        Detected OS: <code id="os-label">—</code>
      </div>
      <div class="action-row">
        <button class="btn-primary" onclick="doDownload('ollama')">
          ⬇ Download Ollama Installer
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://ollama.com')">
          🌐 ollama.com
        </button>
      </div>
      <div class="progress-wrap" id="prog-ollama">
        <div class="progress-top">
          <span id="prog-ollama-speed">—</span>
          <span id="prog-ollama-pct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar" id="bar-ollama"></div>
        </div>
        <div class="progress-label" id="lbl-ollama"></div>
      </div>
    </div>
  </div>

  <div class="comp-card" id="card-llm">
    <div class="card-top" onclick="toggle('llm')">
      <div class="status-dot" id="dot-llm"></div>
      <div class="comp-icon">🧠</div>
      <div class="comp-info">
        <div class="comp-name">LLM Model</div>
        <div class="comp-detail" id="detail-llm">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="doDownload('llm')" title="Download Default">⬇️</button>
        <button class="btn-ghost btn-icon" onclick="pywebview.api.open_folder('llm')" title="Open Folder">📂</button>
      </div>
      <span class="chevron" id="chev-llm">▼</span>
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
          ⬇ Download Qwen3-4B (Recommended)
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('llm')">
          📂 Open LLM Folder
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://huggingface.co/Qwen/Qwen3-4B-Instruct-GGUF')">
          🤗 HuggingFace Repo
        </button>
      </div>
      <div class="progress-wrap" id="prog-llm">
        <div class="progress-top">
          <span id="prog-llm-speed">—</span>
          <span id="prog-llm-pct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar" id="bar-llm"></div>
        </div>
        <div class="progress-label" id="lbl-llm"></div>
      </div>
    </div>
  </div>

  <div class="comp-card" id="card-stt">
    <div class="card-top" onclick="toggle('stt')">
      <div class="status-dot" id="dot-stt"></div>
      <div class="comp-icon">🎙️</div>
      <div class="comp-info">
        <div class="comp-name">Speech-to-Text Model</div>
        <div class="comp-detail" id="detail-stt">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="doDownload('stt')" title="Download Default">⬇️</button>
        <button class="btn-ghost btn-icon" onclick="pywebview.api.open_folder('stt')" title="Open Folder">📂</button>
      </div>
      <span class="chevron" id="chev-stt">▼</span>
    </div>
    <div class="card-body" id="body-stt">
      <div class="desc">
        <strong>faster-whisper-small.en</strong> — JARVIS's ears.
        Converts your voice to text locally with low latency.
        Required files:
      </div>
      <div class="file-list" id="files-stt"></div>
      <div class="action-row">
        <button class="btn-primary" onclick="doDownload('stt')">
          ⬇ Download STT Model
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('stt')">
          📂 Open STT Folder
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://huggingface.co/guillaumekln/faster-whisper-small.en')">
          🤗 HuggingFace Repo
        </button>
      </div>
      <div class="progress-wrap" id="prog-stt">
        <div class="progress-top">
          <span id="prog-stt-speed">—</span>
          <span id="prog-stt-pct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar" id="bar-stt"></div>
        </div>
        <div class="progress-label" id="lbl-stt"></div>
      </div>
    </div>
  </div>

  <div class="comp-card" id="card-tts">
    <div class="card-top" onclick="toggle('tts')">
      <div class="status-dot" id="dot-tts"></div>
      <div class="comp-icon">🔊</div>
      <div class="comp-info">
        <div class="comp-name">TTS Voice Files</div>
        <div class="comp-detail" id="detail-tts">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="pywebview.api.open_url('https://huggingface.co/rhasspy/piper-voices/tree/main/en')" title="Browse HF Voices">🌐</button>
        <button class="btn-ghost btn-icon" onclick="pywebview.api.open_folder('tts')" title="Open Folder">📂</button>
      </div>
      <span class="chevron" id="chev-tts">▼</span>
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
        <button class="btn-primary" onclick="doDownload('jarvis_voice')" id="btn-dl-jarvis-voice">
          ⬇ Download Original Jarvis Voice
        </button>
        <button class="btn-warn"
                onclick="pywebview.api.open_url('https://huggingface.co/rhasspy/piper-voices/tree/main/en')">
          🤗 Browse Piper Voices (English)
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('tts')">
          📂 Open TTS Folder
        </button>
        <div style="font-size:11px;color:var(--sub);max-width:320px;line-height:1.5">
          Download the <code>.onnx</code> + <code>.onnx.json</code> files and place them
          in <code>assets/tts/jarvis_en_GB_high/</code> — then re-check.
        </div>
      </div>
    </div>
  </div>

  <div class="comp-card optional" id="card-embeddings">
    <div class="card-top" onclick="toggle('embeddings')">
      <div class="status-dot" id="dot-embeddings"></div>
      <div class="comp-icon">🔗</div>
      <div class="comp-info">
        <div class="comp-name">Embeddings Model (Ollama)</div>
        <div class="comp-detail" id="detail-embeddings">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="doDownload('embeddings')" title="Pull Model via Ollama">⬇️</button>
      </div>
      <span class="opt-tag">Optional</span>
      <span class="chevron" id="chev-embeddings">▼</span>
    </div>
    <div class="card-body" id="body-embeddings">
      <div class="desc">
        <strong>nomic-embed-text</strong> — Used for semantic memory search.
        Enables JARVIS to find relevant memories by meaning, not just keywords.
        <strong>Not required for basic operation</strong> — skip if you just want to get started.<br><br>
        <em>Note: This model is pulled and managed securely inside Ollama. No local folders are needed.</em>
      </div>
      <div class="action-row">
        <button class="btn-ghost" onclick="doDownload('embeddings')">
          ⬇ Pull Model via Ollama
        </button>
        <button class="btn-ghost"
                onclick="pywebview.api.open_url('https://ollama.com/library/nomic-embed-text')">
          🌐 Ollama Library
        </button>
      </div>
      <div class="progress-wrap" id="prog-embeddings">
        <div class="progress-top">
          <span id="prog-embeddings-speed">—</span>
          <span id="prog-embeddings-pct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar" id="bar-embeddings"></div>
        </div>
        <div class="progress-label" id="lbl-embeddings"></div>
      </div>
    </div>
  </div>

  <div class="comp-card" id="card-sysfiles">
    <div class="card-top" onclick="toggle('sysfiles')">
      <div class="status-dot" id="dot-sysfiles"></div>
      <div class="comp-icon">🎞️</div>
      <div class="comp-info">
        <div class="comp-name">System Files</div>
        <div class="comp-detail" id="detail-sysfiles">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="doDownload('sysfiles')" title="Download Missing">⬇️</button>
      </div>
      <span class="chevron" id="chev-sysfiles">▼</span>
    </div>
    <div class="card-body" id="body-sysfiles">
      <div class="desc">
        <strong>Assets</strong> — Video and sound effects required for the system interface.
      </div>
      <div class="file-list" id="files-sysfiles"></div>
      <div class="action-row">
        <button class="btn-primary" onclick="doDownload('sysfiles')">
          ⬇ Download Missing Assets
        </button>
      </div>
      <div class="progress-wrap" id="prog-sysfiles">
        <div class="progress-top">
          <span id="prog-sysfiles-speed">—</span>
          <span id="prog-sysfiles-pct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar" id="bar-sysfiles"></div>
        </div>
        <div class="progress-label" id="lbl-sysfiles"></div>
      </div>
    </div>
  </div>

  <div class="comp-card" id="card-mpv">
    <div class="card-top" onclick="toggle('mpv')">
      <div class="status-dot" id="dot-mpv"></div>
      <div class="comp-icon">🎞️</div>
      <div class="comp-info">
        <div class="comp-name">MPV Player</div>
        <div class="comp-detail" id="detail-mpv">Checking…</div>
      </div>
      <div class="quick-actions" onclick="event.stopPropagation()">
        <button class="btn-ghost btn-icon" onclick="pywebview.api.open_folder('bin')" title="Open Folder">📂</button>
      </div>
      <span class="chevron" id="chev-mpv">▼</span>
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
          ⬇ Download & Install MPV
        </button>
        <button class="btn-primary" id="btn-info-mpv" onclick="pywebview.api.open_url('https://mpv.io/installation/')" style="display:none">
          🌐 Instructions for Linux
        </button>
        <button class="btn-ghost" onclick="pywebview.api.open_folder('bin')">
          📂 Open bin Folder
        </button>
      </div>
      <div class="progress-wrap" id="prog-mpv">
        <div class="progress-top">
          <span id="prog-mpv-speed">—</span>
          <span id="prog-mpv-pct">0%</span>
        </div>
        <div class="progress-bar-bg">
          <div class="progress-bar" id="bar-mpv"></div>
        </div>
        <div class="progress-label" id="lbl-mpv"></div>
      </div>
    </div>
  </div>

</div><div id="footer">
  <div class="info" id="footer-info">Checking components…</div>
  <button class="btn-ghost" onclick="openSettings()">⚙️ Settings</button>
  <button class="btn-ghost" onclick="recheck()">🔄 Re-check All</button>
  <button class="btn-launch" id="btn-launch" disabled onclick="launchJarvis()">
    🚀 Launch JARVIS
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
  document.getElementById('footer-info').textContent = 'Re-checking…';
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
  // OS badge
  const os = STATUS.os;
  document.getElementById('os-badge').textContent = `${os.name} detected`;
  document.getElementById('os-label').textContent = os.name;

  // VRAM Badge
  const vramBadge = document.getElementById('vram-badge');
  if (STATUS.vram_gb !== null && STATUS.vram_gb !== undefined) {
      vramBadge.style.display = 'block';
      if (STATUS.vram_gb < 4) {
          vramBadge.style.color = 'var(--red)';
          vramBadge.style.borderColor = 'var(--red)';
          vramBadge.textContent = `⚠️ VRAM: ${STATUS.vram_gb} GB (Min 4GB required for smooth operation)`;
      } else {
          vramBadge.style.color = 'var(--sub)';
          vramBadge.style.borderColor = 'var(--border)';
          vramBadge.textContent = `VRAM: ${STATUS.vram_gb} GB`;
      }
  } else {
      vramBadge.style.display = 'none';
  }

  // each component
  renderComp('ollama',     STATUS.ollama,     false);
  renderComp('llm',        STATUS.llm,        false);
  renderComp('stt',        STATUS.stt,        false);
  renderComp('tts',        STATUS.tts,        false);
  renderComp('embeddings', STATUS.embeddings, true);
  renderComp('sysfiles',   STATUS.sysfiles,   false);
  renderComp('mpv',        STATUS.mpv,        false);

  if (STATUS.os.name === 'Windows') {
    document.getElementById('mpv-desc-win').style.display = 'inline';
    document.getElementById('btn-dl-mpv').style.display = 'inline-flex';
  } else {
    document.getElementById('mpv-desc-lin').style.display = 'inline';
    document.getElementById('btn-info-mpv').style.display = 'inline-flex';
  }

  // file pills
  renderFiles('stt',        ['config.json','model.bin','tokenizer.json','vocabulary.txt'],
              STATUS.stt?.missing || []);
  renderFiles('tts',        STATUS.tts?.required || ['model.onnx','model.onnx.json'],
              STATUS.tts?.missing || []);
  renderFiles('embeddings', ['config.json','tokenizer.json','tokenizer_config.json',
                              'vocab.txt','model.safetensors'],
              STATUS.embeddings?.missing || []);
  renderFiles('sysfiles',   STATUS.sysfiles?.required || [],
              STATUS.sysfiles?.missing || []);

  // LLM file pills (found models)
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

  // summary dots
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

  // launch button
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
// ╚══════════════════════════════════════════════════════════════╝
async function doDownload(comp) {
  // If it's the custom voice, map it to update the TTS progress UI
  const uiComp = comp === 'jarvis_voice' ? 'tts' : comp;
  showProg(uiComp, true);
  
  const resStr = await pywebview.api.start_download(comp);
  const res = JSON.parse(resStr);
  
  if (!res.ok && res.reason === "Already Existed") {
      showProg(uiComp, false);
      toast('Already Existed', 'warn');
  }
}

function showProg(comp, show) {
  const el = document.getElementById(`prog-${comp}`);
  if (el) el.classList.toggle('show', show);
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

  // Spin the dot while downloading
  const dot = document.getElementById(`dot-${comp}`);
  if (dot) dot.className = 'status-dot dot-spin';
}

async function onDone(comp) {
  showProg(comp, false);
  toast(`✔ ${comp.toUpperCase()} ready!`, 'ok');
  await recheck();
}

function onError(comp, msg) {
  showProg(comp, false);
  toast(`✕ ${comp}: ${msg}`, 'err');
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
    # 1. Explicit flag
    if not config.get("setup_complete", False):
        return True

    # 2. Critical component check
    checks = run_all_checks()
    critical = ["llm", "stt", "tts", "sysfiles", "mpv"]
    if any(not checks[k]["ok"] for k in critical):
        return True

    return False


def launch_wizard(block=True):
    """Open the setup wizard window."""
    # ─── Single Instance Enforcement (Wizard) ───
    from core.bootstrap.utils import enforce_single_instance
    if not enforce_single_instance("JARVIS_Wizard_Mutex", "JARVIS NEXUS — Setup Wizard"):
        print("Setup Wizard is already open.")
        return

    api = WizardAPI()

    # MODIFIED: Increased default width & height to prevent overlapping elements
    window = webview.create_window(
        title            = "JARVIS NEXUS — Setup Wizard",
        html             = HTML,
        js_api           = api,
        width            = 1150, 
        height           = 850,
        min_size         = (1000, 750),
        resizable        = True,
        background_color = "#0d1117",
    )
    api.set_window(window)
    webview.start(debug=False)


# ── Convenience: call this from your main app entry point ─────
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