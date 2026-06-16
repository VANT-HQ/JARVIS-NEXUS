# core/bootstrap/autostart.py

"""
JARVIS Autostart Manager
========================
Handles cross-platform (Windows/Linux) logic for registering JARVIS 
to run automatically on system boot.
"""

import os
import sys
import platform
import logging
from pathlib import Path

# Setup logging
logger = logging.getLogger("JarvisNexus.Autostart")

APP_NAME = "JarvisNexus"

def get_executable_path() -> str:
    """Returns the correct path whether the application is running as a script or as an executable (PyInstaller)"""
    if getattr(sys, 'frozen', False):
        return sys.executable
    elif "__compiled__" in globals():
        return os.path.abspath(sys.argv[0])
    return os.path.abspath(sys.argv[0])

def sync_startup_state(enable: bool):
    """
    The main function to be called from config.py.
    Enables or disables startup based on the value (True/False).
    """
    if not (getattr(sys, 'frozen', False) or "__compiled__" in globals()):
        logger.info(f"Development mode detected (.py script). Skipping startup sync for {APP_NAME}.")
        return

    os_name = platform.system()
    app_path = get_executable_path()

    if os_name == "Windows":
        _sync_windows_startup(enable, app_path)
    elif os_name == "Linux":
        _sync_linux_startup(enable, app_path)
    else:
        logger.warning(f"Autostart is not implemented for OS: {os_name}")

def _sync_windows_startup(enable: bool, app_path: str):
    import winreg as reg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    
    command = f'"{app_path}"'

    try:
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, key_path, 0, reg.KEY_READ | reg.KEY_SET_VALUE)
        
        current_value = None
        try:
            current_value, _ = reg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            pass 

        if enable:
            if current_value == command:
                logger.info(f"[Windows] {APP_NAME} is already in startup. No changes made.")
            else:
                reg.SetValueEx(key, APP_NAME, 0, reg.REG_SZ, command)
                logger.info(f"[Windows] Added {APP_NAME} to startup.")
        else:
            if current_value is not None:
                reg.DeleteValue(key, APP_NAME)
                logger.info(f"[Windows] Removed {APP_NAME} from startup.")
            else:
                logger.info(f"[Windows] {APP_NAME} is not in startup. No action needed.")
                
        reg.CloseKey(key)
    except Exception as e:
        logger.error(f"[Windows] Failed to update startup registry: {e}")
        print(f"[Windows] Failed to update startup registry: {e}")

def _sync_linux_startup(enable: bool, app_path: str):
    autostart_dir = Path.home() / ".config" / "autostart"
    desktop_file = autostart_dir / f"{APP_NAME}.desktop"
    
    command = app_path

    content = (
        f"[Desktop Entry]\n"
        f"Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Exec={command}\n"
        f"Terminal=false\n"
        f"Hidden=false\n"
    )
    
    try:
        if enable:
            autostart_dir.mkdir(parents=True, exist_ok=True)
            is_set = False
            if desktop_file.exists():
                with open(desktop_file, "r") as f:
                    if f.read() == content:
                        is_set = True

            if is_set:
                logger.info(f"[Linux] {APP_NAME} is already in startup. No changes made.")
            else:
                with open(desktop_file, "w") as f:
                    f.write(content)
                logger.info(f"[Linux] Added {APP_NAME} to startup.")
        else:
            if desktop_file.exists():
                desktop_file.unlink()
                logger.info(f"[Linux] Removed {APP_NAME} from startup.")
            else:
                logger.info(f"[Linux] {APP_NAME} is not in startup. No action needed.")
    except Exception as e:
        logger.error(f"[Linux] Failed to update startup desktop file: {e}")
        print(f"[Linux] Failed to update startup desktop file: {e}")