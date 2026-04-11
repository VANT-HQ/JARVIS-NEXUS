
<div align="center">

# 🤖 JARVIS - Just A Rather Very Intelligent System

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Status: Pre-Release](https://img.shields.io/badge/Status-Pre--Release-orange.svg)]()
[![Offline First](https://img.shields.io/badge/Architecture-Offline--First-success.svg)]()

**Author:** [Hmody](https://github.com/HmodyCode999) - [V.A.N.T.](https://vanthq.net) CEO & Founder

</div>

> ⚠️ **Note:** This project is the result of months of independent research and development. It was built entirely from the ground up to explore the true potential of offline, privacy-first AI orchestration.

---

## 📑 Table of Contents
- [Vision](#-vision)
- [Features](#-features)
- [Architecture](#️-architecture)
- [Installation](#-installation)
- [Configuration](#️-configuration)
- [Usage](#-usage)
- [Privacy & Security](#-privacy--security)
- [Contributing](#-contributing)

---

## 🎯 Vision

JARVIS is a fully **offline-first**, **privacy-focused** AI assistant designed to run entirely on local hardware. Built with a modular architecture combining Local LLMs (via Ollama), advanced memory systems, and browser automation.

**Key Philosophy:**
- 🏠 **100% Offline**: No API keys, no cloud dependencies
- 🧠 **Persistent Memory**: Multi-layer memory (Working, Episodic, Semantic, Procedural)
- 🔧 **Tool Augmented**: Real-time web search, OS control, browser automation
- 🎭 **Personality Engine**: Configurable personas with SQLite-backed settings
- 🌍 **Multilingual**: Native English and Arabic support

---

## ✨ Features

### Core Intelligence
- **Local LLM Integration**: Auto-detects and manages GGUF models via Ollama
- **Dual-Mode Processing**: 
  - *Normal Mode*: Fast responses with smaller model
  - *Overthinking Mode*: Deep analysis with larger model
- **Smart Tool Calling**: Hidden tool syntax (`@@TOOL:...@@`) with multi-step agentic loops

### Memory Architecture
- **Working Memory**: Current conversation context
- **Episodic Memory**: Past conversations and events (SQLite + Embeddings)
- **Semantic Memory**: Knowledge base about entities and facts
- **Procedural Memory**: Task management and TODOs

### Input/Output
- **Ears (STT)**: Faster-Whisper with GPU acceleration support, smart wake-word detection
- **Mouth (TTS)**: Piper TTS with Edge-TTS fallback for Arabic (Beta)
- **Visual Feedback**: Startup/Intro video playback with VLC integration

### Automation
- **Browser Agent**: Stealth browsing with Camoufox, DuckDuckGo search, auto-learning
- **OS Integration**: Open applications, websites, system control
- **Smart Interruption**: Voice interruption during speech

---

## 🏗️ Architecture

```text
jarvis/
├── app.py                 # Main orchestrator & State Manager
├── core/
│   ├── config.py          # Settings & Persona management (SQLite)
│   ├── memory_manager.py  # Multi-layer memory system
│   ├── root/
│   │   ├── ears.py        # Speech Recognition (Whisper)
│   │   └── mouth.py       # Text-to-Speech (Piper/Edge)
│   └── tools/
│       ├── browser_agent.py   # Web scraping & automation
│       └── os_actions.py      # System commands
├── models/llm/            # GGUF models (not in repo)
├── voice/
│   ├── tts/               # Piper voices (not in repo)
│   └── stt/               # Whisper models (not in repo)
├── runtime/
│   ├── camoufox/          # Browser binary (not in repo)
│   └── all-MiniLM-L6-v2/  # Embeddings (optional auto-download)
├── media/                 # Startup & Intro videos (Included)
└── data/                  # SQLite empty template databases (Included)
````

-----

## 🚀 Installation

### Prerequisites

  - Python 3.9+
  - [Ollama](https://ollama.ai) installed
  - Windows 10/11 (Linux support planned)
  - NVIDIA GPU recommended (CUDA) but not required

### 1\. Clone Repository

```bash
git clone [https://github.com/VANT-HQ/JARVIS-NEXUS.git](https://github.com/VANT-HQ/JARVIS-NEXUS.git)
cd jarvis
```

### 2\. Install Python Dependencies

```bash
pip install -r requirements.txt
```

**Key dependencies:**

```text
# Core
numpy>=1.24.0
requests>=2.28.0
pygame>=2.5.0
sqlite3-utils

# AI/ML
faster-whisper>=1.0.0
sentence-transformers>=2.2.0
piper-tts>=1.2.0
edge-tts>=6.1.0

# Browser
scrapling>=0.1.0
patchright>=1.0.0
duckduckgo-search>=3.9.0

# Utilities
pyttsx3>=2.90
tinytag>=1.10.0
beautifulsoup4>=4.12.0
```

### 3\. Setup Large Files

Run the setup assistant to initialize directories:

```bash
python setup.py
```

**Manual Downloads Required:**

  - **LLM Models → `models/llm/`**:
    Download any GGUF model (e.g., `Qwen2.5-7B-Instruct-Q4_K_M.gguf`) from HuggingFace GGUF Models.
  - **Camoufox Browser → `runtime/camoufox/`**:
    Download from [daijro/camoufox](https://github.com/daijro/camoufox) and extract the folder to `runtime/`.
  - **TTS Voices → `voice/tts/`**:
    Download Piper voices from [rhasspy/piper-voices](https://www.google.com/search?q=https://github.com/rhasspy/piper-voices) and place the `.onnx` and `.json` files here.
  - **STT Model → `voice/stt/faster-whisper-small/`**:
    Auto-downloaded by setup script, or manual download from `Systran/faster-whisper-small`.
  - **Embedding Model → `runtime/all-MiniLM-L6-v2/`** *(Optional)*:
    Will auto-download on first run, or place manually from `sentence-transformers/all-MiniLM-L6-v2`.

-----

## ⚙️ Configuration

Settings are managed via `data/settings.db` (auto-created from the included empty template).  
**Default Settings** (can be edited in `core/config.py`):

  - **Wake Word:** "Jarvis"
  - **Language:** Auto-detect (English Default/Arabic Beta)
  - **Startup Video:** Enabled
  - **Always Listening:** Disabled
  - **Personas:**
      - *Default:* "Jarvis (Classic)" - Professional, British-inspired, concise
      - Custom personas can be added via the database

-----

## 🎮 Usage

### Basic Run

```bash
python app.py
```

### Voice Commands

  - **"Jarvis"** - Wake up assistant
  - **"Jarvis startup"** - Play boot sequence
  - **"Apache mode on/off"** - Toggle high-performance mode
  - **"Language mode Arabic/English/Auto"** - Force language
  - **"Overthinking mode on"** - Enable deep analysis
  - **"exit"** or **"shutdown"** - Close application

### Example Interactions

```text
You: "Jarvis, what is the weather?"
Jarvis: [Uses search_web tool] "It's currently 22°C and sunny, sir."

You: "Remember that I prefer VS Code"
Jarvis: [Stores in knowledge base] "Noted. Preference saved."

You: "Research the best Python web frameworks"
Jarvis: [Deep research mode] "Analyzing Django, FastAPI, and Flask..."
```

-----

## 🔒 Privacy & Security

  - **Zero Cloud Dependencies:** Everything runs locally
  - **No Telemetry:** No data leaves your machine
  - **Encrypted Memories:** SQLite database with optional encryption support
  - **Sandboxed Browser:** Camoufox provides anti-fingerprinting protection

-----

## 🤝 Contributing

This is a personal research project currently. Contributions are welcome after the stable release.

