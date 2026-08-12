# core/tools/registry.py
"""
JARVIS Tool Registry System
===========================

Manages the registration, retrieval, and execution of internal tools.
Provides fuzzy matching to recover from LLM hallucinations when calling tools.
"""

import json
import logging
from typing import Callable, Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

try:
    from thefuzz import process
except ImportError:
    logging.warning("thefuzz missing. Tool auto-correction will be disabled.")
    process = None

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    """Data structure representing a registered system tool. Optimized with dataclass."""
    name: str
    func: Callable
    schema: dict = field(default_factory=dict)
    minified_schema: dict = field(default_factory=dict)
    aliases: List[str] = field(default_factory=list)
    summary: str = ""
    announcement: str = ""
    is_free: bool = False
    is_silent: bool = False

    def __post_init__(self):
        self.name = self.name.lower()
        self.aliases = [alias.lower() for alias in self.aliases]


class ToolRegistry:
    """Central hub for managing tool schemas and execution routing."""
    
    def __init__(self):
        # Primary storage: dict for name→tool lookup
        self._tools: Dict[str, ToolSpec] = {}
        # List of unique specs for things like render_help
        self._registered_specs: List[ToolSpec] = []
        
        # Pre-built schema lists, invalidated on register/unregister
        self._schema_cache: Optional[List[dict]] = None
        self._minified_cache: Optional[List[dict]] = None
        
        # Function dispatch map for execution routing
        self._func_map: Dict[str, Callable] = {}

    def register(self, name: str, summary: str, func: Callable, schema: dict, aliases: Optional[List[str]] = None, announcement: str = "", is_free: bool = False, is_silent: bool = False):
        """Registers a new tool and maps its aliases."""
        if aliases is None:
            aliases = []
            
        minified = self._minify_schema(schema)
            
        spec = ToolSpec(
            name=name,
            func=func,
            schema=schema,
            minified_schema=minified,
            aliases=aliases,
            summary=summary,
            announcement=announcement,
            is_free=is_free,
            is_silent=is_silent
        )
        self._registered_specs.append(spec)
        
        # Map primary name and all aliases to the same ToolSpec instance
        self._tools[spec.name] = spec
        self._func_map[spec.name] = func
        
        for alias in spec.aliases:
            self._tools[alias] = spec
            self._func_map[alias] = func
            
        self._invalidate_caches()
        logger.debug(f"Registered Tool: {spec.name} (Aliases: {spec.aliases}, free={is_free}, silent={is_silent})")

    def unregister(self, name: str):
        """Remove a tool from the registry."""
        name = name.lower()
        if name in self._tools:
            spec = self._tools[name]
            
            # Remove main name
            if spec.name in self._tools:
                del self._tools[spec.name]
            if spec.name in self._func_map:
                del self._func_map[spec.name]
                
            # Remove aliases
            for alias in spec.aliases:
                if alias in self._tools:
                    del self._tools[alias]
                if alias in self._func_map:
                    del self._func_map[alias]
                    
            if spec in self._registered_specs:
                self._registered_specs.remove(spec)
                
            self._invalidate_caches()

    def _invalidate_caches(self):
        """Clear cached schema lists. Called on any registry mutation."""
        self._schema_cache = None
        self._minified_cache = None

    @staticmethod
    def _minify_schema(schema: dict) -> dict:
        """
        Concise schema for Qwen3-4B's tight context window.
        Trims long descriptions down to their load-bearing sentences instead of
        an all-or-nothing keyword gate. The old version dropped the ENTIRE
        description unless it contained the literal substring "CRITICAL" or
        "Required" (case-sensitive — "REQUIRED" never matched), and it never
        touched the top-level function description at all.
        """
        import copy
        minified = copy.deepcopy(schema)

        MARKERS = ("CRITICAL", "REQUIRED", "NEVER", "ALWAYS", "FORMAT",
                   "MUST", "ONLY", "IMMEDIATELY", "IMPORTANT", "DO NOT")
        KEEP_IF_SHORTER_THAN = 90  # cheap to keep whole, not worth the surgery

        def trim(desc: str) -> str:
            if not desc or len(desc) <= KEEP_IF_SHORTER_THAN:
                return desc
            safe = desc.replace("e.g.,", "e_g_").replace("e.g.", "e_g_")
            sentences = [s.strip() for s in safe.split(". ") if s.strip()]
            kept = []
            for i, s in enumerate(sentences):
                s = s.replace("e_g_", "e.g.")
                upper = s.upper()
                if i == 0 or any(m in upper for m in MARKERS):
                    kept.append(s)
            result = ". ".join(kept)
            if result and not result.endswith((".", "!", "?")):
                result += "."
            return result or desc[:KEEP_IF_SHORTER_THAN]

        try:
            func_def = minified.get("function", {})

            # NEW: top-level description was the biggest untouched leak — now trimmed too
            func_def["description"] = trim(func_def.get("description", ""))

            params = func_def.get("parameters", {})
            props = params.get("properties", {})

            for prop_name, prop_def in list(props.items()):
                if not isinstance(prop_def, dict):
                    continue

                desc = trim(prop_def.get("description", ""))
                if desc:
                    prop_def["description"] = desc
                elif "description" in prop_def:
                    del prop_def["description"]

                nested_props = prop_def.get("properties", {})
                for nested_name, nested_def in list(nested_props.items()):
                    if isinstance(nested_def, dict):
                        nd = trim(nested_def.get("description", ""))
                        if nd:
                            nested_def["description"] = nd
                        elif "description" in nested_def:
                            del nested_def["description"]

                items = prop_def.get("items", {})
                if isinstance(items, dict):
                    item_props = items.get("properties", {})
                    for item_name, item_def in list(item_props.items()):
                        if isinstance(item_def, dict):
                            idesc = trim(item_def.get("description", ""))
                            if idesc:
                                item_def["description"] = idesc
                            elif "description" in item_def:
                                del item_def["description"]

            if "required" not in params and props:
                params["required"] = list(props.keys())

        except Exception as e:
            logger.warning(f"[Registry] Schema minification failed: {e}. Using full schema.")
            return schema

        return minified

    def get_tool(self, name: str) -> Optional[ToolSpec]:
        """Retrieves a ToolSpec by its primary name or alias."""
        return self._tools.get(name.lower().strip())

    def has_tool(self, name: str) -> bool:
        """O(1) existence check."""
        return name.lower().strip() in self._tools

    @property
    def tool_names(self) -> List[str]:
        """Returns keys view."""
        return list(self._tools.keys())

    def get_all_schemas(self) -> List[dict]:
        """Retrieves all FULL JSON Schemas."""
        if self._schema_cache is None:
            self._schema_cache = [spec.schema for spec in self._registered_specs]
        return self._schema_cache

    def get_all_minified_schemas(self) -> List[dict]:
        """Returns ULTRA-CONCISE schemas for Qwen3-4B context window."""
        if self._minified_cache is None:
            self._minified_cache = [spec.minified_schema for spec in self._registered_specs]
        return self._minified_cache

    def is_free_tool(self, name: str) -> bool:
        spec = self.get_tool(name)
        return spec.is_free if spec else False

    def is_silent_tool(self, name: str) -> bool:
        spec = self.get_tool(name)
        return spec.is_silent if spec else False

    def suggest_closest_tool(self, missing_name: str, limit: int = 2, threshold: int = 75) -> List[str]:
        """Uses fuzzy matching to suggest alternative tools if the LLM hallucinates a name."""
        if not process or not missing_name:
            return []
            
        candidates = list(self._tools.keys())
        suggestions = process.extract(missing_name.lower(), candidates, limit=limit)
        return [cand for cand, score in suggestions if score >= threshold]

    def execute_tool(self, tool_name: str, params: dict) -> Tuple[bool, str]:
        """Executes a requested tool and handles hallucination recovery."""
        func = self._func_map.get(tool_name.lower().strip())
        
        if func:
            try:
                # Validate arguments are a dict 
                if not isinstance(params, dict):
                    if isinstance(params, str):
                        try:
                            params = json.loads(params)
                        except json.JSONDecodeError:
                            return False, f"Tool '{tool_name}': Invalid arguments format."
                    else:
                        params = {}
                        
                # Notice: passing as a single param to match existing JARVIS tool definitions!
                result_text = func(params)
                
                return True, str(result_text) if result_text is not None else "Done."
            except TypeError as e:
                error_msg = f"Tool '{tool_name}': Argument error — {str(e)}"
                logger.error(f"[Registry] {error_msg}")
                return False, error_msg
            except Exception as e:
                logging.error(f"Error executing {tool_name}: {e}")
                print(f"Error executing {tool_name}: {e}")
                return False, f"Internal Error in tool '{tool_name}': {str(e)}"

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

    def get_schema_stats(self) -> dict:
        """Returns token-saving statistics for the minification engine."""
        total_original = 0
        total_minified = 0
        tool_count = len(self._registered_specs)

        for spec in self._registered_specs:
            orig_json = json.dumps(spec.schema)
            mini_json = json.dumps(spec.minified_schema)
            total_original += len(orig_json)
            total_minified += len(mini_json)

        savings = total_original - total_minified if total_original > 0 else 0
        savings_pct = (savings / total_original * 100) if total_original > 0 else 0

        return {
            "tool_count": tool_count,
            "original_chars": total_original,
            "minified_chars": total_minified,
            "savings_chars": savings,
            "savings_percent": round(savings_pct, 1),
        }