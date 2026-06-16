# core/ui/video_player.py

"""
JARVIS Visual Sequences Player
==============================
A lightweight PyQt5 multimedia player dedicated to executing boot-up
animations and full-screen visual effects independently of the main thread.
"""

import os
import sys
import time
import subprocess
import platform
from pathlib import Path
from typing import Optional
from core.config import BIN_DIR
from core.bootstrap.env_setup import check_and_run_wizard

class VideoPlayer:
    """
    Manager class to trigger the isolated native video process.
    """

    def __init__(self):
        self.available = True
        self.current_process = None
        self.os_type = platform.system()

    def _get_mpv_path(self):
        if self.os_type == "Windows":
            mpv_path = BIN_DIR / "mpv.exe"
            if mpv_path.exists():
                return str(mpv_path)
            return None
        else:
            try:
                # Using shutil.which is faster, but keeping your implementation to minimize unnecessary rewrites
                subprocess.run(["mpv", "--version"], capture_output=True, timeout=5)
                return "mpv"
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return None

    def play_video(
        self, video_path: str,
        duration: Optional[float] = None, # Kept purely to avoid breaking old calls in initialize()
        blocking: bool = True
    ) -> bool:
        
        if not self.available:
            return False

        if self.current_process and self.current_process.poll() is None:
            print("⚠️ [Visual System] Video sequence is already active. Skipping duplicate request.")
            return False

        video_file = Path(video_path)
        
        # Fallback mechanism if the video file is missing
        if not video_file.exists():
            print(f"⚠️ [Visual System] Video file missing at: {video_path}")
            print("⏳ Simulating sequence delay (5s) to avoid system crash...")
            time.sleep(5)
            return False

        absolute_path = str(video_file.resolve())

        mpv_exec = self._get_mpv_path()
        if not mpv_exec:
            print("⚠️ [Visual System] mpv player not found. Launching setup wizard...")
            check_and_run_wizard()
            mpv_exec = self._get_mpv_path()
            if not mpv_exec:
                return False

        try:
            print(f"🎬 Initiating event-driven native sequence: {video_file.name}")

            cmd = [
                mpv_exec,
                "--fs",
                "--ontop",
                "--no-border",
                "--cursor-autohide=always",
                "--keep-open=no",               
                "--idle=no",                   
                "--no-input-default-bindings",  
                "--no-osc",                     
                absolute_path
            ]
            
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            self.current_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=flags
            )

            if blocking:
                # Wait naturally for the process to finish on its own terms (No timeout)
                self.current_process.wait()
                
                # Cleanup failsafe if the process somehow hangs
                if self.current_process.poll() is None:
                    self.current_process.kill()
                    self.current_process.wait()

            return True

        except Exception as e:
            print(f"❌ Error in visual sequence: {e}")
            if self.current_process and self.current_process.poll() is None:
                self.current_process.kill()
            return False