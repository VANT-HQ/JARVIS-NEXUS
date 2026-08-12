"""
dev_run.py — JARVIS Test Runner
================================
Usage:
    python dev_run.py                                   # interactive terminal
    python dev_run.py --file tests/test/test_input.txt       # run quick test file
    python dev_run.py --file tests/test/test_input_full.txt  # run full test suite
    python dev_run.py --overthink --file tests/test/test_input_full.txt  # with overthinking mode

This script:
1. Clears llm_raw_debug.txt before every run (clean context window).
2. Enables dev_mode in settings.db automatically.
3. Boots SkipSTTCore (terminal mode — no audio).
4. Optionally feeds test_input.txt line-by-line for automated testing.
"""

import os
import sys
import time
import threading
from pathlib import Path

# ── Ensure project root is on sys.path ─────────────────────────────
# We are currently in tests/test/dev_run.py, so we go up 3 levels to reach the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ── 1. Clear the debug log before anything else ────────────────────
LOGS_DIR = PROJECT_ROOT / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
debug_log = LOGS_DIR / "llm_raw_debug.txt"
debug_log.write_text("", encoding="utf-8")
print(f"🗑️  [Dev] Cleared: {debug_log}")

# ── 2. Enable dev_mode in settings.db ─────────────────────────────
try:
    import sqlite3
    db_path = PROJECT_ROOT / "data" / "settings.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)
    """)
    conn.execute("""
        INSERT INTO settings (key, value) VALUES ('dev_mode', 'true')
        ON CONFLICT(key) DO UPDATE SET value = 'true'
    """)
    conn.commit()
    conn.close()
    print("[OK] dev_mode enabled in settings.db")
except Exception as e:
    print(f"[WARN] Could not set dev_mode: {e}")

# ── 3. Parse args ──────────────────────────────────────────────────
import argparse
parser = argparse.ArgumentParser(description="JARVIS Dev Test Runner")
parser.add_argument("--file", "-f", type=str, default=None,
                    help="Path to test input file (one command per line). If omitted, runs interactive mode.")
parser.add_argument("--overthink", "-o", action="store_true",
                    help="Enable overthinking mode for the session.")
args = parser.parse_args()

# ── 4. Boot SkipSTTCore ────────────────────────────────────────────
from core.logger import setup_logger
logger = setup_logger()

from core.skip_stt import SkipSTTCore

jarvis = SkipSTTCore()
jarvis.initialize()

# ── 5. Activate overthinking if requested ─────────────────────────
if args.overthink:
    jarvis.state.overthinking_mode = True
    jarvis.state.invalidate_system_cache()
    print("🧠 [Dev] OVERTHINKING MODE: ON")

# ── 6. Run ────────────────────────────────────────────────────────
if args.file:
    # Automated test: feed file line-by-line
    test_file = Path(args.file)
    if not test_file.exists():
        fallback_file = PROJECT_ROOT / "tests" / "test" / test_file.name
        if fallback_file.exists():
            test_file = fallback_file
        else:
            print(f"❌ Test file not found: {test_file}")
            sys.exit(1)

    lines = [l.strip() for l in test_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    
    print("\n" + "=" * 60)
    print(f"   📋 AUTOMATED TEST — {test_file.name}")
    print(f"   Total commands: {len(lines)}")
    print("=" * 60 + "\n")

    jarvis.running = True
    for cmd in lines:
        if cmd.lower() in ("exit", "shutdown"):
            print(f"\n  [{jarvis.assistant_name}] You: {cmd}")
            print(f"  🔊 [JARVIS]: Shutting down all systems. Goodbye sir.")
            break

        # Handle internal mode-switch commands
        if "overthinking mode on" in cmd.lower():
            jarvis.state.overthinking_mode = True
            jarvis.state.invalidate_system_cache()
            print(f"\n  [{jarvis.assistant_name}] You: {cmd}")
            print(f"  🧠 [System] OVERTHINKING MODE: ON")
            continue
        if "overthinking mode off" in cmd.lower():
            jarvis.state.overthinking_mode = False
            jarvis.state.invalidate_system_cache()
            print(f"\n  [{jarvis.assistant_name}] You: {cmd}")
            print(f"  🧠 [System] OVERTHINKING MODE: OFF")
            continue

        print(f"\n  [{jarvis.assistant_name}] You: {cmd}")
        print(f"🚀 Executing: {cmd}")

        try:
            response = jarvis.process_command(cmd)
            if response:
                jarvis.mouth.speak(response)
        except Exception as e:
            print(f"❌ Error: {e}")

        jarvis.last_speech_time = time.time()
        jarvis.state.enter_follow_up()
        jarvis.state.clear_temp_memory()
        print()

        # Small gap between commands for readability
        time.sleep(0.3)

    jarvis.watch_dog.stop()
    print(f"\n✅ Test run complete. Check: {debug_log}")

else:
    # Interactive mode — standard terminal loop
    jarvis.run()
