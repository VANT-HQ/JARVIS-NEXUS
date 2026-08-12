# core/bootstrap/template_builder.py
"""
JARVIS NEXUS — Custom Ollama Template Builder (Premium Gold Theme)
==================================================================
Stable logic merged with Gold/Amber premium design.
All original functionality preserved; only visual layer updated.
"""

import json
import logging
import webview
import threading
import sys
import subprocess
import platform
from pathlib import Path
from typing import Optional

try:
    _temp_root = str(Path(__file__).resolve().parent.parent.parent)
    if _temp_root not in sys.path:
        sys.path.insert(0, _temp_root)
    from core.config import TRAY_ICON_PATH
except ImportError as e:
    print(f"❌  Cannot load core/config.py\n{e}")
    logging.error(f"Cannot load core/config.py: {e}")
    TRAY_ICON_PATH = ""
from core.bootstrap.llm_templates import MODEL_TEMPLATES

logger = logging.getLogger(__name__)


# ╔══════════════════════════════════════════════════════════════╗
# ║                   REFERENCE TEMPLATE BUILDER                 ║
# ╚══════════════════════════════════════════════════════════════╝
def _build_reference_payload(model_filename: str) -> str:
    """Builds conversion prompt with Qwen reference template."""
    qwen_ref = MODEL_TEMPLATES.get("qwen_chatml", {})
    template_text = qwen_ref.get("template", "")
    params = qwen_ref.get("parameters", [])
    params_text = "\n".join(f"PARAMETER {p}" for p in params)

    return (
        f"=== CONVERSION REQUEST ===\n"
        f"CONTEXT: This request is for JARVIS-NEXUS (github.com/VANT-HQ/JARVIS-NEXUS).\n\n"
        f"Convert this Qwen/ChatML Ollama Modelfile to work with: \"{model_filename}\"\n\n"
        f"RULES:\n"
        f"1. Adjust ONLY the special tokens (BOS/EOS/role markers) to match this model's tokenizer.\n"
        f"2. Keep the tool_call / tool_response XML structure IDENTICAL.\n"
        f"3. Adjust PARAMETER stop tokens to match the new model's special tokens.\n"
        f"4. CRITICAL: Output EXACTLY ONE raw markdown code block with the final TEMPLATE + PARAMETER lines.\n\n"
        f"=== SOURCE SNIPPET ===\n"
        f'TEMPLATE """\n{template_text}"""\n'
        f"{params_text}\n"
    )


# ╔══════════════════════════════════════════════════════════════╗
# ║                    PYTHON ↔ JS BRIDGE                        ║
# ╚══════════════════════════════════════════════════════════════╝
class TemplateAPI:
    """Exposed to JavaScript via window.pywebview.api.*"""
    
    def __init__(self, model_filename: str, reference_text: str, has_auto: bool):
        self.model_filename = model_filename
        self.reference_text = reference_text
        self.has_auto = has_auto
        self.user_template: Optional[str] = None
        self._window = None

    def set_window(self, w):
        self._window = w

    def get_info(self):
        """Returns model name and reference template."""
        return json.dumps({
            "model": self.model_filename,
            "reference": self.reference_text,
            "has_auto": self.has_auto
        })

    def copy_reference(self):
        """Copies reference to clipboard."""
        try:
            if platform.system() == "Windows":
                subprocess.run("clip", input=self.reference_text, text=True, encoding="utf-8", check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            elif self._window:
                self._window.evaluate_js(
                    f"navigator.clipboard.writeText({json.dumps(self.reference_text)})"
                )
            return json.dumps({"ok": True})
        except Exception as e:
            logger.error(f"Clipboard copy failed: {e}")
            return json.dumps({"ok": False, "error": str(e)})

    def submit_template(self, template: str):
        """User submitted a valid template."""
        self.user_template = template.strip()
        if self._window:
            self._window.destroy()
        return json.dumps({"ok": True})

    def submit_auto(self):
        """User clicked Auto Build."""
        self.user_template = "__AUTO__"
        if self._window:
            self._window.destroy()
        return json.dumps({"ok": True})

    def abort(self):
        """User chose to exit without providing template."""
        self.user_template = None
        if self._window:
            self._window.destroy()
        return json.dumps({"ok": True})


# ╔══════════════════════════════════════════════════════════════╗
# ║              PREMIUM HTML / UI (GOLD THEME MERGED)           ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>JARVIS NEXUS · Template Builder</title>
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
  padding:20px 28px;flex-shrink:0;
  position:relative;z-index:10;
}
#header::after{
  content:'';position:absolute;bottom:-1px;left:0;right:0;
  height:1px;background:linear-gradient(90deg, transparent, var(--gold-glow-strong), transparent);
}

.header-top{display:flex;align-items:center;gap:16px;margin-bottom:8px;}
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

.header-model{
  font-size:13px;color:var(--txt-secondary);margin-top:4px;
  font-family:"JetBrains Mono",monospace;
  background:var(--surface-3);
  padding:6px 12px;border-radius:var(--radius-sm);
  display:inline-block;border:1px solid var(--border-default);
}

/* ── Body ───────────────────────────────────────────────── */
#body{
  flex:1;overflow-y:auto;padding:24px 28px;display:flex;flex-direction:column;gap:20px;
  position:relative;z-index:1;
}

/* Instruction Card */
.inst-card{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);padding:18px 22px;
  box-shadow:var(--shadow-md);
  transition:border-color var(--trans-normal);
}
.inst-card:hover{border-color:var(--border-active);box-shadow:var(--shadow-gold);}

.inst-title{
  font-size:15px;font-weight:600;color:var(--gold-light);
  margin-bottom:14px;display:flex;align-items:center;gap:10px;
}
.inst-title::before{
  content:'\2666';color:var(--gold);font-size:18px;
}
.inst-list{list-style:none;padding:0;}
.inst-list li{
  padding:8px 0;font-size:13px;color:var(--txt-secondary);
  line-height:1.6;position:relative;padding-left:28px;
}
.inst-list li:before{
  content:'\2192';position:absolute;left:0;color:var(--gold);
  font-weight:700;font-size:14px;
}
.inst-list code{
  background:var(--surface-1);padding:2px 8px;border-radius:4px;
  font-family:monospace;font-size:12px;color:var(--gold-light);
  border:1px solid var(--border-gold);
}

/* Textarea Section */
.input-section{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-3));
  border:1px solid var(--border-default);
  border-radius:var(--radius-lg);padding:18px 22px;flex:1;
  display:flex;flex-direction:column;gap:12px;
  box-shadow:var(--shadow-md);
  transition:border-color var(--trans-normal);
}
.input-section:hover{border-color:var(--border-active);box-shadow:var(--shadow-gold);}

.input-label{
  font-size:13px;color:var(--txt-muted);font-weight:600;
  display:flex;align-items:center;gap:8px;
}
.input-label::before{content:'\270E';color:var(--gold);}
textarea{
  flex:1;background:var(--surface-1);color:var(--txt-primary);
  border:1px solid var(--border-default);border-radius:var(--radius-md);
  padding:14px;font-size:12px;font-family:"JetBrains Mono",monospace;
  outline:none;transition:all var(--trans-fast);
  resize:none;min-height:200px;line-height:1.6;
}
textarea:hover{border-color:var(--border-active);}
textarea:focus{border-color:var(--gold);box-shadow:0 0 0 3px var(--gold-glow);}
textarea::placeholder{color:var(--txt-muted);opacity:0.6;}

/* ── Footer ─────────────────────────────────────────────── */
#footer{
  background:linear-gradient(180deg, var(--surface-2), var(--surface-1));
  border-top:1px solid var(--border-default);
  padding:16px 28px;display:flex;align-items:center;gap:12px;
  flex-shrink:0;position:relative;z-index:10;
}
#footer::before{
  content:'';position:absolute;top:-1px;left:0;right:0;
  height:1px;background:linear-gradient(90deg, transparent, var(--gold-glow-strong), transparent);
}
#footer .info{flex:1;font-size:12px;color:var(--txt-muted);}
#footer .status{
  font-size:12px;color:var(--green);opacity:0;
  transition:opacity .3s;
  display:flex;align-items:center;gap:6px;
}
#footer .status.show{opacity:1}
#footer .status::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--green);box-shadow:0 0 8px var(--green);}

/* ── Buttons (Premium) ──────────────────────────────────── */
button{
  display:inline-flex;align-items:center;gap:8px;
  padding:10px 20px;border-radius:var(--radius-md);border:none;
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
button:disabled{opacity:.4;cursor:not-allowed}

.btn-primary{
  background:linear-gradient(135deg, var(--gold), var(--gold-dark));
  color:#0a0e14;box-shadow:0 4px 15px rgba(201,162,39,0.25);
}
.btn-primary:hover:not(:disabled){
  box-shadow:0 6px 20px rgba(201,162,39,0.4);transform:translateY(-1px);
}

.btn-success{
  background:rgba(34,197,94,0.1);color:var(--green);
  border:1px solid rgba(34,197,94,0.2);
}
.btn-success:hover:not(:disabled){background:rgba(34,197,94,0.2);}

.btn-warning{
  background:rgba(234,179,8,0.1);color:var(--yellow);
  border:1px solid rgba(234,179,8,0.2);
}
.btn-warning:hover:not(:disabled){background:rgba(234,179,8,0.2);}

.btn-danger{
  background:rgba(239,68,68,0.08);color:var(--red);
  border:1px solid rgba(239,68,68,0.2);
}
.btn-danger:hover:not(:disabled){background:rgba(239,68,68,0.15);}

.btn-ghost{
  background:var(--surface-3);color:var(--txt-secondary);
  border:1px solid var(--border-default);
}
.btn-ghost:hover:not(:disabled){
  background:var(--surface-4);color:var(--txt-primary);
  border-color:var(--border-active);
}

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
#toast.ok::before{content:'\u2713';width:22px;height:22px;border-radius:50%;background:rgba(34,197,94,0.15);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;}
#toast.err::before{content:'!';width:22px;height:22px;border-radius:50%;background:rgba(239,68,68,0.15);display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;}

/* ── Modal Overlay ──────────────────────────────────────── */
.modal-overlay{
  position:fixed;inset:0;background:rgba(10,14,20,0.85);backdrop-filter:blur(6px);
  display:flex;align-items:center;justify-content:center;z-index:9999;
  opacity:0;pointer-events:none;transition:all var(--trans-normal);
}
.modal-overlay.show{opacity:1;pointer-events:auto;}
.modal-card{
  background:linear-gradient(180deg, var(--surface-1), var(--surface-2));
  border:1px solid var(--border-active);border-radius:var(--radius-lg);
  padding:24px 28px;width:400px;max-width:90%;
  box-shadow:var(--shadow-lg), 0 0 40px rgba(201,162,39,0.15);
  transform:translateY(20px) scale(0.95);transition:all var(--trans-normal);
}
.modal-overlay.show .modal-card{transform:translateY(0) scale(1);}
.modal-title{font-size:18px;font-weight:700;color:var(--gold-light);margin-bottom:12px;}
.modal-msg{font-size:14px;color:var(--txt-secondary);line-height:1.5;margin-bottom:24px;}
.modal-actions{display:flex;justify-content:flex-end;gap:12px;}
</style>
</head>
<body>
<div id="app">

<div id="header">
  <div class="header-top">
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
        <div class="logo-main">JARVIS <span>Templates</span></div>
        <div class="logo-sub">Custom Model Configuration</div>
      </div>
    </div>
    <div class="version-badge" id="version-badge">v__APP_VERSION__</div>
  </div>
  <div class="header-model" id="model-name">Loading...</div>
</div>

<div id="body">

  <div class="inst-card">
    <div class="inst-title">How to Generate a Custom Template</div>
    <ul class="inst-list">
      <li>If <strong style="color:var(--green);">Auto Build</strong> is available, JARVIS has detected the model's architecture. Click it!</li>
      <li>Otherwise, click <strong>"Copy Reference"</strong> to copy the Qwen/ChatML reference to your clipboard.</li>
      <li>Send the copied text to any Cloud AI (ChatGPT, Claude, etc.) and paste its response below.</li>
      <li>Click <strong>"Build Model (Manual)"</strong> to proceed manually, or <strong>"Exit"</strong> to abort.</li>
    </ul>
  </div>

  <div class="input-section">
    <div class="input-label">Paste Generated Template Here (For Manual Entry):</div>
    <textarea id="template-input" 
              placeholder="Paste the TEMPLATE and PARAMETER lines from your AI here...

Example:
TEMPLATE &quot;&quot;&quot;
{{ if .System }}<|im_start|>system
{{ .System }}<|im_end|>
...
&quot;&quot;&quot;
PARAMETER stop <|im_end|>
PARAMETER stop <|endoftext|>"></textarea>
  </div>

</div>

<div id="footer">
  <div class="info">Waiting for template input...</div>
  <span class="status" id="status-msg"></span>
  <button class="btn-ghost" onclick="copyReference()">
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg> Copy Reference
  </button>
  <button class="btn-warning" id="btn-auto" onclick="autoBuild()" disabled>
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg> Auto Build
  </button>
  <button class="btn-danger" onclick="abort()">
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg> Exit
  </button>
  <button class="btn-success" id="btn-build" onclick="buildModel()" disabled>
    <svg width="1em" height="1em" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 22 8.5 12 15 2 8.5 12 2"></polygon><polyline points="2 12.5 12 19 22 12.5"></polyline><polyline points="2 16.5 12 23 22 16.5"></polyline></svg> Build Model (Manual)
  </button>
</div>

</div>

<div id="toast"></div>

<!-- Custom Modal -->
<div id="modal-overlay" class="modal-overlay">
  <div class="modal-card">
    <div class="modal-title" id="modal-title">Confirm</div>
    <div class="modal-msg" id="modal-msg">Are you sure?</div>
    <div class="modal-actions">
      <button class="btn-ghost" id="modal-cancel">Cancel</button>
      <button class="btn-primary" id="modal-ok">OK</button>
    </div>
  </div>
</div>

<script>
// ╔══════════════════════════════════════════════════════════════╗
// ║                        INIT                                  ║
// ╚══════════════════════════════════════════════════════════════╝
window.addEventListener('pywebviewready', async () => {
  const info = JSON.parse(await pywebview.api.get_info());
  document.getElementById('model-name').textContent = info.model;
  window.referenceText = info.reference;  // store for copy
  
  if (info.has_auto) {
      document.getElementById('btn-auto').disabled = false;
      document.getElementById('btn-auto').className = 'btn-success';
  } else {
      document.getElementById('btn-auto').disabled = true;
      document.getElementById('btn-auto').className = 'btn-ghost';
      document.getElementById('btn-auto').title = "No auto-template available for this model family";
  }
});

// ╔══════════════════════════════════════════════════════════════╗
// ║                        ACTIONS                               ║
// ╚══════════════════════════════════════════════════════════════╝
async function copyReference() {
  const res = JSON.parse(await pywebview.api.copy_reference());
  if (res.ok) {
    toast('\u2713 Reference copied to clipboard! Send it to your AI.', 'ok');
    showStatus('Reference copied - ready to paste AI response');
  } else {
    toast('\u2716 Copy failed. Try manually copying from console.', 'err');
  }
}

async function buildModel() {
  const input = document.getElementById('template-input').value.trim();
  if (!input) {
    toast('\u26A0 Please paste the generated template first', 'err');
    return;
  }
  
  // Basic validation
  if (!input.includes('TEMPLATE') || !input.includes('PARAMETER')) {
    const proceed = await customConfirm('Incomplete Template', 'Template seems incomplete (missing TEMPLATE or PARAMETER lines).\n\nContinue anyway?');
    if (!proceed) return;
  }

  await pywebview.api.submit_template(input);
  toast('\u2713 Template submitted. Building model...', 'ok');
}

async function autoBuild() {
  await pywebview.api.submit_auto();
  toast('\u26A1 Auto-building model...', 'ok');
}

async function abort() {
  const proceed = await customConfirm('Exit Wizard', 'Exit without providing a template?\n\nModel build will be aborted.');
  if (proceed) {
    await pywebview.api.abort();
  }
}

// ╔══════════════════════════════════════════════════════════════╗
// ║                        UI HELPERS                            ║
// ╚══════════════════════════════════════════════════════════════╝
let toastTimer;
function toast(msg, type='ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `show ${type}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = '', 3500);
}

function showStatus(msg) {
  const el = document.getElementById('status-msg');
  el.textContent = msg;
  el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 4000);
}

function customConfirm(title, msg) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-overlay');
    document.getElementById('modal-title').textContent = title;
    document.getElementById('modal-msg').textContent = msg;
    
    const btnOk = document.getElementById('modal-ok');
    const btnCancel = document.getElementById('modal-cancel');
    
    const cleanup = () => {
      overlay.classList.remove('show');
      btnOk.onclick = null;
      btnCancel.onclick = null;
    };
    
    btnOk.onclick = () => { cleanup(); resolve(true); };
    btnCancel.onclick = () => { cleanup(); resolve(false); };
    
    overlay.classList.add('show');
  });
}

// Auto-enable build button when user types
document.getElementById('template-input').addEventListener('input', (e) => {
  const btn = document.getElementById('btn-build');
  btn.disabled = e.target.value.trim().length < 20;
});
</script>
</body>
</html>
"""


# ╔══════════════════════════════════════════════════════════════╗
# ║                       PUBLIC API                             ║
# ╚══════════════════════════════════════════════════════════════╝
def request_template_from_user(model_filename: str, has_auto: bool = False) -> Optional[str]:
    """
    Opens a PyWebView dialog for custom Ollama TEMPLATE input.
    If called from a background thread, it safely routes the call to a subprocess
    since pywebview must run on the main thread.
    
    Returns:
      str  → User provided template. Proceed with model build.
      "__AUTO__" → User chose Auto Build.
      None → User chose EXIT. Abort model build.
    """
    if threading.current_thread() is not threading.main_thread():
        logger.info("Routing template builder to subprocess (not on main thread).")
        try:
            if getattr(sys, 'frozen', False):
                args = [sys.executable, "--template", model_filename, str(has_auto)]
            elif "__compiled__" in globals():
                args = [sys.argv[0], "--template", model_filename, str(has_auto)]
            else:
                # MODIFIED: Use absolute path to prevent CWD-dependent failures
                import re as _re
                _app_path = str(Path(__file__).resolve().parent.parent.parent / "app.py")
                args = [sys.executable, _app_path, "--template", model_filename, str(has_auto)]
            
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
            res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs)
            out = res.stdout
            if "__TEMPLATE_ABORT__" in out:
                return None
            if "__TEMPLATE_START__" in out and "__AUTO__" in out and "__TEMPLATE_END__" in out:
                return "__AUTO__"
            # MODIFIED: Regex-based parsing — immune to terminal noise/ANSI codes before sentinel
            _match = _re.search(r'__TEMPLATE_START__\n(.*?)\n__TEMPLATE_END__', out, _re.DOTALL)
            if _match:
                return _match.group(1).strip()
                
            logger.error(f"Template subprocess failed or returned unknown output. Stdout: {out}")
            return _console_fallback(model_filename)
        except Exception as e:
            logger.error(f"Failed to spawn template builder subprocess: {e}")
            return _console_fallback(model_filename)

    try:
        logger.info(f"Opening template builder for: {model_filename}")
        
        import os
        os.environ.setdefault(
            'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS',
            '--disable-background-networking --disable-component-update --disable-domain-reliability'
        )
        
        from core.config import APP_VERSION
        html_content = HTML.replace('v__APP_VERSION__', f'v{APP_VERSION}')

        reference = _build_reference_payload(model_filename)
        api = TemplateAPI(model_filename, reference, has_auto)
        
        window = webview.create_window(
            title="JARVIS NEXUS · Template Builder",
            html=html_content,
            js_api=api,
            width=800,
            height=700,
            min_size=(650, 500),
            resizable=True,
            background_color="#0a0e14"
        )
        
        api.set_window(window)
        webview.start(debug=False, icon=TRAY_ICON_PATH)
        
        # Window closed — check result
        result = api.user_template
        if result:
            logger.info("User provided template (or clicked Auto)")
            return result
        else:
            logger.warning("User aborted template creation")
            return None
            
    except Exception as e:
        logger.error(f"Template builder failed: {e}")
        # Fallback to console
        return _console_fallback(model_filename)


def _console_fallback(model_filename: str) -> Optional[str]:
    """Last resort: console input if PyWebView fails."""
    print(f"\n{'='*60}")
    print(f"⚠️  No matching template for: {model_filename}")
    print(f"{'='*60}")
    print("\nPaste your TEMPLATE + PARAMETER lines below.")
    print("Type 'END' on a new line when done, or 'EXIT' to abort.\n")
    
    lines = []
    try:
        while True:
            line = input()
            if line.strip().upper() == 'END':
                break
            if line.strip().upper() == 'EXIT':
                return None
            lines.append(line)
        
        template = "\n".join(lines).strip()
        return template if template else None
        
    except (EOFError, KeyboardInterrupt):
        return None

if __name__ == "__main__":
    # Test execution when run directly
    import sys
    
    # Simple argument parsing for testing
    model = "Test-Model-Q5_K_M.gguf"
    has_auto = True
    
    if len(sys.argv) > 1:
        model = sys.argv[1]
    if len(sys.argv) > 2:
        has_auto = sys.argv[2].lower() == "true"
        
    res = request_template_from_user(model, has_auto=has_auto)
    
    # Print the result in the format expected by the subprocess caller
    if res == "__AUTO__":
        print("\n__TEMPLATE_START__\n__AUTO__\n__TEMPLATE_END__")
    elif res:
        print(f"\n__TEMPLATE_START__\n{res}\n__TEMPLATE_END__")
    else:
        print("\n__TEMPLATE_ABORT__")