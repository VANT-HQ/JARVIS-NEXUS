
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
 
#! Total time spented on THIS version: 6 months. (v1.0, not including sub-versions)
#! Typed on 16 Jun 2026


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
Version: 1.3 (Stable Release)
"""

# ─── DLL HELL PREVENTION (MUST BE THE ABSOLUTE FIRST LINE) ───
try:
    import rthook_dlls
except ImportError:
    pass  # Running in dev mode, rthook_dlls is only present in compiled builds

import os
import sys
import traceback
import multiprocessing
from pathlib import Path

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ─── Ensure project root is always on sys.path ─────────────────────────────
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
elif "__compiled__" in globals():
    PROJECT_ROOT = Path(sys.argv[0]).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── EARLY EXIT: --template must be handled BEFORE heavy imports ────────────
# Loading core.logger/core.config triggers DB init, audio drivers, etc. — a
# 4-7s penalty just to show a small dialog window. Handle it here instead.
if "--template" in sys.argv:
    # MODIFIED: Fast path — import ONLY the builder, skip all heavy dependencies
    from core.bootstrap.template_builder import request_template_from_user
    _idx = sys.argv.index("--template")
    _model = sys.argv[_idx+1] if len(sys.argv) > _idx+1 else "unknown"
    _has_auto_str = sys.argv[_idx+2] if len(sys.argv) > _idx+2 else "False"
    _res = request_template_from_user(_model, has_auto=(_has_auto_str.lower() == 'true'))
    if _res == "__AUTO__":
        print("__TEMPLATE_START__\n__AUTO__\n__TEMPLATE_END__")
    elif _res:
        print(f"__TEMPLATE_START__\n{_res}\n__TEMPLATE_END__")
    else:
        print("__TEMPLATE_ABORT__")
    sys.exit(0)
# ─── END EARLY EXIT ──────────────────────────────────────────────────────────

# ─── Initialize System Logger ──────────────────────────────────────────────
from core.logger import setup_logger
logger = setup_logger()
from core.config import LOGS_DIR

# =================================================================
# Entry Point
# =================================================================
def main():
    logger.info("Initializing JARVISCore...")
    
    # Early import — locks native modules in correct order before engine boot
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
    
    # ─── Single import from the engine ─────────────────────────────────────────
    # from core.jarvis_engine import JARVISCore  #! Full Program
    from core.skip_stt import SkipSTTCore as JARVISCore  #! TESTING: Terminal mode (no audio)
    
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
        if getattr(sys, 'frozen', False) and not isinstance(e, SystemExit):
            input("\nPress Enter to exit...")
    finally:
        logger.info("JARVIS application terminated.")
        # Ensure terminal stays open in EXE mode ONLY if not a clean exit
        if getattr(sys, 'frozen', False) and 'e' in locals() and not isinstance(e, SystemExit):
            pass

if __name__ == "__main__":
    multiprocessing.freeze_support()
    
    # ─── Single Instance Enforcement (Main App) ───
    if "--settings" not in sys.argv and "--setup" not in sys.argv and "--template" not in sys.argv and "--results" not in sys.argv and "--results-live" not in sys.argv:
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
    elif "--results" in sys.argv:
        from core.ui.results_viewer import open_viewer
        open_viewer(live=False)
    elif "--results-live" in sys.argv:
        from core.ui.results_viewer import open_viewer
        open_viewer(live=True)
    elif "--setup" in sys.argv:
        from core.bootstrap.env_setup import launch_wizard
        launch_wizard()
    elif "--template" in sys.argv:
        # NOTE: This branch is now only reached in edge cases (e.g. if early-exit above was bypassed).
        # The primary handler is the early-exit block at the top of the file.
        from core.bootstrap.template_builder import request_template_from_user
        idx = sys.argv.index("--template")
        model = sys.argv[idx+1] if len(sys.argv) > idx+1 else "unknown"
        has_auto_str = sys.argv[idx+2] if len(sys.argv) > idx+2 else "False"
        has_auto = (has_auto_str.lower() == 'true')
        res = request_template_from_user(model, has_auto=has_auto)
        if res == "__AUTO__":
            print("__TEMPLATE_START__\n__AUTO__\n__TEMPLATE_END__")
        elif res:
            print(f"__TEMPLATE_START__\n{res}\n__TEMPLATE_END__")
        else:
            print("__TEMPLATE_ABORT__")
        sys.exit(0)
    else:
        main()

