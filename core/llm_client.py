# core/llm_client.py
"""
JARVIS LLM Client & Model Manager
=================================

The exclusive communication interface with the Ollama Engine.
Supports: 
- Streaming and Native JSON Tool Calling.
- Auto-restarts and zombie process management.
- Dual-model configuration (Normal vs. Overthink/Fast).
- Smart model discovery (GGUF metadata parsing).
- I/O sanitization and logging.

NOTE: Only Native Tool Calling (Ollama JSON format) is supported.
"""

import os
import re
import json
import time
import threading
import subprocess
import platform
import requests
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# Single Source of Truth for configs and paths
from core.config import config, get_setting, LLM_DIR, LOGS_DIR

# Optional/Dynamic Dependencies Handled Gracefully
try:
    from gguf import GGUFReader
    GGUF_AVAILABLE = True
except ImportError:
    GGUF_AVAILABLE = False

try:
    from core.bootstrap.llm_templates import MODEL_TEMPLATES
except ImportError:
    print("⚠️ Warning: llm_templates.py not found. Will use standard fallback builder.")
    logging.warning("llm_templates.py not found. Will use standard fallback builder.")
    MODEL_TEMPLATES = {}

try:
    from core.bootstrap.template_builder import request_template_from_user
except ImportError:
    print("⚠️ Warning: template_builder.py not found. Template dialog will be unavailable.")
    logging.warning("template_builder.py not found. Template dialog will be unavailable.")
    request_template_from_user = None

try:
    from core.bootstrap.env_setup import safe_run_wizard
except ImportError:
    safe_run_wizard = None


logger = logging.getLogger(__name__)


# =================================================================
# LLM Client (Ollama Engine - Dual Model Support & Auto-Build)
# =================================================================
class LLMClient:

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.normal_model = None
        self.overthink_model = None
        self.supports_native_tools = False
        self._initialize_client()

    # ------------------------------------------------------------------
    # Private: Ollama Lifecycle & Process Management
    # ------------------------------------------------------------------
    def _force_restart_ollama(self):
        """Hunts down zombie Ollama processes and restarts the server cleanly."""
        print("🔪 Forcing Ollama restart (Killing zombie processes)...")
        try:
            if platform.system() == "Windows":
                subprocess.run(
                    "taskkill /F /IM ollama.exe /T",
                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                subprocess.run(
                    "taskkill /F /IM ollama_llama_server.exe /T",
                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            else:
                subprocess.run(
                    ["pkill", "-9", "-f", "ollama"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        except Exception:
            pass

        time.sleep(1)

        try:
            # Start Ollama serve in the background
            if platform.system() == "Windows":
                subprocess.Popen(
                    ['ollama', 'serve'],
                    shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                subprocess.Popen(
                    ['ollama', 'serve'],
                    shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                
            print("⏳ Booting fresh Ollama instance...")
            # OPTIMIZED: Health-check poll — exits as soon as Ollama is ready (Max 10s)
            for attempt in range(20):
                time.sleep(0.5)
                try:
                    requests.get(self.base_url, timeout=1)
                    print(f"   ✅ Ollama ready after {(attempt + 1) * 0.5:.1f}s")
                    break
                except Exception:
                    pass
        except Exception as e:
            print(f"❌ Failed to start Ollama: {e}")
            logger.error(f"Failed to start Ollama: {e}")

    def _initialize_client(self):
        """Checks API health and triggers setup."""
        while True:
            try:
                requests.get(self.base_url, timeout=5)
                print(f"✅ Local LLM server is running at: {self.base_url}")
                break
            except requests.exceptions.ConnectionError:
                print("⚠️ Local LLM API not responding. Executing forced reboot protocol...")
                logger.warning("Local LLM API not responding. Executing forced reboot protocol...")
                self._force_restart_ollama()
                try:
                    requests.get(self.base_url, timeout=5)
                    break
                except requests.exceptions.ConnectionError:
                    print("❌ Ollama server could not be started or is not installed.")
                    logger.error("Ollama server could not be started or is not installed.")
                    if safe_run_wizard:
                        safe_run_wizard()
                    continue
            
        self._ensure_model_exists()

    def _log_raw_io(self, session_id: str, direction: str, data):
        """
        Logs the outgoing payload and incoming stream.
        Smart filtering logic applies to outgoing requests to hide massive
        System Prompts and Tool Schemas to keep the logs clean and readable.
        """
        if not get_setting('dev_mode', False):
            return

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_file = LOGS_DIR / "llm_raw_debug.txt"
        
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        filtered_data = data

        if isinstance(data, dict):
            # Apply filter only if data represents a payload (contains messages or tools)
            if "messages" in data or "tools" in data:
                filtered_data = data.copy()
                if "system" in filtered_data:
                    filtered_data["system"] = "[... SYSTEM PROMPT HIDDEN FOR CLARITY ...]"
                if "tools" in filtered_data:
                    filtered_data["tools"] = f"[... {len(filtered_data['tools'])} TOOLS HIDDEN ...]"

        with open(log_file, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"[{timestamp}] | SESSION: {session_id} | {direction}\n")
            f.write(f"{'-'*60}\n")
            
            if isinstance(filtered_data, (dict, list)):
                f.write(json.dumps(filtered_data, indent=2, ensure_ascii=False))
            else:
                # Raw string output to precisely spot LLM generation errors
                f.write(str(filtered_data))
                
            f.write(f"\n{'='*60}\n")

    def _check_native_tool_support(self, model_name: str):
        """
        Dynamically checks if the model officially supports native tools
        by inspecting its template via the Ollama API.
        If native tools are NOT detected, the model will still run but
        tool calls will not be sent — tools are native-only in this system.
        """
        print(f"🔍 Analyzing tool support for '{model_name}'...")
        try:
            response = requests.post(f"{self.base_url}/api/show", json={"model": model_name}, timeout=5)
            if response.ok:
                template = response.json().get("template", "")
                if "{{ .Tools }}" in template or "{{- if .Tools }}" in template or "tool_calls" in template.lower():
                    self.supports_native_tools = True
                    print(f"✅ LLM supports NATIVE JSON tool calling.")
                else:
                    self.supports_native_tools = False
                    print(f"⚠️ Model template has no native tool support. Tools will NOT be sent.")
                    logger.warning("Model template has no native tool support. Tools will NOT be sent.")
            else:
                print(f"⚠️ Native Tools Support: UNKNOWN (Failed to fetch model info). Assuming no native tools.")
                logger.warning("Native Tools Support: UNKNOWN (Failed to fetch model info). Assuming no native tools.")
                self.supports_native_tools = False
        except Exception as e:
            print(f"⚠️ Native Tools Support: ERROR ({e}). Assuming no native tools.")
            logger.error(f"Native Tools Support: ERROR ({e}). Assuming no native tools.")
            self.supports_native_tools = False

    # =================================================================
    # Quality Parsing Method
    # =================================================================
    def _calculate_model_score(self, file_path: Path) -> float:
        """
        Reads the GGUF Header to extract the parameter count and calculate a quality score
        without loading the model into RAM. (Sub-millisecond operation).
        Formula: (Parameters in millions) + (File size in GB) as a tiebreaker.
        """
        file_size_gb = os.path.getsize(file_path) / (1024**3)
        
        if GGUF_AVAILABLE:
            try:
                reader = GGUFReader(str(file_path))
                param_count = 0
                
                if "general.parameter_count" in reader.fields:
                    raw_val = reader.fields["general.parameter_count"].parts[-1]
                    param_count = getattr(raw_val, "item", lambda: int(raw_val[0] if isinstance(raw_val, (list, tuple)) else raw_val))()

                if param_count > 0:
                    score = (param_count / 1_000_000) + file_size_gb
                    return score
            except Exception as e:
                print(f"⚠️ [Warning] Failed to read GGUF metadata for {file_path.name} ({e}). Using size fallback.")
                logger.warning(f"Failed to read GGUF metadata for {file_path.name} ({e}). Using size fallback.")
        else:
            print("⚠️ [Warning] 'gguf' library not found. Falling back to size-based sorting. Run: pip install gguf")
            logger.warning("'gguf' library not found. Falling back to size-based sorting. Run: pip install gguf")
            
        # Fallback: Rely purely on file size if GGUF is unreadable or unavailable
        return file_size_gb

    def _ensure_model_exists(self):
        """Discovers GGUF models dynamically, respects DB config, and auto-builds them in Ollama."""
        llm_dir = LLM_DIR

        while True:
            if not llm_dir.exists():
                llm_dir.mkdir(parents=True, exist_ok=True)

            gguf_files = list(llm_dir.glob("*.gguf"))
            if not gguf_files:
                print("⚠️ No GGUF models found in models/llm directory.")
                logger.warning("No GGUF models found in models/llm directory.")
                if safe_run_wizard:
                    safe_run_wizard()
                continue
            break

        # 1. Read user preferences from settings
        configured_main = get_setting("main_llm", "auto_max")
        configured_quick = get_setting("quick_llm", "auto_min")

        # 2. Sort files by Quality Score (Parameter Count + Size)
        print("🧠 Evaluating local model qualities...")
        gguf_files.sort(key=lambda x: self._calculate_model_score(x))

        # 3. Determine Normal and Overthink files
        normal_file = next((f for f in gguf_files if f.name == configured_main), gguf_files[-1]) 
        fallback_overthink = gguf_files[0] if len(gguf_files) > 1 else gguf_files[-1]
        overthink_file = next((f for f in gguf_files if f.name == configured_quick), fallback_overthink)

        # 4. Map to Ollama internal model names
        self.normal_model = f"{normal_file.stem.lower()}-jarvis"
        self.overthink_model = f"{overthink_file.stem.lower()}-jarvis"

        required_models = {
            self.normal_model: normal_file,
            self.overthink_model: overthink_file
        }
        
        print(f"🔍 Active Models -> Normal: {self.normal_model} | Overthink: {self.overthink_model}")

        try:
            # 5. Check currently installed Ollama models
            import tempfile
            with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as temp_out:
                subprocess.run(
                    ['ollama', 'list'], 
                    stdout=temp_out, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=True
                )
                temp_out.seek(0)
                installed_models = temp_out.read().lower()

            # 6. Clean up stale/old -jarvis models to save disk space
            for line in installed_models.split('\n')[1:]:
                if not line.strip():
                    continue
                model_name = line.split()[0]
                if model_name.endswith('-jarvis') or model_name.endswith('-jarvis:latest'):
                    clean_name = model_name.replace(':latest', '')
                    if clean_name not in required_models:
                        print(f"🗑️ Removing old/unused system model: {clean_name}")
                        subprocess.run(
                            ['ollama', 'rm', clean_name],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )

            # 7. Register new models via Modelfile if they don't exist
            for mod_name, mod_file in required_models.items():
                if mod_name not in installed_models:
                    print(f"⚠️ Model '{mod_name}' not found in Ollama. Starting Auto-Setup...")
                    logger.warning(f"Model '{mod_name}' not found in Ollama. Starting Auto-Setup...")
                    modelfile_path = llm_dir / f"Modelfile_{mod_name}"
                    try:
                        # Dynamic Template Matching Engine
                        modelfile_content = f'FROM "{mod_file.resolve()}"\n\n'
                        matched_config = None
                        
                        # Match filename against dictionary keywords
                        for family_name, config_data in MODEL_TEMPLATES.items():
                            if any(keyword in mod_file.name.lower() for keyword in config_data.get("keywords", [])):
                                matched_config = config_data
                                print(f"🧠 [Auto-Config] Detected '{family_name}' model family based on name.")
                                break
                        
                        if matched_config:
                            print(f"⚙️ Injecting Native Multi-Tool Template for {family_name.upper()}...")
                            modelfile_content += f'TEMPLATE """{matched_config.get("template", "")}"""\n\n'
                            
                            for param in matched_config.get("parameters", []):
                                modelfile_content += f'PARAMETER {param}\n'
                        else:
                            # No auto-match -> prompt user via GUI
                            if request_template_from_user is None:
                                print(f"❌ [Template Builder] module not found. Cannot build '{mod_name}'.")
                                logger.error(f"[Template Builder] module not found. Cannot build '{mod_name}'.")
                                continue
                                
                            user_template = request_template_from_user(mod_file.name)
                            if user_template is None:
                                print(f"❌ [Template Builder] User chose EXIT. Model '{mod_name}' will NOT be built.")
                                logger.warning(f"[Template Builder] User chose EXIT. Model '{mod_name}' will NOT be built.")
                                print(f"  → To fix this, either:")
                                print(f"    1. Rename your .gguf file to include a known family (e.g. 'qwen', 'llama3', 'mistral')")
                                print(f"    2. Add a new entry in core/data/llm_templates.py")
                                continue

                            print(f"⚙️ [User Template] Injecting user-provided template...")

                            # Clean the user's input before injection
                            _clean_input = user_template.strip()

                            # Strip markdown backticks
                            if _clean_input.startswith("```"):
                                _input_lines = _clean_input.splitlines()
                                _input_lines = _input_lines[1:]
                                if _input_lines and _input_lines[-1].strip().startswith("```"):
                                    _input_lines = _input_lines[:-1]
                                _clean_input = "\n".join(_input_lines).strip()

                            # Detect if the input is a full Modelfile snippet or raw template
                            _has_modelfile_directives = any(
                                line.strip().upper().startswith(('TEMPLATE ', 'TEMPLATE\t', 'TEMPLATE"', 'PARAMETER '))
                                for line in _clean_input.splitlines()
                            )

                            if _has_modelfile_directives:
                                modelfile_content += _clean_input + "\n"
                            else:
                                modelfile_content += f'TEMPLATE """{_clean_input}"""\n\n'

                        # Write assembled configuration
                        with open(modelfile_path, "w", encoding="utf-8") as f:
                            f.write(modelfile_content)
                            
                        # Build the model in Ollama
                        subprocess.run(
                            ['ollama', 'create', mod_name, '-f', str(modelfile_path)],
                            check=True
                        )
                        print(f"✅ Model '{mod_name}' successfully integrated into Ollama!")
                    except Exception as e:
                        print(f"❌ Failed to build model {mod_name}. Error: {e}")
                        logger.error(f"Failed to build model {mod_name}. Error: {e}")
                    finally:
                        # Clean up temporary Modelfile
                        if modelfile_path.exists():
                            modelfile_path.unlink()

            # 8. PERFORM RUNTIME CHECK FOR TOOL SUPPORT
            if self.normal_model:
                self._check_native_tool_support(self.normal_model)

        except Exception as e:
            print(f"❌ Ollama model management error: {e}")
            logger.error(f"Ollama model management error: {e}")

    # ------------------------------------------------------------------
    # Private: I/O Interface Parsers
    # ------------------------------------------------------------------
    def _extract_reasoning(self, text: str) -> Tuple[str, str]:
        """Extracts <reasoning> blocks and returns (cleaned_text, reasoning_string)."""
        reasoning = ""
        clean_text = text
        match = re.search(r'<reasoning>(.*?)</reasoning>', text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            reasoning = match.group(1).strip()
            clean_text = re.sub(r'<reasoning>.*?</reasoning>', '', text, flags=re.DOTALL | re.IGNORECASE).strip()
        return clean_text, reasoning

    def _parse_native_text_tool_call(self, text: str) -> Tuple[List[Dict], str]:
        """
        Recovery parser for small models that emit native tool calls as plain text
        instead of the structured Ollama tool_calls field.

        Handles two formats commonly emitted by weaker models:
          1. <tool_call>{"name": "...", "arguments": {...}}</tool_call>
          2. {"name": "...", "arguments": {...}}   (bare inline JSON)

        Returns (tools_list, clean_text_without_tool_json).
        """
        tools = []
        clean_text = text

        # --- Format 1: <tool_call> XML wrapper ---
        xml_pattern = r'<tool_call>\s*(.*?)(?:</tool_call>|$)'
        xml_matches = list(re.finditer(xml_pattern, text, flags=re.DOTALL | re.IGNORECASE))
        if xml_matches:
            for m in xml_matches:
                json_str = m.group(1).strip()
                try:
                    parsed = json.loads(json_str)
                    if isinstance(parsed, dict) and 'name' in parsed:
                        tools.append(parsed)
                    elif isinstance(parsed, list):
                        for t in parsed:
                            if isinstance(t, dict) and 'name' in t:
                                tools.append(t)
                except json.JSONDecodeError as e:
                    print(f"⚠️ [Text Tool Recovery] Failed to parse <tool_call> JSON: {e}")
                    logger.warning(f"[Text Tool Recovery] Failed to parse <tool_call> JSON: {e}")
            clean_text = re.sub(xml_pattern, '', text, flags=re.DOTALL | re.IGNORECASE).strip()
            return tools, clean_text

        # --- Format 2: Bare inline JSON {"name": ..., "arguments": ...} ---
        _inline_json_pattern = r'\{[^{}]*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^}]*\}[^}]*\}'
        _inline_matches = list(re.finditer(_inline_json_pattern, text))
        for _im in reversed(_inline_matches):
            _raw_json = _im.group(0)
            try:
                _parsed = json.loads(_raw_json)
                if isinstance(_parsed, dict) and 'name' in _parsed:
                    tools.append(_parsed)
                    print(f"   🔧 [Text Tool Recovery] Captured text-encoded tool call: {_parsed['name']}")
            except (json.JSONDecodeError, TypeError):
                pass
            # Always strip the JSON blob from spoken text
            clean_text = clean_text[:_im.start()] + clean_text[_im.end():]

        return tools, clean_text.strip()

    # ------------------------------------------------------------------
    # Public Generation Pipeline
    # ------------------------------------------------------------------
    def generate_response(self, messages: List[Dict], system_prompt: str = None, is_overthinking: bool = False, tools: List[Dict] = None, temperature: float = 0.1, line_callback=None, abort_event=None, on_tool_start_callback=None, ttft_anchor: float = None) -> Dict:
        """Executes LLM generation natively. Strict JSON mapping."""
        try:
            target_model = self.overthink_model if is_overthinking else self.normal_model
            dynamic_timeout = 300 if is_overthinking else 90
            
            raw_response = self._local_generate(
                messages, target_model, temperature,
                dynamic_timeout, line_callback, tools, 
                is_overthinking,
                system_prompt,    
                abort_event=abort_event,
                on_tool_start_callback=on_tool_start_callback,
                ttft_anchor=ttft_anchor
            )
            
            if not raw_response['success']: return raw_response

            raw_text = raw_response['text']
            session_id = raw_response.get('session_id', 'unknown')
            native_tools = raw_response.get('tool_calls', [])
            
            clean_text, reasoning = self._extract_reasoning(raw_text)
            unified_tools = []
            
            # Parse Native Tool Calls (structured Ollama response)
            if native_tools:
                for nt in native_tools:
                    func = nt.get('function', {})
                    name = func.get('name', '')
                    args_str = func.get('arguments', '{}')
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except json.JSONDecodeError:
                        args = {}
                    if name: unified_tools.append({'name': name, 'arguments': args})
            else:
                # Recovery: some small models emit tool calls as text
                recovered_tools, clean_text = self._parse_native_text_tool_call(clean_text)
                unified_tools.extend(recovered_tools)

            # Cleanup: strip <verbal> tags from final spoken text
            clean_text = re.sub(r'(?i)</?verbal>', '', clean_text).strip()

            if clean_text.strip().upper() == "NONE":
                clean_text = ""

            final_result = {
                'success': True, 
                'text': clean_text, 
                'reasoning': reasoning,
                'tools': unified_tools, 
                'raw_text': raw_text
            }

            # Log the final filtered result for comparison
            self._log_raw_io(session_id, "CLEAN PROCESSED RESPONSE", final_result)

            return final_result

        except Exception as e:
            return {'success': False, 'error': str(e)}
            
            
    def _local_generate(self, messages, target_model, temperature, timeout_val, line_callback, tools, is_overthinking: bool = False, system_prompt: str = None, abort_event=None, on_tool_start_callback=None, ttft_anchor: float = None) -> Dict:
        endpoint = f"{self.base_url}/api/chat"
        is_high_perf = get_setting("high_performance", False)
        safe_keep_alive = get_setting('llm_keep_alive_high_perf', '15m') if is_high_perf else get_setting('llm_keep_alive_normal', '10m')
        
        max_tokens = get_setting('llm_max_tokens_overthink', 2048) if is_overthinking else get_setting('llm_max_tokens_normal', 1024)
        context_window = get_setting('llm_context_window', 4096)

        payload = {
            "model": target_model,
            "messages": messages,
            "stream": True,
            "keep_alive": safe_keep_alive,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": context_window,
            }
        }
        
        if system_prompt:
            payload["system"] = system_prompt

        if tools and self.supports_native_tools:
            payload["tools"] = tools

        session_id = str(int(time.time() * 1000))[-6:]
        self._log_raw_io(session_id, "OUTGOING PAYLOAD", payload)

        try:
            start_time = ttft_anchor or time.time()
            first_token_received = False
            tool_announcement_fired = False

            response = requests.post(endpoint, json=payload, timeout=timeout_val, stream=True)
            if not response.ok:
                error_msg = f"API Error ({response.status_code})"
                self._log_raw_io(session_id, "ERROR FROM OLLAMA", error_msg)
                raise Exception(error_msg)

            full_content = ""
            current_chunk = ""
            native_tools = []

            for line in response.iter_lines():
                if abort_event and abort_event.is_set():
                    response.close()
                    return {'success': False, 'aborted': True, 'text': full_content}
                
                if line:
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})

                    if not tool_announcement_fired and "tool_calls" in msg and msg["tool_calls"] and on_tool_start_callback:
                        tool_announcement_fired = True
                        threading.Thread(target=on_tool_start_callback, args=(msg["tool_calls"],), daemon=True).start()

                    if "content" in msg and msg["content"]:
                        char = msg["content"]

                        if not first_token_received and char.strip():
                            ttft = time.time() - start_time
                            print(f"⏱️ [Performance] TTFT: {ttft:.2f}s")
                            if ttft > 15:
                                logger.info(f"TTFT (Time To First Token): {ttft:.2f}s")
                            first_token_received = True

                        full_content += char
                        current_chunk += char

                        # Sentence boundary detection (stops at punctuation followed by space or tag endings)
                        is_tool_call = bool(re.search(r'(?i)<reasoning>|<tool_call>', current_chunk))

                        if not is_tool_call and len(current_chunk.strip()) > 1:
                            match = re.search(r'([.!?])\s+', current_chunk)
                            has_newline = '\n' in current_chunk
                            has_verbal = '</verbal>' in current_chunk.lower()
                            
                            if match or has_newline or has_verbal:
                                if match and not has_newline and not has_verbal:
                                    cut_idx = match.end()
                                    to_speak = current_chunk[:cut_idx]
                                    current_chunk = current_chunk[cut_idx:]
                                else:
                                    to_speak = current_chunk
                                    current_chunk = ""
                                
                                clean_spoken_chunk = re.sub(r'(?i)</?verbal>', '', to_speak).strip()
                                if clean_spoken_chunk and line_callback:
                                    line_callback(clean_spoken_chunk)

                    if "tool_calls" in msg and msg["tool_calls"]:
                        if not native_tools:
                            native_tools = msg["tool_calls"]
                        else:
                            for i, tc in enumerate(msg["tool_calls"]):
                                if i < len(native_tools):
                                    if "function" in tc and "arguments" in tc["function"]:
                                        current_args = native_tools[i]["function"].get("arguments", "")
                                        new_args = tc["function"]["arguments"]
                                        if isinstance(current_args, str) and isinstance(new_args, str):
                                            native_tools[i]["function"]["arguments"] = current_args + new_args
                                        elif isinstance(current_args, dict) and isinstance(new_args, dict):
                                            current_args.update(new_args)
                                            native_tools[i]["function"]["arguments"] = current_args
                                        else:
                                            native_tools[i]["function"]["arguments"] = new_args if isinstance(new_args, dict) else current_args
                                else:
                                    native_tools.append(tc)

            if current_chunk.strip() and line_callback:
                line_callback(current_chunk.strip())

            self._log_raw_io(session_id, "FINAL RAW OUTPUT FROM MODEL", full_content)

            return {'success': True, 'text': full_content, 'tool_calls': native_tools, 'session_id': session_id}

        except Exception as e:
            self._log_raw_io(session_id, "FATAL EXCEPTION", str(e))
            raise e