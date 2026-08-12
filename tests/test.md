# 🧪 JARVIS NEXUS - Automated Testing Environment

This directory is dedicated to validating the core routing architecture, tool execution stability, and LLM reasoning logic without requiring active voice/microphone inputs.

The testing environment is designed to provide **consistent and reproducible test rounds**, ensuring that documented results can be independently validated under the same experimental conditions.

---

## 📂 Directory Structure

The testing environment is isolated from the core application to ensure clean logs and reproducible test rounds. Based on the current architecture, the structure is organized as follows:

```text
tests/
├── test.md              # This documentation file
├── results/                       # Archived outputs from completed successful test rounds
│   ├── llm_raw_debug.txt          # Archived snapshot of backend LLM payloads and background API communication
│   ├── report.md                  # Comprehensive test round report and architectural conclusions
│   └── test_results.txt           # Archived snapshot of the terminal output (stdout) from the test round
└── test/
    ├── dev_run.py           # The automated test execution engine
    └── test_input_full.txt  # The command payload containing the full test suite
```

---

## ⚠️ Pre-Requisites: Editor/Terminal Mode (CRITICAL)

Before executing the test script (`dev_run.py`), you **MUST** configure JARVIS to run in Terminal/Editor mode. This bypasses the STT (Speech-to-Text) and TTS (Text-to-Speech) engines, allowing commands to be piped directly from the text file rather than the microphone.

Open `app.py` in the root directory and modify the core import to use `SkipSTTCore`:

```python
# ─── Single import from the engine ─────────────────────────────────────────
# from core.jarvis_engine import JARVISCore  #! Full Program
from core.skip_stt import SkipSTTCore as JARVISCore  #! TESTING: Terminal mode (no audio)
```

---

## 🚀 Execution & Logging Behavior

To initiate a test round, feed the input file to the development runner:

```bash
python tests/test/dev_run.py --file tests/test/test_input_full.txt
```

> **🧹 Auto-Cleanup Note:**
> Every time a new test round is initiated, the system automatically clears the global `logs/llm_raw_debug.txt` file. This guarantees that your test logs remain completely isolated from previous runs and prevents cross-contamination of data.

---

## 📊 Understanding the Results Data

After a successful round, the outputs are reviewed and backed up into the `tests/results/` directory for historical tracking and debugging:

1. [**`test_results.txt`**](results/test_results.txt): A saved copy of the terminal output from the test round. It shows the exact flow of execution visible to the user (User Command → Status Changes → Jarvis Response).
2. [**`llm_raw_debug.txt`**](results/llm_raw_debug.txt): The "Behind the Scenes" ledger. It contains the exact JSON payloads, raw model outputs, tool execution loops, and prompt injections used during the test. The active debug log is maintained under logs/ and is cleared at the start of each new test round; a copy may then be preserved in tests/results/ for historical analysis.
3. [**`report.md`**](results/report.md): The structured evaluation of the test round. This file documents the success matrix, architectural conclusions, and historical context of improvements across previous development rounds.

---

## 🧬 Tested Model & Environment Configuration

The model specified below represents the **minimum supported model configuration for JARVIS NEXUS**, selected to meet the system's minimum runtime requirement of **4 GB of VRAM**.

All documented test rounds and stability metrics were conducted using this minimum supported model configuration and the exact engine settings specified below. Therefore, the reported results demonstrate the system's core stability under the **minimum model capability and hardware requirements targeted by the system**.

For reproducibility and direct comparison, independent tests should use the same model, quantization, and engine configuration described below. Using a different model or configuration may produce different results and should be considered a different test condition.

### 🧠 Model Specifications

* **Name:** [Qwen3-4B-Instruct-2507-Q5_K_M.gguf](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/tree/main)
* **Parameters:** 4 Billion
* **Quantization:** Q5_K_M (GGUF)

### ⚙️ Engine Configuration

The following configuration is the **lowest configuration** that can be used by JARVIS NEXUS and was used during all documented test rounds:

```json
{
  "llm_context_window": 4608,
  "llm_max_tokens_normal": 1024,
  "llm_max_tokens_overthink": 2048,
  "temperature": 0.1,
  "overthink_temperature": 0.3,
  "fast_iterations": 5,
  "overthink_iterations": 8,
  "history_limit": 3
}
```

These values correspond to the configuration used by the test environment in `core/config.py`.

> **🔬 Reproducibility Note:**
> The reported results were obtained under the exact model and configuration described above. For an independent test round to be directly comparable, the same experimental conditions should be used.
>
> Using a different model version, quantization level, or engine configuration may produce different results and should therefore be considered a different test condition.

---

## 🏆 Current Core Stability Metrics

The current core testing payload (`test_input_full.txt`) aggressively evaluates the routing engine, memory enforcement, and tool integration.

| Total Commands | Success (✅) | Warnings (⚠️) | Failures (❌) | Success Rate |
| -------------- | ----------- | ------------- | ------------ | ------------ |
| **19**         | **19**      | **0**         | **0**        | **100%**     |

*Status: The core routing architecture is fully deterministic, stable.*

---

## 🔁 Reproducing the Documented Test Results

To independently reproduce the documented results under the same minimum supported conditions:

1. Use the exact model specified in the **Tested Model & Environment Configuration** section.
2. Use the same quantization (`Q5_K_M`).
3. Apply the exact engine configuration listed above.
4. Configure JARVIS to run in **Terminal/Editor mode** using `SkipSTTCore`.
5. Execute the same test payload using `test_input_full.txt`.
6. Compare the resulting execution logs and success metrics with the documented results.

The purpose of these requirements is to ensure that test results are evaluated under equivalent conditions. As with scientific or engineering experiments, changing the experimental conditions can affect the outcome and may prevent a direct comparison with the documented results.
