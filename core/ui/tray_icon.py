# core/ui/tray_icon.py #? (Hmody: last thing i want to see is someone mocking me coz he couldn't summon panel via STT)
"""
System Tray Icon (Headless Gateway)
===================================
Provides a lightweight, persistent System Tray interface for JARVIS.
This module acts as the primary user gateway in headless mode, offering:
  - Real-time dynamic state polling (via Hover Tooltip)
  - JARVIS NEXUS Website access (Default Action)
  - Settings Panel and Environment Setup Wizard integration
  - Emergency Immediate Exit
"""

import pystray
from PIL import Image, ImageDraw
import threading
import sys
import os
import subprocess
import time
import webbrowser

from core.config import get_setting
_JARVIS_VERSION = get_setting('app_version', '1.0')

def create_tray_icon(jarvis_engine):
    """
    Creates and runs the System Tray icon for JARVIS.
    """
    # 1. State string generator
    def get_state_text():
        if not jarvis_engine.initialization_complete:
            phase = getattr(jarvis_engine, '_build_phase', '')
            if phase == 'building_model':
                return "🔨 JARVIS: Building Model..."
            elif phase == 'warming_cache':
                return "🔥 JARVIS: Warming Cache..."
            return "🚀 JARVIS: Starting up..."

        state = jarvis_engine.state.interrupt_state
        followup_window = get_setting('followup_window', 10)

        if state == "follow_up":
            elapsed = time.time() - getattr(jarvis_engine, 'last_speech_time', 0)
            if elapsed > followup_window:
                return "💤 JARVIS: Idle"
            return "👂 JARVIS: Listening (Follow-up)..."
        elif state == "processing":
            return "🧠 JARVIS: Thinking..."
        elif state == "speaking":
            return "🗣️ JARVIS: Speaking..."
        elif getattr(jarvis_engine.state, 'always_listening', False):
            return "👂 JARVIS: Always Listening..."
        elif getattr(jarvis_engine.ears, 'is_listening', False):
            return "👂 JARVIS: Listening..."
        return "💤 JARVIS: Idle"

    def update_tooltip(icon):
        """Continuously update the tooltip to reflect JARVIS's current state."""
        icon.visible = True
        # jarvis_engine.running is False during the 17s startup sequence.
        # We must use 'while True' so the thread doesn't exit immediately!
        while True:
            try:
                new_text = get_state_text()
                if icon.title != new_text:
                    icon.title = new_text
            except Exception:
                pass
            time.sleep(0.5)

    def on_open_website(icon, item):
        try:
            webbrowser.open("https://vanthq.net/jarvis")
        except Exception as e:
            pass

    def on_open_settings(icon, item):
        print("\n⚙️ [Tray] Opening Settings Panel...")
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--settings"])
            elif "__compiled__" in globals():
                subprocess.Popen([sys.argv[0], "--settings"])
            else:
                settings_script = os.path.join(os.path.dirname(__file__), "settings_panel.py")
                subprocess.Popen([sys.executable, settings_script])
        except Exception as e:
            print(f"Tray error opening settings: {e}")

    def on_open_setup(icon, item):
        print("\n🛠️ [Tray] Opening Environment Setup Wizard...")
        try:
            if getattr(sys, 'frozen', False):
                subprocess.Popen([sys.executable, "--setup"])
            elif "__compiled__" in globals():
                subprocess.Popen([sys.argv[0], "--setup"])
            else:
                setup_script = os.path.join(os.path.dirname(__file__), "..", "bootstrap", "env_setup.py")
                subprocess.Popen([sys.executable, setup_script])
        except Exception as e:
            print(f"Tray error opening setup: {e}")

    def on_exit(icon, item):
        print("\n🛑 [Tray] Immediate Exit triggered...")
        icon.stop()
        if jarvis_engine:
            jarvis_engine.running = False
            # Attempt to unload Ollama models immediately before exiting
            try:
                if hasattr(jarvis_engine, 'llm_client') and jarvis_engine.llm_client:
                    import requests
                    base_url = getattr(jarvis_engine.llm_client, 'base_url', "http://localhost:11434")
                    models_to_unload = set([getattr(jarvis_engine.llm_client, 'normal_model', None), getattr(jarvis_engine.llm_client, 'overthink_model', None)])
                    for model in models_to_unload:
                        if model:
                            requests.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=3)
            except Exception:
                pass
            os._exit(0)

    # 1. Load an Icon (from standardized TRAY_ICON_PATH)
    try:
        from core.config import TRAY_ICON_PATH
        from pathlib import Path
        icon_path = Path(TRAY_ICON_PATH)
        
        if icon_path.exists():
            image = Image.open(icon_path)
            width, height = image.size
            if width != height:
                min_dim = min(width, height)
                left = (width - min_dim)/2
                top = (height - min_dim)/2
                right = (width + min_dim)/2
                bottom = (height + min_dim)/2
                image = image.crop((left, top, right, bottom))
        else:
            raise FileNotFoundError("Icon not found")
            
    except Exception:
        # Fallback dynamic image
        image = Image.new('RGB', (64, 64), color=(0, 102, 204))
        d = ImageDraw.Draw(image)
        d.text((10, 25), "NEXUS", fill=(255, 255, 255))

    def _do_restart(kill_ollama: bool):
        """Shared restart logic."""
        icon.stop()
        jarvis_engine.running = False
        
        if kill_ollama:
            try:
                import requests as _req
                if hasattr(jarvis_engine, 'llm_client') and jarvis_engine.llm_client:
                    base_url = getattr(jarvis_engine.llm_client, 'base_url', "http://localhost:11434")
                    for model in [jarvis_engine.llm_client.normal_model, jarvis_engine.llm_client.overthink_model]:
                        if model:
                            _req.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=3)
                subprocess.run("taskkill /F /IM ollama.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run("taskkill /F /IM ollama_llama_server.exe /T", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        
        env = os.environ.copy()
        if not kill_ollama:
            env['JARVIS_QUICK_RESTART'] = '1'
        
        try:
            if getattr(sys, 'frozen', False) or "__compiled__" in globals():
                subprocess.Popen([sys.executable], env=env)
            else:
                subprocess.Popen([sys.executable, 'app.py'], env=env)
        except Exception as e:
            print(f"⚠️ Restart failed: {e}")
        
        os._exit(0)

    def on_full_restart(icon, item):
        print("🔄 [Tray] Full Restart triggered...")
        threading.Thread(target=_do_restart, args=(True,), daemon=True).start()

    def on_quick_restart(icon, item):
        print("⚡ [Tray] Quick Restart triggered...")
        threading.Thread(target=_do_restart, args=(False,), daemon=True).start()

    def is_rebuild_enabled(item):
        if getattr(jarvis_engine, '_build_phase', ''):
            return False
        return jarvis_engine._llm_free_event.is_set()

    def on_rebuild_model(icon, item):
        print("🔨 [Tray] Model Rebuild triggered...")
        threading.Thread(
            target=lambda: jarvis_engine.trigger_model_rebuild(mode="smart"),
            daemon=True
        ).start()

    # 2. Construct the Dynamic Menu
    menu = pystray.Menu(
        pystray.MenuItem(f'JARVIS NEXUS v{_JARVIS_VERSION}', on_open_website, default=True),

        pystray.Menu.SEPARATOR,
        pystray.MenuItem('⚙️ Open Settings', on_open_settings),
        pystray.MenuItem('🛠️ Env Setup Wizard', on_open_setup),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('🔄 Restart', pystray.Menu(
            pystray.MenuItem('⚡ Quick Restart (Keep Ollama)', on_quick_restart),
            pystray.MenuItem('🔄 Full Restart (Kill Ollama)', on_full_restart),
        )),
        pystray.MenuItem('🔨 Rebuild LLM', on_rebuild_model, enabled=is_rebuild_enabled),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('🛑 Immediate Exit', on_exit)
    )

    # 3. Run the icon with continuous state polling
    icon = pystray.Icon(f"JARVIS v{_JARVIS_VERSION}", image, get_state_text(), menu)
    icon.run(setup=update_tooltip)

def start_tray(jarvis_engine):
    """Spawns the tray icon in a dedicated daemon thread."""
    tray_thread = threading.Thread(target=create_tray_icon, args=(jarvis_engine,), daemon=True, name="TrayIconThread")
    tray_thread.start()
