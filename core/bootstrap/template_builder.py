# core/bootstrap/template_builder.py
"""
JARVIS NEXUS — Custom Ollama Template Builder
==============================================
Interactive GUI for acquiring a custom TEMPLATE when a GGUF model
doesn't match any known family in MODEL_TEMPLATES.

Returns:
  str  → User provided template. Proceed with model build.
  "__AUTO__" → User chose Auto Build.
  None → User chose EXIT. Abort model build.
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
# ║                          HTML / UI                           ║
# ╚══════════════════════════════════════════════════════════════╝
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>JARVIS · Template Builder</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--card:#1c2128;--input:#21262d;
  --border:#30363d;--accent:#58a6ff;--accent-h:#388bfd;
  --green:#3fb950;--red:#f85149;--yellow:#d29922;
  --txt:#e6edf3;--sub:#8b949e;--mute:#484f58;
  --r:10px;--rs:6px;--t:.18s ease;
}
html,body{
  height:100%;font-family:"Segoe UI",system-ui,sans-serif;
  background:var(--bg);color:var(--txt);font-size:14px;overflow:hidden;
}

/* ── Layout ──────────────────────────────────────────────── */
#app{display:flex;flex-direction:column;height:100vh;padding:0}

/* header */
#header{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:20px 28px;flex-shrink:0;
}
.header-icon{font-size:36px;margin-bottom:8px}
.header-title{font-size:18px;font-weight:700;letter-spacing:.3px}
.header-title span{color:var(--accent)}
.header-model{
  font-size:13px;color:var(--sub);margin-top:8px;
  font-family:monospace;background:var(--input);
  padding:6px 12px;border-radius:var(--rs);display:inline-block;
}

/* body */
#body{flex:1;overflow-y:auto;padding:24px 28px;display:flex;flex-direction:column;gap:20px}
#body::-webkit-scrollbar{width:6px}
#body::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}

/* instruction card */
.inst-card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:18px 22px;
}
.inst-title{
  font-size:15px;font-weight:600;color:var(--accent);
  margin-bottom:12px;display:flex;align-items:center;gap:8px;
}
.inst-list{
  list-style:none;padding:0;
}
.inst-list li{
  padding:8px 0;font-size:13px;color:var(--sub);
  line-height:1.6;position:relative;padding-left:24px;
}
.inst-list li:before{
  content:"→";position:absolute;left:0;color:var(--accent);
  font-weight:700;
}
.inst-list code{
  background:var(--input);padding:2px 8px;border-radius:4px;
  font-family:monospace;font-size:12px;color:var(--accent);
}

/* text area */
.input-section{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:18px 22px;flex:1;
  display:flex;flex-direction:column;gap:12px;
}
.input-label{font-size:13px;color:var(--sub);font-weight:600}
textarea{
  flex:1;background:var(--input);color:var(--txt);
  border:1px solid var(--border);border-radius:var(--rs);
  padding:12px;font-size:12px;font-family:monospace;
  outline:none;transition:border-color var(--t);
  resize:none;min-height:200px;
}
textarea:focus{border-color:var(--accent)}
textarea::placeholder{color:var(--mute)}

/* footer */
#footer{
  background:var(--surface);border-top:1px solid var(--border);
  padding:16px 28px;display:flex;align-items:center;gap:12px;
  flex-shrink:0;
}
#footer .info{flex:1;font-size:12px;color:var(--sub)}
#footer .status{
  font-size:12px;color:var(--green);opacity:0;
  transition:opacity .3s;
}
#footer .status.show{opacity:1}

/* ── Buttons ─────────────────────────────────────────────── */
button{
  display:inline-flex;align-items:center;gap:8px;
  padding:10px 20px;border-radius:var(--rs);border:none;
  font-size:13px;font-weight:600;cursor:pointer;
  font-family:inherit;transition:all var(--t);
}
button:active{transform:scale(.97)}
button:disabled{opacity:.4;cursor:not-allowed}
.btn-primary{background:var(--accent);color:#000}
.btn-primary:hover:not(:disabled){background:var(--accent-h)}
.btn-success{background:var(--green);color:#000}
.btn-success:hover:not(:disabled){background:#2ea043}
.btn-warning{background:var(--yellow);color:#000}
.btn-warning:hover:not(:disabled){background:#b07d1c}
.btn-danger{background:#2d1b1b;color:var(--red);border:1px solid #da3633}
.btn-danger:hover:not(:disabled){background:#3d2020}
.btn-ghost{background:var(--input);color:var(--txt);border:1px solid var(--border)}
.btn-ghost:hover:not(:disabled){background:#30363d}

/* ── Toast ───────────────────────────────────────────────── */
#toast{
  position:fixed;bottom:80px;right:24px;
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--r);padding:12px 20px;font-size:13px;
  box-shadow:0 8px 32px #0008;
  transform:translateY(10px);opacity:0;
  transition:all .22s;pointer-events:none;z-index:999;
}
#toast.show{transform:translateY(0);opacity:1}
#toast.ok{border-color:var(--green);color:var(--green)}
#toast.err{border-color:var(--red);color:var(--red)}
</style>
</head>
<body>
<div id="app">

<div id="header">
  <div class="header-icon">⚙️</div>
  <div class="header-title">JARVIS <span>NEXUS</span> — Template Builder</div>
  <div class="header-model" id="model-name">Loading…</div>
</div>

<div id="body">

  <div class="inst-card">
    <div class="inst-title">📋 How to Generate a Custom Template</div>
    <ul class="inst-list">
      <li>If <strong>⚡ Auto Build</strong> is green, JARVIS has natively detected the model's architecture. Click it!</li>
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
  <div class="info">Waiting for template input…</div>
  <span class="status" id="status-msg"></span>
  <button class="btn-ghost" onclick="copyReference()">📋 Copy Reference</button>
  <button class="btn-warning" id="btn-auto" onclick="autoBuild()" disabled>⚡ Auto Build</button>
  <button class="btn-danger" onclick="abort()">❌ Exit</button>
  <button class="btn-success" id="btn-build" onclick="buildModel()" disabled>🚀 Build Model (Manual)</button>
</div>

</div>
<div id="toast"></div>

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
    toast('✅ Reference copied to clipboard! Send it to your AI.', 'ok');
    showStatus('Reference copied — ready to paste AI response');
  } else {
    toast('❌ Copy failed. Try manually copying from console.', 'err');
  }
}

async function buildModel() {
  const input = document.getElementById('template-input').value.trim();
  if (!input) {
    toast('⚠️ Please paste the generated template first', 'err');
    return;
  }
  
  // Basic validation
  if (!input.includes('TEMPLATE') || !input.includes('PARAMETER')) {
    if (!confirm('⚠️ Template seems incomplete (missing TEMPLATE or PARAMETER lines).\n\nContinue anyway?')) {
      return;
    }
  }

  await pywebview.api.submit_template(input);
  toast('✅ Template submitted. Building model…', 'ok');
}

async function autoBuild() {
  await pywebview.api.submit_auto();
  toast('⚡ Auto-building model...', 'ok');
}

async function abort() {
  if (confirm('⚠️ Exit without providing a template?\n\nModel build will be aborted.')) {
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
                args = [sys.executable, "app.py", "--template", model_filename, str(has_auto)]
            
            kwargs = {}
            if platform.system() == "Windows":
                kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
            res = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", **kwargs)
            out = res.stdout
            if "__TEMPLATE_ABORT__" in out:
                return None
            if "__TEMPLATE_START__\n__AUTO__\n__TEMPLATE_END__" in out:
                return "__AUTO__"
            if "__TEMPLATE_START__" in out and "__TEMPLATE_END__" in out:
                return out.split("__TEMPLATE_START__\n")[1].split("\n__TEMPLATE_END__")[0]
                
            logger.error(f"Template subprocess failed or returned unknown output. Stdout: {out}")
            return _console_fallback(model_filename)
        except Exception as e:
            logger.error(f"Failed to spawn template builder subprocess: {e}")
            return _console_fallback(model_filename)

    try:
        logger.info(f"Opening template builder for: {model_filename}")
        
        reference = _build_reference_payload(model_filename)
        api = TemplateAPI(model_filename, reference, has_auto)
        
        window = webview.create_window(
            title="JARVIS NEXUS · Template Builder",
            html=HTML,
            js_api=api,
            width=800,
            height=700,
            min_size=(650, 500),
            resizable=True,
            background_color="#0d1117"
        )
        
        api.set_window(window)
        webview.start(debug=False)
        
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