# html_LLM_suggester

A smart web form analyzer and input suggester using LLMs (Large Language Models).

## Overview
This project provides a Flask-based backend server and a browser extension to:
- Record HTML/CSS snapshots and user events from web pages.
- Analyze web forms using LLMs (Ollama or OpenRouter/Cerebras).
- Suggest valid input values and ranges for form fields, in Persian, based on the HTML structure.
- Generate Katalon Studio test scripts from recorded user interactions.
- Create comprehensive test case combinations from confirmed field data.
- Provide AI-powered test improvement through an interactive GUI.

## Features
- **Form Field Extraction:** Automatically detects `<input>`, `<textarea>`, and `<select>` fields from HTML
- **LLM-Powered Suggestions:** Uses LLMs to infer field types, validation rules, and generate realistic test values
- **Multi-language Support:** Provides suggestions in Persian with English processing capabilities
- **Snapshot Recording:** Captures page HTML, CSS, and user events for reproducible testing
- **Katalon Test Generation:** Converts recorded user events into Katalon Studio test scripts with smart wait times
- **AI-Powered Test Improvement GUI:** Interactive interface for improving generated Katalon tests using LLM assistance
- **Test Case Generation:** Creates combinatorial test cases from confirmed field suggestions and exports to CSV
- **Chat History:** Maintains conversation context for better AI interactions when improving tests
- **Port Availability Check:** Automatically checks if the server port is available before starting
- **Graceful Shutdown:** Proper application cleanup and shutdown handling
- **Smart Timing Calculation:** Excludes browser extension processing time from Katalon test wait commands
- **Confirmation System:** Allows users to confirm and save field suggestions for better test generation

## API Endpoints
- `POST /snapshot` — Save HTML, CSS, and event data snapshots
- `POST /events` — Save user events, generate Katalon test scripts, and launch AI improvement GUI
- `POST /suggest_inputs` — Analyze HTML and return input suggestions as JSON
- `POST /update_input_suggestion` — Update field suggestions and get new LLM-generated examples
- `POST /confirm_suggestion` — Confirm and save field suggestions from users
- `POST /generate_test_cases` — Generate combinatorial test cases from Katalon files and confirmation data
- `POST /shutdown` — Gracefully shutdown the Flask server

## Getting Started

### Prerequisites
- Python 3.8+
- [Ollama](https://ollama.com/) (for local LLM) or an OpenRouter/Cerebras  API key
- Node.js (for browser extension development, optional)

### Installation
You can use **either** of the following methods:

#### 1. Clone and Run the Python Code
1. **Clone the repository:**
   ```sh
   git clone https://github.com/ArNayyeri/html_LLM_suggester.git
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
   - `tkinter` — GUI framework (built-in)
   - `threading`, `webbrowser` — System utilities (built-in)
   - `csv`, `math`, `itertools` — Data processing (built-in)
   - `socket`, `urllib.parse` — Network utilities (built-in)

3. **(Optional) Set up Ollama or get an OpenRouter/Cerebras API key.**

4. **Run the server:**
   ```sh
   python recorder_server.py
   ```
   You will be prompted to choose between local (Ollama) or API (OpenRouter/Cerebras).

#### 2. Use the Latest Release
- Download the latest pre-built release from the [Releases page](https://github.com/ArNayyeri/html_LLM_suggester/releases) of this repository.
- Extract and run the executable or provided files as described in the release notes.

### Using the Browser Extension
- See the `my_recorder_extension/` folder for a Chrome extension to record page data.
- Load it in Chrome via `chrome://extensions` > "Load unpacked".

## Typical Workflow

1. **Start the Server:**
   ```bash
   python recorder_server.py
   # Choose 'local' for Ollama or 'api' for OpenRouter/Cerebras
   ```

2. **Record User Actions:**
   - Install the browser extension
   - Navigate to your target website
   - Perform actions (clicking, typing, submitting forms)
   - Events are automatically recorded and snapshots are saved

3. **Get Field Suggestions:**
   - The extension analyzes forms and gets LLM suggestions in Persian
   - Review and confirm suggestions through the extension popup
   - Confirmed suggestions are saved for later use in test generation

4. **Generate Katalon Tests:**
   - Recorded events are converted to Katalon test format with smart timing
   - AI improvement GUI opens automatically for test enhancement
   - Interactive chat interface allows for test optimization

5. **Create Test Cases:**
   - Generate combinatorial test cases from confirmed field data
   - Export to CSV for use in testing frameworks
   - Uses both confirmed user data and LLM-generated examples

## Katalon Test Generation

This tool automatically converts recorded user events into Katalon Studio test scripts with the following features:

### Key Features
- **Smart Wait Time Calculation:** Adds realistic wait times between actions based on actual user timing, excluding browser extension processing time
- **Event Type Mapping:** Converts various user events (clicks, input changes, form submissions) into appropriate Katalon commands
- **Extension Event Filtering:** Automatically excludes extension-specific events from test generation
- **AI-Powered Improvement:** After generating tests, an interactive GUI opens for LLM-assisted test optimization

### Generated Test Structure
The tool creates Katalon test scripts with:
- `pause` statements for realistic timing between actions
- `click` for user interactions
- `type` for input field interactions  
- `submit` for form submissions
- `open` for page navigation
- Proper element selectors based on recorded events (prioritizes id > css > xpath)

### AI Test Improvement GUI
After the `/events` endpoint processes user events, an interactive GUI automatically opens featuring:

#### Two-Tab Interface:
1. **Current Test Tab:**
   - Displays the generated Katalon test script in readable format
   - Allows manual editing and saving
   - Shows test commands in a scrollable text area
   - Buttons for saving, regenerating, and opening in browser

2. **AI Assistant Tab:**
   - Interactive chat interface with LLM
   - Contextual understanding of your test with maintained chat history
   - Supports both local (Ollama) and API (OpenRouter/Cerebras) services
   - Real-time conversation for test improvement

#### Available Actions:
- **Send Message:** Ask specific questions about test improvement
- **Apply AI Suggestions:** Let AI automatically improve the test based on conversation
- **Get New Suggestions:** Request fresh analysis and suggestions
- **Clear History:** Reset the conversation context
- **Save Current Test:** Save the improved test to file
- **Regenerate Test:** Recreate test from original events
- **Open in Browser:** View the test in browser format

#### Usage Tips:
- Ask specific questions like "How can I make this test more robust?"
- Request additions like "Add assertions to verify the form submission was successful"
- Get help with "What validations should I add to this test?"
- The AI maintains context throughout the conversation for better suggestions

## Test Case Generation from Katalon Tests

After generating Katalon tests, you can automatically create comprehensive test case combinations:

### Features
- **Smart Field Analysis:** Extracts input fields from Katalon test scripts
- **Confirmation Integration:** Uses user-confirmed field suggestions when available from `/confirm_suggestion` endpoint
- **Combinatorial Test Generation:** Creates all possible combinations of field examples
- **LLM-Enhanced Examples:** Generates additional examples when confirmations are insufficient
- **CSV Export:** Saves test cases in CSV format for easy import into testing tools
- **Intelligent Field Matching:** Matches Katalon fields with confirmation data using flexible identification

### API Endpoint
- `POST /generate_test_cases` — Generate test case combinations from Katalon files

### Usage
The system automatically looks for confirmation files (from `/confirm_suggestion` endpoint) to use validated field examples. If no confirmations are found, it generates examples using LLM analysis based on field types and original values.

Example generated CSV:
```csv
username,password,email
user1,pass123,test1@example.com
user2,pass456,test2@example.com
admin,admin123,admin@company.com
testuser,testpass123,testuser@domain.com
```

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
      "پروژه نمونه 2",
      "پروژه تست",
      "سامانه مدیریت",
      "برنامه کاربردی"
    ]
  }
]
```

### Generated Katalon Test
Example of a generated Katalon test script from recorded events:

| Command | Target | Value |
|---------|--------|-------|
| open | https://example.com/form | |
| pause | 2000 | Wait 2.0s |
| click | id=username | |
| pause | 1000 | Wait 1.0s |
| type | id=username | john_doe |
| pause | 3000 | Wait 3.0s |
| click | id=submit-btn | |
| pause | 2000 | Wait 2.0s |
| submit | id=main-form | |

## Folder Structure
- `recorder_server.py` — Main Flask backend with all functionality
- `my_recorder_extension/` — Chrome extension for recording web page data
- `snapshots/` — Saved data organized by recording sessions
  - `run_[timestamp]_[uid]/` — Individual recording sessions
    - `recorded_events.json` — User interaction events
    - `katalon_test.html` — Generated Katalon test script
    - `[event]_[timestamp].html` — Page snapshots
    - `[event]_[timestamp].css` — Page stylesheets  
    - `confirmation_[timestamp]_[field]_[url].json` — User-confirmed field suggestions
    - `result_suggested_inputs_[timestamp].json` — LLM-generated suggestions
    - `input_suggestion_updates_[timestamp]_[field].json` — Updated field suggestions
    - `temp_katalon_test.html` — Temporary test files for browser viewing

## Advanced Features

### Token Management
- Automatic token counting using tiktoken for LLM optimization
- Context truncation for large HTML documents while preserving target elements
- Smart content selection to stay within model token limits

### Multi-language Processing
- Persian-to-English translation for LLM processing
- English-to-Persian translation for user-facing content
- Maintains cultural context in generated examples

### Error Handling & Recovery
- Graceful degradation when translation services fail
- Fallback example generation when LLM calls fail
- Port availability checking before server startup
- Comprehensive error logging and user feedback

## Acknowledgements
- [Ollama](https://ollama.com/)
- [OpenRouter](https://openrouter.ai/)
- [Cerebras](https://www.cerebras.ai/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
- [Deep Translator](https://github.com/nidhaloff/deep-translator)
- [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/)
