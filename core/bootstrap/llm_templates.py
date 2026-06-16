# core/bootstrap/llm_templates.py
"""
Centralized LLM Template Registry for JARVIS NEXUS.

Architectural Rationale:
  Each model family requires a specific "chat template" defined within its GGUF architecture.
  The Ollama Modelfile overrides this template to enforce our custom tool-calling schema.
  Incorrect templates result in model hallucinations or token repetition loops.

Stop Token Policy:
  Do not include </tool_call> or </tool_response> in stop tokens.
  Ollama terminates generation immediately upon hitting a stop token;
  adding them prematurely prevents the model from generating consecutive tool calls.

Matching Priority:
  Templates are evaluated in the order they appear in the dictionary.
  More specific keywords must precede broader ones (e.g., 'deepseek' before 'qwen').
"""

from pathlib import Path

# =============================================================================
# Template Registry
# =============================================================================

MODEL_TEMPLATES = {

    # =========================================================================
    # [1] DeepSeek
    # Covers: DeepSeek-V2, V3, R1, and distilled variants.
    # =========================================================================
    "deepseek": {
        "description": "DeepSeek V2 / V3 / R1 — custom BOS/EOS tokens",
        "keywords": ["deepseek"],
        "template": """{{- if .System }}<|begin▁of▁sentence|>{{ .System }}
{{- else }}<|begin▁of▁sentence|>You are a helpful AI assistant.
{{- end }}
{{- if .Tools }}

You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, you MUST output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools by outputting consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
<tool_call>
{"name": "another_tool", "arguments": {"key": "value"}}
</tool_call>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|User|>{{ .Content }}<|Assistant|>
{{- else if eq .Role "assistant" }}{{ if .Content }}{{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}<|end▁of▁sentence|>
{{- else if eq .Role "tool" }}<|User|><tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response><|Assistant|>
{{- end }}
{{- end }}""",
        "parameters": [
            'stop "<|begin▁of▁sentence|>"',
            'stop "<|end▁of▁sentence|>"',
            'stop "<|User|>"',
            'stop "<|Assistant|>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },

    # =========================================================================
    # [2] Qwen / ChatML
    # Covers: Qwen1.5/2/2.5/3, Yi, Hermes, NousHermes, any standard ChatML.
    # =========================================================================
    "qwen_chatml": {
        "description": "Qwen / ChatML / Yi / Hermes",
        "keywords": ["qwen", "chatml", "yi-1", "yi-6", "yi-9", "yi-34", "hermes", "nous"],
        "template": """{{- if .System }}<|im_start|>system
{{ .System }}<|im_end|>
{{- end }}
{{- if .Tools }}<|im_start|>system
# Tools
You are a highly capable AI assistant. You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, you MUST output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools by outputting consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
<tool_call>
{"name": "another_tool", "arguments": {"key": "value"}}
</tool_call><|im_end|>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{- else if eq .Role "assistant" }}<|im_start|>assistant
{{ if .Content }}{{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}<|im_end|>
{{- else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response><|im_end|>
{{- end }}
{{- end }}<|im_start|>assistant
""",
        "parameters": [
            'stop "<|im_start|>"',
            'stop "<|im_end|>"',
            'stop "<|endoftext|>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },

    # =========================================================================
    # [3] Meta Llama 3.x
    # Covers: Llama-3, 3.1, 3.2, 3.3.
    # =========================================================================
    "llama3": {
        "description": "Meta Llama 3.x — start_header_id / eot_id format",
        "keywords": ["llama-3", "llama3", "meta-llama-3"],
        "template": """{{- if .System }}<|start_header_id|>system<|end_header_id|>

{{ .System }}<|eot_id|>
{{- end }}
{{- if .Tools }}<|start_header_id|>system<|end_header_id|>

You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, you MUST output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools by outputting consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
<tool_call>
{"name": "another_tool", "arguments": {"key": "value"}}
</tool_call><|eot_id|>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|start_header_id|>user<|end_header_id|>

{{ .Content }}<|eot_id|>
{{- else if eq .Role "assistant" }}<|start_header_id|>assistant<|end_header_id|>

{{ if .Content }}{{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}<|eot_id|>
{{- else if eq .Role "tool" }}<|start_header_id|>user<|end_header_id|>

<tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response><|eot_id|>
{{- end }}
{{- end }}<|start_header_id|>assistant<|end_header_id|>

""",
        "parameters": [
            'stop "<|start_header_id|>"',
            'stop "<|end_header_id|>"',
            'stop "<|eot_id|>"',
            'stop "<|end_of_text|>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },

    # =========================================================================
    # [4] Meta Llama 2 / Code Llama
    # =========================================================================
    "llama2": {
        "description": "Meta Llama 2 / CodeLlama — [INST]/[/INST] with <<SYS>> format",
        "keywords": ["llama-2", "llama2", "codellama", "code-llama"],
        "template": """{{- if .System }}<s>[INST] <<SYS>>
{{ .System }}
{{- if .Tools }}

You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools with consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
{{- end }}
<</SYS>>

{{- else if .Tools }}<s>[INST] You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
Use <tool_call>{"name": "...", "arguments": {...}}</tool_call> to call tools. [/INST] Understood.</s>
{{- else }}<s>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}{{ .Content }} [/INST]
{{- else if eq .Role "assistant" }} {{ if .Content }}{{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}</s><s>[INST]
{{- else if eq .Role "tool" }} <tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response> [/INST]
{{- end }}
{{- end }}""",
        "parameters": [
            'stop "[INST]"',
            'stop "[/INST]"',
            'stop "<<SYS>>"',
            'stop "<</SYS>>"',
            'stop "</s>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },

    # =========================================================================
    # [5] Mistral / Mixtral
    # =========================================================================
    "mistral": {
        "description": "Mistral / Mixtral — [INST]/[/INST] format, system in first user block",
        "keywords": ["mistral", "mixtral"],
        "template": """{{- if or .System .Tools }}<s>[INST] {{ if .System }}{{ .System }}{{ end }}
{{- if .Tools }}

You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools by outputting consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
<tool_call>
{"name": "another_tool", "arguments": {"key": "value"}}
</tool_call>
{{- end }} [/INST]</s>
{{- else }}<s>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}[INST] {{ .Content }} [/INST]
{{- else if eq .Role "assistant" }}{{ if .Content }} {{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}</s>
{{- else if eq .Role "tool" }}[INST] <tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response> [/INST]
{{- end }}
{{- end }}""",
        "parameters": [
            'stop "[INST]"',
            'stop "[/INST]"',
            'stop "</s>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },

    # =========================================================================
    # [6] Google Gemma
    # =========================================================================
    "gemma": {
        "description": "Google Gemma / Gemma 2 / Gemma 3 — start_of_turn/end_of_turn format",
        "keywords": ["gemma"],
        "template": """{{- if .System }}<start_of_turn>user
{{ .System }}<end_of_turn>
<start_of_turn>model
Understood.<end_of_turn>
{{- end }}
{{- if .Tools }}<start_of_turn>user
You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools by outputting consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
<tool_call>
{"name": "another_tool", "arguments": {"key": "value"}}
</tool_call><end_of_turn>
<start_of_turn>model
Understood. I will use tools when needed.<end_of_turn>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<start_of_turn>user
{{ .Content }}<end_of_turn>
{{- else if eq .Role "assistant" }}<start_of_turn>model
{{ if .Content }}{{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}<end_of_turn>
{{- else if eq .Role "tool" }}<start_of_turn>user
<tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response><end_of_turn>
{{- end }}
{{- end }}<start_of_turn>model
""",
        "parameters": [
            'stop "<start_of_turn>"',
            'stop "<end_of_turn>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },

    # =========================================================================
    # [7] Microsoft Phi
    # =========================================================================
    "phi": {
        "description": "Microsoft Phi-3 / Phi-3.5 / Phi-4 — <|user|>/<|assistant|>/<|end|> tokens",
        "keywords": ["phi-3", "phi-4", "phi3", "phi4"],
        "template": """{{- if .System }}<|system|>
{{ .System }}<|end|>
{{- end }}
{{- if .Tools }}<|system|>
You have access to the following tools:
<tools>
{{- range .Tools }}
{"type": "function", "function": {{ .Function }}}
{{- end }}
</tools>
To use a tool, output a JSON object within <tool_call></tool_call> XML tags.
You can call MULTIPLE tools by outputting consecutive <tool_call> blocks.
Example:
<tool_call>
{"name": "tool_name", "arguments": {"key": "value"}}
</tool_call>
<tool_call>
{"name": "another_tool", "arguments": {"key": "value"}}
</tool_call><|end|>
{{- end }}
{{- range .Messages }}
{{- if eq .Role "user" }}<|user|>
{{ .Content }}<|end|>
{{- else if eq .Role "assistant" }}<|assistant|>
{{ if .Content }}{{ .Content }}{{ end }}
{{- if .ToolCalls }}
{{- range .ToolCalls }}<tool_call>
{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
</tool_call>
{{- end }}
{{- end }}<|end|>
{{- else if eq .Role "tool" }}<|user|>
<tool_response>
{"name": "{{ .Name }}", "content": {{ .Content }}}
</tool_response><|end|>
{{- end }}
{{- end }}<|assistant|>
""",
        "parameters": [
            'stop "<|system|>"',
            'stop "<|user|>"',
            'stop "<|assistant|>"',
            'stop "<|end|>"',
            'stop "<|endoftext|>"',
            'repeat_penalty 1.1',
            'temperature 0.1',
            'num_ctx 4096',
        ]
    },
}