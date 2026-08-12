# core/ui/settings_panel.py  #? (Hmody: what do u think about pywebview idea? batter than other win xp looks, huh?)

"""
JARVIS NEXUS Settings Panel
===========================
Stable logic merged with Gold/Amber premium UI design.
All functionality preserved from original; only visual layer updated.
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
    from core.config import config, ConfigManager, SETTINGS_DB_PATH, TRAY_ICON_PATH
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
                if key not in config.settings:
                    config.set(key, value)
                    changed += 1
                else:
                    orig = config.settings[key]
                    
                    # Normalize type based on original config setting
                    if isinstance(orig, bool):
                        val = bool(value)
                    elif isinstance(orig, int):
                        try:
                            val = int(float(value)) # Handle JS sending float strings for ints
                        except:
                            val = orig
                    elif isinstance(orig, float):
                        try:
                            val = float(value)
                        except:
                            val = orig
                    else:
                        val = str(value) if value is not None else ""

                    if orig != val:
                        config.set(key, val)
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
# ║              PREMIUM HTML / UI (MERGED)                     ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>JARVIS NEXUS · Settings</title>
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
  --navy:           #1B3A5C;
  --navy-deep:      #0F1F33;
  --navy-mid:       #1a2d47;
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

/* ── Title Bar ────────────────────────────────────────────── */
#titlebar{
  display:flex;align-items:center;gap:16px;
  background:linear-gradient(180deg, var(--surface-1) 0%, var(--surface-2) 100%);
  padding:0 24px;height:60px;
  border-bottom:1px solid var(--border-default);
  flex-shrink:0;position:relative;z-index:10;
}
#titlebar::after{
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

.version-badge{
  margin-left:auto;
  background:rgba(201,162,39,0.1);
  border:1px solid var(--border-gold);
  color:var(--gold-light);
  font-size:11px;font-weight:700;
  padding:4px 12px;border-radius:20px;
  letter-spacing:0.5px;
}

/* ── Body Layout ──────────────────────────────────────────── */
#body{display:flex;flex:1;overflow:hidden;position:relative;z-index:1}

/* ── Sidebar ──────────────────────────────────────────────── */
#sidebar{
  width:220px;
  background:linear-gradient(180deg, var(--surface-1), var(--surface-2));
  border-right:1px solid var(--border-default);
  display:flex;flex-direction:column;
  flex-shrink:0;overflow-y:auto;
  padding:16px 10px;gap:3px;
}

.nav-group-label{
  font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:1.2px;color:var(--txt-muted);
  padding:12px 14px 6px;
}

.nav-item{
  display:flex;align-items:center;gap:12px;
  padding:11px 14px;border-radius:var(--radius-md);
  cursor:pointer;color:var(--txt-secondary);
  font-size:13px;font-weight:500;
  transition:all var(--trans-fast);
  user-select:none;position:relative;
  border:1px solid transparent;
}
.nav-item:hover{
  background:var(--surface-3);
  color:var(--txt-primary);
  border-color:var(--border-subtle);
}
.nav-item.active{
  background:linear-gradient(135deg, rgba(201,162,39,0.12), rgba(201,162,39,0.05));
  color:var(--gold-light);
  border-color:var(--border-gold);
  font-weight:600;
}
.nav-item.active::before{
  content:'';position:absolute;left:0;top:50%;transform:translateY(-50%);
  width:3px;height:20px;background:var(--gold);border-radius:0 3px 3px 0;
}
.nav-item .icon{
  width:20px;text-align:center;font-size:15px;
  transition:transform var(--trans-fast);
}
.nav-item:hover .icon{transform:scale(1.1)}
.nav-item.active .icon{color:var(--gold)}

.nav-sep{height:1px;background:var(--border-default);margin:10px 8px}

/* ── Content Area ───────────────────────────────────────── */
#content{
  flex:1;overflow-y:auto;padding:28px 32px;
  background:var(--bg);
}

/* ── Footer ─────────────────────────────────────────────── */
#footer{
  display:flex;align-items:center;padding:0 24px;height:58px;
  background:linear-gradient(180deg, var(--surface-2), var(--surface-1));
  border-top:1px solid var(--border-default);
  flex-shrink:0;gap:12px;position:relative;z-index:10;
}
#footer::before{
  content:'';position:absolute;top:-1px;left:0;right:0;
  height:1px;background:linear-gradient(90deg, transparent, var(--gold-glow-strong), transparent);
}
#footer .status{
  flex:1;font-size:12px;color:var(--green);
  opacity:0;transition:opacity .3s;
  display:flex;align-items:center;gap:6px;
}
#footer .status.show{opacity:1}
#footer .status::before{
  content:'';width:6px;height:6px;border-radius:50%;background:var(--green);
  box-shadow:0 0 8px var(--green);
}

/* ── Pages ────────────────────────────────────────────────── */
.page{display:none;animation:fadeIn 0.3s var(--ease-out)}
.page.active{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* ── Section Headers ──────────────────────────────────────── */
.section-header{margin-bottom:20px}
.section-title{
  font-size:20px;font-weight:700;color:var(--txt-primary);
  display:flex;align-items:center;gap:10px;
}
.section-title .accent-line{
  width:4px;height:24px;background:linear-gradient(180deg, var(--gold), var(--gold-dark));
  border-radius:2px;
}
.section-desc{
  font-size:12px;color:var(--txt-muted);margin-top:4px;margin-left:14px;
}

/* ── Cards (Glassmorphism) ───────────────────────────────── */
.card{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);
  margin-bottom:20px;
  overflow:hidden;
  transition:all var(--trans-normal);
  position:relative;
}
.card:hover{
  border-color:var(--border-active);
  box-shadow:var(--shadow-gold);
}
.card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent);
}

.card-header{
  display:flex;align-items:center;gap:12px;
  padding:14px 20px;
  border-bottom:1px solid var(--border-default);
  background:linear-gradient(90deg, rgba(201,162,39,0.05), transparent);
}
.card-header .icon{
  width:32px;height:32px;border-radius:var(--radius-sm);
  background:linear-gradient(135deg, rgba(201,162,39,0.15), rgba(201,162,39,0.05));
  border:1px solid var(--border-gold);
  display:flex;align-items:center;justify-content:center;
  font-size:15px;color:var(--gold);
}
.card-header .title{
  font-size:14px;font-weight:600;color:var(--txt-primary);
}
.card-header .title span{color:var(--gold);font-weight:700}

.card-body{padding:4px 0}

/* ── Rows ─────────────────────────────────────────────────── */
.row{
  display:flex;align-items:center;gap:20px;
  padding:14px 20px;
  border-bottom:1px solid var(--border-subtle);
  transition:background var(--trans-fast);
}
.row:hover{background:rgba(255,255,255,0.015)}
.row:last-child{border-bottom:none}

.row-left{min-width:240px;max-width:260px}
.row-left .label{
  font-size:13px;color:var(--txt-primary);font-weight:600;
  display:flex;align-items:center;gap:8px;
}
.row-left .label .req{
  font-size:9px;color:var(--red);font-weight:700;
  background:rgba(239,68,68,0.1);padding:1px 5px;border-radius:4px;
}
.row-left .hint{
  font-size:11px;color:var(--txt-muted);margin-top:4px;line-height:1.5;
}

.row-right{flex:1;display:flex;align-items:center;gap:10px;flex-wrap:wrap}

/* ── Inputs ───────────────────────────────────────────────── */
input[type=text],input[type=number],select,textarea{
  background:var(--surface-1);
  color:var(--txt-primary);
  border:1px solid var(--border-default);
  border-radius:var(--radius-md);
  padding:10px 14px;
  font-size:13px;font-family:inherit;
  outline:none;
  transition:all var(--trans-fast);
  width:100%;
}
input[type=text]:hover,input[type=number]:hover,
select:hover,textarea:hover{
  border-color:var(--border-active);
}
input[type=text]:focus,input[type=number]:focus,
select:focus,textarea:focus{
  border-color:var(--gold);
  box-shadow:0 0 0 3px var(--gold-glow), inset 0 1px 0 rgba(255,255,255,0.05);
}
input::placeholder{color:var(--txt-muted);opacity:0.6}

select{
  cursor:pointer;
  -webkit-appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='%23C9A227'%3E%3Cpath d='M7 10l5 5 5-5z'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 12px center;
  padding-right:34px;
}

textarea{
  resize:vertical;min-height:140px;
  font-family:"JetBrains Mono","Cascadia Code",monospace;
  font-size:12px;line-height:1.6;
}

.mono{font-family:"JetBrains Mono","Cascadia Code",monospace;font-size:12px}

/* Path input row */
.path-row{display:flex;gap:8px;width:100%}
.path-row input{flex:1;background:var(--surface-1)}
.path-row input:focus{box-shadow:0 0 0 2px var(--gold-glow)}

/* ── Toggle Switch (Premium) ────────────────────────────── */
.toggle{position:relative;width:48px;height:26px;flex-shrink:0}
.toggle input{opacity:0;width:0;height:0;position:absolute}
.toggle-track{
  position:absolute;inset:0;border-radius:13px;
  background:var(--surface-4);
  cursor:pointer;transition:all var(--trans-fast);
  border:1px solid var(--border-default);
}
.toggle input:checked + .toggle-track{
  background:linear-gradient(135deg, var(--gold-dark), var(--gold));
  border-color:var(--gold);
  box-shadow:0 0 12px rgba(201,162,39,0.3);
}
.toggle-thumb{
  position:absolute;top:4px;left:4px;
  width:18px;height:18px;border-radius:50%;
  background:linear-gradient(180deg, #fff, #e2e8f0);
  box-shadow:0 2px 4px rgba(0,0,0,0.3);
  transition:transform var(--trans-spring);
  pointer-events:none;
}
.toggle input:checked ~ .toggle-thumb{transform:translateX(22px)}

/* ── Slider (Premium) ───────────────────────────────────── */
.slider-wrap{display:flex;align-items:center;gap:14px;width:100%}
input[type=range]{
  flex:1;-webkit-appearance:none;height:5px;
  background:var(--surface-4);border-radius:3px;outline:none;cursor:pointer;
  border:1px solid var(--border-subtle);
}
input[type=range]::-webkit-slider-thumb{
  -webkit-appearance:none;width:18px;height:18px;border-radius:50%;
  background:linear-gradient(180deg, var(--gold-light), var(--gold));
  cursor:pointer;box-shadow:0 0 10px rgba(201,162,39,0.4), 0 2px 4px rgba(0,0,0,0.3);
  border:2px solid var(--gold-light);
  transition:all var(--trans-fast);
}
input[type=range]::-webkit-slider-thumb:hover{
  transform:scale(1.15);
  box-shadow:0 0 16px rgba(201,162,39,0.6);
}
.slider-val{
  min-width:56px;text-align:right;color:var(--gold-light);
  font-size:13px;font-weight:700;font-variant-numeric:tabular-nums;
  background:rgba(201,162,39,0.08);padding:4px 10px;border-radius:var(--radius-sm);
  border:1px solid var(--border-gold);
}

/* ── Buttons (Premium) ──────────────────────────────────── */
button{
  display:inline-flex;align-items:center;gap:8px;
  padding:9px 20px;border-radius:var(--radius-md);border:none;
  font-size:13px;font-weight:600;cursor:pointer;
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

.btn-primary{
  background:linear-gradient(135deg, var(--gold), var(--gold-dark));
  color:#0a0e14;box-shadow:0 4px 15px rgba(201,162,39,0.25);
}
.btn-primary:hover{
  box-shadow:0 6px 20px rgba(201,162,39,0.4);
  transform:translateY(-1px);
}

.btn-ghost{
  background:var(--surface-3);
  color:var(--txt-secondary);
  border:1px solid var(--border-default);
}
.btn-ghost:hover{
  background:var(--surface-4);color:var(--txt-primary);
  border-color:var(--border-active);
}

.btn-danger{
  background:rgba(239,68,68,0.08);
  color:var(--red);
  border:1px solid rgba(239,68,68,0.2);
}
.btn-danger:hover{
  background:rgba(239,68,68,0.15);border-color:rgba(239,68,68,0.4);
}

.btn-success{
  background:rgba(34,197,94,0.08);
  color:var(--green);
  border:1px solid rgba(34,197,94,0.2);
}
.btn-success:hover{
  background:rgba(34,197,94,0.15);border-color:rgba(34,197,94,0.4);
}

.btn-sm{padding:6px 14px;font-size:12px}
.btn-icon{padding:8px 12px;font-size:15px}

/* ── Wake Words Tags ──────────────────────────────────────── */
.tags{display:flex;flex-wrap:wrap;gap:8px;align-items:center;width:100%}
.tag{
  display:inline-flex;align-items:center;gap:6px;
  background:linear-gradient(135deg, rgba(201,162,39,0.12), rgba(201,162,39,0.05));
  border:1px solid var(--border-gold);
  border-radius:20px;padding:5px 14px;font-size:12px;
  color:var(--gold-light);font-weight:500;
  animation:tagIn 0.2s var(--ease-spring);
}
@keyframes tagIn{from{opacity:0;transform:scale(0.8)}to{opacity:1;transform:scale(1)}}
.tag .del{
  cursor:pointer;color:var(--txt-muted);font-size:14px;line-height:1;
  border:none;background:none;padding:0;width:16px;height:16px;
  display:flex;align-items:center;justify-content:center;
  border-radius:50%;transition:all var(--trans-fast);
}
.tag .del:hover{color:var(--red);background:rgba(239,68,68,0.1)}
.tag-input{
  flex:1;min-width:140px;background:var(--surface-1);
  border:1px solid var(--border-default);
  border-radius:20px;padding:6px 16px;font-size:12px;
  color:var(--txt-primary);outline:none;
  transition:all var(--trans-fast);
}
.tag-input:focus{border-color:var(--gold);box-shadow:0 0 0 3px var(--gold-glow)}

/* ── Personas Panel ───────────────────────────────────────── */
#personas-layout{display:flex;gap:20px;height:calc(100vh - 200px);min-height:400px}
#persona-list-panel{
  width:240px;flex-shrink:0;
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);
  display:flex;flex-direction:column;overflow:hidden;
  box-shadow:var(--shadow-md);
}
#persona-list-panel .plist-header{
  padding:14px 16px;
  background:linear-gradient(90deg, rgba(201,162,39,0.08), transparent);
  border-bottom:1px solid var(--border-default);
  font-size:12px;font-weight:700;color:var(--gold-light);
  display:flex;align-items:center;gap:8px;
  letter-spacing:0.5px;
}
#persona-list{flex:1;overflow-y:auto;padding:8px}
#persona-list::-webkit-scrollbar{width:4px}
.persona-item{
  padding:12px 14px;border-radius:var(--radius-md);cursor:pointer;
  font-size:13px;color:var(--txt-secondary);
  transition:all var(--trans-fast);
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:3px;border:1px solid transparent;
}
.persona-item:hover{
  background:var(--surface-3);color:var(--txt-primary);
  border-color:var(--border-subtle);
}
.persona-item.active{
  background:linear-gradient(135deg, rgba(201,162,39,0.12), rgba(201,162,39,0.05));
  color:var(--gold-light);border-color:var(--border-gold);
  font-weight:600;
}
.persona-item .badges{display:flex;gap:5px}
.pbadge{
  font-size:9px;padding:2px 8px;border-radius:10px;font-weight:700;
  letter-spacing:0.3px;white-space:nowrap;display:inline-flex;align-items:center;gap:4px;
}
.pbadge.default{background:rgba(34,197,94,0.12);color:var(--green);border:1px solid rgba(34,197,94,0.2)}
.pbadge.locked{background:rgba(234,179,8,0.12);color:var(--yellow);border:1px solid rgba(234,179,8,0.2)}

#persona-editor{
  flex:1;
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);
  display:flex;flex-direction:column;overflow:hidden;
  box-shadow:var(--shadow-md);
}
.editor-header{
  padding:16px 20px;
  background:linear-gradient(90deg, rgba(201,162,39,0.05), transparent);
  border-bottom:1px solid var(--border-default);
  display:flex;align-items:center;gap:12px;
}
.editor-header input{
  flex:1;background:transparent;border:none;
  font-size:16px;font-weight:700;color:var(--txt-primary);
  outline:none;padding:0;
}
.editor-header input:disabled{color:var(--txt-muted);cursor:not-allowed}
.locked-badge{
  font-size:11px;padding:4px 12px;border-radius:20px;
  background:rgba(234,179,8,0.1);color:var(--yellow);
  border:1px solid rgba(234,179,8,0.2);font-weight:600;
}
.editor-body{flex:1;padding:18px 20px;display:flex;flex-direction:column;gap:14px}
#persona-prompt{flex:1;min-height:0;border-radius:var(--radius-md)}
.editor-footer{
  padding:14px 20px;border-top:1px solid var(--border-default);
  display:flex;gap:10px;align-items:center;
  background:var(--surface-2);
}
.editor-status{font-size:12px;margin-left:auto;font-weight:600}
.plist-footer{
  padding:10px;border-top:1px solid var(--border-default);
  display:flex;gap:8px;background:var(--surface-2);
}

/* ── Toast Notification (Premium) ───────────────────────── */
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
#toast.success{border-color:rgba(34,197,94,0.3);color:var(--green)}
#toast.success::before{content:'\2713';width:22px;height:22px;border-radius:50%;background:rgba(34,197,68,0.15);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px}
#toast.error{border-color:rgba(239,68,68,0.3);color:var(--red)}
#toast.error::before{content:'!';width:22px;height:22px;border-radius:50%;background:rgba(239,68,68,0.15);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px}

/* ── Responsive ─────────────────────────────────────────── */
@media (max-width:900px){
  #sidebar{width:64px;padding:16px 6px}
  .nav-item{padding:12px;border-radius:var(--radius-sm);justify-content:center}
  .nav-item span:not(.icon){display:none}
  .nav-group-label{display:none}
  .nav-sep{margin:8px 0}
  .row{flex-direction:column;align-items:flex-start;gap:10px}
  .row-left{max-width:100%;min-width:auto}
  .row-right{width:100%}
}

/* ── SVG Icons ─────────────────────────────────────────── */
svg { vertical-align: middle; }
button svg { margin-top: -1px; width: 1.1em; height: 1.1em; }
.icon svg { width: 1.2em; height: 1.2em; }
.plist-header svg { width: 1.2em; height: 1.2em; margin-right: 4px; }
.tag svg { width: 1em; height: 1em; }
.logo-icon svg { width: 22px; height: 22px; color: #0a0e14; }

</style>
</head>
<body>
<div id="app">

  <!-- Title Bar -->
  <div id="titlebar">
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
        <div class="logo-main">JARVIS <span>Settings</span></div>
        <div class="logo-sub">Configuration Manager - v1</div>
      </div>
    </div>
    <div class="version-badge" id="version-badge">v__APP_VERSION__</div>
  </div>

  <!-- Body -->
  <div id="body">

    <!-- Sidebar -->
    <nav id="sidebar">
      <div class="nav-group-label">Settings</div>
      <div class="nav-item active" data-page="general">
        <span class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg></span> <span>General</span>
      </div>
      <div class="nav-item" data-page="audio">
        <span class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg></span> <span>Audio</span>
      </div>
      <div class="nav-item" data-page="ai">
        <span class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg></span> <span>AI / LLM</span>
      </div>
      <div class="nav-item" data-page="personas">
        <span class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg></span> <span>Personas</span>
      </div>
      <div class="nav-sep"></div>
      <div class="nav-group-label">System</div>
      <div class="nav-item" data-page="advanced">
        <span class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line><line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line><line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line><line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line><line x1="17" y1="16" x2="23" y2="16"></line></svg></span> <span>Advanced</span>
      </div>
    </nav>

    <!-- Content -->
    <main id="content">

      <!-- GENERAL -->
      <div class="page active" id="page-general">
        <div class="section-header">
          <div class="section-title"><div class="accent-line"></div>General Settings</div>
          <div class="section-desc">Configure your identity, startup behavior, and workspace paths</div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 3h20v18H2z"></path><circle cx="8" cy="10" r="3"></circle><path d="M2 18s2-4 6-4 6 4 6 4"></path><line x1="16" y1="8" x2="20" y2="8"></line><line x1="16" y1="12" x2="20" y2="12"></line><line x1="16" y1="16" x2="20" y2="16"></line></svg></div>
            <div class="title">Identity <span>Configuration</span></div>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="row-left">
                <div class="label">Your Name</div>
                <div class="hint">The name the AI assistant will use to address you</div>
              </div>
              <div class="row-right">
                <input type="text" id="user_name" placeholder="e.g. Ahmed">
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Assistant Name <span class="req">REQ</span></div>
                <div class="hint">AI display name - this is how the system identifies itself</div>
              </div>
              <div class="row-right">
                <input type="text" id="assistant_name" placeholder="Jarvis">
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Wake Word(s)</div>
                <div class="hint">Keyword to activate voice listening. Exactly one word required.</div>
              </div>
              <div class="row-right">
                <div class="tags" id="wake-tags">
                  <input class="tag-input" id="wake-input" placeholder="Type & press Enter..." onkeydown="wakeKeydown(event)">
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left">
                <div class="label">Your Location</div>
                <div class="hint">City for weather and timezone context awareness</div>
              </div>
              <div class="row-right">
                <input type="text" id="user_location" placeholder="Cairo">
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg></div>
            <div class="title">Startup <span>& Interface</span></div>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Startup Video</div><div class="hint">Plays an intro animation while AI models load</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="startup_show"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Start with OS</div><div class="hint">Launch JARVIS automatically with the operating system</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="startup_with_os"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Sound Effects</div><div class="hint">UI sounds - beeps, chimes, and listening indicators</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="sound_effects"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Results Panel</div><div class="hint">Show live results panel during task execution</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="results_panal"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Follow-up Window</div><div class="hint">Seconds the model listens without needing the wake word</div></div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="followup_window" min="3" max="60" step="1" oninput="syncVal(this,'followup_window_val')">
                  <span class="slider-val" id="followup_window_val">15s</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Use External API</div><div class="hint">Allow external connections for improved search results</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="external_api"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Task Snooze Duration</div><div class="hint">Default minutes to snooze a postponed task</div></div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="task_snooze_minutes" min="1" max="20" step="1" oninput="syncVal(this,'task_snooze_val')">
                  <span class="slider-val" id="task_snooze_val">5 min</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header">
            <div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path></svg></div>
            <div class="title">Workspace <span>Paths</span></div>
          </div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Shared Area</div><div class="hint">Folder JARVIS can freely read & write</div></div>
              <div class="row-right">
                <div class="path-row"><input type="text" id="share_dir" class="mono" readonly placeholder="Click Browse..."><button class="btn-ghost btn-sm" onclick="browseFolder('share_dir')"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="9" y1="14" x2="15" y2="14"></line><line x1="12" y1="11" x2="12" y2="17"></line></svg> Browse</button></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Results Directory</div><div class="hint">Where executed task markdown results are saved</div></div>
              <div class="row-right">
                <div class="path-row"><input type="text" id="results_dir" class="mono" readonly placeholder="Click Browse..."><button class="btn-ghost btn-sm" onclick="browseFolder('results_dir')"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="9" y1="14" x2="15" y2="14"></line><line x1="12" y1="11" x2="12" y2="17"></line></svg> Browse</button></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Run Directory</div><div class="hint">Working directory for executed tasks & scripts</div></div>
              <div class="row-right">
                <div class="path-row"><input type="text" id="run_dir" class="mono" readonly placeholder="Click Browse..."><button class="btn-ghost btn-sm" onclick="browseFolder('run_dir')"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="9" y1="14" x2="15" y2="14"></line><line x1="12" y1="11" x2="12" y2="17"></line></svg> Browse</button></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- AUDIO -->
      <div class="page" id="page-audio">
        <div class="section-header">
          <div class="section-title"><div class="accent-line"></div>Audio Configuration</div>
          <div class="section-desc">Manage playback, microphone sensitivity, and voice models</div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path><path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path></svg></div><div class="title">Playback <span>Settings</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Master Volume</div><div class="hint">TTS speech output level</div></div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="volume" min="0" max="100" step="1" oninput="syncVal(this,'volume_val')" onchange="testVolume(this.value)">
                  <span class="slider-val" id="volume_val">70%</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg></div><div class="title">Microphone <span>Input</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Pause Threshold</div><div class="hint">Seconds of silence before end-of-speech detection</div></div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="mic_pause_threshold" min="0.1" max="3" step="0.1" oninput="syncValF(this,'mic_pause_val',1,'s')">
                  <span class="slider-val" id="mic_pause_val">0.8s</span>
                </div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Energy Threshold</div><div class="hint">Mic sensitivity - raise to reduce background noise</div></div>
              <div class="row-right">
                <div class="slider-wrap">
                  <input type="range" id="mic_energy_threshold" min="50" max="1000" step="10" oninput="syncVal(this,'mic_energy_val')">
                  <span class="slider-val" id="mic_energy_val">300</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg></div><div class="title">Voice <span>Models</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">English TTS Voice</div><div class="hint">Available voices in models/tts folder</div></div>
              <div class="row-right"><select id="en_tts"></select></div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">STT Model Path</div><div class="hint">Listening model folder</div></div>
              <div class="row-right">
                <div class="path-row"><input type="text" id="main_stt" class="mono" readonly><button class="btn-ghost btn-sm" onclick="browseFolder('main_stt')"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="9" y1="14" x2="15" y2="14"></line><line x1="12" y1="11" x2="12" y2="17"></line></svg> Browse</button></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- AI / LLM -->
      <div class="page" id="page-ai">
        <div class="section-header">
          <div class="section-title"><div class="accent-line"></div>AI & LLM Configuration</div>
          <div class="section-desc">Model selection, performance tuning, and cognitive parameters</div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"></rect><rect x="9" y="9" width="6" height="6"></rect><line x1="9" y1="1" x2="9" y2="4"></line><line x1="15" y1="1" x2="15" y2="4"></line><line x1="9" y1="20" x2="9" y2="23"></line><line x1="15" y1="20" x2="15" y2="23"></line><line x1="20" y1="9" x2="23" y2="9"></line><line x1="20" y1="14" x2="23" y2="14"></line><line x1="1" y1="9" x2="4" y2="9"></line><line x1="1" y1="14" x2="4" y2="14"></line></svg></div><div class="title">Model <span>Selection</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Quick LLM</div><div class="hint">Fast lightweight model for simple queries</div></div>
              <div class="row-right">
                <label class="toggle" style="margin-right:4px"><input type="checkbox" id="quick_llm_auto" onchange="toggleLlm('quick')"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
                <span style="font-size:12px;color:var(--txt-muted);margin-right:10px">Auto</span>
                <div class="path-row" id="quick_llm_row" style="flex:1"><input type="text" id="quick_llm" class="mono" readonly placeholder="Custom .gguf path..."><button class="btn-ghost btn-sm" onclick="browseFile('quick_llm',['.gguf'])"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="9" y1="14" x2="15" y2="14"></line><line x1="12" y1="11" x2="12" y2="17"></line></svg> Browse</button></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Main LLM</div><div class="hint">Full-size model for complex tasks and reasoning</div></div>
              <div class="row-right">
                <label class="toggle" style="margin-right:4px"><input type="checkbox" id="main_llm_auto" onchange="toggleLlm('main')"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
                <span style="font-size:12px;color:var(--txt-muted);margin-right:10px">Auto</span>
                <div class="path-row" id="main_llm_row" style="flex:1"><input type="text" id="main_llm" class="mono" readonly placeholder="Custom .gguf path..."><button class="btn-ghost btn-sm" onclick="browseFile('main_llm',['.gguf'])"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path><line x1="9" y1="14" x2="15" y2="14"></line><line x1="12" y1="11" x2="12" y2="17"></line></svg> Browse</button></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Embedding Model</div><div class="hint">Ollama embedding model name (e.g., all-minilm)</div></div>
              <div class="row-right"><input type="text" id="embedding_model" placeholder="all-minilm" class="mono"></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg></div><div class="title">Performance <span>Mode</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">High Performance Mode</div><div class="hint">Keep models alive in RAM between conversations</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="high_performance"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Sub High Performance</div><div class="hint">Keep secondary models resident. <span style="color:var(--red)"> DO NOT USE</span> on 4GB RAM</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="sub_high_performance"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 0 7 4.5v15A2.5 2.5 0 0 0 9.5 22h5a2.5 2.5 0 0 0 2.5-2.5v-15A2.5 2.5 0 0 0 14.5 2h-5z"></path><path d="M2 12h5"></path><path d="M17 12h5"></path><path d="M3 7h4"></path><path d="M17 7h4"></path><path d="M3 17h4"></path><path d="M17 17h4"></path></svg></div><div class="title">Cognitive <span>Settings</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Active Persona</div><div class="hint">The core personality and behavior rules</div></div>
              <div class="row-right"><select id="active_persona_select" onchange="changeActivePersona(this.value)"></select></div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Max Tool Calls / Turn</div><div class="hint">Maximum tools the model can call in a single cycle</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="tool_maximum" min="1" max="15" step="1" oninput="syncVal(this,'tool_max_val')"><span class="slider-val" id="tool_max_val">5</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Fast Mode Iterations</div><div class="hint">Free thinking cycles in normal conversation mode</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="fast_iterations" min="1" max="20" step="1" oninput="syncVal(this,'fast_iter_val')"><span class="slider-val" id="fast_iter_val">5</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Overthink Iterations</div><div class="hint">Maximum cycles in deep-analysis overthink mode</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="overthink_iterations" min="1" max="30" step="1" oninput="syncVal(this,'overthink_iter_val')"><span class="slider-val" id="overthink_iter_val">8</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">History Limit</div><div class="hint">Conversation turns kept in active context window</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="history_limit" min="1" max="20" step="1" oninput="syncVal(this,'history_val')"><span class="slider-val" id="history_val">3 turns</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Max Syntax Corrections</div><div class="hint">Retries when model fails a request or execution</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="max_syntax_corrections" min="0" max="5" step="1" oninput="syncVal(this,'syntax_val')"><span class="slider-val" id="syntax_val">1</span></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- PERSONAS -->
      <div class="page" id="page-personas">
        <div class="section-header">
          <div class="section-title"><div class="accent-line"></div>Persona Manager</div>
          <div class="section-desc">Create, edit, and manage AI personality profiles</div>
        </div>

        <div id="personas-layout">
          <div id="persona-list-panel">
            <div class="plist-header"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg> Personas</div>
            <div id="persona-list"></div>
            <div class="plist-footer">
              <button class="btn-success btn-sm" style="flex:1" onclick="newPersona()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg> New</button>
              <button class="btn-danger btn-sm" style="flex:1" onclick="deletePersona()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> Delete</button>
            </div>
          </div>
          <div id="persona-editor">
            <div class="editor-header">
              <input type="text" id="persona-name" placeholder="Persona name...">
              <span class="locked-badge" id="lock-badge" style="display:none"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg> System</span>
            </div>
            <div class="editor-body">
              <div style="font-size:11px;color:var(--txt-muted);font-weight:500;letter-spacing:0.5px;text-transform:uppercase">Personality & Behavior Prompt</div>
              <textarea id="persona-prompt" placeholder="Describe tone, speech style, behavioral rules, and personality traits..."></textarea>
            </div>
            <div class="editor-footer">
              <button class="btn-primary btn-sm" onclick="savePersona()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path><polyline points="17 21 17 13 7 13 7 21"></polyline><polyline points="7 3 7 8 15 8"></polyline></svg> Save</button>
              <button class="btn-success btn-sm" onclick="setDefaultPersona()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> Set as Default</button>
              <span class="editor-status" id="persona-status"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- ADVANCED -->
      <div class="page" id="page-advanced">
        <div class="section-header">
          <div class="section-title"><div class="accent-line"></div>Advanced Settings</div>
          <div class="section-desc">API endpoints, context tuning, and developer options</div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg></div><div class="title">API <span>& Connectivity</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Local API URL</div><div class="hint">Ollama / LM Studio endpoint address</div></div>
              <div class="row-right"><input type="text" id="local_api_url" class="mono" placeholder="http://localhost:11434"></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"></ellipse><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"></path><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"></path></svg></div><div class="title">Context <span>& Tokens</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Context Window</div><div class="hint">Total token budget per LLM call (minimum 4608)</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="llm_context_window" min="4608" max="32768" step="512" oninput="syncValK(this,'ctx_val')"><span class="slider-val" id="ctx_val">4608</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Max Tokens - Normal</div><div class="hint">Output cap in standard response mode</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="llm_max_tokens_normal" min="128" max="4608" step="64" oninput="syncVal(this,'max_tok_norm_val')"><span class="slider-val" id="max_tok_norm_val">1024</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Max Tokens - Overthink</div><div class="hint">Output cap in deep-analysis mode</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="llm_max_tokens_overthink" min="256" max="8192" step="128" oninput="syncVal(this,'max_tok_ot_val')"><span class="slider-val" id="max_tok_ot_val">2048</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Overthink Temperature</div><div class="hint">Creativity in deep-analysis mode (0.0 - 1.0)</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="overthink_temperature" min="0" max="1" step="0.05" oninput="syncValF(this,'ot_temp_val',2,'')"><span class="slider-val" id="ot_temp_val">0.30</span></div>
              </div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"></path></svg></div><div class="title">Model <span>Warm-up</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Warmup Timeout (s)</div><div class="hint">Seconds to wait for model to become ready</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="warmup_timeout" min="10" max="300" step="5" oninput="syncVal(this,'warmup_to_val','s')"><span class="slider-val" id="warmup_to_val">60s</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Warmup Max Retries</div><div class="hint">Ping attempts during model startup</div></div>
              <div class="row-right">
                <div class="slider-wrap"><input type="range" id="warmup_max_retries" min="1" max="20" step="1" oninput="syncVal(this,'warmup_ret_val')"><span class="slider-val" id="warmup_ret_val">5</span></div>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Keep-Alive (High Perf.)</div><div class="hint">e.g. <code style="color:var(--gold)">15</code> or <code style="color:var(--gold)">-1</code> (forever)</div></div>
              <div class="row-right"><input type="number" id="llm_keep_alive_high_perf" class="mono" style="max-width:100px" placeholder="15"><span style="font-size:12px;color:var(--txt-muted)">minutes</span></div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Keep-Alive (Normal)</div><div class="hint">e.g. <code style="color:var(--gold)">10</code></div></div>
              <div class="row-right"><input type="number" id="llm_keep_alive_normal" class="mono" style="max-width:100px" placeholder="10"><span style="font-size:12px;color:var(--txt-muted)">minutes</span></div>
            </div>
          </div>
        </div>

        <div class="card">
          <div class="card-header"><div class="icon"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg></div><div class="title">Developer <span>Options</span></div></div>
          <div class="card-body">
            <div class="row">
              <div class="row-left"><div class="label">Developer Mode</div><div class="hint">Full background logging between System/LLM and tool name announcements</div></div>
              <div class="row-right">
                <label class="toggle"><input type="checkbox" id="dev_mode"><div class="toggle-track"></div><div class="toggle-thumb"></div></label>
              </div>
            </div>
            <div class="row">
              <div class="row-left"><div class="label">Re-run Setup Wizard</div><div class="hint">Launch the Environment Setup tool to manage models and assets</div></div>
              <div class="row-right">
                <button class="btn-ghost btn-sm" onclick="pywebview.api.launch_setup_wizard()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></svg> Open Setup</button>
              </div>
            </div>
          </div>
        </div>
      </div>

    </main>
  </div>

  <!-- Footer -->
  <div id="footer">
    <span class="status" id="footer-status"></span>
    <button class="btn-ghost" onclick="resetDefaults()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="1 4 1 10 7 10"></polyline><polyline points="23 20 23 14 17 14"></polyline><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"></path></svg> Reset Defaults</button>
    <button class="btn-danger" onclick="pywebview.api.close_window()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Cancel</button>
    <button class="btn-primary" onclick="saveAll()"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg> Save & Apply</button>
  </div>

</div>

<div id="toast"></div>

<script>
// ╔══════════════════════════════════════════════════════════════╗
// ║                  ORIGINAL STABLE LOGIC                      ║
// ╚══════════════════════════════════════════════════════════════╝
let S = {};
let personas = [];
let selectedPersonaId = null;
let isLocked = false;

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

function applyToUI() {
  setText('user_name',           S.user_name        ?? '');
  setText('assistant_name',      S.assistant_name   ?? '');
  setText('user_location',       S.user_location    ?? '');
  
  const ttsEl = document.getElementById('en_tts');
  if (ttsEl) ttsEl.value = S.en_tts ?? '';
  
  setText('main_stt',            S.main_stt         ?? '');
  setText('share_dir',           S.share_dir        ?? '');
  setText('run_dir',             S.run_dir          ?? '');
  setText('results_dir',         S.results_dir      ?? '');
  setText('embedding_model',     S.embedding_model  ?? '');
  setText('quick_llm',           S.quick_llm        ?? '');
  setText('main_llm',            S.main_llm         ?? '');
  setText('local_api_url',       S.local_api_url    ?? '');
  setText('llm_keep_alive_high_perf', String(S.llm_keep_alive_high_perf ?? '').replace('m',''));
  setText('llm_keep_alive_normal',    String(S.llm_keep_alive_normal    ?? '').replace('m',''));

  const qllm = S.quick_llm ?? 'auto_min';
  setCheck('quick_llm_auto', qllm === 'auto_min');
  toggleLlm('quick', false);

  const mllm = S.main_llm ?? 'auto_max';
  setCheck('main_llm_auto', mllm === 'auto_max');
  toggleLlm('main', false);

  setCheck('startup_show',        S.startup_show);
  setCheck('startup_with_os',     S.startup_with_os);
  setCheck('sound_effects',       S.sound_effects);
  setCheck('external_api',        S.external_api);
  setCheck('high_performance',    S.high_performance);
  setCheck('sub_high_performance',S.sub_high_performance);
  setCheck('dev_mode',            S.dev_mode);

  setSlider('volume',                  S.volume,                  'volume_val',           v=>`${v}%`);
  setSlider('followup_window',         S.followup_window,         'followup_window_val',  v=>`${v}s`);
  setSlider('task_snooze_minutes',     S.task_snooze_minutes,     'task_snooze_val',      v=>`${v} min`);
  setSlider('mic_pause_threshold',     S.mic_pause_threshold,     'mic_pause_val',        v=>`${parseFloat(v).toFixed(1)}s`);
  setSlider('mic_energy_threshold',    S.mic_energy_threshold,    'mic_energy_val',       v=>`${v}`);
  setSlider('tool_maximum',            S.tool_maximum,            'tool_max_val',         v=>`${v}`);
  setSlider('overthink_iterations',    S.overthink_iterations,    'overthink_iter_val',   v=>`${v}`);
  setSlider('fast_iterations',         S.fast_iterations,         'fast_iter_val',        v=>`${v}`);
  setSlider('history_limit',           Math.max(1, S.history_limit || 3), 'history_val', v=>`${v} turns`);
  setSlider('max_syntax_corrections',  S.max_syntax_corrections,  'syntax_val',           v=>`${v}`);
  setSlider('llm_context_window',      S.llm_context_window,      'ctx_val',              v=>fmtK(v));
  setSlider('llm_max_tokens_normal',   S.llm_max_tokens_normal,   'max_tok_norm_val',     v=>`${v}`);
  setSlider('llm_max_tokens_overthink',S.llm_max_tokens_overthink,'max_tok_ot_val',       v=>`${v}`);
  setSlider('overthink_temperature',   S.overthink_temperature,   'ot_temp_val',          v=>parseFloat(v).toFixed(2));
  setSlider('warmup_timeout',          S.warmup_timeout,          'warmup_to_val',        v=>`${v}s`);
  setSlider('warmup_max_retries',      S.warmup_max_retries,      'warmup_ret_val',       v=>`${v}`);

  buildWakeTags(S.wake_word);
}

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

function collectAll() {
  const d = {};

  ['user_name','assistant_name','user_location','en_tts','main_stt',
   'share_dir','run_dir','results_dir','embedding_model', 'local_api_url']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = el.value ?? ''; 
  });

  if (document.getElementById('quick_llm_auto')) {
      d['quick_llm'] = document.getElementById('quick_llm_auto').checked ? 'auto_min' : (document.getElementById('quick_llm').value || 'auto_min');
  }
  if (document.getElementById('main_llm_auto')) {
      d['main_llm'] = document.getElementById('main_llm_auto').checked ? 'auto_max' : (document.getElementById('main_llm').value || 'auto_max');
  }

  ['llm_keep_alive_high_perf','llm_keep_alive_normal'].forEach(k => {
    const el = document.getElementById(k);
    if(el) {
        let val = el.value?.trim() || '';
        val = val.replace('m', '');
        d[k] = val !== '' ? Number(val) : (k === 'llm_keep_alive_high_perf' ? 15 : 10);
    }
  });

  ['startup_show','startup_with_os','sound_effects','external_api','high_performance',
   'sub_high_performance','dev_mode', 'results_panal']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = el.checked ?? false; 
  });

  ['volume','followup_window','task_snooze_minutes','mic_energy_threshold',
   'tool_maximum','overthink_iterations','fast_iterations',
   'max_syntax_corrections','llm_context_window','llm_max_tokens_normal',
   'llm_max_tokens_overthink','warmup_timeout','warmup_max_retries']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = parseInt(el.value) || 0; 
  });

  const hl = document.getElementById('history_limit');
  if(hl) d['history_limit'] = parseInt(hl.value) || 3;

  ['mic_pause_threshold','overthink_temperature']
  .forEach(k => { 
    const el = document.getElementById(k);
    if(el) d[k] = parseFloat(el.value) || 0; 
  });

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
  if (!(await customConfirm('Reset ALL settings to factory defaults?<br><br>Personas will not be affected.'))) return;
  const res = JSON.parse(await pywebview.api.reset_defaults());
  if (res.ok) {
    S = res.settings;
    applyToUI();
    toast('↩ Defaults restored', 'success');
  }
}

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
    if (p.is_locked)  badges.push('<span class="pbadge locked"><svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg></span>');

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
  if (!(await customConfirm(`Delete "${p.name}"?`))) return;
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

function customConfirm(msg) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-overlay');
    document.getElementById('modal-msg').innerHTML = msg;
    overlay.style.display = 'flex';
    document.getElementById('modal-ok').onclick = () => { overlay.style.display = 'none'; resolve(true); };
    document.getElementById('modal-cancel').onclick = () => { overlay.style.display = 'none'; resolve(false); };
  });
}
</script>

<div id="modal-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);z-index:1000;align-items:center;justify-content:center;">
  <div class="card" style="width:360px;margin:0;box-shadow:var(--shadow-lg);animation:tagIn 0.2s var(--ease-spring);">
    <div class="card-header" style="border-bottom:1px solid var(--border-default);padding:16px 20px">
      <div class="icon">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--yellow)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
      </div>
      <div class="title" style="margin-left:10px;font-size:15px;color:var(--txt-primary)">Confirm Action</div>
    </div>
    <div class="card-body" style="padding:20px;font-size:13px;color:var(--txt-secondary);line-height:1.5" id="modal-msg"></div>
    <div style="padding:14px 20px;border-top:1px solid var(--border-default);display:flex;justify-content:flex-end;gap:10px;background:var(--surface-2);border-bottom-left-radius:12px;border-bottom-right-radius:12px">
      <button class="btn-ghost btn-sm" id="modal-cancel">Cancel</button>
      <button class="btn-primary btn-sm" id="modal-ok">Confirm</button>
    </div>
  </div>
</div>

</body>
</html>
"""


# ╔══════════════════════════════════════════════════════════════╗
# ║                       LAUNCHER                               ║
# ╚══════════════════════════════════════════════════════════════╝
def launch():
    from core.bootstrap.utils import enforce_single_instance
    if not enforce_single_instance("JARVIS_Settings_Mutex", "JARVIS NEXUS · Settings"):
        print("Settings panel is already open.")
        return

    import os
    os.environ.setdefault(
        'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS',
        '--disable-background-networking --disable-component-update --disable-domain-reliability'
    )

    from core.config import get_setting, APP_VERSION

    html_content = HTML.replace('v__APP_VERSION__', f'v{APP_VERSION}')

    api = API()
    window = webview.create_window(
        title       = "JARVIS NEXUS · Settings",
        html        = html_content,
        js_api      = api,
        width       = 1000,
        height      = 700,
        min_size    = (800, 560),
        resizable   = True,
        background_color = "#0a0e14",
    )
    webview.start(debug=False, icon=TRAY_ICON_PATH)


if __name__ == "__main__":
    launch()