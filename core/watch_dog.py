# core/watch_dog.py
"""
JARVIS Background WatchDog v1.3 — Redesigned
=============================================
Major architectural changes from prior version:

1. BOOT RECONCILIATION (replaces per-cycle stale guard)
   On startup, memory.reconcile_stale_tasks() bulk-marks all past-due
   'created' tasks as 'missed' in one DB transaction. The WatchDog then
   announces them ONCE at the first Golden Moment and never again.

2. GOLDEN MOMENT GATE (replaces alert-queue + flush architecture)
   Removed: _idle_monitor_loop, _idle_event, _alerts_lock, _pending_alerts,
            _queue_alert, _flush_pending_alerts.
   Replaced with: _is_golden_moment() — a single, clean predicate checked
   every monitor cycle. No queues, no races, no wakeup complexity.
   If the moment isn't right, we simply skip and check again in 15 seconds.

3. CACHED REMINDER TEXT (no repeated LLM calls on snooze)
   _pregenerated_reminders uses .get() not .pop(). Text is generated once
   before due-time and reused across all snooze cycles until the task is
   marked complete, at which point the cache entry is explicitly evicted.
"""

import time
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional
from core.config import get_setting

logger = logging.getLogger(__name__)


class WatchDog:
    """
    Dedicated background daemon responsible for:
    - Boot-time missed-task reconciliation (single-shot, DB-authoritative)
    - Golden Opportunity pre-generation (LLM-free window detection)
    - Task monitoring and IDLE-gated reminder delivery
    - Snooze management (RAM-based, per-session)

    Thread model:
    - _task_monitor_loop    (15s cycle): syncs DB → RAM, checks due tasks
    - _pregenerate_loop     (5s cycle):  generates text before due time
    """

    PREGENERATE_WINDOW_SEC = 90  # Pre-generate if task due within 90s

    def __init__(self, jarvis_core):
        self.jarvis = jarvis_core

        # Core reminder caches (RAM-only, cleared on restart intentionally)
        self._snooze_dict: Dict[int, float] = {}           # {task_id: next_reminder_time}
        self._pregenerated_reminders: Dict[int, str] = {}  # {task_id: text} — persisted across snooze cycles

        # Boot-time missed announcement (generated once, delivered once)
        self._boot_missed_announcement: Optional[str] = None
        self._boot_missed_delivered: bool = False

        self.running = False

        # Thread-safe state lock for _can_speak / _is_golden_moment checks
        self._state_lock = threading.Lock()

        # Event-based shutdown for instant daemon termination
        self._stop_event = threading.Event()

        # Thread references
        self.monitor_thread: Optional[threading.Thread] = None
        self.pregenerate_thread: Optional[threading.Thread] = None

        # Cached state snapshot to suppress duplicate terminal prints
        self._last_jarvis_state = "idle"
        self._last_printed_tasks_hash = None

    # =================================================================
    # Lifecycle Management
    # =================================================================

    def start(self):
        """
        Starts all background monitoring processes.
        Boot reconciliation runs synchronously before threads launch so
        that _boot_missed_announcement is ready before the first monitor cycle.
        """
        self.running = True
        self._stop_event.clear()

        # --- Step 1: Boot reconciliation (sync, runs before threads) ---
        self._reconcile_on_boot()

        # --- Step 2: Task monitor thread (sync + due-check every 15s) ---
        self.monitor_thread = threading.Thread(
            target=self._task_monitor_loop, daemon=True
        )
        self.monitor_thread.start()

        # --- Step 3: Pre-generation thread (5s cycle) ---
        self.pregenerate_thread = threading.Thread(
            target=self._pregenerate_loop, daemon=True
        )
        self.pregenerate_thread.start()

        print(
            "   [WatchDog] v1.3 🐕 Monitor and pregenerate threads active. "
            "Alert-queue replaced by Golden Moment gate."
        )

    def stop(self):
        """Safely stops all monitoring processes."""
        self.running = False
        self._stop_event.set()

    # =================================================================
    # Boot Reconciliation
    # =================================================================

    def _reconcile_on_boot(self):
        """
        Calls memory.reconcile_stale_tasks() to mark all past-due 'created'
        tasks as 'missed' in the DB atomically. If any tasks were missed,
        pre-generates a one-time announcement for the user and stores it in
        _boot_missed_announcement.

        Design decision (backend-architect): reconciliation happens BEFORE
        the monitor thread starts. This guarantees sync_upcoming_tasks()
        will never load stale-from-prior-session tasks into RAM.
        """
        if not getattr(self.jarvis, 'memory', None):
            return

        try:
            missed = self.jarvis.memory.reconcile_stale_tasks()
        except Exception as e:
            logger.error(f"[WatchDog] Boot reconciliation error: {e}", exc_info=True)
            return

        if not missed:
            self._boot_missed_delivered = True  # Nothing to deliver
            return

        # Store on session_missed_tasks for context injection
        if hasattr(self.jarvis.memory, 'session_missed_tasks'):
            for task in missed:
                if not any(t.get('id') == task.get('id')
                           for t in self.jarvis.memory.session_missed_tasks):
                    self.jarvis.memory.session_missed_tasks.append(task)

        # Build a concise task list string for the LLM prompt
        task_descriptions = ', '.join(
            f"'{t['title']}' (was due {datetime.fromtimestamp(t['due_date']).strftime('%H:%M')})"
            for t in missed
            if t.get('due_date')
        )

        prompt = (
            f"The user missed the following task(s) from a previous session: {task_descriptions}. "
            "Inform them briefly and politely — ONE sentence. No XML tags."
        )

        print(f"   [WatchDog] 🗂️ {len(missed)} missed task(s) detected. "
              f"Pre-generating boot announcement...")

        # Pre-generate the announcement (LLM call is safe here — called before
        # threads start, so no concurrency risk on _llm_free_event)
        try:
            text = self.jarvis.pregenerate_text(prompt)
            if text:
                self._boot_missed_announcement = text
                logger.info(f"[WatchDog] Boot missed announcement ready: '{text}'")
            else:
                # Fallback: build a plain announcement without LLM
                titles = ', '.join(f"'{t['title']}'" for t in missed)
                self._boot_missed_announcement = (
                    f"Sir, just so you know, the following tasks were missed "
                    f"from a previous session: {titles}."
                )
        except Exception as e:
            logger.error(f"[WatchDog] Failed to pre-generate boot announcement: {e}")
            titles = ', '.join(f"'{t['title']}'" for t in missed)
            self._boot_missed_announcement = (
                f"Sir, the following task(s) were missed: {titles}."
            )

    # =================================================================
    # Golden Moment Gate
    # =================================================================

    def _can_speak(self) -> bool:
        """
        Hard state check. The WatchDog must NEVER initiate speech unless:
        1. interrupt_state is IDLE
        2. LLM is not processing (_llm_free_event is set)
        3. TTS is not currently busy
        4. Not currently speaking a tool intro

        InterruptState is the single source of truth for system state.
        """
        if not hasattr(self.jarvis, 'state'):
            return False

        state = self.jarvis.state

        try:
            from core.jarvis_engine import InterruptState
        except ImportError:
            interrupt_state = getattr(state, 'interrupt_state', 'idle')
            if interrupt_state not in ('idle', 'follow_up'):
                return False
        else:
            if state.interrupt_state not in (InterruptState.IDLE, InterruptState.FOLLOW_UP):
                return False

        llm_free_event = getattr(self.jarvis, '_llm_free_event', None)
        if llm_free_event and not llm_free_event.is_set():
            return False

        if getattr(self.jarvis, '_is_currently_speaking_tool_intro', False):
            return False

        mouth = getattr(self.jarvis, 'mouth', None)
        if mouth and getattr(mouth, 'is_busy', None) and mouth.is_busy():
            return False

        return True

    def _is_golden_moment(self) -> bool:
        """
        The WatchDog may ONLY initiate speech (reminders, boot announcements)
        when ALL of the following are true:

        1. _can_speak() — system is IDLE, LLM free, TTS free
        2. User is outside the follow-up window (Jarvis just finished speaking
           and we respect the user's natural reply time)
        3. If always_listening is ON: at least 15s since the user's last
           input — we don't interrupt an active conversation

        This replaces the old alert-queue + _flush architecture entirely.
        Simple, race-free: if conditions aren't met, skip and retry next cycle.

        Async note (async-python-patterns): This is a synchronous predicate
        intentionally. The threading model here uses Event-based sleep loops
        rather than asyncio because JARVISCore is built on threading.Thread
        throughout. Mixing asyncio into this layer would require a full engine
        refactor.
        """
        if not self._can_speak():
            return False

        current = time.time()
        last_speech = getattr(self.jarvis, 'last_speech_time', 0.0)
        window = get_setting('followup_window', 15)

        if (current - last_speech) <= window:
            return False

        # In always_listening mode, require 15s of quiet since last user input
        if getattr(self.jarvis.state, 'always_listening', False):
            last_user_input = getattr(self.jarvis, '_last_user_input_time', 0.0)
            if (current - last_user_input) < 15:
                return False

        return True

    # =================================================================
    # Background Workers
    # =================================================================

    def _task_monitor_loop(self):
        """
        Monitors tasks loaded in RAM every 15 seconds.
        Also handles: DB sync, boot-announcement delivery, due-task checking.

        Architecture decision: RAM sync merged into this loop (not a separate
        thread) to eliminate SQLite contention between two concurrent readers.
        """
        while not self._stop_event.is_set():
            try:
                # 1. Sync DB → RAM
                if getattr(self.jarvis, 'memory', None) and hasattr(
                    self.jarvis.memory, 'sync_upcoming_tasks'
                ):
                    self.jarvis.memory.sync_upcoming_tasks()

                # 2. Deliver boot missed announcement at first Golden Moment
                if (
                    self._boot_missed_announcement
                    and not self._boot_missed_delivered
                    and self._is_golden_moment()
                ):
                    self._deliver_boot_announcement()

                # 3. Check due tasks (only attempt speech at Golden Moments)
                self._check_due_tasks()

            except Exception as e:
                logger.error(
                    f"[WatchDog] Task monitor loop error: {e}", exc_info=True
                )

            self._stop_event.wait(timeout=15)

    def _pregenerate_loop(self):
        """Executes every 5 seconds to find pre-generation opportunities."""
        while not self._stop_event.is_set():
            try:
                self._try_pregenerate_pending()
            except Exception as e:
                logger.error(f"[WatchDog] Pregenerate loop error: {e}")
            self._stop_event.wait(timeout=5)

    def _try_pregenerate_pending(self):
        """
        Silently pre-generates reminder text when LLM is idle and a task
        is due within PREGENERATE_WINDOW_SEC.

        Caching contract: text is stored with .get() semantics — it persists
        across snooze cycles and is only cleared on task completion or eviction.
        One task per scan to avoid overloading the LLM.
        """
        llm_free_event = getattr(self.jarvis, '_llm_free_event', None)
        if llm_free_event and not llm_free_event.is_set():
            return

        current_time = time.time()
        ram_tasks = list(getattr(self.jarvis.memory, 'ram_upcoming_tasks', []))

        for task in ram_tasks:
            task_id = task.get('id')
            due_date = task.get('due_date')
            status = task.get('status')
            title = task.get('title')

            if not due_date or status != 'created':
                continue
            if task_id in self._pregenerated_reminders:
                continue  # Already cached — do not regenerate

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
                    f"The user's task '{title}' is now due. "
                    f"Remind them politely. Start with 'Excuse me sir' — ONE sentence, no XML tags."
                )
                if text:
                    self._pregenerated_reminders[task_id] = text
                    logger.info(f"[WatchDog] ✅ Pre-generated for Task #{task_id}: '{text}'")

                break  # One task per scan

    # =================================================================
    # Boot Announcement Delivery
    # =================================================================

    def _deliver_boot_announcement(self):
        """
        Delivers the missed-tasks boot announcement exactly once.
        Called from _task_monitor_loop when _is_golden_moment() is True.
        """
        announcement = self._boot_missed_announcement
        self._boot_missed_delivered = True  # Mark as done before speaking to prevent re-entry
        self._boot_missed_announcement = None

        print(f"\n📋 [WatchDog] Delivering missed-tasks announcement...")
        logger.info("[WatchDog] Delivering boot missed-tasks announcement.")

        self.jarvis._is_currently_speaking_tool_intro = True
        try:
            self.jarvis.mouth.speak(announcement)
        except Exception as e:
            logger.error(f"[WatchDog] Boot announcement speak error: {e}")
        finally:
            self.jarvis._is_currently_speaking_tool_intro = False
            self.jarvis.last_speech_time = time.time()

    # =================================================================
    # Core Evaluation Logic
    # =================================================================

    def _check_due_tasks(self):
        """
        Iterates over RAM tasks and fires reminders for any that are due.
        Only _is_golden_moment() tasks are processed — the rest are skipped
        silently and re-evaluated on the next 15s cycle.
        """
        current_time = time.time()
        ram_tasks = list(getattr(self.jarvis.memory, 'ram_upcoming_tasks', []))

        # DEBUG: Print RAM state only in dev_mode and only when it changes
        if get_setting('dev_mode', False):
            if ram_tasks:
                current_tasks_repr = str([
                    (t.get('id'), t.get('due_date'), t.get('status'))
                    for t in ram_tasks
                ])
                if current_tasks_repr != self._last_printed_tasks_hash:
                    self._last_printed_tasks_hash = current_tasks_repr
                    print(f"\n[WatchDog] 🔍 Monitoring {len(ram_tasks)} task(s) in RAM:")
                    for t in ram_tasks:
                        print(
                            f"   - Task #{t.get('id')}: '{t.get('title')}' "
                            f"| Due: {t.get('due_date')} "
                            f"| Status: {t.get('status')}"
                        )
            else:
                self._last_printed_tasks_hash = None

        for task in ram_tasks:
            self._process_task(task, current_time)

    def _process_task(self, task: dict, current_time: float):
        """
        Evaluates a single task and fires a reminder if ALL of:
        - Task is 'created'
        - Task is past-due
        - Task is not in snooze window
        - This is a Golden Moment

        Stale-task guard removed: boot reconciliation handles that.
        Alert-queue removed: Golden Moment gate handles timing.
        """
        task_id = task.get('id')
        due_date = task.get('due_date')
        status = task.get('status')
        title = task.get('title')

        if not due_date or status != 'created':
            return

        due_timestamp = self._parse_due_date(due_date)
        if due_timestamp is None:
            logger.warning(
                f"[WatchDog] Could not parse due_date for Task #{task_id}: {due_date!r}"
            )
            return

        # Task not yet due
        if current_time < due_timestamp:
            return

        # Task is in active snooze window
        next_reminder = self._snooze_dict.get(task_id, 0)
        if current_time < next_reminder:
            return

        # Only fire at a Golden Moment — otherwise skip silently
        with self._state_lock:
            golden = self._is_golden_moment()

        if not golden:
            return

        self._fire_reminder(task_id, title, current_time)

    # =================================================================
    # DateTime Parsing (Robust Multi-Format)
    # =================================================================

    @staticmethod
    def _parse_due_date(due_date) -> float | None:
        """
        Converts a due_date value to a Unix timestamp.
        Accepts: ISO string, numeric string, int, float, or common date formats.
        Returns None if parsing fails.
        """
        if isinstance(due_date, (int, float)):
            ts = float(due_date)
            if 946684800 < ts < 4102444800:  # 2000–2099 sanity range
                return ts
            return None

        if isinstance(due_date, str):
            due_date = due_date.strip()

            try:
                dt = datetime.fromisoformat(due_date.replace('Z', '+00:00'))
                return dt.timestamp()
            except ValueError:
                pass

            for tz_replace in ('+00:00', 'Z', '+0000'):
                try:
                    dt = datetime.strptime(due_date, f"%Y-%m-%dT%H:%M:%S{tz_replace}")
                    return dt.timestamp()
                except ValueError:
                    continue

            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(due_date, fmt)
                    return dt.timestamp()
                except ValueError:
                    continue

            for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
                try:
                    dt = datetime.strptime(due_date, fmt)
                    return dt.timestamp()
                except ValueError:
                    continue

            try:
                ts = float(due_date)
                if 946684800 < ts < 4102444800:
                    return ts
            except ValueError:
                pass

        return None

    # =================================================================
    # Reminder Execution
    # =================================================================

    def _fire_reminder(self, task_id: int, title: str, current_time: float):
        """
        Delivers the reminder for a due task.

        Priority chain:
        1. Cached pre-generated text → instant delivery (no LLM call)
        2. LLM is free → generate now
        3. Fallback template → used if LLM is unavailable

        Caching contract: _pregenerated_reminders.get() — text is NOT consumed.
        It persists until the task is completed and evict_task_cache() is called.
        This guarantees zero extra LLM calls on each snooze repeat.

        Final state check: re-validates Golden Moment inside the lock before
        speaking to guard against state changes between the outer check and here.
        """
        # Final safety check inside lock
        with self._state_lock:
            if not self._is_golden_moment():
                return

        # Retrieve cached text (non-destructive get)
        reminder_msg = self._pregenerated_reminders.get(task_id)

        if reminder_msg:
            print(f"\n⏰ [WatchDog] ⚡ Instant reminder for Task #{task_id}: '{title}'")
            logger.warning(f"[WatchDog] ⚡ Instant reminder (cached) for Task #{task_id}: '{title}'")
        else:
            print(f"\n⏰ [WatchDog] Generating reminder for Task #{task_id}: '{title}'")
            logger.warning(f"[WatchDog] Generating reminder for Task #{task_id}: '{title}'")

            # Wait for LLM to become available (max 10s)
            llm_free_event = getattr(self.jarvis, '_llm_free_event', None)
            if llm_free_event:
                llm_free_event.wait(timeout=10)

            # Re-check Golden Moment after waiting for LLM
            with self._state_lock:
                if not self._is_golden_moment():
                    logger.info(
                        f"[WatchDog] State changed while waiting for LLM. "
                        f"Skipping Task #{task_id} — will retry next cycle."
                    )
                    return

            reminder_msg = self.jarvis.pregenerate_text(
                f"The user's task '{title}' is now due. "
                f"Remind them politely. Start with 'Excuse me sir' — ONE sentence, no XML tags."
            )

            # Post-generation state re-check
            with self._state_lock:
                if not self._is_golden_moment():
                    logger.info(
                        f"[WatchDog] State changed during LLM generation. "
                        f"Skipping Task #{task_id} — will retry next cycle."
                    )
                    return

            if reminder_msg:
                # Cache for future snooze cycles
                self._pregenerated_reminders[task_id] = reminder_msg
            else:
                reminder_msg = (
                    f"Excuse me sir, a gentle reminder: the task '{title}' is now due."
                )
                logger.warning(f"[WatchDog] ⚠️ Using fallback template for Task #{task_id}")

        # Execute speech — state was validated above
        self.jarvis._is_currently_speaking_tool_intro = True
        try:
            self.jarvis.mouth.speak(reminder_msg)
        except Exception as e:
            logger.error(f"[WatchDog] Speak error for Task #{task_id}: {e}")
        finally:
            self.jarvis._is_currently_speaking_tool_intro = False
            self.jarvis.last_speech_time = time.time()

        # Apply snooze (use time.time() here, not current_time, to get the
        # actual post-speak timestamp and avoid drift across long LLM waits)
        snooze_seconds = get_setting('task_snooze_minutes', 5) * 60
        self._snooze_dict[task_id] = time.time() + snooze_seconds
        logger.info(
            f"[WatchDog] Task #{task_id} snoozed for {snooze_seconds // 60}m."
        )

        # Brief pause to prevent back-to-back firing if multiple tasks are due
        self._stop_event.wait(timeout=3)

    # =================================================================
    # Cache Eviction (called externally when task is completed)
    # =================================================================

    def evict_task_cache(self, task_id: int):
        """
        Clears all in-memory state for a task that has been completed or
        cancelled. Called by the task-completion tool handler so the WatchDog
        stops tracking this task immediately without waiting for the next
        sync_upcoming_tasks() cycle.
        """
        self._pregenerated_reminders.pop(task_id, None)
        self._snooze_dict.pop(task_id, None)
        logger.info(f"[WatchDog] Cache evicted for Task #{task_id}.")
        print(f"   [WatchDog] 🗑️ Cache evicted for Task #{task_id}.")
