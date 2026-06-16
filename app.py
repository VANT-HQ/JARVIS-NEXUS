
#? Dear reader, if u reading this it means u are a developer. (aka victim)
#? when i started this project, only god and me knew how it works,
#? now only god knows. (traditional dev line)
#? during this project, strange things happened to me in my life 
#? i failed my exams, discovered that my only romantic relation was one sided, (guss which side i was?)
#? and even got a new CAT!! (her name is Lilly btw)
#? This has only two explanations: 
#? i've f*ked up or this project is cursed.
#? so if u still reading this, it means u didn't get scared yet 
#? and planning to continue, i just have one advice for u...
#* good luck and take care of yourself, see u in next version. 
#* im exited to see ur collaboration on the repo ^_^

#? SOCIAL MEDIA -> @Hmody Code  

#! Total time spented on THIS version: 6 months. 



"""
JARVIS - Entry Point
=====================
This file does ONE thing: boot JARVIS.
All logic lives in core/jarvis_engine.py and core/llm_client.py.

                     app.py  (you are here)
                        │
                        ▼
              core/jarvis_engine.py  ──imports──►  core/llm_client.py
                (Brain & Muscle)                    (Transport Layer)
                        │
                        ▼
              core/tools, core/audio, core/memory, core/config, ...

To run: python app.py

Author: Hmody -> Lead Architect @ V.A.N.T.
Version: 1.0 (Stable Release)
"""

# ─── DLL HELL PREVENTION (MUST BE THE ABSOLUTE FIRST LINE) ───
import rthook_dlls

import os
import sys
import traceback
import multiprocessing
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Early import — locks native modules in correct order
try:
    import onnxruntime
except Exception:
    pass
try:
    from piper import PiperVoice as _PV
except Exception:
    pass
try:
    import ctranslate2
except Exception:
    pass
try:
    import faster_whisper
except Exception:
    pass
# ───────────────────────────────────────────────────────────────────────────

# ─── Ensure project root is always on sys.path ─────────────────────────────
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
elif "__compiled__" in globals():
    PROJECT_ROOT = Path(sys.argv[0]).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Initialize System Logger ──────────────────────────────────────────────
from core.logger import setup_logger
logger = setup_logger()
from core.config import LOGS_DIR

# ─── Single import from the engine ─────────────────────────────────────────
from core.jarvis_engine import JARVISCore  #! Full Program
# from core.skip_stt import SkipSTTCore as JARVISCore  #! TESTING: Terminal mode (no audio)

# =================================================================
# Entry Point
# =================================================================
def main():
    logger.info("Initializing JARVISCore...")
    
    jarvis = None
    try:
        jarvis = JARVISCore()
        
        # Start System Tray Icon
        try:
            from core.ui.tray_icon import start_tray
            start_tray(jarvis)
        except Exception as e:
            logger.warning(f"Could not start system tray icon: {e}")
            print(f"⚠️ [Tray] Warning: System Tray failed to load ({e}). Ensure pystray and Pillow are installed.")
            
        logger.info("Starting JARVIS application loop.")
        jarvis.run()
    except BaseException as e:
        logger.error(f"Fatal Error: {e}", exc_info=True)
        print(f"\n❌ Fatal Error: {e}")
        traceback.print_exc()
        
        # Write a crash report
        crash_log_path = LOGS_DIR / "crash_report.txt"
        with open(crash_log_path, "w", encoding="utf-8") as f:
            f.write("JARVIS Crash Report\n")
            f.write("===================\n")
            traceback.print_exc(file=f)
        print(f"\n📄 Crash report saved to {crash_log_path}")
        
        # Pause before closing the console so the user can see the error
        if getattr(sys, 'frozen', False):
            input("\nPress Enter to exit...")
    finally:
        logger.info("JARVIS application terminated.")
        # Ensure terminal stays open in EXE mode
        if getattr(sys, 'frozen', False):
            input("\nPress Enter to exit...")

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # ─── Single Instance Enforcement (Main App) ───
    if "--settings" not in sys.argv and "--setup" not in sys.argv:
        from core.bootstrap.utils import enforce_single_instance
        if not enforce_single_instance("JARVIS_Main_App_Mutex"):
            print("\n❌ JARVIS is already running! Only one core instance is allowed.")
            sys.exit(0)
    
    # Global exception hook to catch threading/unhandled errors
    def global_exception_handler(exctype, value, tb):
        logger.error("Unhandled Exception:", exc_info=(exctype, value, tb))
        crash_log_path = LOGS_DIR / "crash_report_unhandled.txt"
        with open(crash_log_path, "w", encoding="utf-8") as f:
            f.write("JARVIS Unhandled Crash Report\n")
            f.write("=============================\n")
            import traceback
            traceback.print_exception(exctype, value, tb, file=f)
        print(f"\n❌ Unhandled Fatal Error. Report saved to {crash_log_path}")
        if getattr(sys, 'frozen', False):
            input("\nPress Enter to exit...")
            
    sys.excepthook = global_exception_handler

    if "--settings" in sys.argv:
        from core.ui.settings_panel import launch
        launch()
    elif "--setup" in sys.argv:
        from core.bootstrap.env_setup import launch_wizard
        launch_wizard()
    else:
        main()

