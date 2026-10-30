# Katalon AI Web Recorder & Form Input Suggester

A smart web form analyzer, input suggester, and test recorder designed for **Katalon Studio / Katalon Recorder**, powered by Large Language Models (GPU servers, OpenRouter free models, or local Ollama).

---

## 🌟 Key Features

- **Automated Form Field Extraction:** Detects all interactive `<input>`, `<textarea>`, and `<select>` elements, associating labels, placeholders, and validation constraints without overwhelming LLMs with raw HTML.
- **Multi-Backend LLM Support:**
  - **Remote GPU Server:** Connects to any remote Ollama/OpenAI-compatible GPU endpoint (e.g., `http://<your-gpu-ip>:3000`) with dynamic IP/host and port selection.
  - **OpenRouter Free Tier with Auto-Failover:** Automatically handles upstream rate limits (`429`) and timeouts (`503/504`) by gracefully falling back across top free models (`gemma-4`, `nemotron-3.5-lightning`, `liquid-lfm`).
  - **Local Ollama:** Fully offline execution on `localhost:11434`.
- **In-Page Interactive Suggestion Modal:** Click the blue `?` button next to any field on the webpage to review, edit, regenerate with AI, or confirm test suggestions directly inside the page.
- **Katalon Test Script Generation:** Converts recorded browser interactions into valid, well-structured Katalon Studio test tables (with guaranteed initial `open` command and user-like pause times).
- **Combinatorial Test Case Matrix (CSV Export):** Generates pairwise/combinatorial test cases from confirmed user inputs and AI edge cases, ready for import into Katalon or other test automation suites.
- **Interactive AI Test Improver GUI:** Built-in Tkinter interface to review, edit, and optimize generated Katalon tests using an interactive AI assistant.
- **Extension Live Health Check:** Popup automatically checks whether the Python backend is running and displays the active model name.

---

## 🚀 Quick Start with `uv` (Recommended)

[`uv`](https://github.com/astral-sh/uv) provides instant virtual environment creation and package resolution:

```bash
# 1. Clone repository
git clone https://github.com/ArNayyeri/html_LLM_suggester.git
cd html_LLM_suggester

# 2. Create virtual environment and install dependencies
uv venv
uv pip install -e .

# 3. Start the server
uv run python recorder_server.py
```

### Alternative: Standard `pip`

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
python recorder_server.py
```

---

## ⚙️ Configuration & Backend Selection

When starting `recorder_server.py`, an interactive menu lets you choose your LLM provider:

```text
================================================================
   HTML LLM Suggester & Katalon Recorder Server
================================================================
Select LLM Backend:
  1) GPU Remote Server   [Port: 3000]
  2) OpenRouter Free API (with automatic failover across free models)
  3) Local Ollama        [http://localhost:11434/v1]
Enter choice (1/2/3, default=1): 
```

### Tokens File (`tokens`)

You can create or edit a file named `tokens` in the project root to store credentials automatically (it is already included in `.gitignore`):

```text
# Line 1: OpenRouter API Token
sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Line 2: GPU Server Token
sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
# Line 3 (optional): GPU Host / IP (or entered interactively on prompt)
# Line 4 (optional): GPU Port (default: 3000)
3000
```

*Key-value syntax is also supported (e.g., `OPENROUTER_TOKEN=...`, `GPU_HOST=...`).*

### Command-Line Arguments

The server also supports headless/scripted execution with flags:

```bash
# Run with GPU backend:
python recorder_server.py --mode gpu --gpu-host <your-gpu-ip> --gpu-port 3000 --model gemma4:e4b

# Run with OpenRouter free models:
python recorder_server.py --mode openrouter --token sk-or-v1-...

# Run with local Ollama:
python recorder_server.py --mode local --model Llama3.2:3b
```

---

## 🧩 Browser Extension Setup

1. Open Google Chrome and navigate to `chrome://extensions`.
2. Enable **Developer mode** (toggle in top right).
3. Click **Load unpacked** and select the `my_recorder_extension/` directory.
4. Pin the extension to your toolbar.

### Workflow:

1. **Start Server:** Ensure `python recorder_server.py` is running on port 5000.
2. **Suggest Inputs:**
   - Navigate to any target website (e.g. login, registration, or Google).
   - Click the extension icon and click **✨ Suggest Inputs (AI)**.
   - Blue `?` buttons will appear next to form fields. Click any `?` button to view AI suggestions, modify validation rules, or click **Confirm & Save**.
3. **Record Actions:**
   - Click **⏺ Start Recording** in the extension popup.
   - Interact with the page (typing, clicking, submitting).
   - Click **⏹ Stop Recording**.
4. **Inspect Generated Test & Combinations:**
   - The Katalon test is automatically saved in `snapshots/run_<id>/katalon_test.html`.
   - The AI Improver GUI will open to assist in refining your test script.

---

## 📡 API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Returns server status, mode, active model, and session ID |
| `POST` | `/suggest_inputs` | Extracts form fields from HTML and returns LLM test data suggestions |
| `POST` | `/update_input_suggestion` | Regenerates field suggestions based on updated constraints |
| `POST` | `/confirm_suggestion` | Confirms and persists user-validated field rules |
| `POST` | `/events` | Saves interaction events, generates Katalon script, opens improver GUI |
| `POST` | `/generate_test_cases` | Generates combinatorial test case matrix and exports to CSV |
| `POST` | `/snapshot` | Saves raw page HTML/CSS snapshots |
| `POST` | `/shutdown` | Gracefully terminates server |

---

## 📂 Project Structure

```text
html_LLM_suggester/
├── recorder_server.py         # Main Flask server & LLM integration
├── pyproject.toml             # uv / PEP 621 project configuration
├── requirements.txt           # Standard pip dependencies
├── tokens                     # Local API tokens and GPU config (git-ignored)
├── my_recorder_extension/     # Chrome Extension (Manifest V3)
│   ├── manifest.json          # Extension metadata and permissions
│   ├── background.js          # Service worker for context menus & sync
│   ├── content.js             # Event recorder and in-page modal UI
│   ├── popup.html             # Extension popup interface
│   ├── popup.js               # Extension popup logic & health check
│   └── icons/                 # 16x16, 48x48, 128x128 icons
└── snapshots/                 # Test recording sessions and output files
    └── run_<timestamp>_<id>/
        ├── recorded_events.json
        ├── katalon_test.html
        └── generated_test_cases.csv
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
