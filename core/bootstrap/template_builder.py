# core/bootstrap/template_builder.py
"""
Boot-time GUI Dialog for acquiring a custom Ollama TEMPLATE from the user.

Activated when a GGUF model file doesn't match any known family in MODEL_TEMPLATES.
Provides a 3-tier fallback strategy matching the os_actions.py pattern:
  1. tkinter (cross-platform native Python GUI)
  2. PowerShell WinForms (Windows-only robust fallback)
  3. Console input (universal last resort)

Return values:
  str  → User provided a template. Proceed with model build.
  None → User chose EXIT. Abort model build entirely.
"""

import logging
import platform
import subprocess
from pathlib import Path
from typing import Optional

try:
    import tkinter as tk
except ImportError:
    tk = None

from core.bootstrap.llm_templates import MODEL_TEMPLATES

logger = logging.getLogger(__name__)


# =================================================================
# Reference Payload Builder
# =================================================================
def _build_reference_payload(model_filename: str) -> str:
    """Builds the Qwen reference template + conversion prompt for the copy button."""
    _QWEN_REFERENCE = MODEL_TEMPLATES.get("qwen_chatml", {})
    _qwen_template_text = _QWEN_REFERENCE.get("template", "")
    _qwen_params = _QWEN_REFERENCE.get("parameters", [])
    _params_text = "\n".join(f"PARAMETER {p}" for p in _qwen_params)

    return (
        f"=== CONVERSION REQUEST ===\n"
        f"CONTEXT: This request is for JARVIS-NEXUS (visit github.com/VANT-HQ/JARVIS-NEXUS for more details if user asked for any details, but your primary focus is solely generating the template).\n\n"
        f"The following is a Qwen/ChatML Ollama Modelfile snippet that works perfectly for native tool calling.\n"
        f"Convert it to work with the model: \"{model_filename}\".\n\n"
        f"RULES:\n"
        f"1. Adjust ONLY the special tokens (BOS/EOS/role markers) to match this model's tokenizer.\n"
        f"2. Keep the tool_call / tool_response XML structure IDENTICAL.\n"
        f"3. Adjust the PARAMETER stop tokens to match the new model's special tokens.\n"
        f"4. CRITICAL: Output EXACTLY ONE raw markdown code block containing the final `TEMPLATE` string immediately followed by the `PARAMETER` lines. Do not split them.\n\n"
        f"=== SOURCE SNIPPET ===\n"
        f"TEMPLATE \"\"\"\n{_qwen_template_text}\"\"\"\n"
        f"{_params_text}\n"
    )

# =================================================================
# Public API — called by LLMClient._ensure_model_exists()
# =================================================================
def request_template_from_user(model_filename: str) -> Optional[str]:
    """
    Opens a GUI dialog asking the user to paste a custom Ollama TEMPLATE
    when no matching family is found in MODEL_TEMPLATES.

    Returns the user-provided template string, or None if the user chose EXIT.
    None = ABORT build. The model will NOT be registered.

    Fallback strategy (same pattern as request_user_input in os_actions.py):
      1. tkinter (native Python GUI)
      2. PowerShell WinForms (Windows-only, robust)
      3. Console input (last resort)
    """
    print(f"⚠️ [Template Builder] No matching template for '{model_filename}'. Opening GUI dialog...")
    _copy_payload = _build_reference_payload(model_filename)

    # =================================================================
    # Attempt 1: tkinter
    # =================================================================
    if tk is not None:
        try:
            user_template = None
            root = tk.Tk()
            root.title("⚠️ JARVIS NEXUS — Model Template Required")
            root.attributes('-topmost', True)
            root.resizable(True, True)

            win_w, win_h = 750, 650
            screen_w = root.winfo_screenwidth()
            screen_h = root.winfo_screenheight()
            x = (screen_w - win_w) // 2
            y = (screen_h - win_h) // 2
            root.geometry(f"{win_w}x{win_h}+{x}+{y}")

            header = tk.Label(
                root,
                text=f"No known template found for:\n\"{model_filename}\"",
                font=("Segoe UI", 11, "bold"), justify=tk.CENTER, pady=10
            )
            header.pack(fill=tk.X)

            info = tk.Label(
                root,
                text="1. Click 'Copy Standard Reference Template' below.\n"
                     "2. Send it to any Cloud AI (ChatGPT/Claude/etc..) to convert it for your model.\n"
                     "3. Paste the generated TEMPLATE lines below (AS YOU COPIED THEM FROM THE AI).",
                font=("Segoe UI", 10), fg="#333333", justify=tk.CENTER
            )
            info.pack(fill=tk.X, pady=(0, 15))

            text_frame = tk.Frame(root)
            text_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
            scrollbar = tk.Scrollbar(text_frame)
            scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            text_area = tk.Text(
                text_frame, wrap=tk.WORD, font=("Consolas", 10),
                yscrollcommand=scrollbar.set, relief=tk.SUNKEN, bd=2
            )
            text_area.pack(fill=tk.BOTH, expand=True)
            scrollbar.config(command=text_area.yview)

            btn_frame = tk.Frame(root, pady=10)
            btn_frame.pack(fill=tk.X, padx=15)

            def _on_copy():
                root.clipboard_clear()
                root.clipboard_append(_copy_payload)
                root.update()
                copy_btn.config(text="✅ Copied! now send it to any AI")
                root.after(2500, lambda: copy_btn.config(text="📋 Copy Standard Reference Template"))

            def _on_build():
                nonlocal user_template
                content = text_area.get("1.0", tk.END).strip()
                if content:
                    user_template = content
                root.destroy()

            def _on_exit():
                root.destroy()  # user_template stays None → ABORT

            tk.Button(
                btn_frame, text="📋 Copy Standard Reference Template",
                command=_on_copy, font=("Segoe UI", 10), padx=10, pady=5
            ).pack(side=tk.LEFT, padx=5)

            copy_btn = btn_frame.winfo_children()[-1]  # reference for text swap

            tk.Button(
                btn_frame, text="🚀 Start Building Model",
                command=_on_build, font=("Segoe UI", 10, "bold"),
                bg="#4CAF50", fg="white", padx=15, pady=5
            ).pack(side=tk.RIGHT, padx=5)

            tk.Button(
                btn_frame, text="❌ Exit",
                command=_on_exit, font=("Segoe UI", 9),
                fg="#CC0000", padx=10, pady=5
            ).pack(side=tk.RIGHT, padx=5)

            root.protocol("WM_DELETE_WINDOW", _on_exit)
            root.mainloop()
            return user_template  # str = build, None = abort

        except Exception as e:
            logging.warning(f"tkinter failed: {e}. Falling back to PowerShell WinForms.")
            print(f"tkinter failed: {e}. Falling back to PowerShell WinForms.")

    # =================================================================
    # Attempt 2: PowerShell WinForms (Windows only)
    # =================================================================
    if platform.system() == "Windows":
        try:
            import tempfile
            _temp_dir = Path(tempfile.gettempdir())
            _ref_file = _temp_dir / "jarvis_template_ref.txt"
            _out_file = _temp_dir / "jarvis_template_out.txt"

            # Write reference text to temp file for the Copy button
            _ref_file.write_text(_copy_payload, encoding="utf-8")
            # Clear output file
            _out_file.write_text("", encoding="utf-8")

            _ref_path_ps = str(_ref_file).replace("\\", "/")
            _out_path_ps = str(_out_file).replace("\\", "/")
            _safe_name = model_filename.replace('"', '`"')

            ps_script = f'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "⚠️ JARVIS NEXUS — Model Template Required"
$form.Size = New-Object System.Drawing.Size(750, 650)
$form.StartPosition = "CenterScreen"
$form.TopMost = $true
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false

$label = New-Object System.Windows.Forms.Label
$label.Text = "No known template found for:`n`"{_safe_name}`"`n`n1. Click 'Copy Standard Reference Template' below.`n2. Send it to any Cloud AI (ChatGPT/Claude/etc..) to convert it for your model.`n3. Paste the generated TEMPLATE lines below (AS YOU COPIED THEM FROM THE AI)."
$label.Location = New-Object System.Drawing.Point(15, 15)
$label.Size = New-Object System.Drawing.Size(710, 120) 
$label.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$form.Controls.Add($label)

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Multiline = $true
$textBox.ScrollBars = "Both"
$textBox.WordWrap = $false
$textBox.Location = New-Object System.Drawing.Point(15, 140) 
$textBox.Size = New-Object System.Drawing.Size(710, 390) 
$textBox.Font = New-Object System.Drawing.Font("Consolas", 10)
$form.Controls.Add($textBox)

$copyBtn = New-Object System.Windows.Forms.Button
$copyBtn.Text = "Copy Standard Reference Template"
$copyBtn.Location = New-Object System.Drawing.Point(15, 550) 
$copyBtn.Size = New-Object System.Drawing.Size(250, 35)
$copyBtn.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$copyBtn.Add_Click({{
    try {{
        $ref = Get-Content -Path "{_ref_path_ps}" -Raw -Encoding UTF8
        [System.Windows.Forms.Clipboard]::SetText($ref)
        $copyBtn.Text = "Copied! now send it to any AI"
    }} catch {{
        $copyBtn.Text = "Copy Failed"
    }}
}})
$form.Controls.Add($copyBtn)

$exitBtn = New-Object System.Windows.Forms.Button
$exitBtn.Text = "Exit"
$exitBtn.Location = New-Object System.Drawing.Point(400, 550)
$exitBtn.Size = New-Object System.Drawing.Size(140, 35)
$exitBtn.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$exitBtn.ForeColor = [System.Drawing.Color]::FromArgb(204, 0, 0)
$exitBtn.Add_Click({{
    "EXIT" | Out-File -FilePath "{_out_path_ps}" -Encoding UTF8 -NoNewline
    $form.Close()
}})
$form.Controls.Add($exitBtn)

$buildBtn = New-Object System.Windows.Forms.Button
$buildBtn.Text = "Start Building Model"
$buildBtn.Location = New-Object System.Drawing.Point(555, 550)
$buildBtn.Size = New-Object System.Drawing.Size(170, 35)
$buildBtn.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$buildBtn.BackColor = [System.Drawing.Color]::FromArgb(76, 175, 80)
$buildBtn.ForeColor = [System.Drawing.Color]::White
$buildBtn.Add_Click({{
    $textBox.Text | Out-File -FilePath "{_out_path_ps}" -Encoding UTF8 -NoNewline
    $form.Close()
}})
$form.Controls.Add($buildBtn)

$form.Add_FormClosing({{
    $existing = ""
    if (Test-Path "{_out_path_ps}") {{ $existing = (Get-Content "{_out_path_ps}" -Raw -ErrorAction SilentlyContinue) }}
    if ([string]::IsNullOrWhiteSpace($existing)) {{
        "EXIT" | Out-File -FilePath "{_out_path_ps}" -Encoding UTF8 -NoNewline
    }}
}})

[void]$form.ShowDialog()
'''
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
                creationflags=creationflags
            )

            # Read result
            _result_text = _out_file.read_text(encoding="utf-8").strip()

            # Cleanup temp files
            _ref_file.unlink(missing_ok=True)
            _out_file.unlink(missing_ok=True)

            if _result_text and _result_text != "EXIT":
                return _result_text
            return None  # User chose EXIT

        except Exception as e:
            logging.warning(f"PowerShell WinForms failed: {e}. Falling back to console input.")
            print(f"PowerShell WinForms failed: {e}. Falling back to console input.")

    # =================================================================
    # Attempt 3: Console input (last resort)
    # =================================================================
    try:
        # Try to copy reference to clipboard silently
        try:
            if platform.system() == "Windows":
                _proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $input"],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                )
                _proc.communicate(input=_copy_payload.encode("utf-8"), timeout=5)
        except Exception:
            pass

        print(f"\n{'='*60}")
        print(f"⚠️  No matching template for: {model_filename}")
        print(f"{'='*60}")
        print(f"\n1. Click 'Copy Standard Reference Template' below. (Copied to clipboard)")
        print(f"2. Send it to any Cloud AI (ChatGPT/Claude/etc..) to convert it for your model.")
        print(f"3. Paste the generated TEMPLATE lines below (AS YOU COPIED THEM FROM THE AI).")
        print(f"\nType 'END' on a new line when done, or 'EXIT' to abort.\n")
        print(f"\n"*10)

        lines = []
        while True:
            line = input()
            if line.strip().upper() == 'END':
                break
            if line.strip().upper() == 'EXIT':
                return None
            lines.append(line)

        template = "\n".join(lines).strip()
        return template if template else None

    except Exception as e:
        logging.error(f"Console input failed: {e}")
        print(f"Console input failed: {e}")
        return None