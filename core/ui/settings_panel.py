# core/ui/settings_panel.py  #? (Hmody: what do u think about pywebview idea? batter than other win xp looks, huh?)

"""
JARVIS NEXUS Settings Panel
===========================
A clean configuration UI for managing AI models, audio thresholds,
wake words, and security settings with real-time JSON DB persistence.
"""

import sys
import json
import webview
import subprocess
from pathlib import Path
import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import pygame


# ── Import config from the core package ──────────────────────────
try:
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from core.config import config, ConfigManager, SETTINGS_DB_PATH
except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Import Error", f"Cannot load core/config.py\n{e}")
    sys.exit(1)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   PYTHON ↔ JS BRIDGE                         ║
# ╚══════════════════════════════════════════════════════════════╝
class API:
    """Exposed to JavaScript via window.pywebview.api.*"""

    # ── Settings ─────────────────────────────────────────────
    def get_all_settings(self):
        return json.dumps(config.settings)

    def save_settings(self, payload: str):
        try:
            data = json.loads(payload)
            changed = 0
            for key, value in data.items():
                if key not in config.settings or config.settings[key] != value:
                    config.set(key, value)
                    changed += 1
            return json.dumps({"ok": True, "saved": changed})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def reset_defaults(self):
        try:
            for key, value in config.default_settings.items():
                config.set(key, value)
            return json.dumps({"ok": True, "settings": config.default_settings})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def get_available_tts_models(self):
        try:
            models = config.get_available_tts_models()
            return json.dumps({"ok": True, "models": models})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Folder picker ─────────────────────────────────────────
    def pick_folder(self):
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.FOLDER
        )
        if result:
            return json.dumps({"ok": True, "path": result[0]})
        return json.dumps({"ok": False})

    # ── File picker (models) ──────────────────────────────────
    def pick_file(self, extensions_json: str = "[]"):
        try:
            exts = tuple(json.loads(extensions_json))
        except Exception:
            exts = ()
        result = webview.windows[0].create_file_dialog(
            webview.FileDialog.OPEN,
            file_types=(f"Model files (*{' *'.join(exts)})",) if exts else ()
        )
        if result:
            return json.dumps({"ok": True, "path": result[0]})
        return json.dumps({"ok": False})

    # ── Personas ──────────────────────────────────────────────
    def get_personas(self):
        return json.dumps(config.get_all_personas())

    def add_persona(self, name: str, prompt: str):
        ok = config.add_persona(name.strip(), prompt.strip())
        return json.dumps({"ok": ok})

    def update_persona(self, persona_id: int, name: str, prompt: str):
        ok = config.update_persona(int(persona_id), name.strip(), prompt.strip())
        return json.dumps({"ok": ok})

    def delete_persona(self, persona_id: int):
        ok = config.delete_persona(int(persona_id))
        return json.dumps({"ok": ok})

    def launch_setup_wizard(self):
        try:
            from core.config import BASE_DIR
            setup_script = BASE_DIR / "core" / "bootstrap" / "env_setup.py"
            subprocess.Popen([sys.executable, str(setup_script)])
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def set_default_persona(self, persona_id: int):
        ok = config.set_default_persona(int(persona_id))
        return json.dumps({"ok": ok})

    def close_window(self):
        try:
            for window in webview.windows:
                if "Settings" in window.title:
                    window.destroy()
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def play_test_sound(self, volume: str):
        try:
            vol = float(volume) / 100.0
            
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            
            from core.config import BEEP_SOUND
            sound_path = Path(BEEP_SOUND)
            
            if sound_path.exists():
                sound = pygame.mixer.Sound(str(sound_path))
                sound.set_volume(vol)
                sound.play()
            else:
                import platform
                if platform.system() == "Windows":
                    import winsound
                    winsound.MessageBeep()

            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})


# ╔══════════════════════════════════════════════════════════════╗
# ║                        HTML / UI                             ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>JARVIS · Settings</title>
<style>
/* ── Reset & Base ─────────────────────────────────────────── */
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:       #0d1117;
  --surface:  #161b22;
  --card:     #1c2128;
  --input-bg: #21262d;
  --border:   #30363d;
  --accent:   #58a6ff;
  --accent-h: #388bfd;
  --green:    #3fb950;
  --red:      #f85149;
  --yellow:   #d29922;
  --txt:      #e6edf3;
  --txt-sub:  #8b949e;
  --txt-mute: #484f58;
  --radius:   10px;
  --radius-sm:6px;
  --trans:    .18s ease;
}
html,body{height:100%;font-family:"Segoe UI",system-ui,sans-serif;
          background:var(--bg);color:var(--txt);font-size:14px;overflow:hidden}

/* ── Layout ───────────────────────────────────────────────── */
#app{display:flex;flex-direction:column;height:100vh}

/* title bar */
#titlebar{
  display:flex;align-items:center;gap:12px;
  background:var(--surface);padding:0 24px;height:54px;
  border-bottom:1px solid var(--border);flex-shrink:0;
}
#titlebar .logo{font-size:18px;font-weight:700;color:var(--txt);letter-spacing:.5px}
#titlebar .logo span{color:var(--accent)}
#titlebar .sub{font-size:11px;color:var(--txt-mute);margin-top:2px}
#titlebar .badge{
  margin-left:auto;background:var(--accent);color:#000;
  font-size:10px;font-weight:700;padding:3px 10px;border-radius:20px
}

/* body area */
#body{display:flex;flex:1;overflow:hidden}

/* sidebar */
#sidebar{
  width:200px;background:var(--surface);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;flex-shrink:0;overflow-y:auto;
  padding:12px 8px;gap:4px;
}
.nav-item{
  display:flex;align-items:center;gap:10px;
  padding:10px 14px;border-radius:var(--radius-sm);
  cursor:pointer;color:var(--txt-sub);font-size:13px;font-weight:500;
  transition:background var(--trans),color var(--trans);user-select:none;
}
.nav-item:hover{background:var(--card);color:var(--txt)}
.nav-item.active{background:var(--accent-h)22;color:var(--accent);font-weight:600}
.nav-item .icon{font-size:16px;width:20px;text-align:center}
.nav-sep{height:1px;background:var(--border);margin:8px 4px}

/* content */
#content{flex:1;overflow-y:auto;padding:28px 32px}
#content::-webkit-scrollbar{width:6px}
#content::-webkit-scrollbar-track{background:transparent}
#content::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* footer */
#footer{
  display:flex;align-items:center;padding:0 24px;height:56px;
  background:var(--surface);border-top:1px solid var(--border);
  flex-shrink:0;gap:10px;
}
#footer .status{flex:1;font-size:12px;color:var(--green);
                 opacity:0;transition:opacity .3s}
#footer .status.show{opacity:1}

/* pages */
.page{display:none}
.page.active{display:block}

/* ── Cards ────────────────────────────────────────────────── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);margin-bottom:20px;overflow:hidden;
}
.card-header{
  display:flex;align-items:center;gap:10px;
  background:var(--surface);padding:12px 18px;
  border-bottom:1px solid var(--border);
  font-size:13px;font-weight:600;color:var(--accent);
}
.card-header .icon{font-size:16px}
.card-body{padding:4px 0}

/* ── Rows ─────────────────────────────────────────────────── */
.row{
  display:flex;align-items:center;gap:16px;
  padding:12px 18px;border-bottom:1px solid var(--border);
}
.row:last-child{border-bottom:none}
.row-left{min-width:220px;max-width:220px}
.row-left .label{font-size:13px;color:var(--txt);font-weight:500}
.row-left .hint{font-size:11px;color:var(--txt-sub);margin-top:3px;line-height:1.4}
.row-right{flex:1;display:flex;align-items:center;gap:8px;flex-wrap:wrap}

/* ── Inputs ───────────────────────────────────────────────── */
input[type=text],input[type=number],select,textarea{
  background:var(--input-bg);color:var(--txt);
  border:1px solid var(--border);border-radius:var(--radius-sm);
  padding:8px 12px;font-size:13px;font-family:inherit;
  outline:none;transition:border-color var(--trans);width:100%;
}
input[type=text]:focus,input[type=number]:focus,
select:focus,textarea:focus{border-color:var(--accent)}
select{cursor:pointer;-webkit-appearance:none;
       background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='%238b949e'%3E%3Cpath d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
       background-repeat:no-repeat;background-position:right 10px center;
       padding-right:30px;}
textarea{resize:vertical;min-height:120px;font-family:monospace;font-size:12px}
.mono{font-family:"Cascadia Code","Consolas",monospace;font-size:12px}

/* path input row */
.path-row{display:flex;gap:6px;width:100%}
.path-row input{flex:1}

/* ── Toggle ───────────────────────────────────────────────── */
.toggle{position:relative;width:44px;height:24px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0;position:absolute}
.toggle-track{
  position:absolute;inset:0;border-radius:12px;
  background:var(--txt-mute);cursor:pointer;
  transition:background var(--trans);
}
.toggle input:checked + .toggle-track{background:var(--green)}
.toggle-thumb{
  position:absolute;top:3px;left:3px;
  width:18px;height:18px;border-radius:50%;background:#fff;
  transition:transform var(--trans);pointer-events:none;
}
.toggle input:checked ~ .toggle-thumb{transform:translateX(20px)}

/* ── Slider ───────────────────────────────────────────────── */
.slider-wrap{display:flex;align-items:center;gap:10px;width:100%}
input[type=range]{
  flex:1;-webkit-appearance:none;height:4px;
  background:var(--border);border-radius:2px;outline:none;cursor:pointer;
}
input[type=range]::-webkit-slider-thumb{
  -webkit-appearance:none;width:16px;height:16px;border-radius:50%;
  background:var(--accent);cursor:pointer;
  transition:background var(--trans);
}
input[type=range]::-webkit-slider-thumb:hover{background:var(--accent-h)}
.slider-val{
  min-width:52px;text-align:right;color:var(--accent);
  font-size:13px;font-weight:600;font-variant-numeric:tabular-nums;
}

/* ── Buttons ──────────────────────────────────────────────── */
button{
  display:inline-flex;align-items:center;gap:6px;
  padding:8px 18px;border-radius:var(--radius-sm);border:none;
  font-size:13px;font-weight:600;cursor:pointer;
  transition:background var(--trans),transform .1s;font-family:inherit;
}
button:active{transform:scale(.97)}
.btn-primary{background:var(--accent);color:#000}
.btn-primary:hover{background:var(--accent-h)}
.btn-ghost{background:var(--card);color:var(--txt);border:1px solid var(--border)}
.btn-ghost:hover{background:var(--input-bg)}
.btn-danger{background:#2d1b1b;color:var(--red);border:1px solid #4a1f1f}
.btn-danger:hover{background:#3d2020}
.btn-success{background:#1b2d1b;color:var(--green);border:1px solid #1f4a1f}
.btn-success:hover{background:#203d20}
.btn-sm{padding:5px 12px;font-size:12px}
.btn-icon{padding:6px 10px;font-size:15px}

/* ── Wake words ───────────────────────────────────────────── */
.tags{display:flex;flex-wrap:wrap;gap:6px;align-items:center;width:100%}
.tag{
  display:inline-flex;align-items:center;gap:5px;
  background:var(--input-bg);border:1px solid var(--border);
  border-radius:20px;padding:4px 12px;font-size:12px;color:var(--txt);
}
.tag .del{
  cursor:pointer;color:var(--txt-mute);font-size:14px;line-height:1;
  border:none;background:none;padding:0;
  transition:color var(--trans);
}
.tag .del:hover{color:var(--red)}
.tag-input{
  flex:1;min-width:140px;background:var(--input-bg);border:1px solid var(--border);
  border-radius:20px;padding:5px 14px;font-size:12px;color:var(--txt);
  outline:none;
}
.tag-input:focus{border-color:var(--accent)}

/* ── Personas panel ───────────────────────────────────────── */
#personas-layout{display:flex;gap:20px;height:calc(100vh - 190px);min-height:400px}
#persona-list-panel{
  width:220px;flex-shrink:0;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);display:flex;flex-direction:column;overflow:hidden;
}
#persona-list-panel .plist-header{
  padding:12px 14px;background:var(--surface);
  border-bottom:1px solid var(--border);
  font-size:12px;font-weight:600;color:var(--accent);
}
#persona-list{flex:1;overflow-y:auto;padding:6px}
#persona-list::-webkit-scrollbar{width:4px}
#persona-list::-webkit-scrollbar-thumb{background:var(--border);border-radius:2px}
.persona-item{
  padding:10px 12px;border-radius:var(--radius-sm);cursor:pointer;
  font-size:13px;color:var(--txt-sub);
  transition:background var(--trans),color var(--trans);
  display:flex;align-items:center;justify-content:space-between;
}
.persona-item:hover{background:var(--input-bg);color:var(--txt)}
.persona-item.active{background:var(--accent-h)22;color:var(--accent)}
.persona-item .badges{display:flex;gap:4px}
.pbadge{
  font-size:9px;padding:2px 6px;border-radius:10px;font-weight:700;
}
.pbadge.default{background:#1b2d1b;color:var(--green)}
.pbadge.locked{background:#2a2010;color:var(--yellow)}
#persona-editor{
  flex:1;background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);display:flex;flex-direction:column;
  overflow:hidden;
}
.editor-header{
  padding:14px 18px;background:var(--surface);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:10px;
}
.editor-header input{
  flex:1;background:transparent;border:none;
  font-size:15px;font-weight:600;color:var(--txt);
  outline:none;padding:0;
}
.editor-header input:disabled{color:var(--txt-sub);cursor:not-allowed}
.locked-badge{
  font-size:11px;padding:3px 10px;border-radius:20px;
  background:#2a2010;color:var(--yellow);border:1px solid #4a3010;
}
.editor-body{flex:1;padding:16px 18px;display:flex;flex-direction:column;gap:12px}
#persona-prompt{flex:1;min-height:0}
.editor-footer{
  padding:12px 18px;border-top:1px solid var(--border);
  display:flex;gap:8px;align-items:center;
}
.editor-status{font-size:12px;margin-left:auto}
.plist-footer{
  padding:8px;border-top:1px solid var(--border);
  display:flex;gap:6px;
}

/* ── Section title ────────────────────────────────────────── */
.section-title{
  font-size:11px;font-weight:700;text-transform:uppercase;
  letter-spacing:.8px;color:var(--txt-mute);
  padding:0 0 10px 2px;
}

/* ── Notification toast ───────────────────────────────────── */
#toast{
  position:fixed;bottom:72px;right:28px;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:12px 20px;
  font-size:13px;color:var(--txt);
  box-shadow:0 8px 32px #0008;
  transform:translateY(20px);opacity:0;
  transition:all .25s ease;pointer-events:none;z-index:999;
}
#toast.show{transform:translateY(0);opacity:1}
#toast.success{border-color:var(--green);color:var(--green)}
#toast.error{border-color:var(--red);color:var(--red)}

/* scrollbar global */
*::-webkit-scrollbar{width:6px;height:6px}
*::-webkit-scrollbar-track{background:transparent}
*::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>
<div id="app">

  <!-- Title Bar -->
  <div id="titlebar">
    <div>
      <div class="logo">⚙ JARVIS <span>NEXUS</span></div>
      <div class="sub">Configuration Manager - v0.1 alpha</div>
    </div>
    <div class="badge">v1.0</div>
  </div>

  <!-- Body -->
  <div id="body">

    <!-- Sidebar -->
    <nav id="sidebar">
      <div class="nav-item active" data-page="general">
        <span class="icon">🏠</span> General
      </div>
      <div class="nav-item" data-page="audio">
        <span class="icon">🔊</span> Audio
      </div>
      <div class="nav-item" data-page="ai">
        <span class="icon">🤖</span> AI / LLM
      </div>
      <div class="nav-item" data-page="personas">
        <span class="icon">🎭</span> Personas
      </div>
      <div class="nav-sep"></div>
      <div class="nav-item" data-page="advanced">
        <span class="icon">⚙️</span> Advanced
      </div>
    </nav>

    <!-- Content -->
    <main id="content">

      <!-- ═══════════════════════════════════════ GENERAL -->
      <div class="page active" id="page-general">

        <div class="card">
          <div class="card-header"><span class="icon">👤</span> Identity</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Your Name</div>
                <div class="hint">The name the model calls you. If left blank, it defaults to Sir / Boss.</div>
              </div>
              <div class="row-right">
                <input type="text" id="user_name" placeholder="e.g. Ahmed">
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Assistant Name</div>
                <div class="hint">AI display name (*Mandatory).</div>
              </div>
              <div class="row-right">
                <input type="text" id="assistant_name" placeholder="Jarvis">
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Wake Word(s)</div>
                <div class="hint">Keyword to activate listening (*Mandatory, exactly ONE word).</div>
              </div>
              <div class="row-right">
                <div class="tags" id="wake-tags">
                  <input class="tag-input" id="wake-input"
                         placeholder="Type & press Enter…"
                         onkeydown="wakeKeydown(event)">
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Your Location</div>
                <div class="hint">City for weather &amp; time-zone context</div>
              </div>
              <div class="row-right">
                <input type="text" id="user_location" placeholder="Cairo">
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">🚀</span> Startup &amp; Interface</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Startup Video</div>
                <div class="hint">Plays an intro animation while the AI model loads in the background</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="startup_show">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Start with OS</div>
                <div class="hint">Launch JARVIS automatically with the OS (not limited to Windows).</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="startup_with_os">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Sound Effects</div>
                <div class="hint">UI sounds — beeps, chimes, listening popup</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="sound_effects">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Follow-up Window</div>
                <div class="hint">Seconds the model will listen to you without needing the wake word.</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="followup_window" min="3" max="60" step="1"
                         oninput="syncVal(this,'followup_window_val')">
                  <span class="slider-val" id="followup_window_val">15s</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Use External API</div>
                <div class="hint">Allow external connections — useful for improving search results.</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="external_api">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Task Snooze Duration</div>
                <div class="hint">Default minutes to snooze a postponed task</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="task_snooze_minutes" min="1" max="60" step="1"
                         oninput="syncVal(this,'task_snooze_val')">
                  <span class="slider-val" id="task_snooze_val">5 min</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">📁</span> Workspace Paths</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Shared Area</div>
                <div class="hint">Folder JARVIS can freely read &amp; write</div>
              </div>
              <div class="row-right">
                <div class="path-row">
                  <input type="text" id="share_dir" class="mono" readonly
                         placeholder="Click Browse…">
                  <button class="btn-ghost btn-sm"
                          onclick="browseFolder('share_dir')">📂 Browse</button>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Run Directory</div>
                <div class="hint">Working directory for executed tasks &amp; scripts</div>
              </div>
              <div class="row-right">
                <div class="path-row">
                  <input type="text" id="run_dir" class="mono" readonly
                         placeholder="Click Browse…">
                  <button class="btn-ghost btn-sm"
                          onclick="browseFolder('run_dir')">📂 Browse</button>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /general -->

      <!-- ═══════════════════════════════════════ AUDIO -->
      <div class="page" id="page-audio">

        <div class="card">
          <div class="card-header"><span class="icon">🔊</span> Playback</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Master Volume</div>
                <div class="hint">TTS speech output level</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="volume" min="0" max="100" step="1"
                         oninput="syncVal(this,'volume_val')" onchange="testVolume(this.value)">
                  <span class="slider-val" id="volume_val">70%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">🎙️</span> Microphone</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Pause Threshold</div>
                <div class="hint">Seconds of silence before end-of-speech is detected</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="mic_pause_threshold"
                         min="0.1" max="3" step="0.1"
                         oninput="syncValF(this,'mic_pause_val',1,'s')">
                  <span class="slider-val" id="mic_pause_val">0.8s</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Energy Threshold</div>
                <div class="hint">Mic sensitivity — raise to reduce background noise</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="mic_energy_threshold"
                         min="50" max="1000" step="10"
                         oninput="syncVal(this,'mic_energy_val')">
                  <span class="slider-val" id="mic_energy_val">300</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">🧠</span> Models</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">English TTS Voice</div>
                <div class="hint">Available voices in models/tts folder</div>
              </div>
              <div class="row-right">
                <select id="en_tts">
                  <!-- options injected via JS -->
                </select>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">STT Model Path</div>
                <div class="hint">Listening model folder (not specifically faster-whisper).</div>
              </div>
              <div class="row-right">
                <div class="path-row">
                  <input type="text" id="main_stt" class="mono" readonly>
                  <button class="btn-ghost btn-sm"
                          onclick="browseFolder('main_stt')">📂 Browse</button>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /audio -->

      <!-- ═══════════════════════════════════════ AI / LLM -->
      <div class="page" id="page-ai">

        <div class="card">
          <div class="card-header"><span class="icon">🤖</span> Model Selection</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Quick LLM</div>
                <div class="hint">Fast lightweight model</div>
              </div>
              <div class="row-right">
                <label class="toggle" style="margin-right:4px">
                  <input type="checkbox" id="quick_llm_auto" onchange="toggleLlm('quick')">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
                <span style="font-size:12px;color:var(--txt-sub);margin-right:8px">Auto</span>
                <div class="path-row" id="quick_llm_row" style="flex:1">
                  <input type="text" id="quick_llm" class="mono" readonly placeholder="Custom .gguf path...">
                  <button class="btn-ghost btn-sm"
                          onclick="browseFile('quick_llm',['.gguf'])">📂 Browse</button>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Main LLM</div>
                <div class="hint">Full-size model for complex tasks</div>
              </div>
              <div class="row-right">
                <label class="toggle" style="margin-right:4px">
                  <input type="checkbox" id="main_llm_auto" onchange="toggleLlm('main')">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
                <span style="font-size:12px;color:var(--txt-sub);margin-right:8px">Auto</span>
                <div class="path-row" id="main_llm_row" style="flex:1">
                  <input type="text" id="main_llm" class="mono" readonly placeholder="Custom .gguf path...">
                  <button class="btn-ghost btn-sm"
                          onclick="browseFile('main_llm',['.gguf'])">📂 Browse</button>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Embedding Model</div>
                <div class="hint">Ollama embedding model name (e.g., all-minilm)</div>
              </div>
              <div class="row-right">
                <input type="text" id="embedding_model" placeholder="all-minilm" class="mono">
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">⚡</span> Performance</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">High Performance Mode</div>
                <div class="hint">Keeps the model alive in RAM between conversations for faster responses.</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="high_performance">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Sub High Performance</div>
                <div class="hint">Keep secondary models resident in RAM. DO NOT USE on 4GB RAM.</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="sub_high_performance">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">🧩</span> Cognitive Settings</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Active Persona</div>
                <div class="hint">The core personality and behavior rules</div>
              </div>
              <div class="row-right">
                <select id="active_persona_select" onchange="changeActivePersona(this.value)">
                  <!-- Injected via JS -->
                </select>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Max Tool Calls / Turn</div>
                <div class="hint">Maximum number of tools the model can call in a single cycle.</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="tool_maximum" min="1" max="15" step="1"
                         oninput="syncVal(this,'tool_max_val')">
                  <span class="slider-val" id="tool_max_val">5</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Fast Mode Iterations</div>
                <div class="hint">Number of free thinking cycles in normal mode.</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="fast_iterations" min="1" max="20" step="1"
                         oninput="syncVal(this,'fast_iter_val')">
                  <span class="slider-val" id="fast_iter_val">5</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Overthink Iterations</div>
                <div class="hint">Maximum number of cycles in overthink mode.</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="overthink_iterations" min="1" max="30" step="1"
                         oninput="syncVal(this,'overthink_iter_val')">
                  <span class="slider-val" id="overthink_iter_val">8</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">History Limit</div>
                <div class="hint">Conversation turns kept in active context</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="history_limit" min="1" max="20" step="1"
                         oninput="syncVal(this,'history_val')">
                  <span class="slider-val" id="history_val">3 turns</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Max Syntax Corrections</div>
                <div class="hint">Retries available to the model when it fails a request or execution.</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="max_syntax_corrections" min="0" max="5" step="1"
                         oninput="syncVal(this,'syntax_val')">
                  <span class="slider-val" id="syntax_val">1</span>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /ai -->

      <!-- ═══════════════════════════════════════ PERSONAS -->
      <div class="page" id="page-personas">
        <div id="personas-layout">
          <!-- List panel -->
          <div id="persona-list-panel">
            <div class="plist-header">🎭 Personas</div>
            <div id="persona-list"></div>
            <div class="plist-footer">
              <button class="btn-success btn-sm" style="flex:1"
                      onclick="newPersona()">＋ New</button>
              <button class="btn-danger btn-sm" style="flex:1"
                      onclick="deletePersona()">✕ Delete</button>
            </div>
          </div>
          <!-- Editor -->
          <div id="persona-editor">
            <div class="editor-header">
              <input type="text" id="persona-name" placeholder="Persona name…">
              <span class="locked-badge" id="lock-badge" style="display:none">🔒 System</span>
            </div>
            <div class="editor-body">
              <div style="font-size:11px;color:var(--txt-sub)">Personality &amp; Behavior Prompt</div>
              <textarea id="persona-prompt"
                        placeholder="Describe tone, speech style, behavioral rules…"></textarea>
            </div>
            <div class="editor-footer">
              <button class="btn-primary btn-sm" onclick="savePersona()">💾 Save</button>
              <button class="btn-success btn-sm" onclick="setDefaultPersona()">✔ Set as Default</button>
              <span class="editor-status" id="persona-status"></span>
            </div>
          </div>
        </div>
      </div><!-- /personas -->

      <!-- ═══════════════════════════════════════ ADVANCED -->
      <div class="page" id="page-advanced">

        <div class="card">
          <div class="card-header"><span class="icon">🌐</span> API &amp; Connectivity</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Local API URL</div>
                <div class="hint">Ollama / LM Studio endpoint</div>
              </div>
              <div class="row-right">
                <input type="text" id="local_api_url" class="mono"
                       placeholder="http://localhost:11434">
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">📏</span> Context &amp; Tokens</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Context Window</div>
                <div class="hint">Total token budget per LLM call (min 4096)</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="llm_context_window"
                         min="4096" max="32768" step="512"
                         oninput="syncValK(this,'ctx_val')">
                  <span class="slider-val" id="ctx_val">4096</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Max Tokens — Normal</div>
                <div class="hint">Output cap in standard response mode</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="llm_max_tokens_normal"
                         min="128" max="4096" step="64"
                         oninput="syncVal(this,'max_tok_norm_val')">
                  <span class="slider-val" id="max_tok_norm_val">1024</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Max Tokens — Overthink</div>
                <div class="hint">Output cap in deep-analysis mode</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="llm_max_tokens_overthink"
                         min="256" max="8192" step="128"
                         oninput="syncVal(this,'max_tok_ot_val')">
                  <span class="slider-val" id="max_tok_ot_val">2048</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Overthink Temperature</div>
                <div class="hint">Creativity in deep-analysis mode (0.0 – 1.0)</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="overthink_temperature"
                         min="0" max="1" step="0.05"
                         oninput="syncValF(this,'ot_temp_val',2,'')">
                  <span class="slider-val" id="ot_temp_val">0.30</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">🔥</span> Model Warm-up</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Warmup Timeout (s)</div>
                <div class="hint">Seconds to wait for model to become ready</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="warmup_timeout" min="10" max="300" step="5"
                         oninput="syncVal(this,'warmup_to_val','s')">
                  <span class="slider-val" id="warmup_to_val">60s</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Warmup Max Retries</div>
                <div class="hint">Ping attempts during model startup</div>
              </div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="warmup_max_retries" min="1" max="20" step="1"
                         oninput="syncVal(this,'warmup_ret_val')">
                  <span class="slider-val" id="warmup_ret_val">5</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Keep-Alive (High Perf.)</div>
                <div class="hint">e.g. <code style="color:var(--accent)">15</code> or <code style="color:var(--accent)">-1</code> (forever)</div>
              </div>
              <div class="row-right">
                <input type="number" id="llm_keep_alive_high_perf"
                       class="mono" style="max-width:100px" placeholder="15">
                <span style="font-size:12px;color:var(--txt-sub)">minutes</span>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Keep-Alive (Normal)</div>
                <div class="hint">e.g. <code style="color:var(--accent)">10</code></div>
              </div>
              <div class="row-right">
                <input type="number" id="llm_keep_alive_normal"
                       class="mono" style="max-width:100px" placeholder="10">
                <span style="font-size:12px;color:var(--txt-sub)">minutes</span>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><span class="icon">🛠️</span> Developer</div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Developer Mode</div>
                <div class="hint">Records a full background log between System/LLM, and makes the model speak the names of called tools.</div>
              </div>
              <div class="row-right">
                <label class="toggle">
                  <input type="checkbox" id="dev_mode">
                  <div class="toggle-track"></div>
                  <div class="toggle-thumb"></div>
                </label>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Re-run Setup Wizard</div>
                <div class="hint">Launch the Environment Setup tool to manage models and assets</div>
              </div>
              <div class="row-right">
                <button class="btn-ghost btn-sm" onclick="pywebview.api.launch_setup_wizard()">🚀 Open Setup</button>
              </div>
            </div>
          </div>
        </div>

      </div><!-- /advanced -->

    </main>
  </div><!-- /body -->

  <!-- Footer -->
  <div id="footer">
    <span class="status" id="footer-status"></span>
    <button class="btn-ghost" onclick="resetDefaults()">↩ Reset Defaults</button>
    <button class="btn-danger" onclick="pywebview.api.close_window()">✕ Cancel</button>
    <button class="btn-primary" onclick="saveAll()">💾 Save &amp; Apply</button>
  </div>

</div><!-- /app -->

<!-- Toast -->
<div id="toast"></div>

<script>
// ╔══════════════════════════════════════════════════════════════╗
// ║                       STATE                                  ║
// ╚══════════════════════════════════════════════════════════════╝
let S = {};          // current settings snapshot
let personas = [];
let selectedPersonaId = null;
let isLocked = false;

// ╔══════════════════════════════════════════════════════════════╗
// ║                       BOOT                                   ║
// ╚══════════════════════════════════════════════════════════════╝
window.addEventListener('pywebviewready', init);

async function init() {
  const ttsRes = JSON.parse(await pywebview.api.get_available_tts_models());
  if (ttsRes.ok) {
    const select = document.getElementById('en_tts');
    select.innerHTML = '';
    if (ttsRes.models.length === 0) {
      select.innerHTML = '<option value="">(No models found)</option>';
    } else {
      ttsRes.models.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        opt.textContent = m;
        select.appendChild(opt);
      });
    }
  }

  const raw = await pywebview.api.get_all_settings();
  S = JSON.parse(raw);
  applyToUI();
  await refreshPersonas();
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                  APPLY SETTINGS → UI                         ║
// ╚══════════════════════════════════════════════════════════════╝
function applyToUI() {
  // text inputs
  setText('user_name',           S.user_name        || '');
  setText('assistant_name',      S.assistant_name   || 'Jarvis');
  setText('user_location',       S.user_location    || 'Cairo');
  
  const ttsEl = document.getElementById('en_tts');
  if (ttsEl) ttsEl.value = S.en_tts || '';
  
  setText('main_stt',            S.main_stt         || '');
  setText('share_dir',           S.share_dir        || '');
  setText('run_dir',             S.run_dir          || '');
  setText('embedding_model',     S.embedding_model  || '');
  setText('quick_llm',           S.quick_llm        || 'auto_min');
  setText('main_llm',            S.main_llm         || 'auto_max');
  setText('local_api_url',       S.local_api_url    || 'http://localhost:11434');
  setText('llm_keep_alive_high_perf', (S.llm_keep_alive_high_perf || '15m').replace('m',''));
  setText('llm_keep_alive_normal',    (S.llm_keep_alive_normal    || '10m').replace('m',''));

  // llm toggles
  const qllm = S.quick_llm || 'auto_min';
  setCheck('quick_llm_auto', qllm === 'auto_min');
  toggleLlm('quick', false);

  const mllm = S.main_llm || 'auto_max';
  setCheck('main_llm_auto', mllm === 'auto_max');
  toggleLlm('main', false);

  // checkboxes / toggles
  setCheck('startup_show',        S.startup_show);
  setCheck('startup_with_os',     S.startup_with_os);
  setCheck('sound_effects',       S.sound_effects);
  setCheck('external_api',        S.external_api);
  setCheck('high_performance',    S.high_performance);
  setCheck('sub_high_performance',S.sub_high_performance);
  setCheck('dev_mode',            S.dev_mode);

  // sliders
  setSlider('volume',                  S.volume,                  'volume_val',           v=>`${v}%`);
  setSlider('followup_window',         S.followup_window,         'followup_window_val',  v=>`${v}s`);
  setSlider('task_snooze_minutes',     S.task_snooze_minutes,     'task_snooze_val',      v=>`${v} min`);
  setSlider('mic_pause_threshold',     S.mic_pause_threshold,     'mic_pause_val',        v=>`${parseFloat(v).toFixed(1)}s`);
  setSlider('mic_energy_threshold',    S.mic_energy_threshold,    'mic_energy_val',       v=>`${v}`);
  setSlider('tool_maximum',            S.tool_maximum,            'tool_max_val',         v=>`${v}`);
  setSlider('overthink_iterations',    S.overthink_iterations,    'overthink_iter_val',   v=>`${v}`);
  setSlider('fast_iterations',         S.fast_iterations,         'fast_iter_val',        v=>`${v}`);
  setSlider('history_limit',           Math.max(1, Math.floor((S.history_limit || 6) / 2)), 'history_val', v=>`${v} turns`);
  setSlider('max_syntax_corrections',  S.max_syntax_corrections,  'syntax_val',           v=>`${v}`);
  setSlider('llm_context_window',      S.llm_context_window,      'ctx_val',              v=>fmtK(v));
  setSlider('llm_max_tokens_normal',   S.llm_max_tokens_normal,   'max_tok_norm_val',     v=>`${v}`);
  setSlider('llm_max_tokens_overthink',S.llm_max_tokens_overthink,'max_tok_ot_val',       v=>`${v}`);
  setSlider('overthink_temperature',   S.overthink_temperature,   'ot_temp_val',          v=>parseFloat(v).toFixed(2));
  setSlider('warmup_timeout',          S.warmup_timeout,          'warmup_to_val',        v=>`${v}s`);
  setSlider('warmup_max_retries',      S.warmup_max_retries,      'warmup_ret_val',       v=>`${v}`);

  // wake words
  buildWakeTags(S.wake_word);
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                    UI HELPERS                                 ║
// ╚══════════════════════════════════════════════════════════════╝
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val;
}
function setCheck(id, val) {
  const el = document.getElementById(id);
  if (el) el.checked = !!val;
}
function setSlider(id, val, labelId, fmt) {
  const el = document.getElementById(id);
  if (!el) return;
  el.value = val;
  const lbl = document.getElementById(labelId);
  if (lbl) lbl.textContent = fmt(val);
}
function fmtK(v) {
  return v >= 1000 ? `${(v/1000).toFixed(0)}K` : `${v}`;
}

// ── Slider oninput helpers ──────────────────────────────────
function syncVal(el, labelId, suffix='') {
  document.getElementById(labelId).textContent = el.value + suffix;
}
function syncValF(el, labelId, decimals, suffix) {
  document.getElementById(labelId).textContent =
    parseFloat(el.value).toFixed(decimals) + suffix;
}
function syncValK(el, labelId) {
  document.getElementById(labelId).textContent = fmtK(el.value);
}

async function testVolume(val) {
  await pywebview.api.play_test_sound(val);
}

// ── Nav ────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
    item.classList.add('active');
    document.getElementById('page-' + item.dataset.page).classList.add('active');
  });
});

// ╔══════════════════════════════════════════════════════════════╗
// ║                    WAKE WORDS                                 ║
// ╚══════════════════════════════════════════════════════════════╝
let wakeWords = [];

function buildWakeTags(raw) {
  // wake_word stored as string — support comma-separated or single
  if (typeof raw === 'string') {
    wakeWords = raw.split(',').map(w=>w.trim()).filter(Boolean);
  } else if (Array.isArray(raw)) {
    wakeWords = raw.map(w=>w.trim()).filter(Boolean);
  } else {
    wakeWords = [];
  }
  renderTags();
}

function renderTags() {
  const container = document.getElementById('wake-tags');
  // remove old tags (keep input)
  container.querySelectorAll('.tag').forEach(t=>t.remove());
  const input = document.getElementById('wake-input');
  wakeWords.forEach((word, i) => {
    const tag = document.createElement('span');
    tag.className = 'tag';
    tag.innerHTML = `${word}<button class="del" onclick="removeWake(${i})">×</button>`;
    container.insertBefore(tag, input);
  });
}

function removeWake(i) {
  wakeWords.splice(i, 1);
  renderTags();
}

function wakeKeydown(e) {
  if (e.key === 'Enter' || e.key === ',') {
    e.preventDefault();
    const val = e.target.value.replace(',','').trim();
    if (val && !wakeWords.includes(val)) {
      wakeWords.push(val);
      renderTags();
    }
    e.target.value = '';
  }
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                  FOLDER / FILE BROWSE                         ║
// ╚══════════════════════════════════════════════════════════════╝
async function browseFolder(targetId) {
  const res = JSON.parse(await pywebview.api.pick_folder());
  if (res.ok) document.getElementById(targetId).value = res.path;
}

async function browseFile(targetId, exts=[]) {
  const res = JSON.parse(await pywebview.api.pick_file(JSON.stringify(exts)));
  if (res.ok) document.getElementById(targetId).value = res.path;
}

function toggleLlm(prefix, promptBrowse=true) {
  const isAuto = document.getElementById(prefix + '_llm_auto').checked;
  const row = document.getElementById(prefix + '_llm_row');
  row.style.display = isAuto ? 'none' : 'flex';
  if (promptBrowse && !isAuto && !document.getElementById(prefix + '_llm').value) {
    browseFile(prefix + '_llm', ['.gguf']);
  }
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                    COLLECT → SAVE                             ║
// ╚══════════════════════════════════════════════════════════════╝
function collectAll() {
  const d = {};

  // text
  ['user_name','assistant_name','user_location','en_tts','main_stt',
   'share_dir','run_dir','embedding_model', 'local_api_url']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = el.value ?? ''; 
  });

  // llm choices
  if (document.getElementById('quick_llm_auto')) {
      d['quick_llm'] = document.getElementById('quick_llm_auto').checked ? 'auto_min' : (document.getElementById('quick_llm').value || 'auto_min');
  }
  if (document.getElementById('main_llm_auto')) {
      d['main_llm'] = document.getElementById('main_llm_auto').checked ? 'auto_max' : (document.getElementById('main_llm').value || 'auto_max');
  }

  // llm keep alives
  ['llm_keep_alive_high_perf','llm_keep_alive_normal'].forEach(k => {
    const el = document.getElementById(k);
    if(el) {
        let val = el.value?.trim() || '';
        if (val !== '' && !val.endsWith('m')) val += 'm';
        d[k] = val;
    }
  });

  // bools
  ['startup_show','startup_with_os','sound_effects','external_api','high_performance',
   'sub_high_performance','dev_mode']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = el.checked ?? false; 
  });

  // ints
  ['volume','followup_window','task_snooze_minutes','mic_energy_threshold',
   'tool_maximum','overthink_iterations','fast_iterations',
   'max_syntax_corrections','llm_context_window','llm_max_tokens_normal',
   'llm_max_tokens_overthink','warmup_timeout','warmup_max_retries']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = parseInt(el.value) || 0; 
  });

  // special int
  const hl = document.getElementById('history_limit');
  if(hl) d['history_limit'] = (parseInt(hl.value) || 3) * 2;

  // floats
  ['mic_pause_threshold','overthink_temperature']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = parseFloat(el.value) || 0; 
  });

  // wake_word
  d['wake_word'] = wakeWords.join(',');

  return d;
}

async function saveAll() {
  if (document.getElementById('assistant_name').value.trim() === '') {
    toast('Assistant Name is mandatory', 'error');
    return;
  }
  if (wakeWords.length !== 1) {
    toast('You must specify exactly ONE wake word', 'error');
    return;
  }
  const data = collectAll();
  const res = JSON.parse(await pywebview.api.save_settings(JSON.stringify(data)));
  if (res.ok) {
    if (res.saved > 0) {
      toast(`✔ ${res.saved} settings updated`, 'success');
      showFooterStatus(`✔ Updated ${res.saved} settings`);
      Object.assign(S, data);
    } else {
      toast(`No changes to save`, 'success');
      showFooterStatus(`No settings were modified`);
    }
  } else {
    toast(`✕ Error: ${res.error}`, 'error');
  }
}

async function resetDefaults() {
  if (!confirm('Reset ALL settings to factory defaults?\n\nPersonas will not be affected.')) return;
  const res = JSON.parse(await pywebview.api.reset_defaults());
  if (res.ok) {
    S = res.settings;
    applyToUI();
    toast('↩ Defaults restored', 'success');
  }
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                      PERSONAS                                 ║
// ╚══════════════════════════════════════════════════════════════╝
async function refreshPersonas() {
  personas = JSON.parse(await pywebview.api.get_personas());
  renderPersonaList();
}

function renderPersonaList() {
  const list = document.getElementById('persona-list');
  list.innerHTML = '';
  personas.forEach(p => {
    const div = document.createElement('div');
    div.className = 'persona-item' + (p.id === selectedPersonaId ? ' active' : '');
    div.onclick = () => selectPersona(p.id);

    const badges = [];
    if (p.is_default) badges.push('<span class="pbadge default">★ Default</span>');
    if (p.is_locked)  badges.push('<span class="pbadge locked">🔒</span>');

    div.innerHTML = `
      <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${p.name}</span>
      <span class="badges">${badges.join('')}</span>
    `;
    list.appendChild(div);
  });
  
  updatePersonaDropdown();
}

function selectPersona(id) {
  selectedPersonaId = id;
  const p = personas.find(x=>x.id===id);
  if (!p) return;
  isLocked = p.is_locked;
  document.getElementById('persona-name').value   = p.name;
  document.getElementById('persona-name').disabled = isLocked;
  document.getElementById('persona-prompt').value = p.prompt;
  document.getElementById('persona-prompt').disabled = isLocked;
  document.getElementById('lock-badge').style.display = isLocked ? 'inline-block' : 'none';
  document.getElementById('persona-status').textContent = '';
  renderPersonaList();
}

async function changeActivePersona(id) {
  const res = JSON.parse(await pywebview.api.set_default_persona(parseInt(id)));
  if(res.ok) {
    toast('Active persona updated', 'success');
    refreshPersonas(); 
  }
}

function updatePersonaDropdown() {
  const select = document.getElementById('active_persona_select');
  if(!select) return;
  select.innerHTML = '';
  let activeId = null;
  personas.forEach(p => {
    if (p.is_default) activeId = p.id;
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = p.name;
    select.appendChild(opt);
  });
  if(activeId !== null) select.value = activeId;
}

function newPersona() {
  selectedPersonaId = null;
  isLocked = false;
  document.getElementById('persona-name').value   = 'New Persona';
  document.getElementById('persona-name').disabled = false;
  document.getElementById('persona-prompt').value =
    'TONE: Describe personality, speech style, and behavioral rules here.';
  document.getElementById('persona-prompt').disabled = false;
  document.getElementById('lock-badge').style.display = 'none';
  document.getElementById('persona-status').textContent = '';
  renderPersonaList();
}

async function savePersona() {
  if (isLocked) return flashPersonaStatus('System persona is read-only', false);
  const name   = document.getElementById('persona-name').value.trim();
  const prompt = document.getElementById('persona-prompt').value.trim();
  if (!name || !prompt) return flashPersonaStatus('Name and prompt required', false);

  let res;
  if (selectedPersonaId === null) {
    res = JSON.parse(await pywebview.api.add_persona(name, prompt));
  } else {
    res = JSON.parse(await pywebview.api.update_persona(selectedPersonaId, name, prompt));
  }
  await refreshPersonas();
  flashPersonaStatus(res.ok ? 'Saved ✔' : 'Error — check name', res.ok);
}

async function deletePersona() {
  if (selectedPersonaId === null) return;
  const p = personas.find(x=>x.id===selectedPersonaId);
  if (!p) return;
  if (p.is_locked) return flashPersonaStatus('Cannot delete system persona', false);
  if (!confirm(`Delete "${p.name}"?`)) return;
  const res = JSON.parse(await pywebview.api.delete_persona(selectedPersonaId));
  if (res.ok) { selectedPersonaId = null; }
  await refreshPersonas();
  flashPersonaStatus(res.ok ? 'Deleted' : 'Error', res.ok);
}

async function setDefaultPersona() {
  if (selectedPersonaId === null) return flashPersonaStatus('Select a persona first', false);
  const res = JSON.parse(await pywebview.api.set_default_persona(selectedPersonaId));
  await refreshPersonas();
  flashPersonaStatus(res.ok ? 'Default updated ✔' : 'Error', res.ok);
}

function flashPersonaStatus(msg, ok) {
  const el = document.getElementById('persona-status');
  el.textContent = msg;
  el.style.color = ok ? 'var(--green)' : 'var(--red)';
  setTimeout(() => el.textContent = '', 3000);
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                  TOAST / FOOTER STATUS                        ║
// ╚══════════════════════════════════════════════════════════════╝
let toastTimer;
function toast(msg, type='success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 3500);
}

function showFooterStatus(msg) {
  const el = document.getElementById('footer-status');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 4000);
}
</script>
</body>
</html>
"""


# ╔══════════════════════════════════════════════════════════════╗
# ║                       LAUNCHER                               ║
# ╚══════════════════════════════════════════════════════════════╝
def launch():
    # ─── Single Instance Enforcement (Settings Panel) ───
    from core.bootstrap.utils import enforce_single_instance
    if not enforce_single_instance("JARVIS_Settings_Mutex", "JARVIS NEXUS · Settings"):
        print("Settings panel is already open.")
        return

    api = API()
    window = webview.create_window(
        title       = "JARVIS NEXUS · Settings",
        html        = HTML,
        js_api      = api,
        width       = 1000,
        height      = 700,
        min_size    = (800, 560),
        resizable   = True,
        background_color = "#0d1117",
    )
    webview.start(debug=False)


if __name__ == "__main__":
    launch()