# core/tools/registry.py
"""
JARVIS Tool Registry System
===========================

Manages the registration, retrieval, and execution of internal tools.
Provides fuzzy matching to recover from LLM hallucinations when calling tools.
"""

import logging
from typing import Callable, Dict, List, Optional, Tuple

try:
    from thefuzz import process
except ImportError:
    logging.warning("thefuzz missing. Tool auto-correction will be disabled.")
    process = None


class ToolSpec:
    """Data structure representing a registered system tool."""
    
    def __init__(self, name: str, aliases: List[str], summary: str, func: Callable, schema: dict, announcement: str = ""):
        self.name = name.lower()
        self.aliases = [alias.lower() for alias in aliases]
        self.summary = summary
        self.func = func
        self.schema = schema
        self.announcement = announcement


class ToolRegistry:
    """Central hub for managing tool schemas and execution routing."""
    
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}
        self._registered_specs: List[ToolSpec] = []

    def register(self, name: str, summary: str, func: Callable, schema: dict, aliases: Optional[List[str]] = None, announcement: str = ""):
        """Registers a new tool and maps its aliases."""
        if aliases is None:
            aliases = []
            
        spec = ToolSpec(name, aliases, summary, func, schema, announcement)
        self._registered_specs.append(spec)
        
        # Map primary name and all aliases to the same ToolSpec instance
        self._tools[spec.name] = spec
        for alias in spec.aliases:
            self._tools[alias] = spec
            
        logging.debug(f"Registered Tool: {spec.name} (Aliases: {spec.aliases})")

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Retrieves a ToolSpec by its primary name or alias."""
        return self._tools.get(name.lower().strip())

    def get_all_schemas(self) -> List[dict]:
        """Retrieves all JSON Schemas to be injected into the LLM payload."""
        return [spec.schema for spec in self._registered_specs]

    def suggest_closest_tool(self, missing_name: str, limit: int = 2, threshold: int = 75) -> List[str]:
        """Uses fuzzy matching to suggest alternative tools if the LLM hallucinates a name."""
        if not process or not missing_name:
            return []
            
        candidates = list(self._tools.keys())
        suggestions = process.extract(missing_name.lower(), candidates, limit=limit)
        return [cand for cand, score in suggestions if score >= threshold]

    def execute_tool(self, tool_name: str, params: dict) -> Tuple[bool, str]:
        """Executes a requested tool and handles hallucination recovery."""
        tool = self.get_tool(tool_name)
        
        if tool:
            try:
                result_text = tool.func(params)
                return True, str(result_text)
            except Exception as e:
                logging.error(f"Error executing {tool.name}: {e}")
                print(f"Error executing {tool.name}: {e}")
                return False, f"Internal Error in tool '{tool.name}': {str(e)}"

        # Auto-correction / Hallucination fallback logic
        suggestions = self.suggest_closest_tool(tool_name)
        if suggestions:
            suggested_str = ", ".join([f"'{s}'" for s in set(suggestions)])
            error_msg = (
                f"Error: Tool '{tool_name}' does not exist. "
                f"Did you mean one of these: {suggested_str}? Please correct your action and try again."
            )
            logging.warning(f"LLM hallucinated tool '{tool_name}'. Suggested: {suggested_str}")
            print(f"LLM hallucinated tool '{tool_name}'. Suggested: {suggested_str}")
            return False, error_msg
            
        return False, f"Error: Tool '{tool_name}' is completely unknown."

    def render_help(self) -> str:
        """Generates a formatted string of all available tools for terminal logging or CLI."""
        lines = ["--- JARVIS AVAILABLE TOOLS ---"]
        for spec in self._registered_specs:
            aliases_str = f" (Aliases: {', '.join(spec.aliases)})" if spec.aliases else ""
            lines.append(f"- {spec.name:<20} {spec.summary}{aliases_str}")
        return "\n".join(lines)