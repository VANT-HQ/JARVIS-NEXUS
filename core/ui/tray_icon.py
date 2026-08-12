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
import threading
import webbrowser
from pathlib import Path

# Fix sys.path for direct execution
import sys, os
if __name__ == "__main__":
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core.config import APP_VERSION
_JARVIS_VERSION = APP_VERSION

# --- Premium SVG Icons ---

SVG_LOGO = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#C9A227" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 20.66 7 20.66 17 12 22 3.34 17 3.34 7"></polygon>
  <circle cx="12" cy="12" r="3.5"></circle>
  <line x1="12" y1="2" x2="12" y2="8.5"></line>
  <line x1="12" y1="22" x2="12" y2="15.5"></line>
  <line x1="20.66" y1="7" x2="15.03" y2="10.25"></line>
  <line x1="20.66" y1="17" x2="15.03" y2="13.75"></line>
  <line x1="3.34" y1="7" x2="8.97" y2="10.25"></line>
  <line x1="3.34" y1="17" x2="8.97" y2="13.75"></line>
  <circle cx="12" cy="2" r="1.5" fill="#C9A227" stroke="none"></circle>
  <circle cx="20.66" cy="7" r="1.5" fill="#C9A227" stroke="none"></circle>
  <circle cx="20.66" cy="17" r="1.5" fill="#C9A227" stroke="none"></circle>
  <circle cx="12" cy="22" r="1.5" fill="#C9A227" stroke="none"></circle>
  <circle cx="3.34" cy="17" r="1.5" fill="#C9A227" stroke="none"></circle>
  <circle cx="3.34" cy="7" r="1.5" fill="#C9A227" stroke="none"></circle>
</svg>"""

SVG_SETTINGS = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a0aab5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"></circle>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
</svg>"""

SVG_RESULTS = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a0aab5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
  <polyline points="14 2 14 8 20 8"></polyline>
  <line x1="16" y1="13" x2="8" y2="13"></line>
  <line x1="16" y1="17" x2="8" y2="17"></line>
  <polyline points="10 9 9 9 8 9"></polyline>
</svg>"""

SVG_SETUP = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a0aab5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
  <line x1="9" y1="3" x2="9" y2="21"></line>
</svg>"""

SVG_RESTART = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a0aab5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="1 4 1 10 7 10"></polyline>
  <polyline points="23 20 23 14 17 14"></polyline>
  <path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path>
</svg>"""

SVG_QUICK_RESTART = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#eab308" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
</svg>"""

SVG_FULL_RESTART = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a0aab5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 2v6h-6"></path>
  <path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path>
  <path d="M3 22v-6h6"></path>
  <path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path>
</svg>"""

SVG_REBUILD = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#a0aab5" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
</svg>"""

SVG_EXIT = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="18" y1="6" x2="6" y2="18"></line>
  <line x1="6" y1="6" x2="18" y2="18"></line>
</svg>"""


def get_svg_icon(svg_str, size=48):
    """Renders raw SVG string to a QIcon preserving transparency."""
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtGui import QIcon, QPixmap, QPainter
    from PyQt5.QtCore import Qt

    renderer = QSvgRenderer(svg_str.encode('utf-8'))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    
    return QIcon(pixmap)


def create_tray_icon(jarvis_engine):
    """
    Creates and runs the PyQt5 System Tray icon for JARVIS.
    """
    from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QAction
    from PyQt5.QtGui import QIcon
    from PyQt5.QtCore import QTimer

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # -------------------------------------------------------------
    # CUSTOM STYLING (Gold/Amber Premium Theme)
    # -------------------------------------------------------------
    app.setStyleSheet("""
        QMenu {
            background-color: #0a0e14;
            border: 1px solid #2d3748;
            border-radius: 6px;
            padding: 4px 2px;
            color: #d1d5db;
            font-family: 'Segoe UI', -apple-system, sans-serif;
        }
        QMenu::item {
            padding: 6px 24px 6px 24px;
            border-radius: 4px;
            margin: 1px 4px;
            font-size: 11.5px;
            background-color: transparent;
        }
        QMenu::item:selected, QMenu::item:open {
            background-color: rgba(201, 162, 39, 0.15);
            color: #C9A227;
        }
        QMenu::item:disabled {
            color: #4b5563;
        }
        QMenu::separator {
            height: 1px;
            background: #1f2937;
            margin: 4px 10px;
        }
        QMenu::icon {
            padding-left: 12px;
        }
    """)

    tray_icon = QSystemTrayIcon(app)
    
    # Load Main System Tray Icon
    try:
        from core.config import TRAY_ICON_PATH
        if Path(TRAY_ICON_PATH).exists():
            tray_icon.setIcon(QIcon(TRAY_ICON_PATH))
        else:
            tray_icon.setIcon(get_svg_icon(SVG_LOGO, 64))
    except Exception:
        tray_icon.setIcon(get_svg_icon(SVG_LOGO, 64))

    # -------------------------------------------------------------
    # MENU ACTIONS & CALLBACKS
    # -------------------------------------------------------------
    def on_open_website():
        try:
            webbrowser.open("https://vanthq.net/jarvis")
        except Exception:
            pass

    def on_open_settings():
        print("\\n⚙️ [Tray] Opening Settings Panel...")
        try:
            if getattr(sys, 'frozen', False) or "__compiled__" in globals():
                subprocess.Popen([sys.executable, "--settings"])
            else:
                # MODIFIED: Use absolute path to prevent CWD-dependent failures
                settings_script = str((Path(__file__).parent / "settings_panel.py").resolve())
                subprocess.Popen([sys.executable, settings_script])
        except Exception as e:
            print(f"Tray error opening settings: {e}")

    def on_open_setup():
        print("\\n🛠️ [Tray] Opening Environment Setup Wizard...")
        try:
            if getattr(sys, 'frozen', False) or "__compiled__" in globals():
                subprocess.Popen([sys.executable, "--setup"])
            else:
                # MODIFIED: Use absolute path to prevent CWD-dependent failures
                setup_script = str((Path(__file__).parent.parent / "bootstrap" / "env_setup.py").resolve())
                subprocess.Popen([sys.executable, setup_script])
        except Exception as e:
            print(f"Tray error opening setup: {e}")

    def on_open_results():
        print("\\n📋 [Tray] Opening Results Viewer...")
        try:
            if getattr(sys, 'frozen', False) or "__compiled__" in globals():
                subprocess.Popen([sys.executable, "--results"])
            else:
                # MODIFIED: Added missing __compiled__ check + use absolute path for app.py
                app_script = str((Path(__file__).parent.parent.parent / "app.py").resolve())
                subprocess.Popen([sys.executable, app_script, "--results"])
        except Exception as e:
            print(f"Tray error opening results viewer: {e}")

    def on_exit():
        print("\\n🛑 [Tray] Immediate Exit triggered...")
        tray_icon.hide()
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
                
            from core.config import config
            config.force_wal_checkpoint()
            if hasattr(jarvis_engine, 'memory') and getattr(jarvis_engine, 'memory', None):
                jarvis_engine.memory.force_wal_checkpoint()
                
            sys.exit(0)

    def _do_restart(kill_ollama: bool):
        """Shared restart logic."""
        tray_icon.hide()
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
            
        from core.config import config
        config.force_wal_checkpoint()
        if hasattr(jarvis_engine, 'memory') and getattr(jarvis_engine, 'memory', None):
            jarvis_engine.memory.force_wal_checkpoint()
            
        sys.exit(0)

    def on_full_restart():
        print("🔄 [Tray] Full Restart triggered...")
        threading.Thread(target=_do_restart, args=(True,), daemon=True).start()

    def on_quick_restart():
        print("⚡ [Tray] Quick Restart triggered...")
        threading.Thread(target=_do_restart, args=(False,), daemon=True).start()

    def on_rebuild_model():
        print("🔨 [Tray] Model Rebuild triggered...")
        threading.Thread(
            target=lambda: jarvis_engine.trigger_model_rebuild(mode="smart"),
            daemon=True
        ).start()

    # -------------------------------------------------------------
    # BUILD MENU
    # -------------------------------------------------------------
    menu = QMenu()

    # Header
    act_header = QAction(get_svg_icon(SVG_LOGO), f"JARVIS NEXUS v{_JARVIS_VERSION}", menu)
    act_header.triggered.connect(on_open_website)
    font = act_header.font()
    font.setBold(True)
    act_header.setFont(font)
    menu.addAction(act_header)
    
    menu.addSeparator()

    # Core Panels
    act_settings = QAction(get_svg_icon(SVG_SETTINGS), "Open Settings", menu)
    act_settings.triggered.connect(on_open_settings)
    menu.addAction(act_settings)

    act_results = QAction(get_svg_icon(SVG_RESULTS), "Open Results Viewer", menu)
    act_results.triggered.connect(on_open_results)
    menu.addAction(act_results)

    act_setup = QAction(get_svg_icon(SVG_SETUP), "Env Setup Wizard", menu)
    act_setup.triggered.connect(on_open_setup)
    menu.addAction(act_setup)

    menu.addSeparator()

    # Restart Submenu
    restart_menu = QMenu("Restart System", menu)
    restart_menu.setIcon(get_svg_icon(SVG_RESTART))
    
    act_quick_restart = QAction(get_svg_icon(SVG_QUICK_RESTART), "Quick Restart (Keep Ollama)", restart_menu)
    act_quick_restart.triggered.connect(on_quick_restart)
    restart_menu.addAction(act_quick_restart)
    
    act_full_restart = QAction(get_svg_icon(SVG_FULL_RESTART), "Full Restart (Kill Ollama)", restart_menu)
    act_full_restart.triggered.connect(on_full_restart)
    restart_menu.addAction(act_full_restart)

    menu.addMenu(restart_menu)

    act_rebuild = QAction(get_svg_icon(SVG_REBUILD), "Rebuild LLM", menu)
    act_rebuild.triggered.connect(on_rebuild_model)
    menu.addAction(act_rebuild)

    menu.addSeparator()

    act_exit = QAction(get_svg_icon(SVG_EXIT), "Immediate Exit", menu)
    act_exit.triggered.connect(on_exit)
    menu.addAction(act_exit)

    tray_icon.setContextMenu(menu)
    tray_icon.show()

    # -------------------------------------------------------------
    # STATE POLLING & TOOLTIP (Replaces pystray loop)
    # -------------------------------------------------------------
    def get_state_text():
        if not jarvis_engine.initialization_complete:
            phase = getattr(jarvis_engine, '_build_phase', '')
            if phase == 'building_model':
                return "🔨 JARVIS: Building Model..."
            elif phase == 'warming_cache':
                return "🔥 JARVIS: Warming Cache..."
            return "🚀 JARVIS: Starting up..."

        state = jarvis_engine.state.interrupt_state
        try:
            from core.ui.settings_panel import get_setting
            followup_window = get_setting('followup_window', 10)
        except Exception:
            followup_window = 10

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

    def update_tooltip_and_state():
        # Update tooltip
        try:
            new_text = get_state_text()
            if tray_icon.toolTip() != new_text:
                tray_icon.setToolTip(new_text)
        except Exception:
            pass
            
        # Dynamically enable/disable 'Rebuild LLM' action
        try:
            if getattr(jarvis_engine, '_build_phase', ''):
                act_rebuild.setEnabled(False)
            else:
                act_rebuild.setEnabled(jarvis_engine._llm_free_event.is_set())
        except Exception:
            pass

    # Use QTimer instead of a while True loop inside the UI thread
    timer = QTimer()
    timer.timeout.connect(update_tooltip_and_state)
    timer.start(500)

    # Double click on tray icon opens settings
    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.DoubleClick:
            on_open_settings()

    tray_icon.activated.connect(on_tray_activated)

    # Run the event loop
    app.exec_()


def start_tray(jarvis_engine):
    """Spawns the tray icon in a dedicated daemon thread."""
    # Since PyQt5 event loop is created inside create_tray_icon,
    # it safely runs encapsulated within this thread.
    tray_thread = threading.Thread(target=create_tray_icon, args=(jarvis_engine,), daemon=True, name="TrayIconThread")
    tray_thread.start()

if __name__ == "__main__":
    import threading
    print("Testing Tray Icon Standalone...")
    
    class MockState:
        interrupt_state = "processing"
        always_listening = False
    
    class MockEars:
        is_listening = True

    class MockEvent:
        def is_set(self): return True

    class MockEngine:
        initialization_complete = True
        _build_phase = ""
        state = MockState()
        ears = MockEars()
        _llm_free_event = MockEvent()

        def trigger_model_rebuild(self, mode="smart"):
            print(f"Mock Engine: Rebuild triggered in mode {mode}")

    mock_engine = MockEngine()
    # Call directly in main thread for testing
    create_tray_icon(mock_engine)

