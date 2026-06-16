# core/watch_dog.py  
"""
JARVIS Background WatchDog
===========================

The WatchDog is a dedicated background daemon responsible for:
- Proactive Task Monitoring (Wake Up Brain)
- Background Context Syncing (RAM Sync)
- Temporal events and snooze logic

This separates background execution from the main orchestrator (app.py) 
and the storage system (memory.py), ensuring a clean architecture.
"""

import time
import threading
import logging
from datetime import datetime
from core.config import get_setting

logger = logging.getLogger(__name__)


class WatchDog:
    def __init__(self, jarvis_core):
        self.jarvis = jarvis_core
        self._snooze_dict = {}              # {task_id: next_reminder_time}
        self._pregenerated_reminders = {}   # {task_id: text}
        self.running = False

        # Event-based shutdown replaces granular sleep loops for instant daemon termination
        self._stop_event = threading.Event()

        # Thread References
        self.monitor_thread = None
        self.sync_thread = None
        self.pregenerate_thread = None

    # ------------------------------------------------------------------
    # Lifecycle Management
    # ------------------------------------------------------------------

    def start(self):
        """Starts all background monitoring processes."""
        self.running = True
        self._stop_event.clear()

        # 1. Start RAM Sync Thread
        self.sync_thread = threading.Thread(target=self._ram_sync_loop, daemon=True)
        self.sync_thread.start()

        # 2. Start Proactive Monitor Thread
        self.monitor_thread = threading.Thread(target=self._task_monitor_loop, daemon=True)
        self.monitor_thread.start()

        # 3. Start Pregenerate Thread
        self.pregenerate_thread = threading.Thread(target=self._pregenerate_loop, daemon=True)
        self.pregenerate_thread.start()

        print("   [WatchDog] 🐕 Monitor, sync, and pregenerate threads active.")

    def stop(self):
        """Safely stops all monitoring processes."""
        self.running = False
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Background Workers
    # ------------------------------------------------------------------

    def _ram_sync_loop(self):
        """
        Background loop: Requests memory to update upcoming tasks to RAM.
        Separated from memory.py to strictly keep memory as a data manager.
        """
        while not self._stop_event.is_set():
            try:
                if getattr(self.jarvis, 'memory', None):
                    self.jarvis.memory.sync_upcoming_tasks()
                    logger.debug("[WatchDog] RAM sync complete.")
            except Exception as e:
                logger.error(
                    f"Watchdog event: RAM sync error / Process failed: {e}",
                    exc_info=True,
                )

            # Wait 20 seconds for near-real-time task awareness.
            self._stop_event.wait(timeout=20)

    def _task_monitor_loop(self):
        """
        Monitors tasks loaded in RAM. 
        If a task is due, it instructs JARVIS to announce it and handles snooze logic.
        """
        while not self._stop_event.is_set():
            try:
                self._check_due_tasks()
            except Exception as e:
                logger.error(
                    f"Watchdog event: Task monitor loop failed/Terminated abnormally: {e}",
                    exc_info=True,
                )

            # Periodic check interval
            self._stop_event.wait(timeout=15)

    # ------------------------------------------------------------------
    # Golden Opportunity Pre-generation
    # ------------------------------------------------------------------
    
    PREGENERATE_WINDOW_SEC = 90  # Initiate pre-generation if task is due within 90s

    def _pregenerate_loop(self):
        """Executes periodically to find opportunities for text pre-generation."""
        while not self._stop_event.is_set():
            try:
                self._try_pregenerate_pending()
            except Exception as e:
                logger.error(f"[WatchDog] Pregenerate loop error: {e}")
            self._stop_event.wait(timeout=5)

    def _try_pregenerate_pending(self):
        """Silently pre-generates text if the LLM is idle and a task is due soon."""
        llm_free_event = getattr(self.jarvis, '_llm_free_event', None)
        if llm_free_event and not llm_free_event.is_set():
            return  # LLM is currently busy, skip pre-generation

        current_time = time.time()
        ram_tasks = list(getattr(self.jarvis.memory, 'ram_upcoming_tasks', []))

        for task in ram_tasks:
            task_id  = task.get('id')
            due_date = task.get('due_date')
            status   = task.get('status')
            title    = task.get('title')

            if not due_date or status != 'created':
                continue
            if task_id in self._pregenerated_reminders:
                continue  # Already pre-generated

            due_ts = self._parse_due_date(due_date)
            if due_ts is None:
                continue

            time_until_due = due_ts - current_time

            if 0 < time_until_due <= self.PREGENERATE_WINDOW_SEC:
                logger.info(
                    f"[WatchDog] 🎯 Golden opportunity! Pre-generating for "
                    f"Task #{task_id} (due in {time_until_due:.0f}s)"
                )
                text = self.jarvis.pregenerate_text(
                    f"Generate a natural polite one-sentence reminder "
                    f"that the task '{title}' is due very soon."
                )
                if text:
                    self._pregenerated_reminders[task_id] = text
                    logger.info(f"[WatchDog] ✅ Pre-generated: '{text}'")

                # Process one task per scan to avoid overloading the LLM
                break  

    # ------------------------------------------------------------------
    # Core Evaluation Logic
    # ------------------------------------------------------------------

    def _check_due_tasks(self):
        """
        Checks all RAM tasks and triggers reminders for any that are due.
        """
        # 1. Ensure JARVIS is not currently interacting or listening
        if getattr(self.jarvis.ears, 'is_actively_listening', False) or \
           getattr(self.jarvis, '_is_currently_speaking_tool_intro', False):
            return

        current_time = time.time()
        last_speech = getattr(self.jarvis, 'last_speech_time', 0.0)

        # 2. Check follow-up window to avoid interrupting the user
        try:
            from core.config import config
            window_limit = config.get('followup_window') if hasattr(config, 'get') else 10
            if window_limit is None:
                window_limit = 10
        except Exception:
            window_limit = 10

        if (current_time - last_speech) <= window_limit:
            return

        # 3. Retrieve tasks from RAM
        ram_tasks = list(getattr(self.jarvis.memory, 'ram_upcoming_tasks', []))

        # DEBUG: Print RAM state only in dev_mode
        if ram_tasks and get_setting('dev_mode', False):
            print(f"\n[WatchDog] 🔍 Monitoring {len(ram_tasks)} task(s) in RAM:")
            for t in ram_tasks:
                print(
                    f"   - Task #{t.get('id')}: '{t.get('title')}' "
                    f"| Due: {t.get('due_date')} "
                    f"| Status: {t.get('status')}"
                )

        for task in ram_tasks:
            self._process_task(task, current_time)

    def _process_task(self, task: dict, current_time: float):
        """Evaluates a single task and fires a reminder if it is due."""
        task_id  = task.get('id')
        due_date = task.get('due_date')
        status   = task.get('status')
        title    = task.get('title')

        if not due_date or status != 'created':
            return

        due_timestamp = self._parse_due_date(due_date)
        if due_timestamp is None:
            logger.warning(f"[WatchDog] Could not parse due_date for Task #{task_id}: {due_date!r}")
            print(f"[WatchDog] Could not parse due_date for Task #{task_id}: {due_date!r}")
            return

        if current_time < due_timestamp:
            return

        # Check if the task is currently snoozed
        next_reminder = self._snooze_dict.get(task_id, 0)
        if current_time < next_reminder:
            return

        self._fire_reminder(task_id, title, current_time)

    @staticmethod
    def _parse_due_date(due_date) -> float | None:
        """
        Converts a due_date value to a Unix timestamp.
        Accepts: ISO string, numeric string, int, or float.
        Returns None if parsing fails.
        """
        if isinstance(due_date, (int, float)):
            return float(due_date)

        if isinstance(due_date, str):
            # Try ISO format first (most common from DB)
            try:
                dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                return dt.timestamp()
            except ValueError:
                pass
            
            # Fallback: raw numeric string (Unix timestamp stored as text)
            try:
                return float(due_date)
            except ValueError:
                pass

        return None

    def _fire_reminder(self, task_id: int, title: str, current_time: float):
        """
        Reminder Execution Priority:
        1. Pre-generated text -> Instant execution
        2. LLM is free -> Generate immediately
        3. LLM is busy -> Wait up to 10s, then generate
        4. Fallback template -> Used if all the above fails
        """
        reminder_msg = self._pregenerated_reminders.pop(task_id, None)

        if reminder_msg:
            print(f"\n⏰ [WatchDog] ⚡ Instant reminder for Task #{task_id}: '{title}'")
            logger.warning(f"[WatchDog] ⚡ Instant reminder for Task #{task_id}: '{title}'")
        else:
            print(f"\n⏰ [WatchDog] Generating reminder for Task #{task_id}: '{title}'")
            logger.warning(f"[WatchDog] Generating reminder for Task #{task_id}: '{title}'")

            # Wait for the LLM to become available (max 10s)
            llm_free_event = getattr(self.jarvis, '_llm_free_event', None)
            if llm_free_event:
                llm_free_event.wait(timeout=10)

            reminder_msg = self.jarvis.pregenerate_text(
                f"Generate a natural polite one-sentence reminder "
                f"that the task '{title}' is now due."
            )

            if not reminder_msg:
                reminder_msg = f"Excuse me sir, a gentle reminder: The task '{title}' is now due."
                logger.warning(f"[WatchDog] ⚠️ Using fallback template for Task #{task_id}")

        # Execute Speech Action
        self.jarvis._is_currently_speaking_tool_intro = True
        try:
            self.jarvis.mouth.speak(reminder_msg)
        except Exception as e:
            logger.error(f"[WatchDog] Speak error for Task #{task_id}: {e}")
        finally:
            self.jarvis._is_currently_speaking_tool_intro = False
            self.jarvis.last_speech_time = time.time()

        # Apply snooze duration
        snooze_seconds = get_setting('task_snooze_minutes', 5) * 60
        self._snooze_dict[task_id] = current_time + snooze_seconds
        self._stop_event.wait(timeout=5)