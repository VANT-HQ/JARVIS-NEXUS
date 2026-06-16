<div align="center">

![JARVIS NEXUS Banner](docs/jarvis_nexus.jpg)

### Autonomous AI Operating System Agent
**100% Local · Zero Cloud · Full OS Control · Lowest Requirements**

<br>

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Ollama](https://img.shields.io/badge/Ollama-Local%20LLM-000000?style=for-the-badge)](https://ollama.com)
[![Status](https://img.shields.io/badge/Status-Stable%20v1.0-brightgreen?style=for-the-badge)](https://github.com/VANT-HQ/JARVIS-NEXUS/releases)
[![Download EXE](https://img.shields.io/badge/Download-Windows%20.exe-blue?style=for-the-badge&logo=windows)](https://github.com/VANT-HQ/JARVIS-NEXUS/releases/latest)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome%20on%20dev-0075ca?style=for-the-badge)](https://github.com/VANT-HQ/JARVIS-NEXUS/tree/dev)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey?style=for-the-badge)](#-hardware-requirements)

[![Privacy](https://img.shields.io/badge/🔒_Privacy-100%25_Offline-success?style=flat-square)]()
[![Memory](https://img.shields.io/badge/🧠_Memory-SQLite_+_FAISS-orange?style=flat-square)]()
[![Tools](https://img.shields.io/badge/🔧_Tools-30+_Built--in-red?style=flat-square)]()
[![STT](https://img.shields.io/badge/🎙_STT-faster--whisper-blueviolet?style=flat-square)]()
[![TTS](https://img.shields.io/badge/🔊_TTS-Piper_TTS-blue?style=flat-square)]()
[![VRAM](https://img.shields.io/badge/Min_VRAM-4_GB-yellow?style=flat-square)](#-hardware-requirements)

<br>

[**Quick Start**](#-quick-start) · [**NEXUS Architecture**](#-the-nexus-architecture) · [**Recommended Models**](#-recommended-models) · [**Contributing**](#-contributing) · [**Issues**](https://github.com/VANT-HQ/JARVIS-NEXUS/issues)

</div>

> 🌐 **Not a developer?** For a full feature showcase, interactive roadmap, and user-friendly documentation, visit **[project official page](https://vanthq.net/jarvisnexus)**.
---

## Overview

JARVIS NEXUS is a fully autonomous, locally-hosted AI assistant that runs as an **OS-level agent** on your desktop. It combines a local LLM (via Ollama), real-time voice I/O, multi-layer persistent memory, and a 30+ tool suite — all without sending a single byte to the cloud.

While competitors demand 8GB+ VRAM for agentic workflows, **NEXUS is meticulously engineered to run flawlessly on just 4GB VRAM**, maintaining near-zero Time-To-First-Token (TTFT) through advanced KV-Cache pre-baking. 

What sets it apart is the **NEXUS Architecture**: a dual-layer message system that pre-bakes the system prompt and tool schemas into Ollama's KV-Cache at startup, achieving near-zero TTFT on every interaction — even the very first one.

## 👥 Core Team & Contributors
JARVIS NEXUS is proudly developed by the V.A.N.T. team and the open-source community.

* 👑 **[Hmody](https://github.com/HmodyCode999)** — *Core Maintainer & Architect*
* 💡 *(Contributors and add your name here! Check out our [Contributing](#-contributing) guide)*

---

## 📑 Table of Contents

- [Core Features](#-core-features)
- [The NEXUS Architecture](#-the-nexus-architecture)
- [Hardware Requirements](#-hardware-requirements)
- [Quick Start](#-quick-start)
- [Recommended Models](#-recommended-models)
- [Configuration](#-configuration)
- [Built-in Tool Suite](#-built-in-tool-suite)
- [Project Structure](#-project-structure)
- [Contributing](#-contributing)
- [About V.A.N.T.](#-about-vant)
- [Dependencies](#-python-dependencies)

---

## ✨ Core Features

| Category | Capabilities |
|---|---|
| 🎙 **Real-Time Voice** | Wake-word activation, continuous listening, mid-speech interruption handling |
| 🧠 **Multi-Layer Memory** | Episodic, semantic & task memory — SQLite + FAISS semantic indexing |
| 🔧 **Full OS Control** | 30+ tools covering files, apps, system commands, screenshots, volume & more |
| 🌐 **Headless Web** | Browses and scrapes the web without a visible browser (curl_cffi + Jina fallback) |
| ⏰ **WatchDog Daemon** | Background task monitoring, proactive spoken reminders, intelligent snooze logic |
| 🛡️ **Self-Healing** | Background recovery sequence (`recovery.json`) that guards against tampering and provides emergency GUI access |
| 🖥️ **System Tray UI** | Headless gateway providing real-time state polling, immediate exit, and quick access to settings/setup |
| 📝 **Smart Logging** | System-wide event tracking (Error/Warning/Critical) with robust 24h auto-cleanup |
| 🎭 **Dynamic Personas** | Switchable AI personalities with a locked immutable default (Jarvis Classic) |
| ⚡ **Instant Responses** | KV-Cache prefix matching eliminates warmup latency after the first boot |
| 🔒 **Security Layer** | Workspace isolation, timed permission gates, root mode, group-based escalation |
| 🛠 **Agentic Loop** | Multi-step tool chaining with self-correction, deduplication & auto-permission resumption |
| 🧩 **Setup Wizard** | First-run webview GUI detects missing components and guides their installation |

---

## 🏗 The NEXUS Architecture

> **The Philosophy:** Inspired by the seamless integration of closed ecosystems (like Apple), NEXUS was engineered in pursuit of absolute perfection. It is a hub-and-spoke autonomous agent architecture where `JARVISCore` acts as the single stateful orchestrator. Every module — memory, voice, execution, and LLM — is designed to operate in flawless, native harmony without bottlenecks.

> **NEXUS** is the internal design pattern powering JARVIS — a hub-and-spoke autonomous agent architecture where `JARVISCore` acts as the single stateful orchestrator connecting every subsystem.

```
                         app.py  (Entry Point)
                            │
                            ▼
               ┌────────────────────────────┐
               │        JARVISCore          │  ◄── Hub Orchestrator
               │     jarvis_engine.py       │       (NEXUS Hub)
               └──────────┬─────────────────┘
                          │
         ┌────────────────┼───────────────────┐
         ▼                ▼                   ▼
   core/audio/       core/memory.py      core/tools/
   ├─ Ears (STT)     (SQLite + FAISS      ├─ registry.py
   └─ Mouth (TTS)     + Embeddings)       ├─ default_tools.py
                                          ├─ os_actions.py
         │                │               └─ browsing_tool.py
         ▼                ▼
  InterruptState     core/watch_dog       core/llm_client.py
  (State Machine)    (Background          (Ollama Transport)
                      Daemon)
                          │
                     core/config.py
                     (Settings DB
                      + Prompts)
```

### What Makes NEXUS Different

**Parallel Boot & KV-Cache Warmup**
While the startup video plays, JARVIS silently loads the LLM into VRAM and builds its KV-Cache using the system prompt + full tool schema. By the time you say the wake word, the model is fully warm. The first response feels as fast as the hundredth.

**Native Tool Registry vs. Cloud MCPs**
Unlike other agents that rely on the Model Context Protocol (MCP) — which forces context re-computation on every dynamic tool fetch — NEXUS utilizes a static, pre-baked tool schema natively integrated into the immutable cache layer. This deliberate architectural choice prevents KV-Cache invalidation, preserving sub-second TTFT while executing complex tool chains locally.

**Dual-Layer Message Construction**
Every request is split into two layers:
- **Immutable Layer** (cached): System prompt + persona + tool schemas — never recomputed unless you change a setting
- **Flex Layer** (per-request): Your message + memory context + permissions — the only part the LLM actually processes fresh

This is why TTFT stays near-zero even with 30+ tools in the schema.

**Formal Interrupt State Machine**
Most voice assistants either can't be interrupted or handle it awkwardly. NEXUS uses a formal state machine (`IDLE → PROCESSING → SPEAKING → FOLLOW_UP`) that handles mid-thought and mid-speech interruptions cleanly. **If you interrupt JARVIS while it's speaking, it knows exactly what word it stopped at**, preserving precise context for optional resume and injecting interrupt markers into the chat history for coherent follow-ups.

**Security-by-Default Tool Execution**
No tool modifies sensitive paths without explicit user permission. The workspace is split into a free zone (shared area) and a guarded zone (desktop/system). Permission groups mean granting access to one file tool covers its siblings. Pending tool calls auto-resume the moment the user grants permission — no re-prompting needed.

---

## 💻 Hardware Requirements

| Tier | GPU VRAM | RAM | Notes |
|---|---|---|---|
| **Minimum** | 4 GB | 8 GB | Runs Qwen3-4B at Q5 quantization · expect slightly slower TTFT |
| **Recommended** | 6–8 GB | 16 GB | Comfortable with full tool suite and faster-whisper running in parallel |
| **Optimal** | 12+ GB | 32 GB | Handles larger models, near-instant TTFT, larger STT models |
| **CPU-only** | — | 16+ GB | Supported but significantly slower — not recommended for daily use |

> **OS Support:** Windows 10/11 ✅ · Linux (Ubuntu 20.04+) ✅ · macOS ❌ (not supported yet)
>
> CUDA-capable GPU is strongly recommended for both LLM inference and STT transcription speed.

---

### Method 1: Ready-to-Run Builds (End Users)

Pre-compiled versions of JARVIS-NEXUS are available for supported operating systems. These builds include the required runtime components and are designed for users who want to run JARVIS without setting up a development environment.

#### Windows
Download the latest Windows build:
- [JARVIS-NEXUS for Windows](https://github.com/VANT-HQ/JARVIS-NEXUS/releases/latest)

#### Linux
A Linux build is planned but **currently unavailable**.
The release is **temporarily postponed** until testing and validation are completed on supported Linux distributions.

#### After downloading:
1. Run the executable.
2. The **Environment Setup Wizard** will automatically guide you through installing required components such as Ollama, STT models, and TTS files.
3. Once initialized, JARVIS will run in the background and minimize to the **System Tray** for easy access.

### Method 2: From Source (Developers)

#### 1. Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.13 | [python.org](https://www.python.org/downloads/release/python-31314/) |
| Ollama | Latest | [ollama.com](https://ollama.com) — must be installed for launch |
| CUDA | 11.8+ *(optional)* | For GPU acceleration on LLM & STT |

### 2. Clone & Install

```bash
git clone https://github.com/VANT-HQ/JARVIS-NEXUS.git
cd JARVIS-NEXUS

# Create a virtual environment (recommended)
python -m venv venv

# Windows
venv\Scripts\activate

# Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Place Your Models

Drop your files into the correct directories and JARVIS will auto-detect them:

```
models/
├── llm/
│   └── Qwen3-4B-Instruct-2507-Q5_K_M.gguf   ← Your LLM (any .gguf works)
└── stt/
    └── faster-whisper-small.en/              ← STT model folder
        ├── config.json
        ├── model.bin
        ├── tokenizer.json
        └── vocabulary.txt

assets/tts/
└── jarvis_en_GB_high/                        ← Your Piper TTS voice
    ├── jarvis_en_GB_high.onnx
    └── jarvis_en_GB_high.onnx.json

bin/
└── mpv.exe                                   ← Required for Video Player
```

> **First-Run Wizard:** If any component is missing, JARVIS launches a webview **Setup Wizard** automatically. It checks all dependencies and lets you download missing files directly from the GUI.

### 4. Run JARVIS

```bash
# Full voice mode (default)
python app.py

# Terminal-only mode (no microphone / for testing)
# Open app.py and swap the import line as commented inside
python app.py
```

Say **"Jarvis"** to wake it up. Say `immediately deactivate` or `immediately shutdown` to immediately force shutdown.

---

## 🧠 Recommended Models

JARVIS auto-detects any `.gguf` file in `models/llm/` and builds its Ollama modelfile automatically. The template engine recognizes most major model families (Qwen, Llama, Mistral) out of the box — just drop the file and boot.

| Model | File Size | VRAM | Tool Calling | Pick If... |
|---|---|---|---|---|
| **Qwen3-4B-Instruct-2507-Q5_K_M** ⭐ | ~3.5 GB | 4 GB | Excellent | You want the best balance of speed, quality, and low VRAM |
| Qwen3-7B-Instruct-Q4_K_M | ~4.4 GB | 5-6 GB | Excellent | You have a bit more VRAM and want richer, smarter responses |
| Qwen3-14B-Instruct-Q4_K_M | ~8.5 GB | 10-12 GB | Exceptional| Maximum reasoning quality, you have the hardware for it |

### Why Qwen3-4B?

The **`Qwen3-4B-Instruct-2507-Q5_K_M`** model is the top recommendation for JARVIS NEXUS because:

- Its native JSON tool calling is the most reliable among 4B-class models — critical for the agentic loop
- Runs comfortably on a 4 GB VRAM GPU, leaving headroom for STT
- Multi-step tool chains work without hallucinating tool names
- TTFT stays fast even with the full 30+ tool schema in context
- First-class support in the NEXUS template auto-detection system

> Download: [Qwen3-4B-Instruct-GGUF on HuggingFace](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF)
>
> All Qwen models (any size) are strongly recommended over alternatives for JARVIS's tool-heavy workloads.

---

## ⚙ Configuration

All settings live in `core/config.py` and persist in `data/settings.db`. They can be changed at runtime without restarting via the **Settings Panel**. 

### 🗣️ Native Voice Commands
JARVIS supports natural language synonyms for its core system modes. You don't need to memorize exact phrases—just speak naturally:

* **Settings Panel:** *"show settings panel"*, *"nexus panel"*, *"open settings"*
* **Always Listening:** *"always listening on"*, *"enable always listening"*
* **Root Mode (No GUI Prompts):** *"root access on"*, *"enable root mode"*
* **Overthinking Mode:** *"overthinking mode on"*, *"activate overthinking"*
* **Introductions:** *"jarvis startup"*, *"introduce yourself"*

| Setting | Default | Description |
|---|---|---|
| `assistant_name` | `"Jarvis"` | What JARVIS calls itself |
| `wake_word` | `"jarvis"` | Voice trigger — comma-separate for multiple wake words |
| `llm_context_window` | `4096` | Context window in tokens |
| `llm_max_tokens_normal` | `1024` | Max output tokens (standard mode) |
| `llm_max_tokens_overthink` | `2048` | Max output tokens (deep thinking mode) |
| `high_performance` | `true` | Keeps model loaded in VRAM between requests |
| `overthink_temperature` | `0.3` | LLM temperature for deep analysis mode |
| `history_limit` | `6` | Max conversation turns kept in context |
| `followup_window` | `15` | Seconds to stay in "always-listening" mode after a response |
| `dev_mode` | `true` | Enable debug output and raw I/O log file |
| `share_dir` | *(system path)* | JARVIS's free-access workspace sandbox |
| `desktop_dir` | *(system path)* | Protected desktop path (requires permission to access) |

---

## 🔧 Built-in Tool Suite

JARVIS ships with 30+ tools registered at boot. The LLM picks them via native JSON tool calling; the NEXUS tool registry handles fuzzy name matching, deduplication, and security gating automatically.

<details>
<summary><b>🧠 Memory & Knowledge</b></summary>

| Tool | Description |
|---|---|
| `search_memory` | Semantic + keyword recall from personal long-term database (Now powered natively by Ollama embeddings) |
| `save_to_memory` | Store facts, preferences, or events (routed to correct memory layer automatically) |

</details>

<details>
<summary><b>🌐 Web & Research</b></summary>

| Tool | Description |
|---|---|
| `search_web` | Real-time web search — headless, returns structured data to the LLM |
| `open_google_search` | Opens visual Google search results in the browser (great for images/products) |
| `open_website` | Navigates to any URL or platform name (JARVIS finds the link if you don't have it) |
| `youtube_action` | Direct video playback or YouTube search — auto-extracts first video ID |
| `deep_research` | Deep multi-page research with content extraction and LLM summarization |

</details>

<details>
<summary><b>📋 Task Management</b></summary>

| Tool | Description |
|---|---|
| `manage_tasks` | Create, list, complete, or delete tasks and reminders |

Supports both **relative time** (*"after 30 minutes"*, *"tomorrow"*) and **absolute time** (*"on the 15th at 5 PM"*). Due tasks are monitored by the WatchDog daemon and spoken aloud proactively.

</details>

<details>
<summary><b>📁 File System</b></summary>

| Tool | Description |
|---|---|
| `list_directory` | List files and folders in a directory |
| `read_file` | Read text or code files (with offset/limit for large files) |
| `write_file` | Create new files — prevents overwriting existing files |
| `edit_file` | Smart in-place string replacement (whitespace-resilient) |
| `manage_workspace` | Create directories, move/rename items, soft-delete to trash |

All file tools enforce workspace boundaries. Access to sensitive paths requires user permission.

</details>

<details>
<summary><b>💻 OS & Applications</b></summary>

| Tool | Description |
|---|---|
| `open_application` | Launch installed apps with fuzzy name matching |
| `kill_process` | Terminate running processes by name (fuzzy matched) |
| `run_scenario` | Execute custom automation scripts (`.ps1` on Windows / `.sh` on Linux) |
| `close_window` | Close the active foreground window (simulates Alt+F4) |
| `take_screenshot` | Capture screen and save to desktop |

</details>

<details>
<summary><b>🔊 Hardware Control</b></summary>

| Tool | Description |
|---|---|
| `set_volume` | Adjust system volume or JARVIS's own TTS volume (`level` for absolute, `change` for relative) |
| `set_brightness` | Control screen brightness (absolute or relative) |
| `system_status` | Get current CPU, RAM, and battery metrics |
| `system_power` | Lock screen, restart, or shutdown the computer |

</details>

<details>
<summary><b>⚙ System Utilities</b></summary>

| Tool | Description |
|---|---|
| `request_user_input` | Opens a GUI popup for precise text input (passwords, long URLs, etc.) |
| `grant_temporary_permission` | Security escalation — grants access and auto-resumes the blocked tool |
| `get_nexus_info` | Returns system architecture and identity information |
| `deactivate_core` | Authorized JARVIS shutdown sequence |

</details>

---

## 🗂 Project Structure

```
JARVIS-NEXUS/
├── app.py                        # Entry point — boots everything
├── core/
│   ├── config.py                 # Centralized settings, paths, prompts, personas
│   ├── jarvis_engine.py          # Main orchestrator (NEXUS Hub)
│   ├── llm_client.py             # Ollama transport, model discovery, tool parsing
│   ├── memory.py                 # Multi-layer memory (episodic, semantic, task)
│   ├── watch_dog.py              # Background daemon (task monitoring, reminders)
│   ├── logger.py                 # System-wide event tracking (Error/Warn/Critical) with 24h auto-cleanup
│   ├── skip_stt.py               # Terminal test harness (no microphone needed)
│   ├── audio/
│   │   ├── stt_engine.py         # Faster-Whisper STT with wake-word detection
│   │   └── tts_engine.py         # Piper TTS with queue-based playback
│   ├── tools/
│   │   ├── registry.py           # Tool registration, schema management, fuzzy dispatch
│   │   ├── default_tools.py      # All 30+ built-in tools + security layer
│   │   ├── os_actions.py         # OS-level actions (files, apps, system control)
│   │   └── browsing_tool.py      # Headless web scraping and deep research
│   ├── bootstrap/
│   │   ├── env_setup.py          # First-run wizard (webview GUI + downloader)
│   │   ├── autostart.py          # System autostart sync (Windows registry / Linux)
│   │   ├── recovery.py           # Emergency Settings Panel trigger
│   │   ├── template_builder.py   # LLM Modelfile builder with GUI template dialog
│   │   ├── llm_templates.py      # Known model family templates (Qwen, Llama, Mistral…)
│   │   └── utils.py              # Core utilities (Mutex, single instance enforcement)
│   └── ui/
│       ├── settings_panel.py     # Settings GUI (webview — live Python ↔ JS bridge)
│       └── video_player.py       # Isolated PyQt5 video player process
├── data/
│   ├── memories.db               # Memory database (auto-created on first run)
│   └── settings.db               # Settings & personas database (auto-created)
├── models/
│   ├── llm/                      # Drop your .gguf files here
│   ├── stt/                      # faster-whisper model folder
│   └── embeddings/               # all-MiniLM-L6-v2 (optional)
├── assets/
│   ├── videos/                   # Boot and intro video sequences
│   ├── sounds/                   # Processing and listening audio cues
│   └── tts/                      # Piper TTS voice data
├── logs/                         # Auto-cleaned log files (24h retention)
└── cache/                        # Runtime cache (FAISS index, app cache)
```

---

## 🤝 Contributing

JARVIS NEXUS is open-source and contributions are very welcome. To keep `main` stable, **all pull requests must target the `dev` branch**. After review by the V.A.N.T. team, accepted changes are merged from `dev` into `main`.

### Branch Policy

| Branch | Purpose | Direct Push |
|---|---|---|
| `main` | Stable releases — what users download | ❌ Protected |
| `dev` | Development branch — **target all PRs here** | ❌ PRs Only |
| `feature/*` | Personal feature branches | ✅ Push to your fork |

### Contribution Workflow

```bash
# 1. Fork the repository on GitHub

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/JARVIS-NEXUS.git
cd JARVIS-NEXUS

# 3. Switch to the dev branch and pull latest
git checkout dev
git pull origin dev

# 4. Create your feature branch from dev
git checkout -b feature/your-feature-name

# 5. Make your changes and commit
git add .
git commit -m "feat: short description of what you did"

# 6. Push your branch to your fork
git push origin feature/your-feature-name

# 7. Open a Pull Request on GitHub
#    ⚠️  Set the base branch to: dev  (NOT main)
```

### What We're Looking For

- New tools for the tool registry (`core/tools/default_tools.py`)
- New model family templates (`core/bootstrap/llm_templates.py`)
- STT / TTS engine improvements or new voice engine support
- Memory system enhancements (new retrieval strategies, compression)
- Bug fixes, performance improvements, cross-platform compatibility
- Documentation and example improvements

> Please [open an issue](https://github.com/VANT-HQ/JARVIS-NEXUS/issues) first before working on major changes, so we can align on direction before you invest the time.

---

## 🏢 About V.A.N.T. & Our Vision

**JARVIS NEXUS** is an open-source project by **[V.A.N.T.](https://vanthq.net)**, a tech initiative where engineering meets creativity. 

At V.A.N.T., our core design philosophy is driven by an obsession with perfection and built upon four unyielding pillars:
1. **Absolute Privacy:** Your data never leaves your machine. Period.
2. **Zero Latency:** Engineered for near-instant Time-To-First-Token (TTFT).
3. **Maximum Performance:** Squeezing every drop of capability out of local hardware.
4. **Minimal Footprint:** Achieving agentic workflows on just 4GB VRAM.

But we believe that great software isn't just about raw numbers; it's about **Creative Architecture**. We design with innovation at our core, proving that powerful, flawless AI doesn't require massive cloud server farms — it just requires brilliant, out-of-the-box engineering. 

---

## 📦 Python Dependencies

```
# Voice I/O
faster-whisper          # Offline speech-to-text
piper-tts               # Offline text-to-speech
speech_recognition      # Microphone input pipeline
pygame                  # Audio playback

# AI & Memory
sentence-transformers   # Semantic memory embeddings
faiss-cpu               # Vector similarity search index

# LLM Communication
requests                # Ollama API & web HTTP client

# OS Integrations
pyautogui               # Screenshot and window control
psutil                  # System monitoring (CPU, RAM, battery)
screen-brightness-control  # Monitor brightness control
pycaw                   # Windows audio endpoint control

# Web
curl_cffi               # Headless scraping with browser fingerprint spoofing

# Utilities
thefuzz                 # Fuzzy tool, process, and app name matching
pywebview               # Setup wizard & settings panel (native webview window)
PyQt5                   # Isolated video player process

# Model Discovery
gguf                    # GGUF file metadata parsing (zero RAM overhead)
```

---

## 🏷 Suggested GitHub Topics

Add these to the repository **Settings → Topics** for discoverability:

```
jarvis  ai-assistant  voice-assistant  local-llm  ollama  python  autonomous-agent
speech-recognition  text-to-speech  desktop-assistant  offline-ai  faster-whisper
piper-tts  gguf  agentic-ai  nexus-architecture  tool-calling
```

---

## 📄 License

This project is open-source. See [`LICENSE`](LICENSE) for full terms.

---

<div align="center">

---

```
      ██╗ █████╗ ██████╗ ██╗   ██╗██╗███████╗    ███╗   ██╗███████╗██╗  ██╗██╗   ██╗███████╗
      ██║██╔══██╗██╔══██╗██║   ██║██║██╔════╝    ████╗  ██║██╔════╝╚██╗██╔╝██║   ██║██╔════╝
      ██║███████║██████╔╝██║   ██║██║███████╗    ██╔██╗ ██║█████╗   ╚███╔╝ ██║   ██║███████╗
██╗   ██║██╔══██║██╔══██╗╚██╗ ██╔╝██║╚════██║    ██║╚██╗██║██╔══╝   ██╔██╗ ██║   ██║╚════██║
╚██████╔╝██║  ██║██║  ██║ ╚████╔╝ ██║███████║    ██║ ╚████║███████╗██╔╝ ██╗╚██████╔╝███████║
 ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝  ╚═══╝  ╚═╝╚══════╝    ╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

**JARVIS NEXUS v1.0** — *Stable Release*

<br>

> *"The architecture is real, the code is clean, and the Jarvis is now in your hands."*
>
> Six months. A lot of lessons. Zero regrets.
>
>
> — [@Hmody Code](https://github.com/HmodyCode999)

<br>

*<a href="https://vanthq.net">
  <img src="https://vanthq.net/favicon.ico" alt="V.A.N.T." style="height: 1em; vertical-align: middle;">
</a> open-source project.*

</div>
