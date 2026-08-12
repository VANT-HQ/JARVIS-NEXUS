# core/ui/results_viewer.py
"""
JARVIS NEXUS – Premium Live Markdown Results Viewer
====================================================
Merged stable logic with Gold/Amber premium design.
All original functionality preserved; only UI layer updated.
"""

import sys
import json
import webview
import re
from pathlib import Path
from datetime import datetime
import os

# ── Import config ──────────────────────────────────────────────
try:
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
    from core.config import config, get_setting, CACHE_DIR, TRAY_ICON_PATH, SHARE_DIR
except ImportError as e:
    import tkinter as tk
    from tkinter import messagebox
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Import Error", f"Cannot load core/config.py\n{e}")
    sys.exit(1)

# Global reference for live feed (set when window is created in live mode)
_live_window = None

# ── Helper: clean display name from a result filename ──────────
def _clean_display_name(filename: str) -> str:
    """
    Cleans filename to a readable format.
    E.g., 'Live_Diagnostic_Report_01072026_result.md' -> 'Live Diagnostic Report (01-07-2026)'
    """
    stem = Path(filename).stem
    
    # Check if it has the date and result suffix
    match = re.search(r'_(\d{2})(\d{2})(\d{4})_result$', stem)
    if match:
        day, month, year = match.groups()
        name_part = stem[:match.start()].replace("_", " ")
        return f"{name_part} ({day}-{month}-{year})"
        
    # Fallback if pattern doesn't perfectly match but ends in _result
    cleaned = re.sub(r'_\d*_?result$', '', stem)
    return cleaned.replace("_", " ").strip()

# ╔══════════════════════════════════════════════════════════════╗
# ║                   PYTHON ↔ JS BRIDGE                         ║
# ╚══════════════════════════════════════════════════════════════╝
class API:
    """
    Exposed to JavaScript via `window.pywebview.api.*`
    """

    def __init__(self):
        self._results_dir = Path(get_setting("results_dir", str(SHARE_DIR / "results")))
        self._results_dir.mkdir(parents=True, exist_ok=True)
        # For live mode accumulation
        self._live_content = ""
        self._live_filename = None
        self.is_ready = False

    # ── File listing ─────────────────────────────────────────
    def get_results_list(self) -> str:
        """Return JSON list of {filename, display_name} for all result files."""
        results = []
        for f in sorted(self._results_dir.glob("*_result.*"), key=os.path.getmtime, reverse=True):
            if f.suffix.lower() in ('.md', '.txt'):
                results.append({
                    "filename": f.name,
                    "display_name": _clean_display_name(f.name),
                    "timestamp": os.path.getmtime(f)
                })
        return json.dumps({"ok": True, "files": results})

    # ── Load content ─────────────────────────────────────────
    def rename_result(self, old_filename: str, new_display_name: str) -> str:
        if not old_filename or not new_display_name: return json.dumps({"ok": False})
        try:
            target = self._results_dir / old_filename
            if target.exists():
                clean_name = new_display_name.strip().lower().replace(" ", "_")
                if not clean_name.endswith("_result.md"):
                    clean_name += "_result.md"
                new_target = self._results_dir / clean_name
                target.rename(new_target)
                return json.dumps({"ok": True, "new_filename": clean_name})
            return json.dumps({"ok": False, "error": "Not found"})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def delete_result(self, filename: str) -> str:
        if not filename: return json.dumps({"ok": False})
        try:
            target = self._results_dir / filename
            if target.exists():
                trash_dir = self._results_dir.parent / ".nexus_trash"
                trash_dir.mkdir(parents=True, exist_ok=True)
                timestamp = __import__("datetime").datetime.now().strftime("%Y%m%d_%H%M%S")
                trashed_name = f"{target.stem}_deleted_{timestamp}{target.suffix}"
                import shutil
                shutil.move(str(target), str(trash_dir / trashed_name))
                return json.dumps({"ok": True})
            return json.dumps({"ok": False, "error": "Not found"})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    def load_result_content(self, filename: str) -> str:
        """Read the full content of a result file."""
        filepath = self._results_dir / filename
        if filepath.exists():
            try:
                content = filepath.read_text(encoding='utf-8')
                return json.dumps({"ok": True, "content": content})
            except Exception as e:
                return json.dumps({"ok": False, "error": str(e)})
        return json.dumps({"ok": False, "error": "File not found"})

    # ── Save content (for future edit mode) ──────────────────
    def save_result_content(self, filename: str, content: str) -> str:
        """Save edited content back to disk."""
        filepath = self._results_dir / filename
        try:
            filepath.write_text(content, encoding='utf-8')
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── Live mode: push text from Python side ────────────────
    def notify_live_ready(self) -> str:
        """Called when the live viewer is ready to receive data.
        We set the internal live content to empty and return status."""
        self._live_content = ""
        self.is_ready = True
        return json.dumps({"ok": True})

    def get_live_content(self) -> str:
        """Called by JS polling to get the latest live content."""
        try:
            cache_dir = CACHE_DIR
            sync_file = cache_dir / ".live_stream.md"
            if sync_file.exists():
                content = sync_file.read_text(encoding='utf-8')
                mtime = sync_file.stat().st_mtime
                return json.dumps({"ok": True, "content": content, "mtime": mtime})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})
        return json.dumps({"ok": True, "content": "", "mtime": 0})

    def close_window(self):
        try:
            if webview.windows:
                webview.windows[0].destroy()
        except Exception:
            pass
        return json.dumps({"ok": True})


# ╔══════════════════════════════════════════════════════════════╗
# ║         PREMIUM HTML / CSS / JS (GOLD THEME MERGED)         ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>JARVIS NEXUS · Results</title>
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
  --syn-comment:    #6b7280;
  --syn-string:     #d7b98e;
  --syn-keyword:    #c9a3ff;
  --syn-number:     #7dd3fc;
  --syn-function:   #6ee7c8;
  --syn-bracket:    #94a3b8;
  --txt-read:       #aebbcb;
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

#mode-badge{
  background:linear-gradient(135deg, var(--gold-dark), var(--gold));
  color:#0a0e14;
  font-size:10px;font-weight:700;
  padding:3px 12px;border-radius:20px;
  letter-spacing:0.5px;
}
#mode-badge:empty{display:none}

#title-options{display:flex;align-items:center;gap:12px;transition:opacity 1.5s ease;}

/* ── Body Layout ──────────────────────────────────────────── */
#body{display:flex;flex:1;overflow:hidden;position:relative;z-index:1}

/* ── Sidebar ──────────────────────────────────────────────── */
#sidebar{
  width:260px;
  background:linear-gradient(180deg, var(--surface-1), var(--surface-2));
  border-right:1px solid var(--border-default);
  display:flex;flex-direction:column;
  flex-shrink:0;overflow-y:auto;
  padding:16px 10px;gap:8px;
}

.search-box{padding:0 8px 12px;}
.search-box input{
  width:100%;
  background:var(--surface-1);
  border:1px solid var(--border-default);
  border-radius:20px;
  padding:8px 16px;
  font-size:13px;
  color:var(--txt-primary);
  outline:none;
  transition:all var(--trans-fast);
}
.search-box input:focus{
  border-color:var(--gold);
  box-shadow:0 0 0 3px var(--gold-glow);
}

#file-list{flex:1;overflow-y:auto}
#file-list::-webkit-scrollbar{width:4px}
#file-list::-webkit-scrollbar-thumb{background:rgba(255,255,255,0.08);border-radius:2px}

.file-item{
  padding:10px 14px;border-radius:var(--radius-md);
  cursor:pointer;color:var(--txt-secondary);
  font-size:13px;font-weight:500;
  transition:all var(--trans-fast);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  position:relative;
  border:1px solid transparent;
  margin-bottom:2px;
}
.file-item:hover{
  background:var(--surface-3);
  color:var(--txt-primary);
  border-color:var(--border-subtle);
}
.file-item.active{
  background:linear-gradient(135deg, rgba(201,162,39,0.12), rgba(201,162,39,0.05));
  color:var(--gold-light);
  border-color:var(--border-gold);
  font-weight:600;
}

.file-item .item-actions{
  display:none;position:absolute;right:8px;top:50%;transform:translateY(-50%);
  color:var(--txt-muted);padding:4px 8px;border-radius:6px;cursor:pointer;
  font-size:16px;line-height:1;
  background:var(--surface-2);
  border:1px solid var(--border-subtle);
  transition:all var(--trans-fast);
}
.file-item:hover .item-actions{display:block}
.file-item .item-actions:hover{background:var(--surface-4);color:var(--gold-light)}

.sidebar-divider{
  border:0;height:1px;background:var(--border-default);margin:8px 12px;
}

.live-item{
  color:var(--gold-light) !important;
  font-weight:600;
  background:rgba(201,162,39,0.08);
  border-color:var(--border-gold);
}
.live-indicator{
  display:inline-block;
  width:8px;height:8px;
  background:var(--gold);
  border-radius:50%;
  margin-right:10px;
  animation:pulse 1.5s infinite;
  box-shadow:0 0 8px var(--gold);
}

.unread-dot{
  display:inline-block;
  width:8px;height:8px;
  background:var(--green);
  border-radius:50%;
  margin-right:10px;
  box-shadow:0 0 8px var(--green);
}

@keyframes pulse{
  0%{opacity:1;transform:scale(1)}
  50%{opacity:0.4;transform:scale(0.8)}
  100%{opacity:1;transform:scale(1)}
}

/* ── Content Area ───────────────────────────────────────── */
#content{flex:1;display:flex;flex-direction:column;overflow:hidden;min-width:0}

#toolbar{
  display:flex;align-items:center;gap:12px;
  padding:14px 24px;
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border-bottom:1px solid var(--border-default);
  flex-shrink:0;
}
#toolbar .file-title{font-size:15px;font-weight:600;color:var(--txt-primary);flex:1}
#toolbar .file-timestamp{font-size:12px;color:var(--txt-muted)}

#content-area{
  flex:1;overflow-y:auto;overflow-x:auto;
  padding:28px 32px;
  background:var(--bg);
  user-select: text; 
}
#content-area::-webkit-scrollbar{width:6px}
#content-area::-webkit-scrollbar-thumb{background:var(--border-default);border-radius:3px}

/* Markdown Display */
.markdown-body{
  line-height:1.7;
  user-select: text; 
}
/* NEW: Block selection strictly during Live Stream */
#body.focus-mode #content-area,
#body.focus-mode .markdown-body {
  user-select: none !important;
}
.markdown-body h1,.markdown-body h2,.markdown-body h3{
  margin-top:24px;margin-bottom:16px;font-weight:600;line-height:1.25;
  color:var(--txt-primary);
}
.markdown-body h1{font-size:2em;border-bottom:1px solid var(--border-gold);padding-bottom:.3em;color:var(--gold-light);}
.markdown-body h2{font-size:1.5em;border-bottom:1px solid var(--border-default);padding-bottom:.3em;}
.markdown-body h3{font-size:1.25em;color:var(--txt-gold);}
.markdown-body p{margin-bottom:16px;color:var(--txt-read);}
.markdown-body code{
  background:var(--surface-3);padding:2px 6px;border-radius:4px;font-family:monospace;
  color:var(--gold-light);
}
.markdown-body pre{
  background:#0d1117;padding:16px;border-radius:var(--radius-md);
  overflow-x:auto;margin-bottom:16px;border:1px solid rgba(255,255,255,0.1);
  box-shadow:inset 0 0 10px rgba(0,0,0,0.5);
  position:relative;
}
.markdown-body pre::before {
  content: " ";
  display: block;
  height: 12px;
  margin-bottom: 12px;
  border-radius: 50%;
  background: #ff5f56;
  width: 12px;
  box-shadow: 20px 0 0 #ffbd2e, 40px 0 0 #27c93f;
  pointer-events: none;
}
.markdown-body pre code{
  background:none;padding:0;color:#c9d1d9;
  font-family:"JetBrains Mono","Cascadia Code",monospace;font-size:13px;
}
.markdown-body pre code .tok-comment{color:var(--syn-comment);font-style:italic}
.markdown-body pre code .tok-string{color:var(--syn-string)}
.markdown-body pre code .tok-keyword{color:var(--syn-keyword);font-weight:600}
.markdown-body pre code .tok-number{color:var(--syn-number)}
.markdown-body pre code .tok-function{color:var(--syn-function)}
.markdown-body pre code .tok-bracket{color:var(--syn-bracket)}
.markdown-body blockquote{
  border-left:3px solid var(--gold);padding-left:16px;color:var(--txt-muted);
  margin-bottom:16px;font-style:italic;
}
.markdown-body ul,.markdown-body ol{padding-left:2em;margin-bottom:16px;color:var(--txt-read);}
.markdown-body img{max-width:100%;border-radius:var(--radius-md);}
.markdown-body table{width:100%;border-collapse:collapse;margin-bottom:16px;}
.markdown-body th,.markdown-body td{
  border:1px solid var(--border-default);padding:8px 12px;text-align:left;
  word-break:break-word;overflow-wrap:anywhere;
}
.markdown-body th{background:var(--surface-2);color:var(--gold-light);font-weight:600;}

/* Edit Area */
#edit-area{
  display:none;width:100%;height:100%;
  background:var(--surface-1);
  color:#94a3b8; 
  border:1px solid var(--border-default);
  padding:24px 32px;
  font-family:"JetBrains Mono","Cascadia Code",monospace;
  font-size:14px;
  line-height:1.8;
  resize:none;outline:none;border-radius:var(--radius-md);
  box-shadow:inset 0 4px 20px rgba(0,0,0,0.4);
  transition:all var(--trans-fast);
}
#edit-area:focus{
  border-color:var(--cyan); 
  box-shadow:inset 0 4px 20px rgba(0,0,0,0.4), 0 0 0 2px rgba(6, 182, 212, 0.15);
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

.btn-ghost{
  background:var(--surface-3);
  color:var(--txt-secondary);
  border:1px solid var(--border-default);
}
.btn-ghost:hover{
  background:var(--surface-4);color:var(--txt-primary);
  border-color:var(--border-active);
}

/* ── Context Menu ────────────────────────────────────────── */
#context-menu{
  position:fixed;
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-md);
  z-index:1000;
  box-shadow:var(--shadow-lg), 0 0 20px rgba(0,0,0,0.4);
  display:none;flex-direction:column;min-width:160px;
  overflow:hidden;
}
#context-menu.show{display:flex}
.dropdown-item{
  padding:11px 16px;font-size:13px;color:var(--txt-secondary);
  cursor:pointer;display:flex;align-items:center;gap:10px;
  transition:all var(--trans-fast);
  font-weight:500;
}
.dropdown-item:hover{
  background:var(--surface-4);color:var(--txt-primary);
}
.dropdown-item.danger{color:var(--red);}
.dropdown-item.danger:hover{background:rgba(239,68,68,0.1);color:var(--red);}

/* ── Toast Notification ──────────────────────────────────── */
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
#toast.success{border-color:rgba(34,197,94,0.3);color:var(--green);}
#toast.error{border-color:rgba(239,68,68,0.3);color:var(--red);}

#center-toast {
  visibility: hidden;
  min-width: 150px;
  background-color: rgba(0, 0, 0, 0.85);
  color: #fff;
  text-align: center;
  border-radius: 30px;
  padding: 12px 24px;
  position: fixed;
  z-index: 9999;
  left: 50%;
  bottom: 50px;
  transform: translateX(-50%);
  font-size: 15px;
  box-shadow: 0 4px 15px rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
  border: 1px solid rgba(255,255,255,0.1);
  transition: opacity 0.3s, bottom 0.3s;
  opacity: 0;
}
#center-toast.show {
  visibility: visible;
  opacity: 1;
  bottom: 70px;
}

/* Focus Mode: Hide Sidebar */
#body.focus-mode #sidebar{display:none;}
</style>
<!-- marked.js inlined for offline use -->
<script>
/*! marked - a markdown parser */ // (minified version inserted inline for brevity)
</script>
<script>
/**
 * DO NOT EDIT THIS FILE
 * The code in this file is generated from files in ./src/
 */
(function(g,f){if(typeof exports=="object"&&typeof module<"u"){module.exports=f()}else if("function"==typeof define && define.amd){define("marked",f)}else {g["marked"]=f()}}(typeof globalThis < "u" ? globalThis : typeof self < "u" ? self : this,function(){var exports={};var __exports=exports;var module={exports};
"use strict";var H=Object.defineProperty;var be=Object.getOwnPropertyDescriptor;var Te=Object.getOwnPropertyNames;var we=Object.prototype.hasOwnProperty;var ye=(l,e)=>{for(var t in e)H(l,t,{get:e[t],enumerable:!0})},Re=(l,e,t,n)=>{if(e&&typeof e=="object"||typeof e=="function")for(let s of Te(e))!we.call(l,s)&&s!==t&&H(l,s,{get:()=>e[s],enumerable:!(n=be(e,s))||n.enumerable});return l};var Se=l=>Re(H({},"__esModule",{value:!0}),l);var kt={};ye(kt,{Hooks:()=>L,Lexer:()=>x,Marked:()=>E,Parser:()=>b,Renderer:()=>$,TextRenderer:()=>_,Tokenizer:()=>S,defaults:()=>w,getDefaults:()=>z,lexer:()=>ht,marked:()=>k,options:()=>it,parse:()=>pt,parseInline:()=>ct,parser:()=>ut,setOptions:()=>ot,use:()=>lt,walkTokens:()=>at});module.exports=Se(kt);function z(){return{async:!1,breaks:!1,extensions:null,gfm:!0,hooks:null,pedantic:!1,renderer:null,silent:!1,tokenizer:null,walkTokens:null}}var w=z();function N(l){w=l}var I={exec:()=>null};function h(l,e=""){let t=typeof l=="string"?l:l.source,n={replace:(s,i)=>{let r=typeof i=="string"?i:i.source;return r=r.replace(m.caret,"$1"),t=t.replace(s,r),n},getRegex:()=>new RegExp(t,e)};return n}var m={codeRemoveIndent:/^(?: {1,4}| {0,3}\t)/gm,outputLinkReplace:/\\([\[\]])/g,indentCodeCompensation:/^(\s+)(?:```)/,beginningSpace:/^\s+/,endingHash:/#$/,startingSpaceChar:/^ /,endingSpaceChar:/ $/,nonSpaceChar:/[^ ]/,newLineCharGlobal:/\n/g,tabCharGlobal:/\t/g,multipleSpaceGlobal:/\s+/g,blankLine:/^[ \t]*$/,doubleBlankLine:/\n[ \t]*\n[ \t]*$/,blockquoteStart:/^ {0,3}>/,blockquoteSetextReplace:/\n {0,3}((?:=+|-+) *)(?=\n|$)/g,blockquoteSetextReplace2:/^ {0,3}>[ \t]?/gm,listReplaceTabs:/^\t+/,listReplaceNesting:/^ {1,4}(?=( {4})*[^ ])/g,listIsTask:/^\[[ xX]\] /,listReplaceTask:/^\[[ xX]\] +/,anyLine:/\n.*\n/,hrefBrackets:/^<(.*)>$/,tableDelimiter:/[:|]/,tableAlignChars:/^\||\| *$/g,tableRowBlankLine:/\n[ \t]*$/,tableAlignRight:/^ *-+: *$/,tableAlignCenter:/^ *:-+: *$/,tableAlignLeft:/^ *:-+ *$/,startATag:/^<a /i,endATag:/^<\/a>/i,startPreScriptTag:/^<(pre|code|kbd|script)(\s|>)/i,endPreScriptTag:/^<\/(pre|code|kbd|script)(\s|>)/i,startAngleBracket:/^</,endAngleBracket:/>$/,pedanticHrefTitle:/^([^'"]*[^\s])\s+(['"])(.*)\2/,unicodeAlphaNumeric:/[\p{L}\p{N}]/u,escapeTest:/[&<>"']/,escapeReplace:/[&<>"']/g,escapeTestNoEncode:/[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/,escapeReplaceNoEncode:/[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/g,unescapeTest:/&(#(?:\d+)|(?:#x[0-9A-Fa-f]+)|(?:\w+));?/ig,caret:/(^|[^\[])\^/g,percentDecode:/%25/g,findPipe:/\|/g,splitPipe:/ \|/,slashPipe:/\\\|/g,carriageReturn:/\r\n|\r/g,spaceLine:/^ +$/gm,notSpaceStart:/^\S*/,endingNewline:/\n$/,listItemRegex:l=>new RegExp(`^( {0,3}${l})((?:[	 ][^\\n]*)?(?:\\n|$))`),nextBulletRegex:l=>new RegExp(`^ {0,${Math.min(3,l-1)}}(?:[*+-]|\\d{1,9}[.)])((?:[ 	][^\\n]*)?(?:\\n|$))`),hrRegex:l=>new RegExp(`^ {0,${Math.min(3,l-1)}}((?:- *){3,}|(?:_ *){3,}|(?:\\* *){3,})(?:\\n+|$)`),fencesBeginRegex:l=>new RegExp(`^ {0,${Math.min(3,l-1)}}(?:\`\`\`|~~~)`),headingBeginRegex:l=>new RegExp(`^ {0,${Math.min(3,l-1)}}#`),htmlBeginRegex:l=>new RegExp(`^ {0,${Math.min(3,l-1)}}<(?:[a-z].*>|!--)`,"i")},$e=/^(?:[ \t]*(?:\n|$))+/,_e=/^((?: {4}| {0,3}\t)[^\n]+(?:\n(?:[ \t]*(?:\n|$))*)?)+/,Le=/^ {0,3}(`{3,}(?=[^`\n]*(?:\n|$))|~{3,})([^\n]*)(?:\n|$)(?:|([\s\S]*?)(?:\n|$))(?: {0,3}\1[~`]* *(?=\n|$)|$)/,O=/^ {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)/,ze=/^ {0,3}(#{1,6})(?=\s|$)(.*)(?:\n+|$)/,F=/(?:[*+-]|\d{1,9}[.)])/,ie=/^(?!bull |blockCode|fences|blockquote|heading|html|table)((?:.|\n(?!\s*?\n|bull |blockCode|fences|blockquote|heading|html|table))+?)\n {0,3}(=+|-+) *(?:\n+|$)/,oe=h(ie).replace(/bull/g,F).replace(/blockCode/g,/(?: {4}| {0,3}\t)/).replace(/fences/g,/ {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g,/ {0,3}>/).replace(/heading/g,/ {0,3}#{1,6}/).replace(/html/g,/ {0,3}<[^\n>]+>\n/).replace(/\|table/g,"").getRegex(),Me=h(ie).replace(/bull/g,F).replace(/blockCode/g,/(?: {4}| {0,3}\t)/).replace(/fences/g,/ {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g,/ {0,3}>/).replace(/heading/g,/ {0,3}#{1,6}/).replace(/html/g,/ {0,3}<[^\n>]+>\n/).replace(/table/g,/ {0,3}\|?(?:[:\- ]*\|)+[\:\- ]*\n/).getRegex(),Q=/^([^\n]+(?:\n(?!hr|heading|lheading|blockquote|fences|list|html|table| +\n)[^\n]+)*)/,Pe=/^[^\n]+/,U=/(?!\s*\])(?:\\.|[^\[\]\\])+/,Ae=h(/^ {0,3}\[(label)\]: *(?:\n[ \t]*)?([^<\s][^\s]*|<.*?>)(?:(?: +(?:\n[ \t]*)?| *\n[ \t]*)(title))? *(?:\n+|$)/).replace("label",U).replace("title",/(?:"(?:\\"?|[^"\\])*"|'[^'\n]*(?:\n[^'\n]+)*\n?'|\([^()]*\))/).getRegex(),Ee=h(/^( {0,3}bull)([ \t][^\n]+?)?(?:\n|$)/).replace(/bull/g,F).getRegex(),v="address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|meta|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul",K=/<!--(?:-?>|[\s\S]*?(?:-->|$))/,Ce=h("^ {0,3}(?:<(script|pre|style|textarea)[\\s>][\\s\\S]*?(?:</\\1>[^\\n]*\\n+|$)|comment[^\\n]*(\\n+|$)|<\\?[\\s\\S]*?(?:\\?>\\n*|$)|<![A-Z][\\s\\S]*?(?:>\\n*|$)|<!\\[CDATA\\[[\\s\\S]*?(?:\\]\\]>\\n*|$)|</?(tag)(?: +|\\n|/?>)[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$)|<(?!script|pre|style|textarea)([a-z][\\w-]*)(?:attribute)*? */?>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$)|</(?!script|pre|style|textarea)[a-z][\\w-]*\\s*>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$))","i").replace("comment",K).replace("tag",v).replace("attribute",/ +[a-zA-Z:_][\w.:-]*(?: *= *"[^"\n]*"| *= *'[^'\n]*'| *= *[^\s"'=<>`]+)?/).getRegex(),le=h(Q).replace("hr",O).replace("heading"," {0,3}#{1,6}(?:\\s|$)").replace("|lheading","").replace("|table","").replace("blockquote"," {0,3}>").replace("fences"," {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list"," {0,3}(?:[*+-]|1[.)]) ").replace("html","</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag",v).getRegex(),Ie=h(/^( {0,3}> ?(paragraph|[^\n]*)(?:\n|$))+/).replace("paragraph",le).getRegex(),X={blockquote:Ie,code:_e,def:Ae,fences:Le,heading:ze,hr:O,html:Ce,lheading:oe,list:Ee,newline:$e,paragraph:le,table:I,text:Pe},re=h("^ *([^\\n ].*)\\n {0,3}((?:\\| *)?:?-+:? *(?:\\| *:?-+:? *)*(?:\\| *)?)(?:\\n((?:(?! *\\n|hr|heading|blockquote|code|fences|list|html).*(?:\\n|$))*)\\n*|$)").replace("hr",O).replace("heading"," {0,3}#{1,6}(?:\\s|$)").replace("blockquote"," {0,3}>").replace("code","(?: {4}| {0,3}	)[^\\n]").replace("fences"," {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list"," {0,3}(?:[*+-]|1[.)]) ").replace("html","</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag",v).getRegex(),Oe={...X,lheading:Me,table:re,paragraph:h(Q).replace("hr",O).replace("heading"," {0,3}#{1,6}(?:\\s|$)").replace("|lheading","").replace("table",re).replace("blockquote"," {0,3}>").replace("fences"," {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list"," {0,3}(?:[*+-]|1[.)]) ").replace("html","</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag",v).getRegex()},Be={...X,html:h(`^ *(?:comment *(?:\\n|\\s*$)|<(tag)[\\s\\S]+?</\\1> *(?:\\n{2,}|\\s*$)|<tag(?:"[^"]*"|'[^']*'|\\s[^'"/>\\s]*)*?/?> *(?:\\n{2,}|\\s*$))`).replace("comment",K).replace(/tag/g,"(?!(?:a|em|strong|small|s|cite|q|dfn|abbr|data|time|code|var|samp|kbd|sub|sup|i|b|u|mark|ruby|rt|rp|bdi|bdo|span|br|wbr|ins|del|img)\\b)\\w+(?!:|[^\\w\\s@]*@)\\b").getRegex(),def:/^ *\[([^\]]+)\]: *<?([^\s>]+)>?(?: +(["(][^\n]+[")]))? *(?:\n+|$)/,heading:/^(#{1,6})(.*)(?:\n+|$)/,fences:I,lheading:/^(.+?)\n {0,3}(=+|-+) *(?:\n+|$)/,paragraph:h(Q).replace("hr",O).replace("heading",` *#{1,6} *[^
]`).replace("lheading",oe).replace("|table","").replace("blockquote"," {0,3}>").replace("|fences","").replace("|list","").replace("|html","").replace("|tag","").getRegex()},qe=/^\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])/,ve=/^(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/,ae=/^( {2,}|\\)\n(?!\s*$)/,De=/^(`+|[^`])(?:(?= {2,}\n)|[\s\S]*?(?:(?=[\\<!\[`*_]|\b_|$)|[^ ](?= {2,}\n)))/,D=/[\p{P}\p{S}]/u,W=/[\s\p{P}\p{S}]/u,ce=/[^\s\p{P}\p{S}]/u,Ze=h(/^((?![*_])punctSpace)/,"u").replace(/punctSpace/g,W).getRegex(),pe=/(?!~)[\p{P}\p{S}]/u,Ge=/(?!~)[\s\p{P}\p{S}]/u,He=/(?:[^\s\p{P}\p{S}]|~)/u,Ne=/\[[^[\]]*?\]\((?:\\.|[^\\\(\)]|\((?:\\.|[^\\\(\)])*\))*\)|`[^`]*?`|<[^<>]*?>/g,ue=/^(?:\*+(?:((?!\*)punct)|[^\s*]))|^_+(?:((?!_)punct)|([^\s_]))/,je=h(ue,"u").replace(/punct/g,D).getRegex(),Fe=h(ue,"u").replace(/punct/g,pe).getRegex(),he="^[^_*]*?__[^_*]*?\\*[^_*]*?(?=__)|[^*]+(?=[^*])|(?!\\*)punct(\\*+)(?=[\\s]|$)|notPunctSpace(\\*+)(?!\\*)(?=punctSpace|$)|(?!\\*)punctSpace(\\*+)(?=notPunctSpace)|[\\s](\\*+)(?!\\*)(?=punct)|(?!\\*)punct(\\*+)(?!\\*)(?=punct)|notPunctSpace(\\*+)(?=notPunctSpace)",Qe=h(he,"gu").replace(/notPunctSpace/g,ce).replace(/punctSpace/g,W).replace(/punct/g,D).getRegex(),Ue=h(he,"gu").replace(/notPunctSpace/g,He).replace(/punctSpace/g,Ge).replace(/punct/g,pe).getRegex(),Ke=h("^[^_*]*?\\*\\*[^_*]*?_[^_*]*?(?=\\*\\*)|[^_]+(?=[^_])|(?!_)punct(_+)(?=[\\s]|$)|notPunctSpace(_+)(?!_)(?=punctSpace|$)|(?!_)punctSpace(_+)(?=notPunctSpace)|[\\s](_+)(?!_)(?=punct)|(?!_)punct(_+)(?!_)(?=punct)","gu").replace(/notPunctSpace/g,ce).replace(/punctSpace/g,W).replace(/punct/g,D).getRegex(),Xe=h(/\\(punct)/,"gu").replace(/punct/g,D).getRegex(),We=h(/^<(scheme:[^\s\x00-\x1f<>]*|email)>/).replace("scheme",/[a-zA-Z][a-zA-Z0-9+.-]{1,31}/).replace("email",/[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+(@)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+(?![-_])/).getRegex(),Je=h(K).replace("(?:-->|$)","-->").getRegex(),Ve=h("^comment|^</[a-zA-Z][\\w:-]*\\s*>|^<[a-zA-Z][\\w-]*(?:attribute)*?\\s*/?>|^<\\?[\\s\\S]*?\\?>|^<![a-zA-Z]+\\s[\\s\\S]*?>|^<!\\[CDATA\\[[\\s\\S]*?\\]\\]>").replace("comment",Je).replace("attribute",/\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*"[^"]*"|\s*=\s*'[^']*'|\s*=\s*[^\s"'=<>`]+)?/).getRegex(),q=/(?:\[(?:\\.|[^\[\]\\])*\]|\\.|`[^`]*`|[^\[\]\\`])*?/,Ye=h(/^!?\[(label)\]\(\s*(href)(?:(?:[ \t]*(?:\n[ \t]*)?)(title))?\s*\)/).replace("label",q).replace("href",/<(?:\\.|[^\n<>\\])+>|[^ \t\n\x00-\x1f]*/).replace("title",/"(?:\\"?|[^"\\])*"|'(?:\\'?|[^'\\])*'|\((?:\\\)?|[^)\\])*\)/).getRegex(),ke=h(/^!?\[(label)\]\[(ref)\]/).replace("label",q).replace("ref",U).getRegex(),ge=h(/^!?\[(ref)\](?:\[\])?/).replace("ref",U).getRegex(),et=h("reflink|nolink(?!\\()","g").replace("reflink",ke).replace("nolink",ge).getRegex(),J={_backpedal:I,anyPunctuation:Xe,autolink:We,blockSkip:Ne,br:ae,code:ve,del:I,emStrongLDelim:je,emStrongRDelimAst:Qe,emStrongRDelimUnd:Ke,escape:qe,link:Ye,nolink:ge,punctuation:Ze,reflink:ke,reflinkSearch:et,tag:Ve,text:De,url:I},tt={...J,link:h(/^!?\[(label)\]\((.*?)\)/).replace("label",q).getRegex(),reflink:h(/^!?\[(label)\]\s*\[([^\]]*)\]/).replace("label",q).getRegex()},j={...J,emStrongRDelimAst:Ue,emStrongLDelim:Fe,url:h(/^((?:ftp|https?):\/\/|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*|^email/,"i").replace("email",/[A-Za-z0-9._+-]+(@)[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![-_])/).getRegex(),_backpedal:/(?:[^?!.,:;*_'"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_'"~)]+(?!$))+/,del:/^(~~?)(?=[^\s~])((?:\\.|[^\\])*?(?:\\.|[^\s~\\]))\1(?=[^~]|$)/,text:/^([`~]+|[^`~])(?:(?= {2,}\n)|(?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)|[\s\S]*?(?:(?=[\\<!\[`*~_]|\b_|https?:\/\/|ftp:\/\/|www\.|$)|[^ ](?= {2,}\n)|[^a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-](?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)))/},nt={...j,br:h(ae).replace("{2,}","*").getRegex(),text:h(j.text).replace("\\b_","\\b_| {2,}\\n").replace(/\{2,\}/g,"*").getRegex()},B={normal:X,gfm:Oe,pedantic:Be},P={normal:J,gfm:j,breaks:nt,pedantic:tt};var st={"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"},fe=l=>st[l];function R(l,e){if(e){if(m.escapeTest.test(l))return l.replace(m.escapeReplace,fe)}else if(m.escapeTestNoEncode.test(l))return l.replace(m.escapeReplaceNoEncode,fe);return l}function V(l){try{l=encodeURI(l).replace(m.percentDecode,"%")}catch{return null}return l}function Y(l,e){let t=l.replace(m.findPipe,(i,r,o)=>{let a=!1,c=r;for(;--c>=0&&o[c]==="\\";)a=!a;return a?"|":" |"}),n=t.split(m.splitPipe),s=0;if(n[0].trim()||n.shift(),n.length>0&&!n.at(-1)?.trim()&&n.pop(),e)if(n.length>e)n.splice(e);else for(;n.length<e;)n.push("");for(;s<n.length;s++)n[s]=n[s].trim().replace(m.slashPipe,"|");return n}function A(l,e,t){let n=l.length;if(n===0)return"";let s=0;for(;s<n;){let i=l.charAt(n-s-1);if(i===e&&!t)s++;else if(i!==e&&t)s++;else break}return l.slice(0,n-s)}function de(l,e){if(l.indexOf(e[1])===-1)return-1;let t=0;for(let n=0;n<l.length;n++)if(l[n]==="\\")n++;else if(l[n]===e[0])t++;else if(l[n]===e[1]&&(t--,t<0))return n;return t>0?-2:-1}function me(l,e,t,n,s){let i=e.href,r=e.title||null,o=l[1].replace(s.other.outputLinkReplace,"$1");n.state.inLink=!0;let a={type:l[0].charAt(0)==="!"?"image":"link",raw:t,href:i,title:r,text:o,tokens:n.inlineTokens(o)};return n.state.inLink=!1,a}function rt(l,e,t){let n=l.match(t.other.indentCodeCompensation);if(n===null)return e;let s=n[1];return e.split(`
`).map(i=>{let r=i.match(t.other.beginningSpace);if(r===null)return i;let[o]=r;return o.length>=s.length?i.slice(s.length):i}).join(`
`)}var S=class{options;rules;lexer;constructor(e){this.options=e||w}space(e){let t=this.rules.block.newline.exec(e);if(t&&t[0].length>0)return{type:"space",raw:t[0]}}code(e){let t=this.rules.block.code.exec(e);if(t){let n=t[0].replace(this.rules.other.codeRemoveIndent,"");return{type:"code",raw:t[0],codeBlockStyle:"indented",text:this.options.pedantic?n:A(n,`
`)}}}fences(e){let t=this.rules.block.fences.exec(e);if(t){let n=t[0],s=rt(n,t[3]||"",this.rules);return{type:"code",raw:n,lang:t[2]?t[2].trim().replace(this.rules.inline.anyPunctuation,"$1"):t[2],text:s}}}heading(e){let t=this.rules.block.heading.exec(e);if(t){let n=t[2].trim();if(this.rules.other.endingHash.test(n)){let s=A(n,"#");(this.options.pedantic||!s||this.rules.other.endingSpaceChar.test(s))&&(n=s.trim())}return{type:"heading",raw:t[0],depth:t[1].length,text:n,tokens:this.lexer.inline(n)}}}hr(e){let t=this.rules.block.hr.exec(e);if(t)return{type:"hr",raw:A(t[0],`
`)}}blockquote(e){let t=this.rules.block.blockquote.exec(e);if(t){let n=A(t[0],`
`).split(`
`),s="",i="",r=[];for(;n.length>0;){let o=!1,a=[],c;for(c=0;c<n.length;c++)if(this.rules.other.blockquoteStart.test(n[c]))a.push(n[c]),o=!0;else if(!o)a.push(n[c]);else break;n=n.slice(c);let p=a.join(`
`),u=p.replace(this.rules.other.blockquoteSetextReplace,`
    $1`).replace(this.rules.other.blockquoteSetextReplace2,"");s=s?`${s}
${p}`:p,i=i?`${i}
${u}`:u;let d=this.lexer.state.top;if(this.lexer.state.top=!0,this.lexer.blockTokens(u,r,!0),this.lexer.state.top=d,n.length===0)break;let g=r.at(-1);if(g?.type==="code")break;if(g?.type==="blockquote"){let T=g,f=T.raw+`
`+n.join(`
`),y=this.blockquote(f);r[r.length-1]=y,s=s.substring(0,s.length-T.raw.length)+y.raw,i=i.substring(0,i.length-T.text.length)+y.text;break}else if(g?.type==="list"){let T=g,f=T.raw+`
`+n.join(`
`),y=this.list(f);r[r.length-1]=y,s=s.substring(0,s.length-g.raw.length)+y.raw,i=i.substring(0,i.length-T.raw.length)+y.raw,n=f.substring(r.at(-1).raw.length).split(`
`);continue}}return{type:"blockquote",raw:s,tokens:r,text:i}}}list(e){let t=this.rules.block.list.exec(e);if(t){let n=t[1].trim(),s=n.length>1,i={type:"list",raw:"",ordered:s,start:s?+n.slice(0,-1):"",loose:!1,items:[]};n=s?`\\d{1,9}\\${n.slice(-1)}`:`\\${n}`,this.options.pedantic&&(n=s?n:"[*+-]");let r=this.rules.other.listItemRegex(n),o=!1;for(;e;){let c=!1,p="",u="";if(!(t=r.exec(e))||this.rules.block.hr.test(e))break;p=t[0],e=e.substring(p.length);let d=t[2].split(`
`,1)[0].replace(this.rules.other.listReplaceTabs,Z=>" ".repeat(3*Z.length)),g=e.split(`
`,1)[0],T=!d.trim(),f=0;if(this.options.pedantic?(f=2,u=d.trimStart()):T?f=t[1].length+1:(f=t[2].search(this.rules.other.nonSpaceChar),f=f>4?1:f,u=d.slice(f),f+=t[1].length),T&&this.rules.other.blankLine.test(g)&&(p+=g+`
`,e=e.substring(g.length+1),c=!0),!c){let Z=this.rules.other.nextBulletRegex(f),te=this.rules.other.hrRegex(f),ne=this.rules.other.fencesBeginRegex(f),se=this.rules.other.headingBeginRegex(f),xe=this.rules.other.htmlBeginRegex(f);for(;e;){let G=e.split(`
`,1)[0],C;if(g=G,this.options.pedantic?(g=g.replace(this.rules.other.listReplaceNesting,"  "),C=g):C=g.replace(this.rules.other.tabCharGlobal,"    "),ne.test(g)||se.test(g)||xe.test(g)||Z.test(g)||te.test(g))break;if(C.search(this.rules.other.nonSpaceChar)>=f||!g.trim())u+=`
`+C.slice(f);else{if(T||d.replace(this.rules.other.tabCharGlobal,"    ").search(this.rules.other.nonSpaceChar)>=4||ne.test(d)||se.test(d)||te.test(d))break;u+=`
`+g}!T&&!g.trim()&&(T=!0),p+=G+`
`,e=e.substring(G.length+1),d=C.slice(f)}}i.loose||(o?i.loose=!0:this.rules.other.doubleBlankLine.test(p)&&(o=!0));let y=null,ee;this.options.gfm&&(y=this.rules.other.listIsTask.exec(u),y&&(ee=y[0]!=="[ ] ",u=u.replace(this.rules.other.listReplaceTask,""))),i.items.push({type:"list_item",raw:p,task:!!y,checked:ee,loose:!1,text:u,tokens:[]}),i.raw+=p}let a=i.items.at(-1);if(a)a.raw=a.raw.trimEnd(),a.text=a.text.trimEnd();else return;i.raw=i.raw.trimEnd();for(let c=0;c<i.items.length;c++)if(this.lexer.state.top=!1,i.items[c].tokens=this.lexer.blockTokens(i.items[c].text,[]),!i.loose){let p=i.items[c].tokens.filter(d=>d.type==="space"),u=p.length>0&&p.some(d=>this.rules.other.anyLine.test(d.raw));i.loose=u}if(i.loose)for(let c=0;c<i.items.length;c++)i.items[c].loose=!0;return i}}html(e){let t=this.rules.block.html.exec(e);if(t)return{type:"html",block:!0,raw:t[0],pre:t[1]==="pre"||t[1]==="script"||t[1]==="style",text:t[0]}}def(e){let t=this.rules.block.def.exec(e);if(t){let n=t[1].toLowerCase().replace(this.rules.other.multipleSpaceGlobal," "),s=t[2]?t[2].replace(this.rules.other.hrefBrackets,"$1").replace(this.rules.inline.anyPunctuation,"$1"):"",i=t[3]?t[3].substring(1,t[3].length-1).replace(this.rules.inline.anyPunctuation,"$1"):t[3];return{type:"def",tag:n,raw:t[0],href:s,title:i}}}table(e){let t=this.rules.block.table.exec(e);if(!t||!this.rules.other.tableDelimiter.test(t[2]))return;let n=Y(t[1]),s=t[2].replace(this.rules.other.tableAlignChars,"").split("|"),i=t[3]?.trim()?t[3].replace(this.rules.other.tableRowBlankLine,"").split(`
`):[],r={type:"table",raw:t[0],header:[],align:[],rows:[]};if(n.length===s.length){for(let o of s)this.rules.other.tableAlignRight.test(o)?r.align.push("right"):this.rules.other.tableAlignCenter.test(o)?r.align.push("center"):this.rules.other.tableAlignLeft.test(o)?r.align.push("left"):r.align.push(null);for(let o=0;o<n.length;o++)r.header.push({text:n[o],tokens:this.lexer.inline(n[o]),header:!0,align:r.align[o]});for(let o of i)r.rows.push(Y(o,r.header.length).map((a,c)=>({text:a,tokens:this.lexer.inline(a),header:!1,align:r.align[c]})));return r}}lheading(e){let t=this.rules.block.lheading.exec(e);if(t)return{type:"heading",raw:t[0],depth:t[2].charAt(0)==="="?1:2,text:t[1],tokens:this.lexer.inline(t[1])}}paragraph(e){let t=this.rules.block.paragraph.exec(e);if(t){let n=t[1].charAt(t[1].length-1)===`
`?t[1].slice(0,-1):t[1];return{type:"paragraph",raw:t[0],text:n,tokens:this.lexer.inline(n)}}}text(e){let t=this.rules.block.text.exec(e);if(t)return{type:"text",raw:t[0],text:t[0],tokens:this.lexer.inline(t[0])}}escape(e){let t=this.rules.inline.escape.exec(e);if(t)return{type:"escape",raw:t[0],text:t[1]}}tag(e){let t=this.rules.inline.tag.exec(e);if(t)return!this.lexer.state.inLink&&this.rules.other.startATag.test(t[0])?this.lexer.state.inLink=!0:this.lexer.state.inLink&&this.rules.other.endATag.test(t[0])&&(this.lexer.state.inLink=!1),!this.lexer.state.inRawBlock&&this.rules.other.startPreScriptTag.test(t[0])?this.lexer.state.inRawBlock=!0:this.lexer.state.inRawBlock&&this.rules.other.endPreScriptTag.test(t[0])&&(this.lexer.state.inRawBlock=!1),{type:"html",raw:t[0],inLink:this.lexer.state.inLink,inRawBlock:this.lexer.state.inRawBlock,block:!1,text:t[0]}}link(e){let t=this.rules.inline.link.exec(e);if(t){let n=t[2].trim();if(!this.options.pedantic&&this.rules.other.startAngleBracket.test(n)){if(!this.rules.other.endAngleBracket.test(n))return;let r=A(n.slice(0,-1),"\\");if((n.length-r.length)%2===0)return}else{let r=de(t[2],"()");if(r===-2)return;if(r>-1){let a=(t[0].indexOf("!")===0?5:4)+t[1].length+r;t[2]=t[2].substring(0,r),t[0]=t[0].substring(0,a).trim(),t[3]=""}}let s=t[2],i="";if(this.options.pedantic){let r=this.rules.other.pedanticHrefTitle.exec(s);r&&(s=r[1],i=r[3])}else i=t[3]?t[3].slice(1,-1):"";return s=s.trim(),this.rules.other.startAngleBracket.test(s)&&(this.options.pedantic&&!this.rules.other.endAngleBracket.test(n)?s=s.slice(1):s=s.slice(1,-1)),me(t,{href:s&&s.replace(this.rules.inline.anyPunctuation,"$1"),title:i&&i.replace(this.rules.inline.anyPunctuation,"$1")},t[0],this.lexer,this.rules)}}reflink(e,t){let n;if((n=this.rules.inline.reflink.exec(e))||(n=this.rules.inline.nolink.exec(e))){let s=(n[2]||n[1]).replace(this.rules.other.multipleSpaceGlobal," "),i=t[s.toLowerCase()];if(!i){let r=n[0].charAt(0);return{type:"text",raw:r,text:r}}return me(n,i,n[0],this.lexer,this.rules)}}emStrong(e,t,n=""){let s=this.rules.inline.emStrongLDelim.exec(e);if(!s||s[3]&&n.match(this.rules.other.unicodeAlphaNumeric))return;if(!(s[1]||s[2]||"")||!n||this.rules.inline.punctuation.exec(n)){let r=[...s[0]].length-1,o,a,c=r,p=0,u=s[0][0]==="*"?this.rules.inline.emStrongRDelimAst:this.rules.inline.emStrongRDelimUnd;for(u.lastIndex=0,t=t.slice(-1*e.length+r);(s=u.exec(t))!=null;){if(o=s[1]||s[2]||s[3]||s[4]||s[5]||s[6],!o)continue;if(a=[...o].length,s[3]||s[4]){c+=a;continue}else if((s[5]||s[6])&&r%3&&!((r+a)%3)){p+=a;continue}if(c-=a,c>0)continue;a=Math.min(a,a+c+p);let d=[...s[0]][0].length,g=e.slice(0,r+s.index+d+a);if(Math.min(r,a)%2){let f=g.slice(1,-1);return{type:"em",raw:g,text:f,tokens:this.lexer.inlineTokens(f)}}let T=g.slice(2,-2);return{type:"strong",raw:g,text:T,tokens:this.lexer.inlineTokens(T)}}}}codespan(e){let t=this.rules.inline.code.exec(e);if(t){let n=t[2].replace(this.rules.other.newLineCharGlobal," "),s=this.rules.other.nonSpaceChar.test(n),i=this.rules.other.startingSpaceChar.test(n)&&this.rules.other.endingSpaceChar.test(n);return s&&i&&(n=n.substring(1,n.length-1)),{type:"codespan",raw:t[0],text:n}}}br(e){let t=this.rules.inline.br.exec(e);if(t)return{type:"br",raw:t[0]}}del(e){let t=this.rules.inline.del.exec(e);if(t)return{type:"del",raw:t[0],text:t[2],tokens:this.lexer.inlineTokens(t[2])}}autolink(e){let t=this.rules.inline.autolink.exec(e);if(t){let n,s;return t[2]==="@"?(n=t[1],s="mailto:"+n):(n=t[1],s=n),{type:"link",raw:t[0],text:n,href:s,tokens:[{type:"text",raw:n,text:n}]}}}url(e){let t;if(t=this.rules.inline.url.exec(e)){let n,s;if(t[2]==="@")n=t[0],s="mailto:"+n;else{let i;do i=t[0],t[0]=this.rules.inline._backpedal.exec(t[0])?.[0]??"";while(i!==t[0]);n=t[0],t[1]==="www."?s="http://"+t[0]:s=t[0]}return{type:"link",raw:t[0],text:n,href:s,tokens:[{type:"text",raw:n,text:n}]}}}inlineText(e){let t=this.rules.inline.text.exec(e);if(t){let n=this.lexer.state.inRawBlock;return{type:"text",raw:t[0],text:t[0],escaped:n}}}};var x=class l{tokens;options;state;tokenizer;inlineQueue;constructor(e){this.tokens=[],this.tokens.links=Object.create(null),this.options=e||w,this.options.tokenizer=this.options.tokenizer||new S,this.tokenizer=this.options.tokenizer,this.tokenizer.options=this.options,this.tokenizer.lexer=this,this.inlineQueue=[],this.state={inLink:!1,inRawBlock:!1,top:!0};let t={other:m,block:B.normal,inline:P.normal};this.options.pedantic?(t.block=B.pedantic,t.inline=P.pedantic):this.options.gfm&&(t.block=B.gfm,this.options.breaks?t.inline=P.breaks:t.inline=P.gfm),this.tokenizer.rules=t}static get rules(){return{block:B,inline:P}}static lex(e,t){return new l(t).lex(e)}static lexInline(e,t){return new l(t).inlineTokens(e)}lex(e){e=e.replace(m.carriageReturn,`
`),this.blockTokens(e,this.tokens);for(let t=0;t<this.inlineQueue.length;t++){let n=this.inlineQueue[t];this.inlineTokens(n.src,n.tokens)}return this.inlineQueue=[],this.tokens}blockTokens(e,t=[],n=!1){for(this.options.pedantic&&(e=e.replace(m.tabCharGlobal,"    ").replace(m.spaceLine,""));e;){let s;if(this.options.extensions?.block?.some(r=>(s=r.call({lexer:this},e,t))?(e=e.substring(s.raw.length),t.push(s),!0):!1))continue;if(s=this.tokenizer.space(e)){e=e.substring(s.raw.length);let r=t.at(-1);s.raw.length===1&&r!==void 0?r.raw+=`
`:t.push(s);continue}if(s=this.tokenizer.code(e)){e=e.substring(s.raw.length);let r=t.at(-1);r?.type==="paragraph"||r?.type==="text"?(r.raw+=`
`+s.raw,r.text+=`
`+s.text,this.inlineQueue.at(-1).src=r.text):t.push(s);continue}if(s=this.tokenizer.fences(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.heading(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.hr(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.blockquote(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.list(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.html(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.def(e)){e=e.substring(s.raw.length);let r=t.at(-1);r?.type==="paragraph"||r?.type==="text"?(r.raw+=`
`+s.raw,r.text+=`
`+s.raw,this.inlineQueue.at(-1).src=r.text):this.tokens.links[s.tag]||(this.tokens.links[s.tag]={href:s.href,title:s.title});continue}if(s=this.tokenizer.table(e)){e=e.substring(s.raw.length),t.push(s);continue}if(s=this.tokenizer.lheading(e)){e=e.substring(s.raw.length),t.push(s);continue}let i=e;if(this.options.extensions?.startBlock){let r=1/0,o=e.slice(1),a;this.options.extensions.startBlock.forEach(c=>{a=c.call({lexer:this},o),typeof a=="number"&&a>=0&&(r=Math.min(r,a))}),r<1/0&&r>=0&&(i=e.substring(0,r+1))}if(this.state.top&&(s=this.tokenizer.paragraph(i))){let r=t.at(-1);n&&r?.type==="paragraph"?(r.raw+=`
`+s.raw,r.text+=`
`+s.text,this.inlineQueue.pop(),this.inlineQueue.at(-1).src=r.text):t.push(s),n=i.length!==e.length,e=e.substring(s.raw.length);continue}if(s=this.tokenizer.text(e)){e=e.substring(s.raw.length);let r=t.at(-1);r?.type==="text"?(r.raw+=`
`+s.raw,r.text+=`
`+s.text,this.inlineQueue.pop(),this.inlineQueue.at(-1).src=r.text):t.push(s);continue}if(e){let r="Infinite loop on byte: "+e.charCodeAt(0);if(this.options.silent){console.error(r);break}else throw new Error(r)}}return this.state.top=!0,t}inline(e,t=[]){return this.inlineQueue.push({src:e,tokens:t}),t}inlineTokens(e,t=[]){let n=e,s=null;if(this.tokens.links){let o=Object.keys(this.tokens.links);if(o.length>0)for(;(s=this.tokenizer.rules.inline.reflinkSearch.exec(n))!=null;)o.includes(s[0].slice(s[0].lastIndexOf("[")+1,-1))&&(n=n.slice(0,s.index)+"["+"a".repeat(s[0].length-2)+"]"+n.slice(this.tokenizer.rules.inline.reflinkSearch.lastIndex))}for(;(s=this.tokenizer.rules.inline.anyPunctuation.exec(n))!=null;)n=n.slice(0,s.index)+"++"+n.slice(this.tokenizer.rules.inline.anyPunctuation.lastIndex);for(;(s=this.tokenizer.rules.inline.blockSkip.exec(n))!=null;)n=n.slice(0,s.index)+"["+"a".repeat(s[0].length-2)+"]"+n.slice(this.tokenizer.rules.inline.blockSkip.lastIndex);let i=!1,r="";for(;e;){i||(r=""),i=!1;let o;if(this.options.extensions?.inline?.some(c=>(o=c.call({lexer:this},e,t))?(e=e.substring(o.raw.length),t.push(o),!0):!1))continue;if(o=this.tokenizer.escape(e)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.tag(e)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.link(e)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.reflink(e,this.tokens.links)){e=e.substring(o.raw.length);let c=t.at(-1);o.type==="text"&&c?.type==="text"?(c.raw+=o.raw,c.text+=o.text):t.push(o);continue}if(o=this.tokenizer.emStrong(e,n,r)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.codespan(e)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.br(e)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.del(e)){e=e.substring(o.raw.length),t.push(o);continue}if(o=this.tokenizer.autolink(e)){e=e.substring(o.raw.length),t.push(o);continue}if(!this.state.inLink&&(o=this.tokenizer.url(e))){e=e.substring(o.raw.length),t.push(o);continue}let a=e;if(this.options.extensions?.startInline){let c=1/0,p=e.slice(1),u;this.options.extensions.startInline.forEach(d=>{u=d.call({lexer:this},p),typeof u=="number"&&u>=0&&(c=Math.min(c,u))}),c<1/0&&c>=0&&(a=e.substring(0,c+1))}if(o=this.tokenizer.inlineText(a)){e=e.substring(o.raw.length),o.raw.slice(-1)!=="_"&&(r=o.raw.slice(-1)),i=!0;let c=t.at(-1);c?.type==="text"?(c.raw+=o.raw,c.text+=o.text):t.push(o);continue}if(e){let c="Infinite loop on byte: "+e.charCodeAt(0);if(this.options.silent){console.error(c);break}else throw new Error(c)}}return t}};var $=class{options;parser;constructor(e){this.options=e||w}space(e){return""}code({text:e,lang:t,escaped:n}){let s=(t||"").match(m.notSpaceStart)?.[0],i=e.replace(m.endingNewline,"")+`
`;return s?'<pre><code class="language-'+R(s)+'">'+(n?i:R(i,!0))+`</code></pre>
`:"<pre><code>"+(n?i:R(i,!0))+`</code></pre>
`}blockquote({tokens:e}){return`<blockquote>
${this.parser.parse(e)}</blockquote>
`}html({text:e}){return e}heading({tokens:e,depth:t}){return`<h${t}>${this.parser.parseInline(e)}</h${t}>
`}hr(e){return`<hr>
`}list(e){let t=e.ordered,n=e.start,s="";for(let o=0;o<e.items.length;o++){let a=e.items[o];s+=this.listitem(a)}let i=t?"ol":"ul",r=t&&n!==1?' start="'+n+'"':"";return"<"+i+r+`>
`+s+"</"+i+`>
`}listitem(e){let t="";if(e.task){let n=this.checkbox({checked:!!e.checked});e.loose?e.tokens[0]?.type==="paragraph"?(e.tokens[0].text=n+" "+e.tokens[0].text,e.tokens[0].tokens&&e.tokens[0].tokens.length>0&&e.tokens[0].tokens[0].type==="text"&&(e.tokens[0].tokens[0].text=n+" "+R(e.tokens[0].tokens[0].text),e.tokens[0].tokens[0].escaped=!0)):e.tokens.unshift({type:"text",raw:n+" ",text:n+" ",escaped:!0}):t+=n+" "}return t+=this.parser.parse(e.tokens,!!e.loose),`<li>${t}</li>
`}checkbox({checked:e}){return"<input "+(e?'checked="" ':"")+'disabled="" type="checkbox">'}paragraph({tokens:e}){return`<p>${this.parser.parseInline(e)}</p>
`}table(e){let t="",n="";for(let i=0;i<e.header.length;i++)n+=this.tablecell(e.header[i]);t+=this.tablerow({text:n});let s="";for(let i=0;i<e.rows.length;i++){let r=e.rows[i];n="";for(let o=0;o<r.length;o++)n+=this.tablecell(r[o]);s+=this.tablerow({text:n})}return s&&(s=`<tbody>${s}</tbody>`),`<table>
<thead>
`+t+`</thead>
`+s+`</table>
`}tablerow({text:e}){return`<tr>
${e}</tr>
`}tablecell(e){let t=this.parser.parseInline(e.tokens),n=e.header?"th":"td";return(e.align?`<${n} align="${e.align}">`:`<${n}>`)+t+`</${n}>
`}strong({tokens:e}){return`<strong>${this.parser.parseInline(e)}</strong>`}em({tokens:e}){return`<em>${this.parser.parseInline(e)}</em>`}codespan({text:e}){return`<code>${R(e,!0)}</code>`}br(e){return"<br>"}del({tokens:e}){return`<del>${this.parser.parseInline(e)}</del>`}link({href:e,title:t,tokens:n}){let s=this.parser.parseInline(n),i=V(e);if(i===null)return s;e=i;let r='<a href="'+e+'"';return t&&(r+=' title="'+R(t)+'"'),r+=">"+s+"</a>",r}image({href:e,title:t,text:n,tokens:s}){s&&(n=this.parser.parseInline(s,this.parser.textRenderer));let i=V(e);if(i===null)return R(n);e=i;let r=`<img src="${e}" alt="${n}"`;return t&&(r+=` title="${R(t)}"`),r+=">",r}text(e){return"tokens"in e&&e.tokens?this.parser.parseInline(e.tokens):"escaped"in e&&e.escaped?e.text:R(e.text)}};var _=class{strong({text:e}){return e}em({text:e}){return e}codespan({text:e}){return e}del({text:e}){return e}html({text:e}){return e}text({text:e}){return e}link({text:e}){return""+e}image({text:e}){return""+e}br(){return""}};var b=class l{options;renderer;textRenderer;constructor(e){this.options=e||w,this.options.renderer=this.options.renderer||new $,this.renderer=this.options.renderer,this.renderer.options=this.options,this.renderer.parser=this,this.textRenderer=new _}static parse(e,t){return new l(t).parse(e)}static parseInline(e,t){return new l(t).parseInline(e)}parse(e,t=!0){let n="";for(let s=0;s<e.length;s++){let i=e[s];if(this.options.extensions?.renderers?.[i.type]){let o=i,a=this.options.extensions.renderers[o.type].call({parser:this},o);if(a!==!1||!["space","hr","heading","code","table","blockquote","list","html","paragraph","text"].includes(o.type)){n+=a||"";continue}}let r=i;switch(r.type){case"space":{n+=this.renderer.space(r);continue}case"hr":{n+=this.renderer.hr(r);continue}case"heading":{n+=this.renderer.heading(r);continue}case"code":{n+=this.renderer.code(r);continue}case"table":{n+=this.renderer.table(r);continue}case"blockquote":{n+=this.renderer.blockquote(r);continue}case"list":{n+=this.renderer.list(r);continue}case"html":{n+=this.renderer.html(r);continue}case"paragraph":{n+=this.renderer.paragraph(r);continue}case"text":{let o=r,a=this.renderer.text(o);for(;s+1<e.length&&e[s+1].type==="text";)o=e[++s],a+=`
`+this.renderer.text(o);t?n+=this.renderer.paragraph({type:"paragraph",raw:a,text:a,tokens:[{type:"text",raw:a,text:a,escaped:!0}]}):n+=a;continue}default:{let o='Token with "'+r.type+'" type was not found.';if(this.options.silent)return console.error(o),"";throw new Error(o)}}}return n}parseInline(e,t=this.renderer){let n="";for(let s=0;s<e.length;s++){let i=e[s];if(this.options.extensions?.renderers?.[i.type]){let o=this.options.extensions.renderers[i.type].call({parser:this},i);if(o!==!1||!["escape","html","link","image","strong","em","codespan","br","del","text"].includes(i.type)){n+=o||"";continue}}let r=i;switch(r.type){case"escape":{n+=t.text(r);break}case"html":{n+=t.html(r);break}case"link":{n+=t.link(r);break}case"image":{n+=t.image(r);break}case"strong":{n+=t.strong(r);break}case"em":{n+=t.em(r);break}case"codespan":{n+=t.codespan(r);break}case"br":{n+=t.br(r);break}case"del":{n+=t.del(r);break}case"text":{n+=t.text(r);break}default:{let o='Token with "'+r.type+'" type was not found.';if(this.options.silent)return console.error(o),"";throw new Error(o)}}}return n}};var L=class{options;block;constructor(e){this.options=e||w}static passThroughHooks=new Set(["preprocess","postprocess","processAllTokens"]);preprocess(e){return e}postprocess(e){return e}processAllTokens(e){return e}provideLexer(){return this.block?x.lex:x.lexInline}provideParser(){return this.block?b.parse:b.parseInline}};var E=class{defaults=z();options=this.setOptions;parse=this.parseMarkdown(!0);parseInline=this.parseMarkdown(!1);Parser=b;Renderer=$;TextRenderer=_;Lexer=x;Tokenizer=S;Hooks=L;constructor(...e){this.use(...e)}walkTokens(e,t){let n=[];for(let s of e)switch(n=n.concat(t.call(this,s)),s.type){case"table":{let i=s;for(let r of i.header)n=n.concat(this.walkTokens(r.tokens,t));for(let r of i.rows)for(let o of r)n=n.concat(this.walkTokens(o.tokens,t));break}case"list":{let i=s;n=n.concat(this.walkTokens(i.items,t));break}default:{let i=s;this.defaults.extensions?.childTokens?.[i.type]?this.defaults.extensions.childTokens[i.type].forEach(r=>{let o=i[r].flat(1/0);n=n.concat(this.walkTokens(o,t))}):i.tokens&&(n=n.concat(this.walkTokens(i.tokens,t)))}}return n}use(...e){let t=this.defaults.extensions||{renderers:{},childTokens:{}};return e.forEach(n=>{let s={...n};if(s.async=this.defaults.async||s.async||!1,n.extensions&&(n.extensions.forEach(i=>{if(!i.name)throw new Error("extension name required");if("renderer"in i){let r=t.renderers[i.name];r?t.renderers[i.name]=function(...o){let a=i.renderer.apply(this,o);return a===!1&&(a=r.apply(this,o)),a}:t.renderers[i.name]=i.renderer}if("tokenizer"in i){if(!i.level||i.level!=="block"&&i.level!=="inline")throw new Error("extension level must be 'block' or 'inline'");let r=t[i.level];r?r.unshift(i.tokenizer):t[i.level]=[i.tokenizer],i.start&&(i.level==="block"?t.startBlock?t.startBlock.push(i.start):t.startBlock=[i.start]:i.level==="inline"&&(t.startInline?t.startInline.push(i.start):t.startInline=[i.start]))}"childTokens"in i&&i.childTokens&&(t.childTokens[i.name]=i.childTokens)}),s.extensions=t),n.renderer){let i=this.defaults.renderer||new $(this.defaults);for(let r in n.renderer){if(!(r in i))throw new Error(`renderer '${r}' does not exist`);if(["options","parser"].includes(r))continue;let o=r,a=n.renderer[o],c=i[o];i[o]=(...p)=>{let u=a.apply(i,p);return u===!1&&(u=c.apply(i,p)),u||""}}s.renderer=i}if(n.tokenizer){let i=this.defaults.tokenizer||new S(this.defaults);for(let r in n.tokenizer){if(!(r in i))throw new Error(`tokenizer '${r}' does not exist`);if(["options","rules","lexer"].includes(r))continue;let o=r,a=n.tokenizer[o],c=i[o];i[o]=(...p)=>{let u=a.apply(i,p);return u===!1&&(u=c.apply(i,p)),u}}s.tokenizer=i}if(n.hooks){let i=this.defaults.hooks||new L;for(let r in n.hooks){if(!(r in i))throw new Error(`hook '${r}' does not exist`);if(["options","block"].includes(r))continue;let o=r,a=n.hooks[o],c=i[o];L.passThroughHooks.has(r)?i[o]=p=>{if(this.defaults.async)return Promise.resolve(a.call(i,p)).then(d=>c.call(i,d));let u=a.call(i,p);return c.call(i,u)}:i[o]=(...p)=>{let u=a.apply(i,p);return u===!1&&(u=c.apply(i,p)),u}}s.hooks=i}if(n.walkTokens){let i=this.defaults.walkTokens,r=n.walkTokens;s.walkTokens=function(o){let a=[];return a.push(r.call(this,o)),i&&(a=a.concat(i.call(this,o))),a}}this.defaults={...this.defaults,...s}}),this}setOptions(e){return this.defaults={...this.defaults,...e},this}lexer(e,t){return x.lex(e,t??this.defaults)}parser(e,t){return b.parse(e,t??this.defaults)}parseMarkdown(e){return(n,s)=>{let i={...s},r={...this.defaults,...i},o=this.onError(!!r.silent,!!r.async);if(this.defaults.async===!0&&i.async===!1)return o(new Error("marked(): The async option was set to true by an extension. Remove async: false from the parse options object to return a Promise."));if(typeof n>"u"||n===null)return o(new Error("marked(): input parameter is undefined or null"));if(typeof n!="string")return o(new Error("marked(): input parameter is of type "+Object.prototype.toString.call(n)+", string expected"));r.hooks&&(r.hooks.options=r,r.hooks.block=e);let a=r.hooks?r.hooks.provideLexer():e?x.lex:x.lexInline,c=r.hooks?r.hooks.provideParser():e?b.parse:b.parseInline;if(r.async)return Promise.resolve(r.hooks?r.hooks.preprocess(n):n).then(p=>a(p,r)).then(p=>r.hooks?r.hooks.processAllTokens(p):p).then(p=>r.walkTokens?Promise.all(this.walkTokens(p,r.walkTokens)).then(()=>p):p).then(p=>c(p,r)).then(p=>r.hooks?r.hooks.postprocess(p):p).catch(o);try{r.hooks&&(n=r.hooks.preprocess(n));let p=a(n,r);r.hooks&&(p=r.hooks.processAllTokens(p)),r.walkTokens&&this.walkTokens(p,r.walkTokens);let u=c(p,r);return r.hooks&&(u=r.hooks.postprocess(u)),u}catch(p){return o(p)}}}onError(e,t){return n=>{if(n.message+=`
Please report this to https://github.com/markedjs/marked.`,e){let s="<p>An error occurred:</p><pre>"+R(n.message+"",!0)+"</pre>";return t?Promise.resolve(s):s}if(t)return Promise.reject(n);throw n}}};var M=new E;function k(l,e){return M.parse(l,e)}k.options=k.setOptions=function(l){return M.setOptions(l),k.defaults=M.defaults,N(k.defaults),k};k.getDefaults=z;k.defaults=w;k.use=function(...l){return M.use(...l),k.defaults=M.defaults,N(k.defaults),k};k.walkTokens=function(l,e){return M.walkTokens(l,e)};k.parseInline=M.parseInline;k.Parser=b;k.parser=b.parse;k.Renderer=$;k.TextRenderer=_;k.Lexer=x;k.lexer=x.lex;k.Tokenizer=S;k.Hooks=L;k.parse=k;var it=k.options,ot=k.setOptions,lt=k.use,at=k.walkTokens,ct=k.parseInline,pt=k,ut=b.parse,ht=x.lex;

if(__exports != exports)module.exports = exports;return module.exports}));

</script>
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
        <div class="logo-main">JARVIS <span>Results</span></div>
        <div class="logo-sub">Live Markdown Viewer</div>
      </div>
    </div>
    <div class="version-badge" id="version-badge">v__APP_VERSION__</div>
    <div id="title-options" style="display:flex; align-items:center; gap:12px; transition: opacity 1.5s ease;">
      <span id="mode-badge"></span>
    </div>
  </div>

  <!-- Body -->
  <div id="body">
    <!-- Sidebar -->
    <nav id="sidebar">
      <div class="search-box">
        <input type="text" id="search" placeholder="Filter results..." oninput="renderFileList()">
      </div>
      <div id="file-list"></div>
    </nav>

    <!-- Content -->
    <div id="content">
      <div id="toolbar">
        <span class="file-title" id="current-file-title">Select a result</span>
        <span class="file-timestamp" id="current-file-timestamp"></span>
      </div>
      <div id="content-area">
        <div class="markdown-body" id="md-display"></div>
        <textarea id="edit-area" placeholder="Edit markdown content..."></textarea>
      </div>
    </div>
  </div>

</div>

<div id="toast"></div>
<div id="center-toast">Copied!</div>

  <div id="context-menu">
    <div class="dropdown-item" onclick="cmRename()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg> Rename</div>
    <div class="dropdown-item" onclick="cmCopy()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> Copy Content</div>
    <div class="dropdown-item" onclick="cmToggleEdit()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg> Read / Source</div>
    <div class="dropdown-item danger" onclick="cmDelete()"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg> Delete</div>
  </div>

<script>
// ═══════════════════════════════════════════════════════════════
//  GLOBALS
// ═══════════════════════════════════════════════════════════════
let files = [];
let currentFile = null;
let isEditMode = false;
let isLiveActive = false;

// Variables for background live tracking and unread status
let unreadFiles = new Set(); 
let userNavigatedAway = false; 
let liveContentBuffer = "";
let lastLiveMtime = 0;
let liveInterval = null;
let fileListElements = new Map(); // filename -> DOM node (لمنع إعادة بناء القائمة بالكامل)
let lastRenderedBlocks = []; // raw (pre-highlight) HTML لكل block في md-display — أساس الـ diff

// ═══════════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════════
window.addEventListener('pywebviewready', init);

async function init() {
  try {
    await loadFileList();
    
    if (typeof window.LIVE_MODE !== 'undefined' && window.LIVE_MODE) {
      lastLiveMtime = 0; // Ensure we catch the current stream
      setupFocusMode();
    } else {
      // If opened normally, initialize lastLiveMtime so we ignore past finished streams
      try {
        const res = JSON.parse(await pywebview.api.get_live_content());
        if (res.ok) {
          lastLiveMtime = res.mtime;
        }
      } catch (e) {}
    }

    // Always poll to detect new streams starting in the background
    liveInterval = setInterval(pollLiveStream, 500);
  } catch (e) {
    document.getElementById('md-display').innerHTML = `<p style="color:var(--red)">Init failed: ${e.message}</p>`;
  }
}

function setupFocusMode() {
  isLiveActive = true;
  userNavigatedAway = false;
  currentFile = null;
  
  const titleOpts = document.getElementById('title-options');
  if (titleOpts) {
    titleOpts.style.opacity = '0';
    titleOpts.style.pointerEvents = 'none';
  }

  // Exclusive Live Mode -> Hide Sidebar
  document.getElementById('body').classList.add('focus-mode');
  
  document.getElementById('mode-badge').textContent = 'LIVE';
  pywebview.api.notify_live_ready();
  document.getElementById('current-file-title').textContent = 'Live Streaming...';
  lastRenderedBlocks = [];
  document.getElementById('md-display').innerHTML = '';
}

async function pollLiveStream() {
  try {
    const res = JSON.parse(await pywebview.api.get_live_content());
    if (res.ok && res.mtime > lastLiveMtime) {
      lastLiveMtime = res.mtime;
      const isDone = res.content.includes('&LIVE_DONE&');

      // Detect new live stream start (only if there is actual content!)
      if (!isLiveActive && !isDone && res.content.trim() !== "") {
        isLiveActive = true;
        liveContentBuffer = res.content;
        
        userNavigatedAway = (currentFile !== null);
        
        if (!userNavigatedAway) {
          setupFocusMode();
        }
        
        renderFileList(); // Show live indicator in sidebar
      }

      if (isLiveActive) {
        if (isDone) {
          // Stream finished
          const parts = res.content.split('&LIVE_DONE&');
          const finalContent = parts[0].trimEnd();
          const finalFilename = parts[1] ? parts[1].trim() : "";
          
          isLiveActive = false;
          
          document.getElementById('body').classList.remove('focus-mode');
          document.getElementById('mode-badge').textContent = '';
          toast('Live stream completed.', 'success');
          
          await animateSidebarReveal(finalFilename);
          
          const titleOpts = document.getElementById('title-options');
          if (titleOpts) {
            titleOpts.style.opacity = '1';
            titleOpts.style.pointerEvents = 'auto';
          }
          
          if (userNavigatedAway && finalFilename) {
            unreadFiles.add(finalFilename);
            await loadFileList();
          } else {
            showMarkdown(finalContent);
            await loadFileList();
            if (finalFilename) {
              const targetFile = files.find(f => f.filename === finalFilename);
              if (targetFile) selectFile(targetFile);
            }
          }
        } else {
          // Normal streaming
          liveContentBuffer = res.content;
          
          if (!userNavigatedAway) {
            const contentArea = document.getElementById('content-area');
            const isAtBottom = contentArea.scrollHeight - contentArea.clientHeight <= contentArea.scrollTop + 50;
            const oldScrollTop = contentArea.scrollTop;
            
            // Do not interrupt user if they are selecting text
            const isSelecting = window.getSelection().toString().length > 0;
            
            if (!isSelecting) {
              showMarkdown(res.content);
              
              if (isAtBottom) {
                contentArea.scrollTop = contentArea.scrollHeight;
              } else {
                contentArea.scrollTop = oldScrollTop;
              }
            }
          }
        }
      }
    }
  } catch (e) {
    console.error('Bridge error:', e);
  }
}

//   Function to animate the final filename revealing in the sidebar
async function animateSidebarReveal(filename) {
  // Try to clean the name exactly how Python does it
  let displayName = filename.replace(/_\d{8}_result\.md$/, '').replace(/_/g, ' ') + ' (New)';
  
  const liveNameSpan = document.getElementById('live-sidebar-name');
  const liveIndicator = document.querySelector('.live-indicator');
  
  if (liveIndicator) liveIndicator.remove(); // Remove pulse dot
  
  if (liveNameSpan) {
    liveNameSpan.textContent = '';
    // Slow typing effect for the name
    for (let i = 0; i < displayName.length; i++) {
      liveNameSpan.textContent += displayName.charAt(i);
      await new Promise(r => setTimeout(r, 60)); // 60ms delay per char
    }
    // Hold for a moment to let the user see it completed
    await new Promise(r => setTimeout(r, 500));
  }
}

// ═══════════════════════════════════════════════════════════════
//  CONTEXT MENU ACTIONS
// ═══════════════════════════════════════════════════════════════
let contextMenuTarget = null;
function showContextMenu(event, filename, display_name, timestamp) {
  event.stopPropagation();
  contextMenuTarget = {filename, display_name, timestamp};
  const menu = document.getElementById('context-menu');
  menu.classList.add('show');
  
  const rect = event.target.getBoundingClientRect();
  menu.style.top = (rect.bottom + window.scrollY) + 'px';
  menu.style.left = (rect.right - menu.offsetWidth + window.scrollX) + 'px';
}
document.addEventListener('click', function(e) {
  const menu = document.getElementById('context-menu');
  if (menu && menu.classList.contains('show') && !menu.contains(e.target)) {
    menu.classList.remove('show');
  }
});
async function cmRename() {
  if (!contextMenuTarget) return;
  const target = contextMenuTarget;
  document.getElementById('context-menu').classList.remove('show');
  
  const newName = await customPrompt("Enter new name:", target.display_name);
  if (newName && newName.trim() !== target.display_name) {
    const res = JSON.parse(await pywebview.api.rename_result(target.filename, newName));
    if (res.ok) {
      if (currentFile && currentFile.filename === target.filename) {
        currentFile.filename = res.new_filename;
        currentFile.display_name = newName;
        document.getElementById('current-file-title').textContent = newName;
      }
      loadFileList();
    } else {
      toast("Error renaming file: " + (res.error || ''), "error");
    }
  }
}
async function cmDelete() {
  if (!contextMenuTarget) return;
  const target = contextMenuTarget;
  document.getElementById('context-menu').classList.remove('show');
  
  if (await customConfirm(`Are you sure you want to delete "${target.display_name}"?`)) {
    const res = JSON.parse(await pywebview.api.delete_result(target.filename));
    if (res.ok) {
      if (currentFile && currentFile.filename === target.filename) {
        document.getElementById('current-file-title').textContent = 'Select a result';
        document.getElementById('current-file-timestamp').textContent = '';
        document.getElementById('md-display').innerHTML = '';
        document.getElementById('edit-area').style.display = 'none';
        document.getElementById('md-display').style.display = 'block';
        currentFile = null;
        isEditMode = false;
      }
      loadFileList();
      toast("File deleted.", "success");
    } else {
      toast("Error deleting file: " + (res.error || ''), "error");
    }
  }
}
async function cmToggleEdit() {
  if (!contextMenuTarget) return;
  const target = contextMenuTarget;
  document.getElementById('context-menu').classList.remove('show');
  if (!currentFile || currentFile.filename !== target.filename) {
     await selectFile(target);
  }
  toggleEdit();
}

async function cmCopy() {
  if (!contextMenuTarget) return;
  document.getElementById('context-menu').classList.remove('show');

  try {
    let content = "";
    if (currentFile && currentFile.filename === contextMenuTarget.filename) {
       content = currentFile.content || "";
    } else {
       const res = JSON.parse(await pywebview.api.load_result_content(contextMenuTarget.filename));
       content = res.content || "";
    }

    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(content);
    } else {
      // Fallback for pywebview or non-secure contexts
      const textArea = document.createElement("textarea");
      textArea.value = content;
      textArea.style.position = "fixed";
      textArea.style.left = "-9999px";
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      document.execCommand("copy");
      document.body.removeChild(textArea);
    }
    showCenterToast("Copied!");
  } catch (err) {
    toast("Failed to copy", "error");
  }
}

// ═══════════════════════════════════════════════════════════════
//  FILE LISTING
// ═══════════════════════════════════════════════════════════════
async function loadFileList() {
  const res = JSON.parse(await pywebview.api.get_results_list());
  if (res.ok) {
    files = res.files;
    renderFileList();
  }
}

function renderFileList() {
  const list = document.getElementById('file-list');
  const search = document.getElementById('search').value.toLowerCase();

  // عنصر اللايف بيتحدث لوحده من غير ما يمسح باقي القائمة
  let liveDiv = document.getElementById('live-sidebar-item');
  let divider = list.querySelector('.sidebar-divider');
  if (isLiveActive) {
    if (!liveDiv) {
      liveDiv = document.createElement('div');
      liveDiv.className = 'file-item live-item';
      liveDiv.id = 'live-sidebar-item';
      liveDiv.innerHTML = '<span class="live-indicator"></span><span id="live-sidebar-name">Live Streaming...</span>';
      liveDiv.onclick = () => {
        userNavigatedAway = false;
        document.getElementById('current-file-title').textContent = 'Live Streaming...';
        lastRenderedBlocks = [];
        showMarkdown(liveContentBuffer);
        renderFileList(); // Re-render to clear active state from other files
      };
      list.insertBefore(liveDiv, list.firstChild);
    }
    if (!divider) {
      divider = document.createElement('hr');
      divider.className = 'sidebar-divider';
      list.insertBefore(divider, liveDiv.nextSibling);
    }
  } else {
    if (liveDiv) liveDiv.remove();
    if (divider) divider.remove();
  }

  const visible = files.filter(f => !search || f.display_name.toLowerCase().includes(search));
  const visibleNames = new Set(visible.map(f => f.filename));

  // شيل بس العناصر اللي فعلاً اتشالت أو اتفلترت
  for (const [filename, node] of fileListElements) {
    if (!visibleNames.has(filename)) {
      node.remove();
      fileListElements.delete(filename);
    }
  }

  // أضف/حدّث بس اللي اتغير — العناصر الثابتة متتلمسش خالص = صفر ومضة
  let anchor = divider || liveDiv || null;
  visible.forEach(f => {
    const isActive = currentFile && currentFile.filename === f.filename && !(!userNavigatedAway && isLiveActive);
    let node = fileListElements.get(f.filename);
    const prefix = unreadFiles.has(f.filename) ? '<span class="unread-dot" title="New / Unread"></span>' : '';
    const safeTitle = escapeHtml(f.display_name);
    const safeTitleJs = f.display_name.replace(/'/g, "\\'");
    const desiredHTML = prefix + safeTitle + `<div class="item-actions" onclick="showContextMenu(event, '${f.filename}', '${safeTitleJs}', ${f.timestamp})"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg></div>`;

    if (!node) {
      node = document.createElement('div');
      node.dataset.filename = f.filename;
      fileListElements.set(f.filename, node);
    }
    node.onclick = () => selectFile(f);

    if (node.dataset.html !== desiredHTML) {
      node.innerHTML = desiredHTML;
      node.dataset.html = desiredHTML;
    }
    const desiredClass = 'file-item' + (isActive ? ' active' : '');
    if (node.className !== desiredClass) node.className = desiredClass;

    const nextSibling = anchor ? anchor.nextSibling : list.firstChild;
    if (nextSibling !== node) list.insertBefore(node, nextSibling);
    anchor = node;
  });
}

async function selectFile(file) {
  // Mark that user is reading something else (Background Live Mode)
  if (isLiveActive) {
    userNavigatedAway = true;
    const titleOpts = document.getElementById('title-options');
    if (titleOpts) {
      titleOpts.style.opacity = '1';
      titleOpts.style.pointerEvents = 'auto';
    }
  }

  if (unreadFiles.has(file.filename)) {
    unreadFiles.delete(file.filename);
  }

  currentFile = file;
  document.getElementById('current-file-title').textContent = file.display_name;
  
  const tsElem = document.getElementById('current-file-timestamp');
  if (tsElem && file.timestamp) {
    const diff = (Date.now() / 1000) - file.timestamp;
    if (diff < 60) {
      tsElem.textContent = 'Just now';
    } else {
      const d = new Date(file.timestamp * 1000);
      tsElem.textContent = d.toLocaleDateString();
    }
  } else if (tsElem) {
    tsElem.textContent = '';
  }

  // Reset Edit mode when switching files
  isEditMode = false;
  document.getElementById('edit-area').style.display = 'none';
  document.getElementById('md-display').style.display = 'block';
  lastRenderedBlocks = [];

  const res = JSON.parse(await pywebview.api.load_result_content(file.filename));
  if (res.ok) {
    currentFile.content = res.content;
    showMarkdown(res.content);
  } else {
    document.getElementById('md-display').innerHTML = `<p style="color:var(--red)">Error: ${res.error}</p>`;
  }
  renderFileList();
}

// ═══════════════════════════════════════════════════════════════
//  MARKDOWN RENDERING
// ═══════════════════════════════════════════════════════════════
function highlightSyntax(raw) {
  const rules = [
    { cls: 'tok-comment',  re: /\/\/[^\n]*|#[^\n]*|\/\*[\s\S]*?\*\/|<!--[\s\S]*?-->/ },
    { cls: 'tok-string',   re: /"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`/ },
    { cls: 'tok-number',   re: /\b0[xX][0-9a-fA-F]+\b|\b\d+\.?\d*(?:[eE][+-]?\d+)?\b/ },
    { cls: 'tok-keyword',  re: /\b(?:function|def|class|const|let|var|return|if|else|elif|for|while|import|from|export|default|new|try|catch|except|finally|async|await|public|private|static|void|int|string|bool|true|false|null|None|True|False|self|this|switch|case|break|continue|struct|interface|extends|implements|namespace|using|package|throw|yield|lambda|in|is|not|and|or)\b/ },
    { cls: 'tok-function', re: /\b[A-Za-z_$][\w$]*(?=\s*\()/ },
    { cls: 'tok-bracket',  re: /[{}()\[\]]/ },
  ];
  const combined = new RegExp(rules.map(r => '(' + r.re.source + ')').join('|'), 'gm');
  let out = '', lastIndex = 0, m;
  while ((m = combined.exec(raw)) !== null) {
    out += escapeHtml(raw.slice(lastIndex, m.index));
    const idx = m.slice(1).findIndex(g => g !== undefined);
    out += `<span class="${rules[idx].cls}">${escapeHtml(m[0])}</span>`;
    lastIndex = combined.lastIndex;
    if (m.index === combined.lastIndex) combined.lastIndex++;
  }
  out += escapeHtml(raw.slice(lastIndex));
  return out;
}

function applyCodeHighlighting(root) {
  const blocks = root.tagName === 'PRE' ? root.querySelectorAll('code') : root.querySelectorAll('pre code');
  blocks.forEach(block => {
    block.innerHTML = highlightSyntax(block.textContent);
  });
}

// NEW: Recursive DOM diffing algorithm to update only changed elements/text
// This targets the exact line/character being streamed without destroying the inner DOM.
function syncNodes(oldNode, newNode) {
  // 1. If node types or tags are completely different, replace entirely
  if (oldNode.nodeType !== newNode.nodeType || oldNode.nodeName !== newNode.nodeName) {
    oldNode.replaceWith(newNode.cloneNode(true));
    return;
  }
  
  // 2. If it's a text node, update only if the text changed
  if (oldNode.nodeType === Node.TEXT_NODE) {
    if (oldNode.nodeValue !== newNode.nodeValue) {
      oldNode.nodeValue = newNode.nodeValue;
    }
    return;
  }
  
  // 3. Sync Attributes
  if (oldNode.attributes && newNode.attributes) {
    const newAttrs = Array.from(newNode.attributes);
    const oldAttrs = Array.from(oldNode.attributes);
    
    // Remove old attributes that don't exist anymore
    oldAttrs.forEach(attr => {
      if (!newNode.hasAttribute(attr.name)) oldNode.removeAttribute(attr.name);
    });
    // Add/Update new attributes
    newAttrs.forEach(attr => {
      if (oldNode.getAttribute(attr.name) !== attr.value) {
        oldNode.setAttribute(attr.name, attr.value);
      }
    });
  }
  
  // 4. Sync Children (The magic part)
  const oldChildren = Array.from(oldNode.childNodes);
  const newChildren = Array.from(newNode.childNodes);
  
  for (let i = 0; i < newChildren.length; i++) {
    if (!oldChildren[i]) {
      // If new node has more children, append them
      oldNode.appendChild(newChildren[i].cloneNode(true));
    } else {
      // Dive deeper into existing children
      syncNodes(oldChildren[i], newChildren[i]);
    }
  }
  
  // Remove any excess children from the old node
  while (oldNode.childNodes.length > newChildren.length) {
    oldNode.removeChild(oldNode.lastChild);
  }
}

// MODIFIED: morphMarkdown now uses granular sync instead of innerHTML replacement
function morphMarkdown(container, rawHTML) {
  const temp = document.createElement('div');
  temp.innerHTML = rawHTML;
  const newBlocks = Array.from(temp.children);
  const newRawHTML = newBlocks.map(n => n.outerHTML);

  newBlocks.forEach((freshNode, i) => {
    if (newRawHTML[i] === lastRenderedBlocks[i]) return; // Block hasn't changed at all
    
    applyCodeHighlighting(freshNode);
    const existing = container.children[i];
    
    if (existing) {
      // We now sync the DOM tree node-by-node (Zero flashing)
      syncNodes(existing, freshNode);
    } else {
      container.appendChild(freshNode);
    }
  });

  while (container.children.length > newBlocks.length) {
    container.lastElementChild.remove(); 
  }
  lastRenderedBlocks = newRawHTML;
}

function showMarkdown(text) {
  let lines = text.split('\n');
  let firstLine = lines[0] ? lines[0].trim() : '';
  let isCode = false;
  let codeExt = '';
  
  let match = firstLine.match(/^(?:>\s*)?([^\s]+\.([a-z0-9]+))$/i);
  if (match) {
    lines.shift();
    let ext = match[2].toLowerCase();
    if (ext !== 'md' && ext !== 'txt') {
      isCode = true;
      codeExt = ext;
    }
  } else if (lines.length > 0 && firstLine.match(/\.(md|txt)$/i)) {
    lines.shift();
  }
  
  let cleanText = lines.join('\n').trimStart();

  if (isCode && !cleanText.startsWith('```')) {
    cleanText = '```' + codeExt + '\n' + cleanText + '\n```';
  }

  const mdDisplay = document.getElementById('md-display');
  if (typeof marked === 'undefined') {
    mdDisplay.innerHTML = `<pre>${escapeHtml(cleanText)}</pre>`;
    return;
  }
  morphMarkdown(mdDisplay, marked.parse(cleanText));
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ═══════════════════════════════════════════════════════════════
//  EDIT MODE TOGGLE (PLACEHOLDER)
// ═══════════════════════════════════════════════════════════════
function toggleEdit() {
  if (!currentFile) return;
  isEditMode = !isEditMode;
  const display = document.getElementById('md-display');
  const editArea = document.getElementById('edit-area');
  if (isEditMode) {
    // switch to edit
    editArea.value = currentFile.content || '';
    display.style.display = 'none';
    editArea.style.display = 'block';
    toast('Switched to Edit mode', 'success');
  } else {
    // save edited content back to file
    const newContent = editArea.value;
    currentFile.content = newContent;
    showMarkdown(newContent);
    display.style.display = 'block';
    editArea.style.display = 'none';
    toast('Switched to Read mode', 'success');
    // Save to disk
    pywebview.api.save_result_content(currentFile.filename, newContent).then(res => {
      const r = JSON.parse(res);
      if (r.ok) toast('Saved changes to disk', 'success');
      else toast('Error saving', 'error');
    });
  }
}

// ═══════════════════════════════════════════════════════════════
//  LIVE UPDATE (called from Python via evaluate_js)
// ═══════════════════════════════════════════════════════════════
window.updateLiveContent = function(markdownText) {
  if (isLiveActive) {
    showMarkdown(markdownText);
    // Optionally scroll to bottom
    const contentArea = document.getElementById('content-area');
    contentArea.scrollTop = contentArea.scrollHeight;
  }
}

// ═══════════════════════════════════════════════════════════════
//  TOAST / CLOSE
// ═══════════════════════════════════════════════════════════════
function toast(msg, type='success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  setTimeout(() => el.className = '', 3500);
}

function showCenterToast(msg) {
  const el = document.getElementById('center-toast');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 2000);
}

async function closeWindow() {
  await pywebview.api.close_window();
}

function customConfirm(msg) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-overlay');
    document.getElementById('modal-msg').innerHTML = msg;
    const input = document.getElementById('modal-input');
    input.style.display = 'none';
    input.value = '';
    
    overlay.style.display = 'flex';
    document.getElementById('modal-ok').onclick = () => { overlay.style.display = 'none'; resolve(true); };
    document.getElementById('modal-cancel').onclick = () => { overlay.style.display = 'none'; resolve(false); };
  });
}

function customPrompt(msg, defaultText) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-overlay');
    document.getElementById('modal-msg').innerHTML = msg;
    
    const input = document.getElementById('modal-input');
    input.style.display = 'block';
    input.value = defaultText || '';
    
    overlay.style.display = 'flex';
    input.focus();
    input.select();
    
    document.getElementById('modal-ok').onclick = () => { overlay.style.display = 'none'; resolve(input.value); };
    document.getElementById('modal-cancel').onclick = () => { overlay.style.display = 'none'; resolve(null); };
  });
}
</script>

<div id="modal-overlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);backdrop-filter:blur(4px);z-index:1000;align-items:center;justify-content:center;">
  <div class="card" style="background:var(--surface-1);border:1px solid var(--border-default);border-radius:var(--radius-md);width:360px;margin:0;box-shadow:var(--shadow-lg);">
    <div class="card-header" style="border-bottom:1px solid var(--border-default);padding:16px 20px;display:flex;align-items:center;">
      <div class="icon" style="width:32px;height:32px;border-radius:var(--radius-sm);background:linear-gradient(135deg, rgba(201,162,39,0.15), rgba(201,162,39,0.05));border:1px solid var(--border-gold);display:flex;align-items:center;justify-content:center;color:var(--gold);">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
      </div>
      <div class="title" style="margin-left:10px;font-size:15px;color:var(--txt-primary);font-weight:600;">Action Required</div>
    </div>
    <div class="card-body" style="padding:20px;font-size:13px;color:var(--txt-secondary);line-height:1.5">
      <div id="modal-msg"></div>
      <input type="text" id="modal-input" style="display:none;margin-top:12px;width:100%;background:var(--surface-2);color:var(--txt-primary);border:1px solid var(--border-default);border-radius:var(--radius-md);padding:10px 14px;font-size:13px;font-family:inherit;outline:none;transition:all var(--trans-fast);" />
    </div>
    <div style="padding:14px 20px;border-top:1px solid var(--border-default);display:flex;justify-content:flex-end;gap:10px;background:var(--surface-2);border-bottom-left-radius:12px;border-bottom-right-radius:12px">
      <button class="btn-ghost btn-sm" id="modal-cancel" style="padding:6px 14px;border-radius:6px;background:var(--surface-3);color:var(--txt-secondary);border:1px solid var(--border-default);cursor:pointer;">Cancel</button>
      <button class="btn-primary btn-sm" id="modal-ok" style="padding:6px 14px;border-radius:6px;background:linear-gradient(135deg, var(--gold), var(--gold-dark));color:#0a0e14;border:none;font-weight:600;cursor:pointer;">Confirm</button>
    </div>
  </div>
</div>

</body>
</html>
"""


# ╔══════════════════════════════════════════════════════════════╗
# ║                LIVE FEED WRAPPER                              ║
# ╚══════════════════════════════════════════════════════════════╝
class LiveFeed:
    """Object used to push data to the external viewer process via a sync file."""
    def __init__(self, on_first_chunk=None):
        self._accumulated = ""
        self._results_dir = Path(get_setting("results_dir", str(SHARE_DIR / "results")))
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir = CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._sync_file = self._cache_dir / ".live_stream.md"
        self._on_first_chunk = on_first_chunk
        self._has_sent = False
        # Clear the file on init
        self._sync_file.write_text("", encoding='utf-8')

    def send(self, text: str):
        if not self._has_sent and self._on_first_chunk:
            self._has_sent = True
            try:
                self._on_first_chunk()
            except Exception:
                pass
                
        self._accumulated += text
        
        # Hide the first line if it looks like a raw filename (e.g., iPhone_Differences.md)
        display_text = self._accumulated
        lines = display_text.split('\n', 1)
        first_line = lines[0].strip()
        
        if first_line.lower().endswith('.md') or first_line.lower().endswith('.txt'):
            if len(lines) > 1:
                display_text = lines[1].lstrip('\n')
            else:
                display_text = ""
        elif len(lines) == 1 and not ' ' in first_line and len(first_line) < 40:
            # While still streaming the potential filename and no newline has been reached yet
            display_text = ""
            
        # Clean up closing tag if the LLM reached it
        display_text = display_text.replace('</result>', '')
            
        try:
            self._sync_file.write_text(display_text, encoding='utf-8')
        except Exception:
            pass

    def signal_done(self, filename: str):
        """Append the LIVE_DONE marker to the stream file so the JS viewer can transition."""
        try:
            marker = f"\n\n&LIVE_DONE&{filename}"
            self._sync_file.write_text(self._accumulated + marker, encoding='utf-8')
            # The JS will read this, transition, and we don't immediately delete it here 
            # so the JS has time to see the marker on its 500ms polling interval.
        except Exception:
            pass


# ╔══════════════════════════════════════════════════════════════╗
# ║                   LAUNCHER FUNCTIONS                          ║
# ╚══════════════════════════════════════════════════════════════╝
def open_viewer(live: bool = False):
    """
    Open the results viewer window.
    - If `live=False`, opens in browse mode.
    - If `live=True`, opens in live‑streaming mode and polls for updates.
    NOTE: This blocks the thread until the window is closed. It should be run in a separate process.
    """
    os.environ.setdefault(
        'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS',
        '--disable-background-networking --disable-component-update --disable-domain-reliability'
    )
    # Enforce single instance (optional)
    from core.bootstrap.utils import enforce_single_instance
    mutex_name = "JARVIS_ResultsViewer_Mutex"
    if not enforce_single_instance(mutex_name, "JARVIS NEXUS · Results Viewer"):
        print("Results Viewer is already open.")
        return

    # Prepare HTML with live flag
    live_flag = 'true' if live else 'false'
    from core.config import APP_VERSION
    html_content = HTML.replace('v__APP_VERSION__', f'v{APP_VERSION}')
    # Inject the LIVE_MODE variable before pywebviewready
    html_content = html_content.replace(
        'window.addEventListener(\'pywebviewready\', init);',
        f'window.LIVE_MODE = {live_flag};\nwindow.addEventListener(\'pywebviewready\', init);'
    )

    api = API()
    window = webview.create_window(
        title       = "JARVIS NEXUS · Results Viewer",
        html        = html_content,
        js_api      = api,
        width       = 1000,
        height      = 700,
        min_size    = (800, 560),
        resizable   = True,
        background_color = "#0a0e14",
    )

    if live:
        # Live mode is now handled purely by frontend JavaScript polling the backend API
        # to completely avoid cross-thread COM exceptions in pywebview on Windows.
        pass

    webview.start(debug=False, icon=TRAY_ICON_PATH)


# ── Standalone test ────────────────────────────────────────────
if __name__ == "__main__":
    # Test viewer mode
    open_viewer(live=False)