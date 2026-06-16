# core/tools/os_actions.py  #? (Hmody: why just win and linux? why i didnt add mac?  well im racist to mac :p) 

"""
JARVIS OS Interactions & File Management
========================================
Provides secure, isolated system utilities for file operations, 
shell commands, application launching, and hardware interactions.
"""

import os
import sys
import webbrowser
import subprocess  
import glob  
import time  
import random  
import logging  
import datetime  
import shutil 
import json
import urllib.parse
import re
from pathlib import Path
from datetime import datetime
try:
    import tkinter as tk
    from tkinter import simpledialog
except ImportError:
    tk = None
    simpledialog = None

# =====================================================================
# Unified System Configurations
# =====================================================================

try: 
    from core.config import config, BASE_DIR
except ImportError as e:
    logging.error(f"❌ Could not import centralized config. {e}")
    sys.exit(1)

# =====================================================================
# Platform Specific Imports
# =====================================================================
try:
    import requests  
except ImportError:
    logging.warning("requests missing. Open site disabled.")
    requests = None

try:
    import psutil  
except ImportError:
    logging.warning("psutil missing. Process management disabled.")
    psutil = None

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from ctypes import cast, POINTER
    from comtypes import CLSCTX_ALL
except ImportError:
    logging.warning("pycaw missing. System volume control disabled for Windows.")
    AudioUtilities = None

try:
    import screen_brightness_control as sbc
except ImportError:
    logging.warning("screen-brightness-control missing. Brightness disabled.")
    sbc = None

try:
    import pyautogui  
except ImportError:
    logging.warning("pyautogui missing. Window control disabled.")
    pyautogui = None

try:
    from thefuzz import fuzz, process  
except ImportError:
    logging.warning("thefuzz missing. Run Item matching will be basic.")
    fuzz = None

# =====================================================================
# Security Layer for File Operations
# =====================================================================
ALLOWED_EXTENSIONS = {
    # Text and web files
    '.txt', '.md', '.json', '.html', '.css', '.csv', '.log', '.xml',
    # Configuration files
    '.ini', '.env', '.yml', '.yaml', '.toml',
    # Scripts
    '.sh', '.bat', '.ps1',
    # Programming languages
    '.py', '.js', '.ts', '.c', '.cpp', '.h', '.hpp', '.cs', 
    '.java', '.rb', '.php', '.go', '.rs', '.swift', '.sql'
}

MAX_READ_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_WRITE_SIZE = 5 * 1024 * 1024  # 5 MB

def _is_binary_file(filepath):
    """
    Checks if a file is binary by reading the first 8KB and searching for NUL bytes (\x00).
    """
    try:
        with open(filepath, 'rb') as f:
            chunk = f.read(8192)
            if b'\x00' in chunk:
                return True
    except Exception:
        pass
    return False


def _validate_file_access(file_path, override_permission=False):
    """
    Workspace Boundaries Security System:
    - Free Zone (share_dir): Full permissions without prompts.
    - Desktop (desktop_dir): Allowed only if override_permission=True is internally provided.
    """
    path = Path(file_path).resolve()
    
    if path.suffix and path.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False, f"Security Block: The extension '{path.suffix}' is not supported. Only text/code files are allowed to prevent binary corruption."
    
    share_dir_path = config.get("share_dir")
    desktop_dir_path = config.get("desktop_dir")
    
    if not share_dir_path or not desktop_dir_path:
        return False, "Error: 'share_dir' or 'desktop_dir' is not configured in system settings."
        
    share_dir = Path(share_dir_path).resolve()
    desktop_dir = Path(desktop_dir_path).resolve()
    
    try:
        if path.is_relative_to(share_dir):
            return True, ""
    except AttributeError:
        if str(share_dir) in str(path):
            return True, ""

    try:
        if path.is_relative_to(desktop_dir):
            if override_permission:
                return True, ""
            else:
                return False, "Security Block: This path is restricted. Ask the user for permission. If granted, use 'grant_temporary_permission' for this tool."
    except AttributeError:
        if str(desktop_dir) in str(path):
             if override_permission:
                 return True, ""
             else:
                 return False, "Security Block: This path is restricted. Ask the user for permission. If granted, use 'grant_temporary_permission' for this tool."

    return False, f"Security Block: Path '{file_path}' escapes allowed workspaces. You can only access '{share_dir}' or '{desktop_dir}'."


def _validate_critical_action(override_permission=False, action_name="System Action"):
    """ 
    Verifies that the model has explicit permission to execute critical system commands.
    """
    if not override_permission:
        return False, f"Security Block: '{action_name}' is protected. Ask the user for permission. If granted, use 'grant_temporary_permission' for the current tool."
    return True, ""

# =====================================================================
# Command Functions
# =====================================================================

def open_website(params):
    """ Opens any requested website by name or URL with ultra-fast validation. """
    site = params.get("site_name")
    os_type = params.get("os_type", "").lower()
    
    if not site:
        return False, "Error: What website should I open, sir?", None
    
    logging.info(f"Executing: Open Website '{site}' on OS: {os_type}")
    try:
        if not site.startswith("http"):
            if "." not in site:
                site = f"https://www.{site.lower().replace(' ', '')}.com"
            else:
                site = f"https://{site}"
                
        # Ultra-fast validation using HEAD request
        if requests:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                check = requests.head(site, headers=headers, timeout=2)
                
                if check.status_code >= 400 and check.status_code not in [401, 403, 405]: 
                    check = requests.get(site, headers=headers, timeout=2, stream=True)
                    if check.status_code >= 400 and check.status_code not in [401, 403, 405]:
                        return False, f"Error: '{site}' is unreachable (Status {check.status_code}). Tell the user it failed and immediately use the 'search_web' tool to find the correct link.", None
            except requests.exceptions.RequestException:
                return False, f"Error: Could not reach '{site}'. Tell the user it failed and use the 'search_web' tool to search for it.", None

        webbrowser.open(site)
        return True, f"Successfully opened {site}.", None
        
    except Exception as e:
        logging.error(f"Error opening website: {e}")
        print(f"Error opening website: {e}")
        return False, f"Error: Failed to open the website: {e}", None


def google_search(params):
    """ Dedicated Google Search for images and visual results using tbm=isch. """
    query = params.get("query")
    if not query:
        return False, "What should I search for, sir?", None
    logging.info(f"Executing: Google Image Search for '{query}'")
    try:
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(query)
        webbrowser.open(f"https://www.google.com/search?q={encoded_query}&tbm=isch")
        return True, f"Showing visual results for {query}.", None
    except Exception as e:
        logging.error(f"Error Google search: {e}")
        print(f"Error Google search: {e}")
        return False, "Error searching Google.", None
    

def youtube_action(params):
    """
    Smart YouTube tool: Executes either direct playback (play) or search and display results (search).
    """
    query = params.get("query")
    action = params.get("action", "play").lower()
    os_type = params.get("os_type", "").lower()
    
    if not query:
        logging.info(f"Executing: Open YouTube Homepage on OS: {os_type}")
        webbrowser.open("https://www.youtube.com")
        return True, "Success: Opened YouTube homepage. Tell the user you opened it.", None

    logging.info(f"Executing: YouTube {action} for '{query}' on OS: {os_type}")
    try:
        encoded_query = urllib.parse.quote_plus(query)
        
        if action == "play":
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            if requests:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    r = requests.get(url, headers=headers, timeout=3)
                    video_ids = re.findall(r'"videoId":"([^"]{11})"', r.text)
                    if video_ids:
                        url = f"https://www.youtube.com/watch?v={video_ids[0]}&autoplay=1"
                        msg = f"Success: Playing '{query}' directly on YouTube. Stay completely silent."
                    else:
                        msg = f"Success: Opened YouTube search for '{query}'. Stay completely silent."
                except Exception:
                    msg = f"Success: Opened YouTube search for '{query}'. Stay completely silent."
            else:
                msg = f"Success: Opened YouTube for '{query}'. Stay completely silent."
        else:
            url = f"https://www.youtube.com/results?search_query={encoded_query}"
            msg = f"Success: Opened YouTube search results for '{query}'. Stay completely silent."
            
        webbrowser.open(url)
        return True, msg, None
        
    except Exception as e:
        logging.error(f"Error executing YouTube action: {e}")
        print(f"Error executing YouTube action: {e}")
        return False, f"Error: Failed to execute YouTube action. Details: {str(e)}", None


def set_volume(params):
    """ Controls system volume (Windows/Linux) or JARVIS's internal volume. """
    target = params.get("target", "system")
    level = params.get("level")
    change = params.get("change")
    os_type = params.get("os_type", "").lower()
    
    if level is None and change is None:
        change = 10

    # 1. Control JARVIS internal volume
    if target == "jarvis":
        current_vol = config.get("volume", 50)
        if level is not None:
            new_vol = int(level)
        else:
            new_vol = current_vol + int(change)
            
        new_vol = max(0, min(100, new_vol))
        config.set("volume", new_vol)
        return True, f"My internal volume is now set to {new_vol}%.", None

    # 2. Control System volume
    try:
        if os_type == "windows":
            if not AudioUtilities:
                return False, "System audio controls unavailable on Windows.", None
            
            # Initialize COM for Windows to avoid Thread errors
            import comtypes
            comtypes.CoInitialize()
            
            device = AudioUtilities.GetSpeakers()
            
            # Compatibility with both new and old versions of pycaw
            if hasattr(device, 'Activate'):
                # Old version path
                interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                volume = cast(interface, POINTER(IAudioEndpointVolume))
            else:
                # New version path (2024+)
                volume = device.EndpointVolume.QueryInterface(IAudioEndpointVolume)
                
            if level is not None:
                new_vol_scalar = max(0.0, min(1.0, float(level) / 100.0))
                volume.SetMasterVolumeLevelScalar(new_vol_scalar, None)
                return True, f"System volume set to {level}%.", None
                
            if change is not None:
                current_scalar = volume.GetMasterVolumeLevelScalar()
                new_vol_scalar = max(0.0, min(1.0, current_scalar + (float(change) / 100.0)))
                volume.SetMasterVolumeLevelScalar(new_vol_scalar, None)
                return True, f"System volume adjusted by {change}%.", None

        else:
            # Linux Audio Control via amixer
            if level is not None:
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{level}%"], stdout=subprocess.DEVNULL)
                return True, f"System volume set to {level}%.", None
            if change is not None:
                sign = "+" if int(change) > 0 else "-"
                subprocess.run(["amixer", "-D", "pulse", "sset", "Master", f"{abs(int(change))}%{sign}"], stdout=subprocess.DEVNULL)
                return True, f"System volume adjusted by {change}%.", None

    except Exception as e:
        logging.error(f"Volume error: {e}")
        print(f"Volume error: {e}")
        return False, "Failed to adjust system volume.", None


def system_status(params):
    if not psutil: return False, "Error: System monitoring tools (psutil) are missing.", None
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory().percent
    bat = psutil.sensors_battery()
    msg = f"CPU is at {cpu}%. Memory is at {mem}%."
    if bat:
        msg += f" Battery is {bat.percent}%."
    return True, msg, None


def set_brightness(params):
    """ 
    Controls screen brightness across operating systems (Windows/Linux).
    Supports absolute values or relative increments/decrements.
    """
    level = params.get("level")
    change = params.get("change")
    
    if not sbc:
        return False, "Brightness control module (screen-brightness-control) is missing.", None
        
    try:
        if level is not None:
            # Set brightness to an absolute value
            target_level = max(0, min(100, int(level)))
            sbc.set_brightness(target_level)
            return True, f"Screen brightness set to {target_level}%.", None
            
        elif change is not None:
            # Read current brightness of primary display and adjust relatively
            current_levels = sbc.get_brightness()
            if not current_levels:
                return False, "Could not read current brightness.", None
                
            current_level = current_levels[0]
            new_level = max(0, min(100, current_level + int(change)))
            sbc.set_brightness(new_level)
            return True, f"Screen brightness adjusted by {change}%. Now at {new_level}%.", None
            
        else:
            return False, "No brightness level or change value provided.", None
            
    except Exception as e:
        logging.error(f"Brightness error: {e}")
        print(f"Brightness error: {e}")
        return False, f"Failed to adjust screen brightness: {e}", None


def take_screenshot(params):
    save_dir = config.get("desktop_dir") or str(Path.home() / "Desktop")
    ast_name = config.get("assistant_name", "System")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ast_name}_Screenshot_{timestamp}.png"
    filepath = os.path.join(save_dir, filename)
    os_type = params.get("os_type", "").lower()
    
    os.makedirs(save_dir, exist_ok=True)
    
    try:
        if pyautogui:
            pyautogui.screenshot().save(filepath)
            spoken_name = f"{ast_name} Screenshot"
            return True, "Screenshot saved to desktop.", spoken_name
    except Exception as e:
        # Fallback for Linux native tools (e.g., Wayland environments)
        if os_type == "linux":
            try:
                subprocess.run(["gnome-screenshot", "-f", filepath], check=True)
                spoken_name = f"{ast_name} Screenshot"
                return True, "Screenshot saved to desktop using native Linux tools.", spoken_name
            except Exception as linux_e:
                return False, f"Failed to capture screenshot natively: {linux_e}", None
                
        return False, f"Failed to capture screenshot: {e}", None


def close_window(params):
    """Simulates ALT+F4 to close the currently active foreground window."""
    os_type = params.get("os_type", "").lower()
    try:
        if os_type == "windows":
            if not pyautogui:
                return False, "Error: pyautogui is required for window control.", None
            time.sleep(0.3)  # Brief yield to ensure the target window has focus
            pyautogui.hotkey('alt', 'F4')
            return True, "Successfully closed the active window.", None
        else:
            # Linux: xdotool fallback
            subprocess.run(["xdotool", "key", "alt+F4"], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True, "Successfully closed the active window.", None
    except Exception as e:
        logging.error(f"Close window error: {e}")
        print(f"Close window error: {e}")
        return False, f"Failed to close the active window: {e}", None


def request_user_input(params):
    """ 
    Opens a GUI text input dialog for the user. 
    Highly useful when the LLM requires precise text that cannot be captured via voice (e.g., links, passwords).
    """
    title = params.get("title", "Input Required")
    prompt_text = params.get("prompt_text", "Jarvis requires your input:")
    
    try:
        # Create a hidden root window for the Dialog
        root = tk.Tk()
        root.withdraw() 
        # Force the window to appear above all others
        root.attributes('-topmost', True)
        
        # Open the input dialog and halt execution until user submits
        user_input = simpledialog.askstring(title, prompt_text, parent=root)
        
        # Destroy the window after completion
        root.destroy()
        
        if user_input is not None:
            return True, f"User manually inputted: {user_input}", user_input
        else:
            return False, "Error: User canceled the input dialog.", None
            
    except Exception as e:
        logging.warning(f"tkinter failed: {e}. Falling back to OS native input.")
        os_type = params.get("os_type", "").lower()
        if not os_type: 
            import platform
            os_type = platform.system().lower()
            
        if os_type == "windows":
            try:
                # Fallback for Windows using PowerShell
                safe_prompt = prompt_text.replace("'", "''")
                safe_title = title.replace("'", "''")
                ps_cmd = f"Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.Interaction]::InputBox('{safe_prompt}', '{safe_title}')"
                
                # Use CREATE_NO_WINDOW to prevent black console flashing
                import subprocess
                creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                
                result = subprocess.run(
                    ["powershell", "-Command", ps_cmd], 
                    capture_output=True, text=True, 
                    creationflags=creationflags
                )
                
                user_input = result.stdout.strip()
                if user_input:
                    return True, f"User manually inputted: {user_input}", user_input
                else:
                    return False, "Error: User canceled or entered empty input.", None
            except Exception as ps_e:
                logging.error(f"PowerShell fallback failed: {ps_e}")
                print(f"PowerShell fallback failed: {ps_e}")
                return False, f"Failed to open input dialog (Both Tkinter and PS failed): {e}", None
                
        elif os_type == "linux":
            try:
                # Fallback for Linux using zenity
                import subprocess
                result = subprocess.run(
                    ["zenity", "--entry", f"--title={title}", f"--text={prompt_text}"], 
                    capture_output=True, text=True
                )
                
                if result.returncode == 0:
                    user_input = result.stdout.strip()
                    return True, f"User manually inputted: {user_input}", user_input
                else:
                    return False, "Error: User canceled the input dialog.", None
            except Exception as linux_e:
                logging.error(f"Zenity fallback failed: {linux_e}")
                print(f"Zenity fallback failed: {linux_e}")
                return False, f"Failed to open input dialog (Both Tkinter and Zenity failed): {e}", None
                
        else:
            logging.error(f"GUI Input error: {e}")
            print(f"GUI Input error: {e}")
            return False, f"Failed to open input dialog: {e}", None


def list_directory(params):
    """ Lists the contents of a specific directory (ls) while respecting security boundaries. """
    dir_path = params.get("dir_path")
    override = params.get("override_permission", False)

    if not dir_path:
        # Default to the share directory if no path is specified
        dir_path = config.get("share_dir")
    else:
        # Route random path aliases to their actual system paths
        _path_lower = dir_path.strip().lower().replace("\\", "").replace("/", "")
        if _path_lower in ("desktop", "mydesktop", "userdesktop"):
            dir_path = config.get("desktop_dir")
        elif _path_lower in ("shared", "shared_area", "jarvissharedarea", "share", "workspace", "area"):
            dir_path = config.get("share_dir")

    # Security check: Only allow Desktop and Share directories
    is_safe, error_msg = _validate_file_access(dir_path, override)
    if not is_safe:
        return False, error_msg, None

    try:
        path = Path(dir_path).resolve()
        if not path.is_dir():
            return False, f"Error: '{path.name}' is not a valid directory.", None

        # Fetch files and directories
        items = os.listdir(path)
        if not items:
            return True, f"Directory '{path.name}' is empty.", "EMPTY"

        # Format output for LLM comprehension
        files = [f for f in items if (path / f).is_file()]
        folders = [d for d in items if (path / d).is_dir()]
        
        result_data = f"Folders: {folders}\nFiles: {files}"
        return True, f"Successfully listed {len(items)} items in {path.name}.", result_data

    except Exception as e:
        logging.error(f"Error listing directory {dir_path}: {e}")
        print(f"Error listing directory {dir_path}: {e}")
        return False, f"Failed to list directory: {e}", None


def _resolve_file_path(file_path: str) -> str:
    """
    Resolves relative paths or shortened aliases to absolute real paths.
    - desktop/foo.txt → config["desktop_dir"]/foo.txt
    - foo.txt (relative) → config["share_dir"]/foo.txt
    - shared_area/foo.txt → config["share_dir"]/foo.txt (strips redundant prefix)
    """
    if not file_path:
        return ""
        
    path = Path(file_path)
    if path.is_absolute():
        return file_path

    parts = path.parts

    # Strip "shared_area" prefix if the model echoed back the workspace label. 
    # "shared_area" IS the share_dir root — it's not a subfolder inside it.
    _SHARE_ALIASES = ("shared_area", "sharedarea", "workspace", "shared", "jarvissharedarea", "area")
    
    if parts and parts[0].lower() in _SHARE_ALIASES:
        # Remove the alias prefix and treat the rest as relative to share_dir
        parts = parts[1:]
        if not parts:
            return str(config.get("share_dir"))
        return str(Path(config.get("share_dir")) / Path(*parts))

    if parts and parts[0].lower() in ("desktop", "mydesktop", "userdesktop"):
        desktop = Path(config.get("desktop_dir"))
        resolved = desktop / Path(*parts[1:]) if len(parts) > 1 else desktop
        return str(resolved)

    base_share_dir = Path(config.get("share_dir"))
    standard_resolved = base_share_dir / path

    # Smart Fallback - Self Healing: 
    # If the composed path does not exist, and the model potentially repeated a descriptive name, 
    # strip the first directory and re-check from root.
    if not standard_resolved.exists() and len(parts) > 1:
        fallback_resolved = base_share_dir / Path(*parts[1:])
        if fallback_resolved.exists():
            return str(fallback_resolved)

    return str(standard_resolved)


def read_file(params):
    """ Reads the content of a text file enforcing size limits and file type checks. """
    file_path = params.get("file_path")
    
    file_path = _resolve_file_path(file_path)
    
    offset = params.get("offset", 0)
    limit = params.get("limit")

    if not file_path:
        return False, "Error: 'file_path' is required to read a file.", None

    override = params.get("override_permission", False)
    is_safe, error_msg = _validate_file_access(file_path, override)
    if not is_safe:
        return False, error_msg, None
        
    path = Path(file_path).resolve()
    if not path.is_file():
        return False, f"Error: File not found at {path}", None

    # --- Rust-inspired boundary checks ---
    try:
        file_size = path.stat().st_size
        if file_size > MAX_READ_SIZE:
            return False, f"Error: File is too large ({file_size} bytes). Max allowed is {MAX_READ_SIZE} bytes.", None
    except Exception as e:
        return False, f"Error checking file size: {e}", None

    if _is_binary_file(path):
        return False, "Error: File appears to be binary and cannot be read as text.", None

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        start = max(0, int(offset))
        end = start + int(limit) if limit else len(lines)
        
        selected_lines = lines[start:end]
        content = "".join(selected_lines)
        
        return True, f"Successfully read {len(selected_lines)} lines from {path.name}.", content
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")
        print(f"Error reading file {file_path}: {e}")
        return False, f"Failed to read file: {e}", None
    

def write_file(params):
    """ Creates a new file or overwrites an existing one, enforcing size and security boundaries. """
    file_path = params.get("file_path")
    content = params.get("content", "")
    override = params.get("override_permission", False)

    if not file_path:
        return False, "Error: 'file_path' is required to write a file.", None

    file_path = _resolve_file_path(file_path)
    temp_path = Path(file_path)
        
    # Ensure a default text extension if the model omits one
    if not temp_path.suffix:
        temp_path = temp_path.with_suffix('.txt')
    file_path = str(temp_path)

    # --- Size boundary check ---
    if len(content.encode('utf-8')) > MAX_WRITE_SIZE:
        return False, f"Error: Content to write is too large. Max allowed is {MAX_WRITE_SIZE} bytes.", None

    # --- Workspace security check ---
    is_safe, error_msg = _validate_file_access(file_path, override)
    if not is_safe:
        return False, error_msg, None

    path = Path(file_path).resolve()
    
    # Prevent overwriting existing files to avoid data loss, forcing the model to use the 'edit_file' tool.
    if path.exists():
        return False, f"Error: The file '{path.name}' already exists. To prevent accidental data loss, please use the 'edit_file' tool to modify existing files, or choose a new file name.", None

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        return True, f"Successfully wrote to {path.name}.", str(path)
    except Exception as e:
        logging.error(f"Error writing to file {file_path}: {e}")
        print(f"Error writing to file {file_path}: {e}")
        return False, f"Failed to write file: {e}", None
    

def edit_file(params):
    """
    Replaces specific text within a file securely, providing high resilience against model errors.
    Supports Exact Match and Smart Match to ignore whitespace inconsistencies.
    """
    file_path = params.get("file_path")
    
    file_path = _resolve_file_path(file_path)
    
    old_string = params.get("old_string")
    new_string = params.get("new_string")
    replace_all = params.get("replace_all", False)
    override = params.get("override_permission", False)

    if not all([file_path, old_string is not None, new_string is not None]):
        return False, "Error: 'file_path', 'old_string', and 'new_string' are required.", None

    is_safe, error_msg = _validate_file_access(file_path, override)
    if not is_safe:
        return False, error_msg, None

    path = Path(file_path).resolve()
    if not path.is_file():
        return False, f"Error: File not found at {path}", None

    # Prevent editing binary files
    if _is_binary_file(path):
        return False, "Error: File appears to be binary and cannot be edited as text.", None

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # 1. First Attempt: Exact literal match
        if old_string in content:
            if replace_all:
                new_content = content.replace(old_string, new_string)
            else:
                new_content = content.replace(old_string, new_string, 1)
        else:
            # 2. Second Attempt: Smart regex match (ignores whitespace/newline mismatches)
            escaped_words = [re.escape(word) for word in old_string.split()]
            
            if not escaped_words:
                return False, "Error: 'old_string' is empty or only contains whitespaces.", None
                
            # Build a pattern that accepts any whitespace (\s+) between words
            smart_pattern = r'\s+'.join(escaped_words)
            
            # Search for the pattern in the file
            matches = re.findall(smart_pattern, content)
            
            if not matches:
                return False, f"Error: The exact 'old_string' was not found in {path.name}. Tip: Ensure you provide the exact words, or use 'read_file' first to check the code.", None
            
            # Additional protection: If multiple matches exist and replace_all is False
            if len(matches) > 1 and not replace_all:
                return False, f"Error: Found {len(matches)} occurrences of 'old_string'. Please provide a larger block of code in 'old_string' to uniquely identify the part you want to replace.", None
            
            # Execute smart replacement
            count = 0 if replace_all else 1
            new_content = re.sub(smart_pattern, lambda m: new_string, content, count=count)

        # Verify new content size
        if len(new_content.encode('utf-8')) > MAX_WRITE_SIZE:
             return False, "Error: The resulting file would be too large.", None

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return True, f"Successfully edited {path.name}.", str(path)
        
    except Exception as e:
        logging.error(f"Error editing file {file_path}: {e}")
        print(f"Error editing file {file_path}: {e}")
        return False, f"Failed to edit file: {e}", None


def manage_workspace(params):
    """
    Unified tool for file system management (create, move, soft delete).
    Merged to reduce token usage and simplify LLM decision making.
    """
    action = params.get("action")
    target_path = params.get("target_path")
    dest_path = params.get("destination_path")
    override = params.get("override_permission", False)

    if not action or not target_path:
        return False, "Error: 'action' and 'target_path' are strictly required.", None

    # Normalize base path
    target_path = _resolve_file_path(target_path)
    is_safe, error_msg = _validate_file_access(target_path, override)
    
    if not is_safe:
        return False, f"Security Block: {error_msg}", None

    target = Path(target_path).resolve()

    try:
        # 1. Create Directory
        if action == "mkdir":
            if target.exists():
                return False, f"Error: Directory '{target.name}' already exists.", None
            target.mkdir(parents=True, exist_ok=True)
            return True, f"Successfully created directory '{target.name}'.", str(target)

        # 2. Soft Delete (Move to trash)
        elif action == "delete":
            if not target.exists():
                return False, f"Error: '{target.name}' does not exist.", None
                
            share_dir = Path(config.get("share_dir")).resolve()
            trash_dir = share_dir / ".nexus_trash"
            trash_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            trashed_name = f"{target.stem}_deleted_{timestamp}{target.suffix}"
            trash_path = trash_dir / trashed_name
            
            shutil.move(str(target), str(trash_path))
            return True, f"Successfully moved '{target.name}' to trash.", str(trash_path)

        # 3. Move / Rename
        elif action == "move":
            if not target.exists():
                return False, f"Error: Source '{target.name}' does not exist.", None
            if not dest_path:
                return False, "Error: 'destination_path' is required for the 'move' action.", None
                
            dest_path = _resolve_file_path(dest_path)
            is_safe_dest, err_dest = _validate_file_access(dest_path, override)
            
            if not is_safe_dest:
                return False, f"Destination Security Block: {err_dest}", None
                
            destination = Path(dest_path).resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(destination))
            return True, f"Successfully moved to '{destination.parent.name}'.", str(destination)

        else:
            return False, f"Error: Invalid action '{action}'.", None

    except Exception as e:
        logging.error(f"Workspace management error ({action}): {e}")
        print(f"Workspace management error ({action}): {e}")
        return False, f"Failed to execute {action}: {e}", None


def _get_all_scenarios(): 
    """
    Scans the scripts directory (run_dir) and extracts their names without extensions.
    Converts names like 'party_is_over.ps1' to 'party is over' to facilitate Fuzzy Matching.
    """
    run_dir_path = config.get("run_dir")
    
    # Default path if not specified in config
    if not run_dir_path:
        run_dir_path = str(BASE_DIR / "scenarios")
        
    run_dir = Path(run_dir_path).resolve()
    
    if not run_dir.exists():
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logging.error(f"Failed to create scenarios directory: {e}")
            print(f"Failed to create scenarios directory: {e}")
            return {}

    scenarios = {}
    
    # Restrict supported extensions to unify the environment and prevent fragmentation
    valid_extensions = {'.ps1', '.sh'}
    
    for file_path in run_dir.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in valid_extensions:
            # Clean the name to match natural user speech (remove dashes/underscores)
            clean_name = file_path.stem.replace("_", " ").replace("-", " ").lower()
            scenarios[clean_name] = str(file_path)
            
    return scenarios


def run_scenario(params):   #? (Hmody: created with one goal, breaking limits)
    """
    Automation scenarios execution tool. Relies on smart Fuzzy Matching.
    On failure, it provides the LLM with a list of available scenarios to self-correct.
    """
    scenario_name = params.get("scenario_name", "").strip()
    os_type = params.get("os_type", "").lower()
    
    if not scenario_name:
        return False, "Error: Scenario name missing.", None
        
    logging.info(f"Executing: Run Scenario '{scenario_name}' on {os_type}")
    
    try:
        scenarios_cache = _get_all_scenarios()
        
        if not scenarios_cache:
            return False, "Error: No automation scripts found in the run directory. Tell the user they haven't created any scenarios yet.", None
            
        # Apply Fuzzy Matching
        if fuzz and process:
            best_match, score = process.extractOne(scenario_name.lower(), scenarios_cache.keys(), scorer=fuzz.token_sort_ratio)
            
            # Accept script if match score is >= 65%
            if score >= 65:
                script_path = scenarios_cache[best_match]
                ext = Path(script_path).suffix.lower()
                
                logging.info(f"Fuzzy matched scenario '{scenario_name}' to '{best_match}' (Ext: {ext}) with score {score}")
                
                # Enforce strict execution for .ps1 and .sh in the background
                if ext == '.ps1':
                    # Use WindowStyle Hidden to prevent PowerShell console flashing
                    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script_path]
                elif ext == '.sh':
                    # Standard secure execution in Linux environment
                    cmd = ["bash", script_path]
                else:
                    # Extra security layer for invalid file types
                    return False, f"Error: Unsupported script type '{ext}'. Please use strictly .ps1 for Windows or .sh for Linux.", None
                
                # Execute script in the background
                if os_type == "windows":
                    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=creationflags)
                else:
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    
                return True, f"Successfully executed scenario: {best_match}.", None

        # ==========================================
        # Smart feedback on scenario lookup failure
        # ==========================================
        available_scenarios = ", ".join(list(scenarios_cache.keys()))
        smart_error_msg = (
            f"Error: Could not find exactly '{scenario_name}'. "
            f"However, the system found these available scenarios: [{available_scenarios}]. "
            "INSTRUCTION: If one of the available scenarios matches the user's intent, run it. Otherwise, tell the user the scenario wasn't found."
        )
        return False, smart_error_msg, None
        
    except Exception as e:
        logging.error(f"Error running scenario: {e}")
        print(f"Error running scenario: {e}")
        return False, f"Failed to run scenario '{scenario_name}': {e}", None


def _get_all_applications(os_type="windows"):
    """
    Builds or retrieves a JSON cache of installed applications for Fuzzy Matching.
    The cache is stored in CACHE_DIR and sorted alphabetically.
    """
    try:
        from core.config import CACHE_DIR
    except ImportError:
        return {}
        
    cache_file = CACHE_DIR / "apps_cache.json"
    current_time = time.time()
    cache_valid_time = 24 * 3600  # Update cache every 24 hours
    
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)
            if current_time - cache_data.get("last_modified", 0) < cache_valid_time:
                return cache_data.get("apps", {})
        except Exception as e:
            logging.warning(f"App cache read error: {e}. Rebuilding...")

    logging.info("Scanning applications... (Cache miss or expired)")
    apps = {}
    
    if os_type == "windows":
        paths = [
            os.path.expandvars(r'%ProgramData%\Microsoft\Windows\Start Menu\Programs'),
            os.path.expandvars(r'%APPDATA%\Microsoft\Windows\Start Menu\Programs')
        ]
        for p in paths:
            if os.path.exists(p):
                for f in glob.glob(os.path.join(p, '**', '*.lnk'), recursive=True):
                    app_name = os.path.splitext(os.path.basename(f))[0]
                    apps[app_name] = f
    else:
        paths = ["/usr/share/applications", os.path.expanduser("~/.local/share/applications")]
        for p in paths:
            if os.path.exists(p):
                for f in glob.glob(os.path.join(p, '**', '*.desktop'), recursive=True):
                    app_name = os.path.splitext(os.path.basename(f))[0]
                    apps[app_name] = f
                    
    # Alphabetical sorting for faster lookup and clean file structure
    sorted_apps = {k: apps[k] for k in sorted(apps.keys())}
    
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "last_modified": current_time,
                "apps": sorted_apps
            }, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Failed to write app cache: {e}")
        print(f"Failed to write app cache: {e}")
        
    return sorted_apps


def open_application(params):
    app_name = params.get("app_name", "").strip()
    os_type = params.get("os_type", "").lower()
    if not app_name: 
        return False, "Error: Application name missing.", None
    
    logging.info(f"Executing: Open Application '{app_name}' on {os_type}")
    
    try:
        apps_cache = _get_all_applications(os_type) or {}

        # 1. First Attempt: Smart matching with applications cache
        for app_name_key in apps_cache.keys():
            if app_name.lower() == app_name_key.lower() or app_name.lower() == app_name_key.lower().replace('.lnk', ''):
                app_path = apps_cache[app_name_key]
                if os_type == "windows" and hasattr(os, 'startfile'):
                    try:
                        os.startfile(app_path)
                        return True, f"Successfully opened {app_name_key}.", None
                    except Exception as e:
                        logging.error(f"Failed to open via shortcut: {e}")
                        print(f"Failed to open via shortcut: {e}")
                break 
        
        if fuzz and process and apps_cache:
            best_match, score = process.extractOne(app_name, apps_cache.keys(), scorer=fuzz.token_sort_ratio)
            if score >= 75:
                logging.info(f"Fuzzy matched '{app_name}' to '{best_match}' with score {score}")
                app_path = apps_cache[best_match]
                if os_type == "windows":
                    if hasattr(os, 'startfile'):
                        try:
                            os.startfile(app_path)
                            return True, f"Successfully opened {best_match}.", None
                        except Exception as e:
                            logging.error(f"Failed to open via shortcut: {e}")
                            print(f"Failed to open via shortcut: {e}")
                else:
                    subprocess.Popen(["gtk-launch", best_match], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return True, f"Successfully opened {best_match}.", None

        # 2. Second Attempt: Traditional direct execution
        app_started = False
        if os_type == "windows":
            # Sanitize application name from potential Command Injection symbols
            clean_name = re.sub(r'[&|;<>^]', '', app_name).replace(".exe", "").strip()
            if hasattr(os, 'startfile'):
                try:
                    os.startfile(clean_name)
                    app_started = True
                    return True, f"Successfully opened {clean_name}.", None
                except FileNotFoundError:
                    pass
        else:
            # Linux execution logic
            clean_name = re.sub(r'[&|;<>`]', '', app_name).strip()
            if shutil.which(clean_name):
                subprocess.Popen([clean_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                app_started = True
                return True, f"Successfully opened {clean_name}.", None

        # 3. Third Attempt: App not found, attempt to reach it as a website
        if not app_started and requests:
            site = f"https://www.{app_name.lower().replace(' ', '')}.com"
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                check = requests.head(site, headers=headers, timeout=2.0)
                if check.status_code < 400 or check.status_code in [401, 403, 405]:
                    return False, f"Error: Application '{app_name}' is not installed. However, a website exists at {site}. Ask the user if they meant to open the website instead, and if so, call 'open_website' tool.", None
            except requests.exceptions.RequestException:
                pass
                
        return False, f"Error: Application '{app_name}' was not found on this system.", None
            
    except Exception as e:
        return False, f"Error: Failed to open {app_name}. Details: {str(e)}", None


def kill_process(params):
    process_name = params.get("process_name")
    os_type = params.get("os_type", "").lower()
    override = params.get("override_permission", False)

    if not process_name or not psutil: 
        return False, "Error: Target process missing or system tools unavailable.", None

    is_safe, error_msg = _validate_critical_action(override, f"kill_process ({process_name})")
    if not is_safe:
        return False, error_msg, None

    if process_name.lower() == "all":
        count = 0
        me = psutil.Process()
        win_ignore = ["explorer.exe", "cmd.exe", "python.exe"]
        lin_ignore = ["bash", "gnome-shell", "systemd", "python", "python3", "Xorg", "wayland"]
        ignore_list = win_ignore if os_type == "windows" else lin_ignore

        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                if (proc.info['username'] == me.username() and proc.pid != me.pid and 
                    proc.info['name'] and proc.info['name'].lower() not in ignore_list):
                        proc.terminate()
                        count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied): continue
        return True, f"Success: Closed {count} applications.", None
    
    killed = False
    process_list = []
    
    # Gather all running processes
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name']:
                process_list.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue

    # First Attempt: Exact substring match
    for proc in process_list:
        if process_name.lower() in proc.info['name'].lower():
            try:
                proc.terminate()
                killed = True
            except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            
    if killed: 
        return True, f"Success: Terminated {process_name}.", None
        
    # Second Attempt: Fuzzy Matching if termination failed
    if not killed and fuzz and process:
        proc_names = list(set([p.info['name'] for p in process_list]))
        best_match, score = process.extractOne(process_name, proc_names, scorer=fuzz.token_sort_ratio)
        if score >= 65:
            logging.info(f"Fuzzy matched process '{process_name}' to '{best_match}' with score {score}")
            for proc in process_list:
                if proc.info['name'] == best_match:
                    try:
                        proc.terminate()
                        killed = True
                    except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            if killed:
                return True, f"Success: Terminated {best_match} (fuzzy matched from {process_name}).", None

    # Adjust response to provide an explicit, guided error
    return False, f"Error: Process '{process_name}' not found. Ask the user to confirm the correct application name.", None


def system_power(params):
    action = params.get("action", "").lower()
    os_type = params.get("os_type", "").lower()
    override = params.get("override_permission", False)

    is_safe, error_msg = _validate_critical_action(override, f"system_power ({action})")
    if not is_safe:
        return False, error_msg, None

    try:
        dramatic_prompt = ""
        
        if action == "shutdown":
            if os_type == "windows":
                subprocess.run(["shutdown", "/s", "/t", "20"], check=True)
            else:
                subprocess.Popen("sleep 20 && shutdown -h now", shell=True) # extra 5 secs for TTFT & TTS spelling
            dramatic_prompt = "SYSTEM ACTION: OS Shutdown initiated in 15 seconds. STRICT DIRECTIVE: Bypass your <thinking> tags entirely. Output EXACTLY ONE dramatic, poetic goodbye sentence immediately."

        elif action == "restart":
            if os_type == "windows":
                subprocess.run(["shutdown", "/r", "/t", "20"], check=True)
            else:
                subprocess.Popen("sleep 20 && shutdown -r now", shell=True)
            dramatic_prompt = "SYSTEM ACTION: OS Restart initiated in 15 seconds. STRICT DIRECTIVE: Bypass your <thinking> tags entirely. Output EXACTLY ONE dramatic 'see you soon' sentence immediately."

        elif action == "lock":
            if os_type == "windows":
                import ctypes
                ctypes.windll.user32.LockWorkStation()
            else:
                commands = [
                    ["loginctl", "lock-session"],
                    ["xdg-screensaver", "lock"],
                    ["gnome-screensaver-command", "-l"]
                ]
                for cmd in commands:
                    try:
                        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        break
                    except:
                        continue
            dramatic_prompt = "SYSTEM ACTION: Screen locked safely. STRICT DIRECTIVE: Bypass your <thinking> tags entirely. Inform the user elegantly in ONE short sentence."

        else:
            return False, f"Error: Invalid power action '{action}'. Valid actions are: lock, restart, shutdown.", None

        return True, dramatic_prompt, None

    except Exception as e:
        logging.error(f"System Power Error: {e}")
        print(f"System Power Error: {e}")
        return False, f"Failed to execute {action}: {e}", None
