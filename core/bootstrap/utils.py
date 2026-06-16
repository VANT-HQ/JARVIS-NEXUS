# core/bootstrap/utils.py
"""
Utility functions for JARVIS Bootstrap and Process Management.
"""

import os

_ACTIVE_LOCKS = []

def enforce_single_instance(lock_name: str, window_title: str = None) -> bool:
    """
    Cross-platform single instance enforcer.
    Returns True if we obtained the lock. Returns False if already running.
    If on Windows and window_title is provided, it brings the existing window to the front.
    """
    if os.name == 'nt':
        import ctypes
        kernel32 = ctypes.windll.kernel32
        mutex = kernel32.CreateMutexW(None, False, lock_name)
        if kernel32.GetLastError() == 183: # ERROR_ALREADY_EXISTS
            if window_title:
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, window_title)
                if hwnd:
                    user32.ShowWindow(hwnd, 9) # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
            return False
        _ACTIVE_LOCKS.append(mutex)
        return True
    else:
        import fcntl
        import tempfile
        lock_file_path = os.path.join(tempfile.gettempdir(), f"{lock_name}.lock")
        try:
            lock_file = open(lock_file_path, 'w')
            fcntl.lockf(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _ACTIVE_LOCKS.append(lock_file)
            return True
        except (IOError, BlockingIOError):
            return False
