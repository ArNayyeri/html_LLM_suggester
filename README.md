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
- **API Endpoints:**
  - `/snapshot` — Save a snapshot of the current page.
  - `/events` — Save a list of recorded user events.
  - `/suggest_inputs` — Analyze HTML and return suggested input values as JSON.
  - `/update_input_suggestion` — Update field suggestions and get new examples from the LLM.
- **Browser Extension:** (in `my_recorder_extension/`) for capturing page data and sending to the backend.

## Getting Started

### Prerequisites
- Python 3.8+
- [Ollama](https://ollama.com/) (for local LLM) or an OpenRouter API key
- Node.js (for browser extension development, optional)

### Installation
1. **Clone the repository:**
   ```sh
   git clone https://github.com/yourusername/html_LLM_suggester.git
   cd html_LLM_suggester
   ```
2. **Install Python dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
   (You may need to manually install: `flask`, `flask-cors`, `pydantic`, `bs4`, `openai`, `ollama`)

3. **(Optional) Set up Ollama or get an OpenRouter API key.**

### Running the Server
```sh
python recorder_server.py
```
You will be prompted to choose between local (Ollama) or API (OpenRouter).

### Using the Browser Extension
- See the `my_recorder_extension/` folder for a Chrome extension to record page data.
- Load it in Chrome via `chrome://extensions` > "Load unpacked".

## API Endpoints
- `POST /snapshot` — Save HTML, CSS, and event data.
- `POST /events` — Save a list of user events.
- `POST /suggest_inputs` — Analyze HTML and return input suggestions as JSON.
- `POST /update_input_suggestion` — Update a field's range/examples and get new LLM-generated examples.

## Example Output
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

## Folder Structure
- `recorder_server.py` — Main Flask backend.
- `my_recorder_extension/` — Chrome extension for recording web page data.
- `snapshots/` — Saved HTML/CSS/events and LLM suggestions.


## Acknowledgements
- [Ollama](https://ollama.com/)
- [OpenRouter](https://openrouter.ai/)
- [OpenAI Python SDK](https://github.com/openai/openai-python)
