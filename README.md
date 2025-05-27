# html_LLM_suggester

A smart web form analyzer and input suggester using LLMs (Large Language Models).

## Overview
This project provides a Flask-based backend server and a browser extension to:
- Record HTML/CSS snapshots and user events from web pages.
- Analyze web forms using LLMs (Ollama or OpenRouter).
- Suggest valid input values and ranges for form fields, in Persian, based on the HTML structure.
- Save and update suggestions for further testing or automation.

## Features
- **Form Field Extraction:** Automatically detects `<input>`, `<textarea>`, and `<select>` fields from HTML.
- **LLM-Powered Suggestions:** Uses LLMs to infer field types, validation rules, and generate realistic test values.
- **Snapshot Recording:** Captures page HTML, CSS, and user events for reproducible testing.
- **Katalon Test Generation:** Converts recorded user events into Katalon Studio test scripts with proper wait times between actions.
- **AI-Powered Test Improvement GUI:** Interactive interface for improving generated Katalon tests using LLM assistance.
- **Chat History:** Maintains conversation context for better AI interactions when improving tests.
- **API Endpoints:**
  - `/snapshot` — Save a snapshot of the current page.
  - `/events` — Save a list of recorded user events and generate Katalon test scripts.
  - `/suggest_inputs` — Analyze HTML and return suggested input values as JSON.
  - `/update_input_suggestion` — Update field suggestions and get new examples from the LLM.
- **Browser Extension:** (in `my_recorder_extension/`) for capturing page data and sending to the backend.

## Getting Started

### Prerequisites
- Python 3.8+
- [Ollama](https://ollama.com/) (for local LLM) or an OpenRouter API key
- Node.js (for browser extension development, optional)

### Installation
You can use **either** of the following methods:

#### 1. Clone and Run the Python Code
1. **Clone the repository:**
   ```sh
   git clone https://github.com/yourusername/html_LLM_suggester.git
   cd html_LLM_suggester
   ```
2. **Install Python dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
   Key dependencies include:
   - `flask`, `flask-cors` — Web server framework
   - `pydantic`, `bs4`, `beautifulsoup4` — Data parsing and validation
   - `openai`, `ollama` — LLM integration
   - `tiktoken` — Token counting for LLMs
   - `deep-translator` — Translation services
   - Built-in Python modules: `tkinter` (GUI), `threading`, `webbrowser`
3. **(Optional) Set up Ollama or get an OpenRouter API key.**
4. **Run the server:**
   ```sh
   python recorder_server.py
   ```
   You will be prompted to choose between local (Ollama) or API (OpenRouter).

#### 2. Use the Latest Release
- Download the latest pre-built release from the [Releases page](https://github.com/ArNayyeri/html_LLM_suggester/releases) of this repository.
- Extract and run the executable or provided files as described in the release notes.

### Using the Browser Extension
- See the `my_recorder_extension/` folder for a Chrome extension to record page data.
- Load it in Chrome via `chrome://extensions` > "Load unpacked".

## Katalon Test Generation

This tool automatically converts recorded user events into Katalon Studio test scripts with the following features:

### Key Features
- **Smart Wait Time Calculation:** Adds realistic wait times between actions based on actual user timing, excluding browser extension processing time.
- **Event Type Mapping:** Converts various user events (clicks, input changes, form submissions) into appropriate Katalon commands.
- **AI-Powered Improvement:** After generating tests, an interactive GUI opens for LLM-assisted test optimization.

### Generated Test Structure
The tool creates Katalon test scripts with:
- `WebUI.delay()` statements for realistic timing
- `WebUI.click()` for user interactions
- `WebUI.setText()` for input field interactions
- `WebUI.submit()` for form submissions
- Proper element selectors based on recorded events

### AI Test Improvement GUI
After the `/events` endpoint processes user events, an interactive GUI automatically opens featuring:

#### Two-Tab Interface:
1. **Current Test Tab:** 
   - Displays the generated Katalon test script
   - Allows manual editing and saving
   - Shows test in a scrollable text area

2. **AI Assistant Tab:**
   - Interactive chat interface with LLM
   - Contextual understanding of your test
   - Maintains chat history for better conversations
   - Supports both local (Ollama) and API (OpenRouter) services

#### Available Actions:
- **Ask AI for Improvements:** Get suggestions for test optimization, error handling, or additional validations
- **Regenerate Test:** Have the AI completely rewrite the test with improvements
- **Save Test:** Save the current test to a file
- **Clear Chat:** Reset the conversation history
- **Open in Browser:** View the original page snapshot

#### Usage Tips:
- Ask specific questions like "How can I make this test more robust?"
- Request additions like "Add assertions to verify the form submission was successful"
- Get help with "What validations should I add to this test?"

## API Endpoints
- `POST /snapshot` — Save HTML, CSS, and event data.
- `POST /events` — Save a list of user events, generate Katalon test scripts with proper wait times, and launch the AI improvement GUI.
- `POST /suggest_inputs` — Analyze HTML and return input suggestions as JSON.
- `POST /update_input_suggestion` — Update a field's range/examples and get new LLM-generated examples.

## Example Output

### Input Suggestions
A typical response from `/suggest_inputs`:
```json
[
  {
    "name": "نام پروژه",
    "id": "input-209",
    "type": "text",
    "range": "حداکثر 255 کاراکتر",
    "examples": [
      "پروژه نمونه 1",
      "پروژه نمونه 2"
    ]
  },
  ...
]
```

### Generated Katalon Test
Example of a generated Katalon test script from recorded events:

| Line | Command | Description | Target | Value |
|------|---------|-------------|--------|-------|
| 1 | openBrowser | Opens a new browser | | |
| 2 | navigateToUrl | Navigates to the specified URL | https://example.com/form | |
| 3 | maximizeWindow | Maximizes the browser window | | |
| 4 | delay | Waits for 2 seconds | | 2 |
| 5 | click | Clicks on the name input field | Page_form/input_name | |
| 6 | delay | Waits for 1 second | | 1 |
| 7 | setText | Enters text into the name field | Page_form/input_name | John Doe |
| 8 | delay | Waits for 3 seconds | | 3 |
| 9 | click | Clicks on the submit button | Page_form/button_submit | |
| 10 | delay | Waits for 2 seconds | | 2 |
| 11 | submit | Submits the main form | Page_form/form_main | |
| 12 | closeBrowser | Closes the browser | | |

## Folder Structure
- `recorder_server.py` — Main Flask backend with Katalon test generation and AI GUI.
- `my_recorder_extension/` — Chrome extension for recording web page data.
- `snapshots/` — Saved HTML/CSS/events, LLM suggestions, and generated Katalon test scripts.
  - `run_*/` — Individual recording sessions
  - `run_*/events.json` — Recorded user events
  - `run_*/katalon_test.html` — Generated Katalon test script
  - `run_*/page_snapshot.html` — Captured page HTML


## Acknowledgements
- [Ollama](https://ollama.com/)
- [OpenRouter](https://openrouter.ai/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
