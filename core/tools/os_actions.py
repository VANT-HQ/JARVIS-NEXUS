# -*- coding: utf-8 -*-
# core/tools/os_actions.py

import os
import sys
import webbrowser
import subprocess  
import glob  
import time  
import random  
import logging  
import datetime  
import ctypes  
import shutil  
from pathlib import Path

# =================================================================
# Unified System Configuration Import
# =================================================================
# Add root directory to access core modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try: 
    from core.config import config, BASE_DIR
except ImportError as e:
    logging.error(f"❌ Could not import centralized config. {e}")
    sys.exit(1)

# =================================================================
# Platform Specific Imports
# =================================================================
try:
    import requests  
except ImportError:
    logging.warning("requests missing. Weather disabled.")
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
    logging.warning("pycaw missing. System volume control disabled.")
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


# =================================================================
# Command Functions
# =================================================================

def open_website(params):
    """ Opens any requested website by name or URL with ultra-fast validation. """
    site = params.get("site_name")
    if not site:
        return False, "Error: What website should I open, sir?", None
    
    logging.info(f"Executing: Open Website '{site}'")
    try:
        if not site.startswith("http"):
            if "." not in site:
                site = f"https://www.{site.lower().replace(' ', '')}.com"
            else:
                site = f"https://{site}"
                
        # Ultra-fast check using HEAD (fetches headers only without downloading content)
        if requests:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                check = requests.head(site, headers=headers, timeout=2)
                
                # Some websites block HEAD requests, so attempt a quick GET if an error is returned
                if check.status_code >= 400 and check.status_code not in [401, 403, 405]: 
                    check = requests.get(site, headers=headers, timeout=2, stream=True)
                    if check.status_code >= 400 and check.status_code not in [401, 403, 405]:
                        return False, f"Error: '{site}' is unreachable (Status {check.status_code}). Tell the user it failed and immediately use the 'search_web' tool to find the correct link.", None
            except requests.exceptions.RequestException:
                return False, f"Error: Could not reach '{site}'. Tell the user it failed and use the 'search_web' tool to search for it.", None

        # If the check succeeds, open the browser
        webbrowser.open(site)
        return True, f"Successfully opened {site}.", None
        
    except Exception as e:
        logging.error(f"Error opening website: {e}")
        return False, f"Error: Failed to open the website: {e}", None

def google_search(params):
    """ Standard Google search. """
    query = params.get("query")
    if not query:
        return False, "What should I search for, sir?", None
    logging.info(f"Executing: Google Search for '{query}'")
    try:
        import urllib.parse
        encoded_query = urllib.parse.quote_plus(query)
        webbrowser.open(f"https://www.google.com/search?q={encoded_query}")
        return True, f"Searching the web for {query}.", None
    except Exception as e:
        logging.error(f"Error Google search: {e}")
        return False, "Error searching Google.", None

def get_current_time(params):
    """ Returns the time in a human-readable format. """
    current_time = time.strftime("%I:%M %p") # Returns: 08:44 PM
    return True, f"The current time is {current_time}.", None

def get_current_date(params):
    """ Returns the date in a human-readable format. """
    current_date = time.strftime("%d/%B/%Y") # Returns: 04/March/2026
    return True, f"Today's date is {current_date}.", None

def get_weather(params):
    """ Fetch current weather conditions. """
    logging.info("Executing: Get Weather")
    if not requests:
        return False, "Internet connection requests module is missing.", None
    
    city = params.get("city", "") 
    try:
        url = f"https://wttr.in/{city}?format=%C+and+%t"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            weather_text = response.text.strip().replace("+", "")
            return True, f"The current weather is {weather_text}.", None
        else:
            return False, "I couldn't retrieve the weather data right now.", None
    except Exception as e:
        logging.error(f"Weather error: {e}")
        return False, "Unable to connect to the weather service.", None

# -----------------------------------------------------------------
# New Audio Management (List & Play)
# -----------------------------------------------------------------

def list_local_audio(params):
    """ 
    Scans the designated audio directory and returns a list of filenames 
    to the LLM so it can decide what to play.
    """
    audio_dir = config.get("audio_dir") or str(Path.home() / "Music")
    if not os.path.exists(audio_dir):
        return False, f"Audio directory {audio_dir} not found.", None
        
    extensions = ('*.mp3', '*.wav', '*.flac', '*.m4a')
    music_files = []
    for ext in extensions:
        music_files.extend(glob.glob(os.path.join(audio_dir, "**", ext), recursive=True))
        
    if not music_files:
        return True, "The audio library is empty.", []
        
    # Return filenames only to minimize token consumption
    file_names = [os.path.basename(f) for f in music_files]
    return True, f"Found {len(file_names)} audio files.", file_names

def play_music(params):
    """ Play a specific or random audio file based on the model's selection. """
    logging.info("Executing: Play Music")
    audio_dir = config.get("audio_dir") or str(Path.home() / "Music")
    song_name = params.get("song_name", "").lower()

    if not os.path.exists(audio_dir):
        return False, f"The directory {audio_dir} does not exist.", None

    extensions = ('*.mp3', '*.wav', '*.flac', '*.m4a')
    music_files = []
    for ext in extensions:
        music_files.extend(glob.glob(os.path.join(audio_dir, "**", ext), recursive=True))

    target_file = None
    if song_name:
        for f in music_files:
            if song_name in os.path.basename(f).lower():
                target_file = f
                break
                
    if not target_file:
        if song_name: 
            return False, f"I couldn't find an audio file named {song_name}.", None
        if music_files:
            target_file = random.choice(music_files)
        else:
            return False, "No audio files available to play.", None

    try:
        os.startfile(target_file)
        return True, f"Playing {os.path.basename(target_file)}.", None
    except Exception as e:
        logging.error(f"Music error: {e}")
        return False, "Error executing playback.", None

# -----------------------------------------------------------------
# Dual Volume Control
# -----------------------------------------------------------------

def set_volume(params):
    """ 
    Controls either the global system volume or Jarvis's internal volume.
    Accepts 'level' (fixed percentage) or 'change' (increment/decrement amount).
    """
    target = params.get("target", "system") # "system" or "jarvis"
    level = params.get("level")
    change = params.get("change")
    
    # Default to an increment of +10 if no value is provided
    if level is None and change is None:
        change = 10

    # 1. Control Jarvis's internal application volume
    if target == "jarvis":
        current_vol = config.get("volume")
        if level is not None:
            new_vol = int(level)
        else:
            new_vol = current_vol + int(change)
            
        new_vol = max(0, min(100, new_vol))
        config.set("volume", new_vol)
        return True, f"My internal volume is now set to {new_vol}%.", None

    # 2. Control system-wide OS volume
    if not AudioUtilities:
        return False, "System audio controls unavailable.", None

    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = cast(interface, POINTER(IAudioEndpointVolume))
        
        if level is not None:
            new_vol_scalar = max(0.0, min(1.0, float(level) / 100.0))
            volume.SetMasterVolumeLevelScalar(new_vol_scalar, None)
            return True, f"System volume set to {level}%.", None
            
        if change is not None:
            current_scalar = volume.GetMasterVolumeLevelScalar()
            new_vol_scalar = max(0.0, min(1.0, current_scalar + (float(change) / 100.0)))
            volume.SetMasterVolumeLevelScalar(new_vol_scalar, None)
            return True, f"System volume adjusted by {change}%.", None
            
    except Exception as e:
        logging.error(f"Volume error: {e}")
        return False, "Failed to adjust system volume.", None

# -----------------------------------------------------------------
# Jarvis Power Management (Sleep / Restart)
# -----------------------------------------------------------------

def jarvis_control(params):
    """ 
    Manages Jarvis's execution state (nap, restart, shutdown).
    Invokes watch_dog.py in the background to handle revival protocols.
    """
    action = params.get("action", "nap") # nap, restart, shutdown
    minutes = params.get("minutes", 30)
    
    watchdog_path = BASE_DIR / "core" / "tools" / "watch_dog.py"
    
    try:
        if action == "nap":
            # Launch the watchdog as an independent process that survives Jarvis termination
            subprocess.Popen(
                [sys.executable, str(watchdog_path), "nap", str(minutes)],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            logging.info(f"Taking a nap for {minutes} minutes.")
            os._exit(0) # Terminate Jarvis process immediately
            
        elif action == "restart":
            subprocess.Popen(
                [sys.executable, str(watchdog_path), "restart"],
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
            logging.info("Restarting Jarvis system.")
            os._exit(0)
            
        elif action == "shutdown":
            logging.info("Shutting down Jarvis system permanently.")
            os._exit(0)
            
    except Exception as e:
        logging.error(f"Jarvis control error: {e}")
        return False, "Failed to execute core system protocol.", None

# -----------------------------------------------------------------
# Smart Item Execution (Run Item)
# -----------------------------------------------------------------

def run_item(params):
    """ 
    Accepts search terms to scan within the configured shortcuts directory
    and launches the most relevant match.
    """
    search_terms = params.get("search_terms", [])
    if isinstance(search_terms, str):
        search_terms = [search_terms]
        
    if not search_terms:
        return False, "I need a name to search for, sir.", None
        
    shortcuts_dir = config.get("shortcuts_dir") or str(Path.home() / "Desktop")
    
    if not os.path.exists(shortcuts_dir):
        return False, "The shortcuts directory is missing.", None

    logging.info(f"Executing: Run Item '{search_terms}'")
    
    files = [f for f in os.listdir(shortcuts_dir) if os.path.isfile(os.path.join(shortcuts_dir, f))]
    if not files:
        return False, "The shortcuts folder is empty.", None

    best_match_file = None
    highest_score = 0
    
    if fuzz:
        # Evaluate every search term provided by the LLM to guarantee the optimal match
        for term in search_terms:
            for f in files:
                name_no_ext = os.path.splitext(f)[0]
                score = fuzz.token_sort_ratio(term.lower(), name_no_ext.lower())
                if score > highest_score:
                    highest_score = score
                    best_match_file = f
    else:
        # Fallback primitive matching if the fuzzing library is not installed
        for term in search_terms:
            for f in files:
                if term.lower() in f.lower():
                    best_match_file = f
                    highest_score = 100
                    break

    if best_match_file and highest_score > 60:
        full_path = os.path.join(shortcuts_dir, best_match_file)
        try:
            os.startfile(full_path)
            return True, f"Executing {best_match_file}.", None
        except Exception as e:
            logging.error(f"Run Item error: {e}")
            return False, "Failed to launch the requested item.", None
    else:
        return False, f"Could not find a valid match for {search_terms}.", None

# -----------------------------------------------------------------
# Utility & Environment Commands
# -----------------------------------------------------------------

def system_status(params):
    """ Fetch system performance metrics. """
    if not psutil: return False, "System tools missing.", None
    cpu = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory().percent
    bat = psutil.sensors_battery()
    msg = f"CPU is at {cpu}%. Memory is at {mem}%."
    if bat:
        msg += f" Battery is {bat.percent}%."
    return True, msg, None

def set_brightness(params):
    level = params.get("level")
    if not sbc or level is None: return False, "Brightness control failed.", None
    try:
        sbc.set_brightness(int(level))
        return True, f"Brightness set to {level}%.", None
    except Exception as e:
        return False, "Failed to set brightness.", None

def take_screenshot(params):
    if not pyautogui: return False, "Screenshot tools unavailable.", None
    try:
        save_dir = config.get("desktop_dir") or str(Path.home() / "Desktop")
        filename = f"Jarvis_Screenshot_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.png"
        filepath = os.path.join(save_dir, filename)
        pyautogui.screenshot().save(filepath)
        return True, "Screenshot saved to desktop.", filepath
    except Exception as e:
        return False, "Failed to capture screenshot.", None

def save_text_to_file(params):
    file_name = params.get("file_name", f"Jarvis_Note_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt")
    content = params.get("content", "")
    if not content: return False, "Content is empty.", None

    save_dir = config.get("desktop_dir") or str(Path.home() / "Desktop")
    # Sanitize the file name
    file_name = "".join([c for c in file_name if c.isalnum() or c in (' ', '.', '_', '-')]).strip()
    if not file_name.endswith(".txt"): file_name += ".txt"
    
    full_path = os.path.join(save_dir, file_name)
    try:
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, f"Note saved to desktop as {file_name}.", None
    except Exception as e:
        return False, "Failed to save the file.", None

def open_application(params):
    app_name = params.get("app_name")
    if not app_name: return False, "Application name missing.", None
    try:
        subprocess.Popen(f"start {app_name}", shell=True)
        return True, f"Opening {app_name}.", None
    except Exception as e:
        return False, f"Failed to open {app_name}.", None

def kill_process(params):
    process_name = params.get("process_name")
    if not process_name or not psutil: return False, "Target missing or tools unavailable.", None

    if process_name.lower() == "all":
        count = 0
        me = psutil.Process()
        for proc in psutil.process_iter(['pid', 'name', 'username']):
            try:
                if (proc.info['username'] == me.username() and proc.pid != me.pid and 
                    proc.info['name'].lower() not in ["explorer.exe", "cmd.exe", "python.exe"]):
                        proc.terminate()
                        count += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied): continue
        return True, f"Closed {count} applications.", None
    
    killed = False
    for proc in psutil.process_iter(['name']):
        try:
            if process_name.lower() in proc.info['name'].lower():
                proc.terminate()
                killed = True
        except (psutil.NoSuchProcess, psutil.AccessDenied): continue
            
    if killed: return True, f"Terminated {process_name}.", None
    return False, f"Process {process_name} not found.", None

def close_window(params):
    if not pyautogui: return False, "Window tools missing.", None
    pyautogui.hotkey('alt', 'f4')
    return True, "Closing active window.", None

def shutdown_computer(params):
    subprocess.run(["shutdown", "/s", "/t", "5"], check=True)
    return True, "Shutting down system.", None

def restart_computer(params):
    subprocess.run(["shutdown", "/r", "/t", "5"], check=True)
    return True, "Restarting system.", None

def lock_workstation(params):
    ctypes.windll.user32.LockWorkStation()
    return True, "Locking workstation.", None