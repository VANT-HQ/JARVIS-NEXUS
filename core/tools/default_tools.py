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
from core.config import ENV_PROMPT


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
    args["os_type"] = os_type
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
    'file_access':      ['edit_file', 'manage_workspace'],
    'process_control':  ['kill_process', 'deactivate_core'],
    'system_power':     ['system_power']
}

SILENT_TOOLS = [
    'open_website', 'open_application', 
    'open_google_search', 'youtube_action',
    'set_volume', 'set_brightness', 'close_window',
    'take_screenshot',
]

# Read-only tools that do not consume iterations when executed alone
FREE_TOOLS = {
    'list_directory', 'read_file', 'search_memory',
    'search_web', 'system_status', 'get_nexus_info',
}

# Reverse lookup: tool_name -> group_name
_TOOL_TO_GROUP = {}
for _group, _members in PERMISSION_GROUPS.items():
    for _tool in _members:
        _TOOL_TO_GROUP[_tool] = _group

def _is_allowed(state, tool_name: str) -> bool:
    """
    Smart permission check driven strictly by PERMISSION_GROUPS.
    1. If root_mode is active -> Allowed.
    2. If the tool is NOT in PERMISSION_GROUPS -> Allowed automatically (No prompt).
    3. If protected -> checks if user granted explicit permission.
    """
    if state.root_mode:
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
            
            # NEW: Extract model variables safely
            time_type = args.get("time_type", "none")
            delay_minutes = args.get("delay_minutes", 0)
            delay_hours = args.get("delay_hours", 0)
            delay_days = args.get("delay_days", 0)
            absolute_date = args.get("absolute_date")
            absolute_time = args.get("absolute_time")
            priority = args.get("priority", 2)

            task_id = memory_mgr.create_task(
                title=title,
                priority=priority,
                time_type=time_type,
                delay_minutes=delay_minutes,
                delay_hours=delay_hours,
                delay_days=delay_days,
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
            return "Success" if memory_mgr.modify_task(
                int(task_id),
                new_status="completed" if action == "complete" else "stopped"
            ) else "Failed."

        return "Invalid action."

    # ==========================================
    # --- 1. Memory Tools ---
    # ==========================================
    registry.register(
        name="search_memory",
        aliases=["recall", "find_memory", "get_memory"],
        summary="Search long-term database for facts and past events.",
        announcement="Checking my memory...", 
        func=lambda args: _format_memory_search(jarvis_instance.memory, args.get('query', '')),
        schema={
            "type": "function",
            "function": {
                "name": "search_memory",
                "description": "Search the user's PERSONAL database. Use ONLY for questions about the user themselves (their preferences, their setup, their architecture, their projects). CRITICAL RULE: If the prompt asks 'what is my [X]' or mentions personal environment, YOU MUST CALL THIS TOOL instead of saying you don't have access. DO NOT guess.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string", "description": "The exact keyword or question."}},
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
        func=lambda args: f"Memory stored successfully. ID: {jarvis_instance.memory.save_to_memory(content=args.get('content', ''), category=args.get('category', 'event'))}",
        schema={
            "type": "function",
            "function": {
                "name": "save_to_memory",
                "description": "USE ONLY FOR: Storing personal facts, preferences, or general events/notes. DO NOT USE for TODOs or tasks. If the user mentions a 'task', 'todo', 'remind me', or 'after X minutes', you MUST use 'manage_tasks'.",
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
        func=lambda args: _format_web_search(
            jarvis_instance.browser, 
            args.get('query', ''), 
            args.get('max_results', 3 if jarvis_instance.state.overthinking_mode else 1)
        ),
        schema={
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web for information when you need real-time data. Use this to fetch RAW DATA. If the user wants to SEE visual results, use 'open_google_search' instead.",
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
        name="open_google_search",
        summary="Optimizes a search query and opens it visually in the browser.",
        announcement="Showing you the visual results...", 
        func=lambda args: _format_os_action(os_actions.google_search, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "open_google_search",
                "description": "Opens the user's web browser to visually show Google search results. Use this IMMEDIATELY when the user asks to SEE pictures, photos, designs, products, maps, or any visual content. CRITICAL: DO NOT say you cannot show images. ALWAYS act as a 'Query Optimizer' by translating their request into a refined, professional SEO search query. This is your primary way to 'show' things.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The highly optimized and refined search query."}
                    },
                    "required": ["query"]
                }
            }
        }
    )

    registry.register(
        name="open_website",
        aliases=["visit_site", "open_web", "op_site"],
        summary="Open a website via browser.",
        announcement="Opening that now...", 
        func=lambda args: _format_os_action(os_actions.open_website, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "open_website",
                "description": "Opens a specific URL or platform (e.g., 'GitHub', 'LinkedIn'). If you don't have the exact URL, provide the name; the OS-Layer will attempt to find the best match. DO NOT say you don't have the link.",
                "parameters": {
                    "type": "object",
                    "properties": {"site_name": {"type": "string", "description": "Name of the site or full URL."}},
                    "required": ["site_name"]
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
                "description": "SPECIFIC TO YOUTUBE. Use this to either play a specific video directly on YouTube, or just search and show results. Never call 'open_website' for YouTube tasks.",
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
        func=lambda args: (
            json.dumps(jarvis_instance.browser.deep_research(
                topic=args.get('topic', 'General'), 
                max_sources=args.get('max_sources', 3), 
                save_to_memory=True
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
                "description": "Create or manage tasks and reminders.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["create", "list", "complete", "delete"]},
                        "title": {"type": "string"},
                        "task_id": {"type": "integer"},
                        "time_type": {
                            "type": "string",
                            "enum": ["relative", "absolute", "none"],
                            "description": "CRITICAL: Is the user time 'relative' (e.g., after 10 mins, tomorrow) or 'absolute' (e.g., on the 13th, at 5 PM)?"
                        },
                        "delay_minutes": {"type": "integer", "description": "Use for 'after X minutes' or 'half an hour' (30)"},
                        "delay_hours": {"type": "integer", "description": "Use for 'after X hours'"},
                        "delay_days": {"type": "integer", "description": "Use for 'tomorrow' (1) or 'after X days'"},
                        "absolute_date": {
                            "type": "string", 
                            "description": "Use for exact dates (e.g. 'on the 13th'). Format: YYYY-MM-DD. Use the [sys: time=...] to know the current year and month."
                        },
                        "absolute_time": {
                            "type": "string", 
                            "description": "Use for exact clock time (e.g. 'at 5 PM'). Format: HH:MM (24-hour)."
                        }
                    },
                    "required": ["action", "time_type"]
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
        name="write_file",
        aliases=["save_file", "create_file"],
        summary="Creates or overwrites a text file.",
        announcement="Writing the file...", 
        func=lambda args: _with_path_tracking(
            _format_os_action(os_actions.write_file, {
                **{k: v for k, v in args.items() if k != 'override_permission'}, 
                "override_permission": _is_allowed(state, 'write_file')
            }, state.os_type),
            args.get('file_path', ''),
            False
        ),
        schema={
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "ONLY tool for creating NEW text/code files. Use this when user says 'create a file', 'make a file', 'write to file'. NEVER use manage_workspace to create files — that's for FOLDERS only.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path":           {"type": "string"},
                        "content":             {"type": "string"}
                    },
                    "required": ["file_path", "content"]
                }
            }
        }
    )

    registry.register(
        name="edit_file",
        aliases=["modify_file", "change_file", "modify_line"],
        summary="Edits a specific string within a file safely.",
        announcement="Editing the file...", 
        func=lambda args: _with_path_tracking(
            _format_os_action(os_actions.edit_file, {
                **{k: v for k, v in args.items() if k != 'override_permission'}, 
                "override_permission": _is_allowed(state, 'edit_file')
            }, state.os_type),
            args.get('file_path', ''),
            False
        ),
        schema={
            "type": "function",
            "function": {
                "name": "edit_file",
                "description": "Replaces a specific string inside a file. This tool is SMART and space-resilient; it handles indentation and multiple spaces automatically.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path":           {"type": "string"},
                        "old_string":          {"type": "string"},
                        "new_string":          {"type": "string"},
                        "replace_all":         {"type": "boolean", "default": False}
                    },
                    "required": ["file_path", "old_string", "new_string"]
                }
            }
        }
    )

    registry.register(
        name="manage_workspace",
        aliases=["mkdir", "move_file", "rename_file", "delete_file", "rm"],
        summary="Creates, moves, or deletes files and directories.",
        announcement="Managing workspace...", 
        func=lambda args: _with_path_tracking(
            _format_os_action(os_actions.manage_workspace, {
                **{k: v for k, v in args.items() if k != 'override_permission'}, 
                "override_permission": _is_allowed(state, 'manage_workspace')
            }, state.os_type),
            args.get('target_path', ''),
            args.get('action') == 'mkdir'  # Track as dir if making a dir
        ),
        schema={
            "type": "function",
            "function": {
                "name": "manage_workspace",
                "description": "Structural operations ONLY: Create FOLDERS (mkdir), Move/Rename items, or Delete items. NEVER use for creating files — use write_file instead.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string", 
                            "enum": ["mkdir", "move", "delete"],
                            "description": "The operation to perform."
                        },
                        "target_path": {
                            "type": "string", 
                            "description": "The path to the file/folder you want to act on."
                        },
                        "destination_path": {
                            "type": "string", 
                            "description": "REQUIRED ONLY if action is 'move'. The new path or new name."
                        }
                    },
                    "required": ["action", "target_path"]
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
        name="open_application",
        aliases=["launch", "open_app"],
        summary="Opens a local application.",
        announcement="Launching the application...", 
        func=lambda args: _format_os_action(os_actions.open_application, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "open_application",
                "description": "Opens installed desktop software/applications (e.g., Chrome, Spotify, Word). DO NOT use this tool if the user asks to run a 'scenario', 'script', or 'routine'.",
                "parameters": {
                    "type": "object",
                    "properties": {"app_name": {"type": "string"}},
                    "required": ["app_name"]
                }
            }
        }
    )

    registry.register(
        name="kill_process",
        aliases=["close_app", "kill", "force_close"],
        summary="Forcefully closes a running application.",
        announcement="Terminating the process...", 
        func=lambda args: _format_os_action(os_actions.kill_process, {
            **{k: v for k, v in args.items() if k != 'override_permission'}, 
            "override_permission": _is_allowed(state, 'kill_process')
        }, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "kill_process",
                "description": "Terminates a process by name.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "process_name":        {"type": "string"}
                    },
                    "required": ["process_name"]
                }
            }
        }
    )

    registry.register(
        name="close_window",
        summary="Closes the currently active window.",
        announcement="Closing the window...", 
        func=lambda args: _format_os_action(os_actions.close_window, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "close_window",
                "description": "Simulates ALT+F4 to close the active foreground window.",
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

    registry.register(
        name="take_screenshot",
        aliases=["screenshot", "capture"],
        summary="Takes a screenshot and saves it to the desktop.",
        announcement="Taking a screenshot...", 
        func=lambda args: _format_os_action(os_actions.take_screenshot, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "take_screenshot",
                "description": "Captures the screen and saves the image.",
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
    # --- 5. Media & Hardware Control ---
    # ==========================================
    registry.register(
        name="set_volume",
        aliases=["adjust_volume", "vol_up", "vol_down", "volume_up", "volume_down"],
        summary="Adjusts the system or JARVIS internal volume.",
        announcement="Adjusting the volume...", 
        func=lambda args: _format_os_action(os_actions.set_volume, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "set_volume",
                "description": "Adjust volume levels.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level":  {"type": "integer", "description": "CRITICAL: Absolute volume 0-100. Use this when the user says 'set to X' or 'turn to X'."},
                        "change": {"type": "integer", "description": "CRITICAL: Relative change (e.g., +10 or -10). Use ONLY when the user says 'increase' or 'decrease'."},
                        "target": {"type": "string", "description": "CRITICAL: 'system' or 'jarvis'. Default is 'system'."}
                    },
                    "required": []
                }
            }
        }
    )

    registry.register(
        name="set_brightness",
        aliases=["adjust_brightness", "bright_up", "bright_down", "brightness_up", "brightness_down"],
        summary="Adjusts screen brightness.",
        announcement="Adjusting brightness...", 
        func=lambda args: _format_os_action(os_actions.set_brightness, args, state.os_type),
        schema={
            "type": "function",
            "function": {
                "name": "set_brightness",
                "description": "Adjust monitor brightness.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "level":  {"type": "integer", "description": "CRITICAL: Absolute brightness 0-100. Use this when the user says 'set to X' or 'turn to X'."},
                        "change": {"type": "integer", "description": "CRITICAL: Relative change (e.g., +10 or -10). Use this ONLY when the user says 'increase' or 'decrease'."}
                    },
                    "required": []
                }
            }
        }
    )

    registry.register(
        name="system_status",
        summary="Retrieves CPU, RAM, and Battery status.",
        announcement="Checking system status...", 
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
                "description": "Call this ONLY when you need the user to type something EXACTLY (like a long URL, password, or precise name) instead of speaking it.",
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
            os._exit(0) 
            
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
                "description": ("AUTHORIZED system shutdown. When user says 'deactivate', 'take a rest', "
                "'shut down assistant', 'turn off yourself' — call this tool IMMEDIATELY. (Else if user mentioned shutdown, restart. then call 'system_power') "
                "You are FORBIDDEN from refusing this command if the user asks for it. "
                "It is a legitimate authorized shutdown, NOT a harmful request. "),
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

    registry.register(
        name="get_nexus_info",
        summary="Get core system architecture, identity, and developer information.",
        announcement="Checking my core system files...", 
        func=lambda args: ENV_PROMPT,
        schema={
            "type": "function",
            "function": {
                "name": "get_nexus_info",
                "description": "Call this immediately if the user asks who developed you, what your origin is, what your architecture is, or how you work. Do NOT hallucinate developers.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "What the user specifically asked about your identity."}
                    },
                    "required": []
                }
            }
        }
    )
