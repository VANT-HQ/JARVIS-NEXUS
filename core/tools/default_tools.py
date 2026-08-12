# core/tools/default_tools.py
"""
JARVIS NEXUS Default Tools Registry
===================================

Defines the core functional tools available to the LLM. 
Manages tool definitions, automatic permission handling, OS action routing,
and intelligent state tracking.
"""

import json
import time
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List
import core.tools.os_actions as os_actions



# ------------------------------------------------------------------
# Pure Helper Functions (Decoupled from Engine)
# ------------------------------------------------------------------

def _format_memory_search(memory_manager, query: str) -> str:
    """Helper to format memory search results explicitly for the LLM."""
    results = memory_manager.recall_memory(query=query, limit=3)
    if not results:
        return f"No personal memories found for '{query}' in memory. INSTRUCTION: Use search_web tool instead before answering."
    formatted = [f"- {r.get('full_content', r.get('summary', ''))}" for r in results]
    return "Found in personal memory:\n" + "\n".join(formatted) + "\n\nINSTRUCTION: Formulate a natural spoken response to the user based on these memories."

def _format_web_search(browser, query: str, max_results: int) -> str:
    """Helper to format web search results explicitly and handle empty states."""
    response = browser.quick_search(query=query, max_results=max_results)
    if not response or not response.get('success') or not response.get('results'):
        return f"No web search results found for '{query}'. INSTRUCTION: Tell the user you couldn't find up-to-date information on the web, and answer from your general knowledge if possible."
    formatted_results = json.dumps(response, ensure_ascii=False, indent=2)
    return formatted_results + "\n\nINSTRUCTION: Read the raw data above, rephrase it naturally, and give the user a clear, summarized spoken answer."

def _format_os_action(action_func, args: dict, os_type: str) -> str:
    """Helper to inject OS context and format OS action returns."""
    args = {**args, "os_type": os_type}  # MODIFIED: copy instead of mutate — prevents _done_names signature mismatch
    success, msg, data = action_func(args)
    if data:
        return f"{msg}\n\n[DATA]\n{data}"
    return msg

def _extract_friendly_path(raw_arg: str, is_dir: bool = False) -> str:
    """
    Converts the LLM's raw path argument to a workspace-relative string.
    Operates strictly on the string level without executing filesystem calls.
    
    Examples:
        'desktop'               (dir)  -> 'desktop/'
        'desktop/test.txt'      (file) -> 'desktop/'
        'desktop/Projects/a.py' (file) -> 'desktop/Projects/'
        'notes.txt'             (file) -> 'shared_area/'
        'Projects/notes.txt'    (file) -> 'shared_area/Projects/'
    """
    if not raw_arg:
        return ""

    p = raw_arg.strip().replace("\\", "/")
    parts = [x for x in p.split("/") if x]
    if not parts:
        return "shared_area/"

    is_desktop = parts[0].lower() in ("desktop", "mydesktop", "userdesktop")

    if is_dir:
        sub = "/".join(parts[1:] if is_desktop else parts)
        base = "desktop" if is_desktop else "shared_area"
        return f"{base}/{sub}/" if sub else f"{base}/"
    else:
        # File: return parent directory
        parent = parts[1:-1] if is_desktop else parts[:-1]
        base = "desktop" if is_desktop else "shared_area"
        return f"{base}/{'/'.join(parent)}/" if parent else f"{base}/"


# =====================================================================
# Unified Permission Groups
# =====================================================================
# Tools that share a logical security domain. Granting permission for
# ANY member auto-escalates to the entire group.

PERMISSION_GROUPS = {
    'file_access':      ['mutate_filesystem'],
    'process_control':  ['manage_desktop_apps', 'deactivate_core'],
    'system_power':     ['system_power']
}

SILENT_TOOLS = [
    'youtube_action',
    'adjust_hardware', 'open_browser_visuals', 'manage_desktop_apps'
]

# Read-only tools that do not consume iterations when executed alone
FREE_TOOLS = {
    'list_directory', 'read_file', 'search_memory',
    'search_web', 'system_status',
}

# Reverse lookup: tool_name -> group_name
_TOOL_TO_GROUP = {}
for _group, _members in PERMISSION_GROUPS.items():
    for _tool in _members:
        _TOOL_TO_GROUP[_tool] = _group

def _is_allowed(state, tool_name: str, args: dict = None) -> bool:
    """
    Smart permission check driven strictly by PERMISSION_GROUPS.
    1. If root_mode is active -> Allowed.
    2. If the tool is NOT in PERMISSION_GROUPS -> Allowed automatically (No prompt).
    3. If protected -> checks if user granted explicit permission.
    """
    if args is None:
        args = {}

    if state.root_mode:
        return True
        
    # Dynamic Action Check for consolidated tools
    if tool_name == 'manage_desktop_apps' and args.get('action') != 'kill':
        return True
        


    # Dynamic Check: If not protected by our list, execute freely
    if tool_name not in _TOOL_TO_GROUP and tool_name not in PERMISSION_GROUPS:
        return True
        
    # Check explicit tool permission
    if tool_name in state.active_permissions:
        return True
        
    # Check group permission
    group = _TOOL_TO_GROUP.get(tool_name)
    if group and group in state.active_permissions:
        return True
        
    return False

def _handle_grant_permission(args, jarvis_instance):
    """
    Grants permission and automatically escalates to the tool's
    permission group (if any). Also auto-resumes any pending/blocked tool.
    """
    tool_name = args.get('tool_name', '')
    minutes = args.get('minutes', 10)
    
    # 1. Grant the permission (direct)
    jarvis_instance.state.grant_permission(tool_name, minutes)
    msg = f"Permission for '{tool_name}' granted."

    # 2. Auto-escalate to group siblings
    group = _TOOL_TO_GROUP.get(tool_name)
    if group:
        jarvis_instance.state.grant_permission(group, minutes)
        siblings = [t for t in PERMISSION_GROUPS[group] if t != tool_name]
        for sibling in siblings:
            jarvis_instance.state.grant_permission(sibling, minutes)
        msg += f" (Group '{group}' activated — also covers: {', '.join(siblings)})"

    # 3. Check for a held/pending tool call waiting for this permission
    pending = getattr(jarvis_instance.state, 'pending_tool_call', None)
    if pending:
        pending_name = pending['name']
        # Match if exact name OR same permission group
        pending_group = _TOOL_TO_GROUP.get(pending_name)
        if pending_name == tool_name or (group and pending_group == group):
            pending_args = pending['args']
            jarvis_instance.state.pending_tool_call = None  # Clear the queue
            
            msg += f"\n\n[AUTO-RESUME] System intercepted the permission and automatically executed the previously blocked '{pending_name}' action.\n"
            
            # 4. Re-execute the tool now that permission is active
            res = jarvis_instance.execute_tool(pending_name, pending_args)
            msg += f"Result:\n{res}"

    return msg


#? (Hmody: dont follow MCP trend, its not healthy for poor LLMs! ) 
# =====================================================================
# Tools Registration
# =====================================================================

def register_all_tools(jarvis_instance):
    """
    Injects all default tools into the provided JARVIS instance safely.
    All lambda functions now use .get() to prevent KeyError if the LLM hallucinated parameters.
    Permissions are handled automatically via Backend injection.
    """
    
    registry = jarvis_instance.tool_registry
    state = jarvis_instance.state
    internal_cmds = jarvis_instance.internal_commands

    def _with_path_tracking(result: str, raw_path: str, is_dir: bool = False) -> str:
        """Silently updates state.last_file_path after any successful file operation."""
        if raw_path and not any(x in str(result) for x in ("Security Block", "Error:", "Failed")):
            tracked = _extract_friendly_path(raw_path, is_dir)
            if tracked:
                state.last_file_path = tracked
        return result

    def _handle_manage_tasks(args, memory_mgr):
        action = args.get('action', '').lower()
        if not action:
            return "Error: Action is required."

        if action == "list":
            tasks = memory_mgr.get_tasks(status="created")
            return json.dumps(tasks, indent=2)

        elif action == "create":
            title = args.get("title")
            if not title:
                return "Failed: Title is required."
            
            time_expression = args.get("time_expression", "")
            priority = args.get("priority", 2)
            
            absolute_date = None
            absolute_time = None
            time_type = "none"
            
            if time_expression:
                try:
                    import dateparser
                    parsed_date = dateparser.parse(time_expression, settings={'PREFER_DATES_FROM': 'future'})
                    if parsed_date:
                        absolute_date = parsed_date.strftime("%Y-%m-%d")
                        absolute_time = parsed_date.strftime("%H:%M")
                        time_type = "absolute"
                except Exception as e:
                    print(f"Failed to parse time expression '{time_expression}': {e}")

            task_id = memory_mgr.create_task(
                title=title,
                priority=priority,
                time_type=time_type,
                delay_minutes=0,
                delay_hours=0,
                delay_days=0,
                absolute_date=absolute_date,
                absolute_time=absolute_time
            )
            
            if task_id != -1:
                memory_mgr.sync_upcoming_tasks()
                return f"Task created successfully with ID #{task_id}."
            return "Error: Failed to save task to database."

        elif action in ["complete", "delete"]:
            task_id = args.get('task_id')
            if not task_id:
                return "Failed: task_id is required."

            task_id_int = int(task_id)
            success = memory_mgr.modify_task(
                task_id_int,
                new_status="completed" if action == "complete" else "stopped"
            )

            if success:
                # Evict WatchDog cache immediately so it stops tracking this task
                # without waiting for the next sync_upcoming_tasks() cycle.
                watch_dog = getattr(jarvis_instance, 'watch_dog', None)
                if watch_dog and hasattr(watch_dog, 'evict_task_cache'):
                    watch_dog.evict_task_cache(task_id_int)
                return "Success"
            return "Failed."


    # ==========================================
    # --- 1. Memory Tools ---
    # ==========================================
    registry.register(
        name="search_memory",
        aliases=["recall", "find_memory", "get_memory"],
        summary="Search long-term database for facts and past events.",
        announcement="Checking my memory...", 
        is_free=True,
        is_silent=True,
        func=lambda args: _format_memory_search(jarvis_instance.memory, args.get('query', '')),
        schema={
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": "CRITICAL: ALWAYS use this tool BEFORE saying 'I don't know' or asking the user to remind you about personal facts, names, or preferences. Searches your internal database for the user's personal facts, preferences, and past events. NEVER ask the user for information before searching first.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "The specific topic or question (e.g., 'coffee', 'favorite color')."}},
                    "required": ["query"]
                }
            }
        }
    )

    registry.register(
        name="save_to_memory",
        aliases=["remember", "store_knowledge", "note_down", "add_fact"],
        summary="Save an event, thought, preference, or factual knowledge.",
        announcement="Saving that to memory...", 
        is_silent=True,
        func=lambda args: f"Memory stored successfully. ID: {jarvis_instance.memory.save_to_memory(content=args.get('content', ''), category=args.get('category', 'event'))}",
        schema={
            "type": "function",
            "function": {
                "name": "save_to_memory",
                "description": "CRITICAL: Saves the user's personal facts, preferences, and events to your internal database. You MUST call this tool whenever the user shares information about themselves. DO NOT just acknowledge it verbally.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string", 
                            "description": "The full text to save. CRITICAL: You must convert pronouns before saving to avoid confusion. 'I/my' becomes 'The user/The user\\'s'. 'You/your' becomes 'Jarvis/Jarvis\\'s'. Example: 'I love cats' MUST be saved as 'The user loves cats'. 'You are smart' MUST be saved as 'Jarvis is smart'."
                        },
                        "category": {"type": "string", "enum": ["fact", "preference", "event"], "description": "Type of memory to store."}
                    },
                    "required": ["content", "category"]
                }
            }
        }
    )

    # ==========================================
    # --- 2. Web & Research Tools ---
    # ==========================================
    registry.register(
        name="search_web",
        aliases=["google", "browse", "search", "search_site"],
        summary="Search the web for real-time information.",
        announcement="Searching the web...", 
        is_free=True,
        is_silent=True,
        func=lambda args: _format_web_search(
            jarvis_instance.browser, 
            args.get('query', ''), 
            args.get('max_results', 3 if jarvis_instance.state.overthinking_mode else 1)
        ),
        schema={
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "CRITICAL: You MUST call this tool whenever the user asks for real-time information, weather, news, current stock prices, or events. Example: weather in Tokyo -> call search_web. DO NOT say you lack access.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query":       {"type": "string"},
                        "max_results": {"type": "integer"}
                    },
                    "required": ["query"]
                }
            }
        }
    )
 
    registry.register(
        name="open_browser_visuals",
        aliases=["open_website", "google_search", "open_google_search", "visit_site"],
        summary="Opens a website or performs a Google image search.",
        announcement="Opening the browser...",
        func=lambda args: _format_os_action(os_actions.open_browser_visuals, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "open_browser_visuals",
                "description": "Opens a specific URL/platform or performs a Google image search for visual results.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["google_image_search", "visit_url"]},
                        "target": {"type": "string", "description": "The search query (for google_image_search) or site name/URL (for visit_url)."}
                    },
                    "required": ["action", "target"]
                }
            }
        }
    )

    registry.register(
        name="youtube_action",
        aliases=["play_youtube", "search_youtube", "play_video", "youtube", "open_youtube"],
        summary="Play a video directly or search for it on YouTube.",
        announcement="Opening YouTube...", 
        func=lambda args: _format_os_action(os_actions.youtube_action, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "youtube_action",
                "description": "CRITICAL: You MUST call this tool whenever the user asks to play music, play a video, play something, or search YouTube. Example: 'play some synthwave music' or 'play a song' -> call youtube_action. DO NOT just respond verbally without calling this tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query":  {"type": "string", "description": "The exact name of the video, song, or topic."},
                        "action": {"type": "string", "enum": ["play", "search"],
                                   "description": "Choose 'play' to instantly start the video. Even if the user's request is vague (e.g. 'trendy music'), ALWAYS default to 'play' unless the user explicitly asks to 'search'."}
                    },
                    "required": ["query", "action"]
                }
            }
        }
    )

    registry.register(
        name="deep_research",
        summary="Perform complex web research and autonomously extract/save facts.",
        announcement="Starting deep research...", 
        is_silent=True,
        func=lambda args: (
            json.dumps(jarvis_instance.browser.deep_research(
                topic=args.get('topic', 'General'), 
                max_sources=args.get('max_sources', 3), 
                save_to_memory=True                                 #? (Hmody: it save every thing for now, will get full support soon)
            ))
            if hasattr(jarvis_instance.browser, 'deep_research')
            else "Deep research module offline."
        ),
        schema={
            "type": "function",
            "function": {
                "name": "deep_research",
                "description": "Conduct deep internet research and extract facts. IMPORTANT: Facts are AUTOMATICALLY saved to the knowledge base internally. Do NOT call 'save_to_memory' after this tool — it would create duplicates. Just provide a verbal summary of findings.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "The main topic to research."}
                    },
                    "required": ["topic"]
                }
            }
        }
    )

    # ==========================================
    # --- 3. Task Management ---
    # ========================================== 
    registry.register(
        name="manage_tasks",
        aliases=["todo", "edit_task", "complete_task", "delete_task", "create_task"],
        summary="List, create, edit, complete, or delete a task.",
        announcement="Updating your tasks...", 
        func=lambda args: _handle_manage_tasks(args, jarvis_instance.memory),
        schema={
            "type": "function",
            "function": {
                "name": "manage_tasks",
                "description": "CRITICAL: You MUST call this tool whenever the user says remind me, set a reminder, set a timer, or create a todo. For completing/deleting, you MUST provide the correct 'task_id' (look for [ID: X] in the TIME-AWARE TASK CONTEXT). DO NOT guess the ID.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "list", "complete", "delete"]},
                        "title": {"type": "string"},
                        "task_id": {"type": "integer", "description": "The EXACT task ID from the [ID: X] block in your system context. REQUIRED for complete/delete actions."},
                        "time_expression": {
                            "type": "string", 
                            "description": "The exact time the user requested (e.g., 'tomorrow at 5pm', 'in 30 minutes', 'next monday'). Leave empty if none."
                        }
                    },
                    "required": ["action"]
                }
            }
        }
    )

    # ==========================================
    # --- 4. OS & File Actions ---
    # ==========================================
    registry.register(
        name="list_directory",
        aliases=["ls", "dir", "show_files"],
        summary="Lists all files and folders in a specific directory.",
        announcement="Listing the directory...", 
        is_free=True,
        func=lambda args: _with_path_tracking(
            _format_os_action(os_actions.list_directory, {**args, "override_permission": _is_allowed(state, 'list_directory')}, state.os_type),
            args.get('dir_path', ''),
            True
        ),
        schema={
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "CRITICAL: Use this to see what files exist in a directory. If the user asked to READ or EDIT a file, you MUST follow up by calling 'read_file' or 'edit_file' with the discovered file path in your NEXT tool call. Do NOT just list and stop.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dir_path": {"type": "string", "description": "CRITICAL: The path to the folder. Use 'desktop' for the user's Desktop. Leave empty for the default Shared Area."}
                    },
                    "required": []
                }
            }
        }
    )
    
    registry.register(
        name="read_file",
        aliases=["read", "cat"],
        summary="Reads the content of a text-based file.",
        announcement="Reading the file...", 
        is_free=True,
        func=lambda args: _with_path_tracking(
            _format_os_action(os_actions.read_file, {
                **{k: v for k, v in args.items() if k != 'override_permission'}, 
                "override_permission": _is_allowed(state, 'read_file')
            }, state.os_type),
            args.get('file_path', ''),
            False
        ),
        schema={
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Reads file content with offset/limit support.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "offset":     {"type": "integer", "default": 0},
                        "limit":      {"type": "integer"}
                    },
                    "required": ["file_path"]
                }
            }
        }
    )

    registry.register(
        name="mutate_filesystem",
        aliases=["write_file", "edit_file", "manage_workspace", "mkdir", "delete", "move"],
        summary="Creates, edits, moves, or deletes files and directories.",
        announcement="Modifying the filesystem...",
        func=lambda args: _with_path_tracking(
            _format_os_action(os_actions.mutate_filesystem, {
                **{k: v for k, v in args.items() if k != 'override_permission'},
                "override_permission": _is_allowed(state, 'mutate_filesystem', args)
            }, state.os_type),
            args.get('path', ''),
            args.get('action') == 'mkdir'
        ),
        schema={
            "type": "function",
            "function": {
                "name": "mutate_filesystem",
                "description": "Modifies the filesystem. Actions: create_file, edit_string, mkdir, move, delete.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create_file", "edit_string", "mkdir", "move", "delete"]},
                        "path": {"type": "string", "description": "Target file or directory path."},
                        "content": {"type": "string", "description": "Used only for create_file."},
                        "old_string": {"type": "string", "description": "Used only for edit_string."},
                        "new_string": {"type": "string", "description": "Used only for edit_string."},
                        "destination_path": {"type": "string", "description": "Used only for move."}
                    },
                    "required": ["action", "path"]
                }
            }
        }
    )

    registry.register(
        name="run_scenario",
        aliases=["run_script", "execute_scenario", "start_scenario", "run"],
        summary="Executes pre-defined automation scripts/scenarios.",
        announcement="Running the scenario...", 
        func=lambda args: _format_os_action(os_actions.run_scenario, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "run_scenario",
                "description": "Executes a custom user-defined automation script or routine. USE THIS ONLY when the user explicitly asks to run a 'scenario', 'routine', or 'script' (e.g., 'morning routine', 'party mode'). DO NOT use this for normal applications.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "scenario_name": {
                            "type": "string", 
                            "description": "The exact name of the scenario without file extensions (e.g., 'party is over')."
                        }
                    },
                    "required": ["scenario_name"]
                }
            }
        }
    )

    registry.register(
        name="manage_desktop_apps",
        aliases=["open_application", "kill_process", "close_window", "screenshot"],
        summary="Manages desktop applications (launch, kill, close window, screenshot).",
        announcement="Managing desktop applications...",
        func=lambda args: _format_os_action(os_actions.manage_desktop_apps, {
            **{k: v for k, v in args.items() if k != 'override_permission'},
            "override_permission": _is_allowed(state, 'manage_desktop_apps', args)
        }, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "manage_desktop_apps",
                "description": "Launches, kills, or manages desktop applications and windows. Use this for opening apps, forcefully closing processes, closing the active window, or taking a screenshot.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["launch", "kill", "close_active_window", "screenshot"]},
                        "target_name": {"type": "string", "description": "The application name (for launch) or process name (for kill). Leave empty for close/screenshot."}
                    },
                    "required": ["action"]
                }
            }
        }
    )

    # ==========================================
    # --- 5. Media & Hardware Control ---
    # ==========================================
    registry.register(
        name="adjust_hardware",
        aliases=[
            "set_volume", "set_brightness", "vol_up", "vol_down", 
            "volume_up", "volume_down", "bright_up", "bright_down", 
            "brightness_up", "brightness_down", "adjust_volume", "adjust_brightness"
        ],
        summary="Adjusts system/JARVIS volume or screen brightness.",
        announcement="Adjusting hardware settings...", 
        func=lambda args: _format_os_action(os_actions.adjust_hardware, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "adjust_hardware",
                "description": "Adjusts system volume, JARVIS volume, or screen brightness.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target": {"type": "string", "enum": ["volume_system", "volume_jarvis", "brightness"], "description": "The hardware to adjust."},
                        "level":  {"type": "integer", "description": "Absolute level 0-100."},
                        "change": {"type": "integer", "description": "Relative change (e.g., +10 or -10)."}
                    },
                    "required": ["target"]
                }
            }
        }
    )

    registry.register(
        name="system_status",
        summary="Retrieves CPU, RAM, and Battery status.",
        announcement="Checking system status...", 
        is_free=True,
        func=lambda args: _format_os_action(os_actions.system_status, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "system_status",
                "description": "Get current hardware metrics.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "execute": {"type": "boolean", "description": "Always set to true."}
                    },
                    "required": []
                }
            }
        }
    )

    # ==========================================
    # --- 6. Power & System Security ---
    # ==========================================
    registry.register(
        name="system_power",
        aliases=["shutdown", "restart", "lock"],
        summary="Control system power state.",
        announcement="Executing power command...", 
        func=lambda args: _format_os_action(os_actions.system_power, {
            **{k: v for k, v in args.items() if k != 'override_permission'}, 
            "override_permission": _is_allowed(state, 'system_power')
        }, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "system_power",
                "description": "Lock the screen, restart, or shutdown the computer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["lock", "restart", "shutdown"]}
                    },
                    "required": ["action"]
                }
            }
        }
    )

    # ==========================================
    # --- 7. System & Internal Tools ---
    # ==========================================
    registry.register(
        name="request_user_input",
        aliases=["ask_user", "popup_input", "get_text"],
        summary="Opens a GUI popup to ask the user to type text explicitly.",
        announcement="Prompting for input...", 
        func=lambda args: _format_os_action(os_actions.request_user_input, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "request_user_input",
                "description": "CRITICAL: Call this tool IMMEDIATELY if the user explicitly asks to 'type' something, 'take my input', or share a 'secret/code' securely. DO NOT just reply conversationally. YOU MUST call this tool so they get a safe text box to type in.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title":       {"type": "string", "description": "Title of the popup window."},
                        "prompt_text": {"type": "string", "description": "The question to ask the user."}
                    },
                    "required": ["prompt_text"]
                }
            }
        }
    )

    registry.register(
        name="grant_temporary_permission",
        summary="Store user permission to bypass security prompts for a specific tool.",
        announcement="Updating permissions...", 
        func=lambda args: _handle_grant_permission(
            {"tool_name": args.get('tool_name'), "minutes": 10}, 
            jarvis_instance
        ), 
        schema={
            "type": "function",
            "function": {
                "name": "grant_temporary_permission",
                "description": "Call this when the user explicitly grants you permission to perform an action. This will auto-resume the blocked action.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string", "description": "The exact name of the tool (e.g., edit_file)"}
                    },
                    "required": ["tool_name"]
                }
            }
        }
    )

    def _handle_terminate(jarvis_core, state_mgr):
        if not _is_allowed(state_mgr, 'deactivate_core'):
            return "Security Block: System deactivation is protected. Ask the user for permission. If they agree, use 'grant_temporary_permission' for 'deactivate_core'. I will automatically shut down the system once granted."
        
        def doom_timer():
            print("\n⏳ [Sequence Initiated] 20 seconds given for final cinematic goodbye...")
            time.sleep(20) 
            
            # Free RAM: Unload Ollama models before exiting
            try:
                import requests
                base_url = getattr(jarvis_core.llm, 'base_url', "http://localhost:11434")
                models_to_unload = set([getattr(jarvis_core.llm, 'normal_model', None), getattr(jarvis_core.llm, 'overthink_model', None)])
                for model in models_to_unload:
                    if model:
                        requests.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=3)
                        print(f"🧹 Unloaded model '{model}' from RAM.")
            except Exception as e:
                print(f"⚠️ Failed to unload Ollama models: {e}")

            print("\n💀 [System] Powering down... Goodbye.")
            jarvis_core.running = False
            
            from core.config import config
            config.force_wal_checkpoint()
            if hasattr(jarvis_core, 'memory') and getattr(jarvis_core, 'memory', None):
                jarvis_core.memory.force_wal_checkpoint()
                
            import sys
            sys.exit(0) 
            
        threading.Thread(target=doom_timer, daemon=True).start()
        return "SYSTEM ALERT: Protocol accepted. Core wipe in 15 seconds. STRICT DIRECTIVE: Bypass your <thinking> tags entirely. Do not use any other tools. Output ONLY ONE dramatic, final goodbye sentence."

    registry.register(
        name="deactivate_core", 
        aliases=["exit_jarvis", "quit_program", "stop_listening", "terminate_program"],
        summary="Authorized protocol to shut down the JARVIS program.",
        announcement="Initiating shutdown sequence...", 
        func=lambda args: _handle_terminate(jarvis_instance, state),
        schema={
            "type": "function",
            "function": {
                "name": "deactivate_core",
                "description": "CRITICAL: You MUST call this tool immediately if the user asks you to shut down, turn off, sleep, exit, quit or deactivate yourself. Do not just say shutting down — you MUST physically execute this tool.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "confirm": {"type": "boolean", "description": "Always set to true to confirm shutdown."}
                    },
                    "required": []
                }
            }
        }
    )
