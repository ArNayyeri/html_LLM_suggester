import os
import sys
import json
import re
import time
import uuid
import math
import csv
import socket
import argparse
import threading
import webbrowser
from collections import defaultdict
from itertools import product
from urllib.parse import urlparse

# Ensure UTF-8 output in Windows terminals
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from flask import Flask, request, jsonify
from flask_cors import CORS
from bs4 import BeautifulSoup
from openai import OpenAI
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

# Default configuration values
DEFAULT_GPU_HOST = ""
DEFAULT_GPU_PORT = 3000
DEFAULT_GPU_MODEL = "gemma4:e4b"

DEFAULT_LOCAL_URL = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "Llama3.2:3b"

DEFAULT_OPENROUTER_URL = "https://openrouter.ai/api/v1"
OPENROUTER_FREE_MODELS = [
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    "liquid/lfm-2.5-2.6b:free",
    "google/gemma-4-31b-it:free"
]


# ==============================================================================
# Token & Configuration Loader
# ==============================================================================

def load_tokens_file(file_path="tokens"):
    """
    Reads tokens and configuration from 'tokens' file if present.
    Format support:
      Line 1: OpenRouter API Token
      Line 2: GPU Server Token
      Line 3 (optional): GPU Host / IP (e.g. 192.168.1.50)
      Line 4 (optional): GPU Port (default 3000)
    Also supports KEY=VALUE format (e.g., OPENROUTER_TOKEN=..., GPU_HOST=...).
    """
    config = {
        'openrouter_token': '',
        'gpu_token': '',
        'gpu_host': DEFAULT_GPU_HOST,
        'gpu_port': DEFAULT_GPU_PORT,
    }
    if not os.path.exists(file_path):
        return config

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]

        positional_idx = 0
        for line in lines:
            if '=' in line:
                k, v = line.split('=', 1)
                k = k.strip().upper()
                v = v.strip()
                if k in ('OPENROUTER_TOKEN', 'OPENROUTER_KEY', 'OPENROUTER'):
                    config['openrouter_token'] = v
                elif k in ('GPU_TOKEN', 'GPU_KEY'):
                    config['gpu_token'] = v
                elif k in ('GPU_HOST', 'GPU_IP', 'IP'):
                    config['gpu_host'] = v
                elif k in ('GPU_PORT', 'PORT'):
                    try:
                        config['gpu_port'] = int(v)
                    except ValueError:
                        pass
            else:
                if positional_idx == 0:
                    config['openrouter_token'] = line
                elif positional_idx == 1:
                    config['gpu_token'] = line
                elif positional_idx == 2:
                    config['gpu_host'] = line
                elif positional_idx == 3:
                    try:
                        config['gpu_port'] = int(line)
                    except ValueError:
                        pass
                positional_idx += 1
    except Exception as e:
        print(f"[!] Warning reading tokens file: {e}")

    return config


def check_port_available(port_num):
    """Check if a port is available for use"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.bind(('127.0.0.1', port_num))
        sock.close()
        return True
    except OSError:
        return False


# ==============================================================================
# Initialization & Setup
# ==============================================================================

tokens_cfg = load_tokens_file("tokens")

parser = argparse.ArgumentParser(description="HTML LLM Suggester & Katalon Recorder Server")
parser.add_argument("--mode", choices=["gpu", "openrouter", "local"], default=None, help="Backend mode")
parser.add_argument("--gpu-host", type=str, default=None, help="GPU server host/IP")
parser.add_argument("--gpu-port", type=int, default=None, help="GPU server port")
parser.add_argument("--model", type=str, default=None, help="Model name")
parser.add_argument("--token", type=str, default=None, help="API token")
parser.add_argument("--port", type=int, default=5000, help="Port to run Flask server on")
args, _ = parser.parse_known_args()

selected_mode = args.mode
cli_model = args.model
cli_token = args.token
server_port = args.port
gpu_host = args.gpu_host or tokens_cfg.get('gpu_host', '')
gpu_port = args.gpu_port or tokens_cfg.get('gpu_port', DEFAULT_GPU_PORT)

# Interactive configuration if run directly in terminal without CLI flags
if not selected_mode and sys.stdin.isatty():
    print("=" * 64)
    print("   HTML LLM Suggester & Katalon Recorder Server")
    print("=" * 64)
    print("Select LLM Backend:")
    host_display = f"{gpu_host}:{gpu_port}" if gpu_host else f"Port: {gpu_port}"
    print(f"  1) GPU Remote Server   [{host_display}]")
    print("  2) OpenRouter Free API (with automatic failover across free models)")
    print(f"  3) Local Ollama        [{DEFAULT_LOCAL_URL}]")
    choice = input("Enter choice (1/2/3, default=1): ").strip()

    if choice == '2':
        selected_mode = 'openrouter'
    elif choice == '3':
        selected_mode = 'local'
    else:
        selected_mode = 'gpu'
        # Ask for dynamic GPU IP/Host (NOT hardcoded in code)
        if gpu_host:
            host_input = input(f"Enter GPU IP/Host [default: {gpu_host}]: ").strip()
            if host_input:
                gpu_host = host_input
        else:
            while not gpu_host:
                gpu_host = input("Enter GPU IP/Host: ").strip()
                if not gpu_host:
                    print("[!] GPU IP/Host is required.")

        port_input = input(f"Enter GPU Port [default: {gpu_port}]: ").strip()
        if port_input:
            try:
                gpu_port = int(port_input)
            except ValueError:
                pass
elif not selected_mode:
    # Default when imported or running headless
    selected_mode = 'gpu'
    if not gpu_host:
        gpu_host = tokens_cfg.get('gpu_host', '127.0.0.1')

# Configure client based on selected mode
if selected_mode == 'openrouter':
    base_url = DEFAULT_OPENROUTER_URL
    token = cli_token or tokens_cfg.get('openrouter_token')
    if not token and sys.stdin.isatty():
        token = input("Enter OpenRouter API token: ").strip()
    active_model = cli_model or OPENROUTER_FREE_MODELS[0]
    extra_headers = {
        'HTTP-Referer': 'https://github.com/ArNayyeri/html_LLM_suggester',
        'X-Title': 'HTML LLM Suggester'
    }
    client = OpenAI(base_url=base_url, api_key=token or 'none', default_headers=extra_headers)
    print(f"\n[*] Mode: OpenRouter Free API")
    print(f"[*] Primary Model: {active_model} (Fallbacks: {len(OPENROUTER_FREE_MODELS)-1} models)")

elif selected_mode == 'local':
    base_url = DEFAULT_LOCAL_URL
    token = cli_token or 'ollama'
    active_model = cli_model or DEFAULT_LOCAL_MODEL
    client = OpenAI(base_url=base_url, api_key=token)
    print(f"\n[*] Mode: Local Ollama ({base_url})")
    print(f"[*] Model: {active_model}")

else:  # GPU mode
    base_url = f"http://{gpu_host}:{gpu_port}/v1"
    token = cli_token or tokens_cfg.get('gpu_token')
    if not token and sys.stdin.isatty():
        token = input("Enter GPU API Token: ").strip()
    token = token or 'ollama'
    active_model = cli_model or DEFAULT_GPU_MODEL
    client = OpenAI(base_url=base_url, api_key=token)
    print(f"\n[*] Mode: GPU Server ({base_url})")
    print(f"[*] Model: {active_model}")

app = Flask(__name__)
CORS(app)

SAVE_DIR = "snapshots"
os.makedirs(SAVE_DIR, exist_ok=True)

# Run session management
_run_time = int(time.time())
_run_uid = uuid.uuid4().hex[:8]
RUN_ID = f"run_{_run_time}_{_run_uid}"
RUN_SAVE_DIR = os.path.join(SAVE_DIR, RUN_ID)
os.makedirs(RUN_SAVE_DIR, exist_ok=True)
print(f"[*] Session Run ID: {RUN_ID}")
print(f"[*] Artifacts directory: {RUN_SAVE_DIR}")

# In-memory storage for user confirmed suggestions
CONFIRMED_FIELDS = {}


# ==============================================================================
# Resilient LLM Caller (with Free Model Failover)
# ==============================================================================

def call_llm(messages, max_tokens=1500, temperature=0.2):
    """
    Executes a chat completion call with automatic model failover.
    For OpenRouter, if a free model is rate-limited (429) or busy (503/504),
    it dynamically tries the next free model in OPENROUTER_FREE_MODELS.
    """
    if selected_mode == 'openrouter':
        models_to_try = [active_model] + [m for m in OPENROUTER_FREE_MODELS if m != active_model]
        last_error = None
        for m in models_to_try:
            try:
                res = client.chat.completions.create(
                    model=m,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                msg = res.choices[0].message
                raw_text = msg.content or getattr(msg, 'reasoning_content', '') or ''
                return raw_text.strip()
            except Exception as e:
                err_str = str(e)
                print(f"[!] OpenRouter model '{m}' failed ({err_str[:80]}), trying next free model...")
                last_error = e
                time.sleep(0.8)
        raise RuntimeError(f"All OpenRouter free models failed: {last_error}")

    else:
        # GPU or Local
        res = client.chat.completions.create(
            model=active_model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
        msg = res.choices[0].message
        raw_text = msg.content or getattr(msg, 'reasoning_content', '') or ''
        return raw_text.strip()


# ==============================================================================
# Helper Functions: Robust JSON Parsing & Extraction
# ==============================================================================

def clean_llm_json(raw_text):
    """
    Robustly extract and parse JSON from LLM outputs.
    Handles markdown fences (```json ... ```), trailing commas, and unescaped characters.
    """
    text = raw_text.strip()

    # Remove markdown code blocks if present
    if '```' in text:
        text = re.sub(r'```(?:json)?', '', text)
        text = text.replace('```', '').strip()

    # Look for list brackets [ ... ]
    start = text.find('[')
    end = text.rfind(']')
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            return json.loads(candidate)
        except Exception:
            fixed = re.sub(r',\s*([\]\}])', r'\1', candidate)
            try:
                return json.loads(fixed)
            except Exception:
                pass

    # Look for single object { ... }
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        try:
            parsed = json.loads(candidate)
            return [parsed] if isinstance(parsed, dict) else parsed
        except Exception:
            fixed = re.sub(r',\s*([\]\}])', r'\1', candidate)
            try:
                parsed = json.loads(fixed)
                return [parsed] if isinstance(parsed, dict) else parsed
            except Exception:
                pass

    # Fallback: extract individual JSON objects using regex
    items = []
    for m in re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text):
        try:
            items.append(json.loads(m.group(0)))
        except Exception:
            pass
    if items:
        return items

    raise ValueError(f"Could not parse valid JSON from LLM response:\n{raw_text[:300]}")


def extract_form_fields(html):
    """
    Extract all relevant interactive form elements (up to 4-10 fields) with metadata.
    Avoids sending raw HTML dumps; extracts concise structural context (< 300 tokens per field).
    Supports inputs (with/without type attribute), textareas, and selects.
    """
    soup = BeautifulSoup(html, 'html.parser')
    page_title = soup.title.string.strip() if soup.title and soup.title.string else ''

    elements = soup.find_all(['input', 'textarea', 'select'])
    valid_input_types = {
        'text', 'search', 'email', 'password', 'tel', 'url',
        'number', 'date', 'datetime-local', 'month', 'time', 'week'
    }

    fields = []
    seen = set()

    for el in elements:
        tag = el.name
        el_id = el.get('id', '').strip()
        name = el.get('name', '').strip()

        # In standard HTML, default input type is 'text' if not specified
        el_type = el.get('type', 'text').lower().strip() if tag == 'input' else tag

        # Only accept text-like input types, textareas, and selects
        if tag == 'input' and el_type not in valid_input_types:
            continue

        # Skip hidden inputs or elements styled as display:none
        style = el.get('style', '').lower()
        if 'display:none' in style.replace(' ', '') or 'visibility:hidden' in style.replace(' ', ''):
            continue
        if el.get('hidden') is not None:
            continue

        # Find associated label text
        label_text = ''
        if el_id:
            lbl = soup.find('label', attrs={'for': el_id})
            if lbl:
                label_text = lbl.get_text(strip=True)
        if not label_text and el.parent and el.parent.name == 'label':
            label_text = el.parent.get_text(strip=True)

        aria_label = el.get('aria-label', '').strip()
        placeholder = el.get('placeholder', '').strip()
        label = label_text or aria_label or placeholder or name or el_id or tag

        identifier = el_id or name
        if not identifier or identifier in seen:
            continue
        seen.add(identifier)

        options = []
        if tag == 'select':
            for opt in el.find_all('option')[:10]:
                opt_val = opt.get('value', '').strip() or opt.get_text(strip=True)
                if opt_val:
                    options.append(opt_val)

        fields.append({
            'id': el_id or identifier,
            'name': name or identifier,
            'tag': tag,
            'type': el_type,
            'label': label,
            'placeholder': placeholder,
            'options': options,
            'page_title': page_title
        })

    return fields


def generate_field_suggestions(fields):
    """
    Generate realistic test input values and validation rules for fields in ONE prompt.
    Produces high quality Persian/English suggestions.
    """
    if not fields:
        return []

    prompt = f"""You are a test automation and QA expert.
Analyze the following form field(s) from a webpage and generate appropriate test input suggestions in Persian (فارسی).

Fields to analyze:
{json.dumps(fields, ensure_ascii=False, indent=2)}

For EACH input field in the list above, output ONE JSON object in an array:
- id: exact 'id' from the field above
- name: exact 'name' from the field above
- type: 'type' from the field above
- range: validation rules, constraints, or search guidelines written in Persian (فارسی). (e.g. 'حداکثر ۲۵۵ کاراکتر، متن جستجو').
- examples: 5 realistic, valid test values that would be accepted by the form.
- bad_examples: 5 invalid or boundary values for negative testing (empty, boundary overflow, special characters, SQLi/XSS test inputs).

Return ONLY a valid JSON array of objects with exactly {len(fields)} item(s). No explanations, no markdown comments."""

    try:
        raw_output = call_llm([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.2)
        parsed = clean_llm_json(raw_output)

        # Validate and align with DOM fields
        results = []
        for i, item in enumerate(parsed):
            target_field = fields[i] if i < len(fields) else fields[0]
            field_id = item.get('id') or target_field['id']
            field_name = item.get('name') or target_field['name']

            results.append({
                'id': field_id,
                'name': field_name,
                'type': item.get('type') or target_field['type'],
                'range': item.get('range') or item.get('limitations') or 'قوانین اعتبارسنجی پیش‌فرض',
                'examples': item.get('examples') or [f"تست {j+1}" for j in range(5)],
                'bad_examples': item.get('bad_examples') or ["", "   ", "1234567890", "<script>alert(1)</script>", "!@#$%^"]
            })
        return results

    except Exception as e:
        print(f"Error in generate_field_suggestions: {e}")
        # Deterministic fallback so the extension NEVER breaks
        fallback_results = []
        for f in fields:
            fallback_results.append({
                'id': f['id'],
                'name': f['name'],
                'type': f['type'],
                'range': f"فیلد {f['label']} - متن ورودی معتبر",
                'examples': [f"نمونه {i+1} برای {f['label']}" for i in range(5)],
                'bad_examples': ["", "   ", "<script>", "' OR '1'='1", "A" * 300]
            })
        return fallback_results


# ==============================================================================
# Flask Routes
# ==============================================================================

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'online',
        'mode': selected_mode,
        'model': active_model,
        'run_id': RUN_ID
    })


@app.route('/snapshot', methods=['POST'])
def snapshot():
    try:
        data = request.get_json(force=True)
        event_type = data.get('eventType', 'event')
        event_time = data.get('time', int(time.time() * 1000))
        print(f"[*] Received snapshot: {event_type} at {event_time}")

        base = f"{event_type}_{event_time}"
        if 'html' in data and data['html']:
            html_path = os.path.join(RUN_SAVE_DIR, f"{base}.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(data['html'])

        if 'css' in data and data['css']:
            css_path = os.path.join(RUN_SAVE_DIR, f"{base}.css")
            with open(css_path, "w", encoding="utf-8") as f:
                f.write(data['css'])

        event_path = os.path.join(RUN_SAVE_DIR, f"{base}_event.json")
        event_data = data.get('event') or {
            "eventType": event_type,
            "time": event_time,
            "url": data.get('url', '')
        }
        with open(event_path, "w", encoding="utf-8") as f:
            json.dump(event_data, f, ensure_ascii=False, indent=2)

        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"Error in snapshot: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/suggest_inputs', methods=['POST'])
def suggest_inputs():
    print("\n[*] Received /suggest_inputs request")
    run_time_temp = int(time.time())
    try:
        data = request.get_json(force=True)
        html = data.get('html', '')

        # Save HTML for session record
        html_file = os.path.join(RUN_SAVE_DIR, f'html_suggest_inputs_{run_time_temp}.html')
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)

        # 1. Extract concise field information
        fields = extract_form_fields(html)
        print(f"[*] Extracted {len(fields)} field(s) from page:")
        for f in fields:
            print(f"    - [{f['tag']}] id='{f['id']}' name='{f['name']}' label='{f['label']}'")

        if not fields:
            print("[!] No interactive inputs found on page.")
            return jsonify([])

        # 2. Call LLM to generate suggestions
        results = generate_field_suggestions(fields)

        # 3. Save JSON result
        result_file = os.path.join(RUN_SAVE_DIR, f'result_suggested_inputs_{run_time_temp}.json')
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        print(f"[+] Successfully generated suggestions for {len(results)} field(s)")
        return jsonify(results)

    except Exception as e:
        print(f"[!] Error in suggest_inputs: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/update_input_suggestion', methods=['POST'])
def update_input_suggestion():
    print("\n[*] Received /update_input_suggestion request")
    run_time_temp = int(time.time())
    try:
        data = request.get_json(force=True)
        field = data.get('field', 'field')
        range_ = data.get('range', '')
        examples_ = data.get('examples', [])
        bad_examples_ = data.get('bad_examples', [])

        prompt = f"""You are a test automation expert.
A QA tester is refining test values for a form field named '{field}'.
Current validation rules / range description:
{range_}

Existing user provided examples:
Good: {json.dumps(examples_, ensure_ascii=False)}
Bad: {json.dumps(bad_examples_, ensure_ascii=False)}

Please generate an improved description of the range (in Persian), exactly 5 high quality realistic GOOD examples, and 5 BAD (invalid/negative) examples.
Return ONLY a JSON object:
{{
  "range": "توضیح قوانین به فارسی",
  "examples": ["val1", "val2", "val3", "val4", "val5"],
  "bad_examples": ["bad1", "bad2", "bad3", "bad4", "bad5"]
}}"""

        raw_output = call_llm([{"role": "user", "content": prompt}], max_tokens=800, temperature=0.3)
        parsed = clean_llm_json(raw_output)
        if isinstance(parsed, list) and parsed:
            parsed = parsed[0]

        new_range = parsed.get('range') or range_
        new_examples = parsed.get('examples') or examples_
        new_bad = parsed.get('bad_examples') or bad_examples_

        updates = {
            'field': field,
            'range': new_range,
            'new_examples': new_examples,
            'new_bad_examples': new_bad
        }

        update_path = os.path.join(RUN_SAVE_DIR, f'input_suggestion_updates_{run_time_temp}_{field}.json')
        with open(update_path, 'w', encoding='utf-8') as f:
            json.dump(updates, f, ensure_ascii=False, indent=2)

        return jsonify({
            'status': 'ok',
            'range': new_range,
            'new_examples': new_examples,
            'new_bad_examples': new_bad
        })

    except Exception as e:
        print(f"[!] Error in update_input_suggestion: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/confirm_suggestion', methods=['POST'])
def confirm_suggestion():
    try:
        data = request.get_json(force=True)
        field_name = data.get('field', 'unknown_field')
        timestamp = data.get('time', int(time.time() * 1000))
        url_part = data.get('url', '')[-30:].replace('/', '_').replace(':', '_')

        print(f"[*] Confirmed suggestion for field: '{field_name}'")

        # Store in memory for immediate test generation use
        CONFIRMED_FIELDS[field_name] = data

        filename = f"confirmation_{timestamp}_{field_name}_{url_part}.json"
        save_path = os.path.join(RUN_SAVE_DIR, filename)
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return jsonify({
            'status': 'success',
            'message': f'Confirmation saved for {field_name}',
            'field': field_name,
            'filename': filename
        })
    except Exception as e:
        print(f"[!] Error in confirm_suggestion: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/events', methods=['POST'])
def events():
    try:
        data = request.get_json(force=True)
        raw_events = data.get('events', [])
        print(f"\n[*] Received {len(raw_events)} events from extension")

        events_path = os.path.join(RUN_SAVE_DIR, 'recorded_events.json')
        with open(events_path, 'w', encoding='utf-8') as f:
            json.dump(raw_events, f, ensure_ascii=False, indent=2)

        # Convert to Katalon format
        katalon_table = convert_to_katalon_format(raw_events)
        katalon_path = os.path.join(RUN_SAVE_DIR, 'katalon_test.html')
        with open(katalon_path, 'w', encoding='utf-8') as f:
            f.write(katalon_table)

        print(f"[+] Saved Katalon Recorder test to {katalon_path}")

        # Launch GUI improver safely
        try:
            show_katalon_improver(katalon_table, katalon_path, raw_events)
        except Exception as gui_err:
            print(f"[!] Note: Could not launch GUI improver ({gui_err}). Test file saved.")

        return jsonify({'status': 'ok', 'saved_events': len(raw_events)})
    except Exception as e:
        print(f"[!] Error in events endpoint: {e}")
        return jsonify({'error': str(e)}), 500


# ==============================================================================
# Katalon HTML Conversion
# ==============================================================================

def convert_to_katalon_format(events):
    """
    Convert recorded events to a fully valid Katalon Studio / Recorder HTML test.
    GUARANTEES that the scenario ALWAYS starts with an 'open' command.
    """
    extension_events = {
        'suggest_inputs_start', 'suggest_inputs_complete',
        'suggestion_question_mark_click', 'suggestion_modal_open',
        'suggestion_modal_cancel', 'suggestion_modal_confirm',
        'suggestion_modal_submit_start', 'suggestion_modal_submit_success',
        'suggestion_modal_submit_failure'
    }

    extension_prefixes = (
        'edit-range', 'edit-examples', 'edit-bad-examples',
        'edit-cancel', 'edit-confirm', 'edit-submit',
        'input-suggestion-modal', 'suggest-inputs', 'llm-suggestion'
    )

    valid_events = []
    initial_url = "https://www.google.com/"

    for ev in events:
        ev_type = ev.get('type', '')
        el_id = ev.get('id', '')
        ev_url = ev.get('url', '')

        if ev_type in extension_events:
            continue
        if any(el_id.startswith(p) for p in extension_prefixes):
            continue
        if ev_url.startswith('chrome-extension://'):
            continue

        if ev_url and not initial_url:
            initial_url = ev_url

        valid_events.append(ev)

    if valid_events and valid_events[0].get('url'):
        initial_url = valid_events[0]['url']

    # Build commands list
    katalon_commands = []

    # Command #1 MUST ALWAYS be 'open'
    katalon_commands.append({
        'command': 'open',
        'target': initial_url,
        'value': ''
    })

    previous_time = valid_events[0].get('time') if valid_events else None

    for ev in valid_events:
        ev_type = ev.get('type', '')
        tag = ev.get('tag', '').lower()
        el_id = ev.get('id', '')
        xpath = ev.get('xpath', '')
        value = ev.get('value', '')
        url = ev.get('url', '')
        curr_time = ev.get('time')

        # Add pause if significant time gap
        if previous_time and curr_time:
            time_diff = curr_time - previous_time
            if time_diff > 1200:
                wait_sec = round(time_diff / 1000, 1)
                katalon_commands.append({
                    'command': 'pause',
                    'target': str(int(time_diff)),
                    'value': f'Wait {wait_sec}s'
                })

        # Determine target selector
        if el_id:
            target = f"id={el_id}"
        elif xpath:
            target = f"xpath={xpath}"
        elif tag:
            target = f"css={tag}"
        else:
            target = ""

        # Map event to command
        if ev_type == 'verification_command':
            katalon_commands.append({
                'command': ev.get('command', 'verifyElementPresent'),
                'target': ev.get('target', target),
                'value': ev.get('value', '')
            })
            previous_time = curr_time

        elif ev_type == 'click':
            katalon_commands.append({
                'command': 'click',
                'target': target,
                'value': ''
            })
            previous_time = curr_time

        elif ev_type in ('change', 'input'):
            if tag in ('input', 'textarea') and value is not None:
                katalon_commands.append({
                    'command': 'type',
                    'target': target,
                    'value': str(value)
                })
                previous_time = curr_time

        elif ev_type == 'submit':
            katalon_commands.append({
                'command': 'submit',
                'target': target,
                'value': ''
            })
            previous_time = curr_time

        elif ev_type in ('pageload', 'popstate', 'hashchange'):
            if url and url != initial_url:
                katalon_commands.append({
                    'command': 'open',
                    'target': url,
                    'value': ''
                })
                previous_time = curr_time

    # Base URL for Selenium
    parsed = urlparse(initial_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else "https://www.google.com"

    # Generate table HTML
    rows_html = []
    for cmd in katalon_commands:
        rows_html.append(f"""<tr>
    <td>{cmd['command']}</td>
    <td>{cmd['target']}</td>
    <td>{cmd['value']}</td>
</tr>""")

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <link rel="selenium.base" href="{base_url}">
    <title>Recorded Test</title>
</head>
<body>
<table cellpadding="1" cellspacing="1" border="1">
<thead>
<tr><td rowspan="1" colspan="3">Recorded Test</td></tr>
</thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</body>
</html>"""

    return html_content


# ==============================================================================
# Katalon AI Improver GUI
# ==============================================================================

class KatalonTestImprover:
    def __init__(self, katalon_html, katalon_path, events_data):
        self.katalon_html = katalon_html
        self.katalon_path = katalon_path
        self.events_data = events_data
        self.current_katalon = katalon_html
        self.chat_history = []

        self.root = tk.Tk()
        self.root.title("Katalon Test Improver")
        self.root.geometry("1100x700")

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.setup_ui()

    def on_closing(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        title_label = ttk.Label(main_frame, text="Katalon Test AI Improver", font=('Arial', 14, 'bold'))
        title_label.pack(pady=(0, 10))

        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Current Test
        test_frame = ttk.Frame(notebook)
        notebook.add(test_frame, text="Current Test")

        self.test_display = scrolledtext.ScrolledText(test_frame, height=18, wrap=tk.WORD)
        self.test_display.pack(fill=tk.BOTH, expand=True, pady=5)
        self.test_display.insert(tk.END, self.extract_table_content(self.katalon_html))

        btn_frame = ttk.Frame(test_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Save Test", command=self.save_test).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Open in Browser", command=self.open_browser).pack(side=tk.LEFT, padx=5)

        # Tab 2: AI Chat
        chat_frame = ttk.Frame(notebook)
        notebook.add(chat_frame, text="AI Assistant")

        self.chat_display = scrolledtext.ScrolledText(chat_frame, height=18, wrap=tk.WORD)
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=5)

        chat_input_frame = ttk.Frame(chat_frame)
        chat_input_frame.pack(fill=tk.X, pady=5)
        self.chat_input = ttk.Entry(chat_input_frame)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        ttk.Button(chat_input_frame, text="Ask AI", command=self.send_ai_message).pack(side=tk.RIGHT)

    def extract_table_content(self, html):
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        if not table:
            return "No test commands found."
        lines = []
        for row in table.find_all('tr')[1:]:
            cells = [td.get_text(strip=True) for td in row.find_all('td')]
            if len(cells) >= 3:
                lines.append(f"{cells[0]:<15} | {cells[1]:<35} | {cells[2]}")
        return "\n".join(lines)

    def save_test(self):
        with open(self.katalon_path, 'w', encoding='utf-8') as f:
            f.write(self.current_katalon)
        messagebox.showinfo("Saved", "Katalon test script saved successfully!")

    def open_browser(self):
        temp_path = os.path.join(RUN_SAVE_DIR, 'temp_katalon_view.html')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(self.current_katalon)
        webbrowser.open(f'file://{os.path.abspath(temp_path)}')

    def send_ai_message(self):
        user_msg = self.chat_input.get().strip()
        if not user_msg:
            return
        self.chat_display.insert(tk.END, f"\nUser: {user_msg}\n")
        self.chat_input.delete(0, tk.END)

        def query():
            try:
                answer = call_llm([
                    {"role": "system", "content": "You are a QA automation assistant."},
                    {"role": "user", "content": f"Test script:\n{self.extract_table_content(self.current_katalon)}\n\nQuestion: {user_msg}"}
                ], max_tokens=600)
                self.root.after(0, lambda: self.chat_display.insert(tk.END, f"\nAI: {answer}\n"))
            except Exception as e:
                self.root.after(0, lambda: self.chat_display.insert(tk.END, f"\nError: {e}\n"))

        threading.Thread(target=query, daemon=True).start()

    def show(self):
        self.root.mainloop()


def show_katalon_improver(katalon_html, katalon_path, events_data):
    def run_gui():
        try:
            improver = KatalonTestImprover(katalon_html, katalon_path, events_data)
            improver.show()
        except Exception as e:
            print(f"[!] GUI Improver error: {e}")
    threading.Thread(target=run_gui, daemon=True).start()


# ==============================================================================
# Combinatorial Test Case Generation
# ==============================================================================

@app.route('/generate_test_cases', methods=['POST'])
def generate_test_cases_endpoint():
    try:
        data = request.get_json(force=True)
        katalon_path = data.get('katalon_path') or os.path.join(RUN_SAVE_DIR, 'katalon_test.html')
        output_csv_path = data.get('output_csv_path') or os.path.join(RUN_SAVE_DIR, 'generated_test_cases.csv')
        num_test_cases = int(data.get('num_test_cases', 10))

        if not os.path.exists(katalon_path):
            return jsonify({'error': f'Katalon file not found: {katalon_path}'}), 404

        with open(katalon_path, 'r', encoding='utf-8') as f:
            html = f.read()

        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        if not table:
            return jsonify({'error': 'No table found in Katalon test'}), 400

        # Extract all type commands
        type_fields = {}
        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 3:
                cmd = cells[0].get_text(strip=True)
                tgt = cells[1].get_text(strip=True)
                val = cells[2].get_text(strip=True)
                if cmd == 'type' and tgt:
                    field_key = tgt.replace('id=', '').replace('name=', '').replace('xpath=', '')
                    if field_key not in type_fields:
                        type_fields[field_key] = val

        if not type_fields:
            return jsonify({'error': 'No input/type fields found in test'}), 400

        # Collect examples for each field
        field_examples = {}
        for f_name, default_val in type_fields.items():
            if f_name in CONFIRMED_FIELDS and CONFIRMED_FIELDS[f_name].get('examples'):
                field_examples[f_name] = CONFIRMED_FIELDS[f_name]['examples']
            else:
                field_examples[f_name] = [f"{default_val}_{i+1}" if default_val else f"test_{i+1}" for i in range(5)]

        headers = list(field_examples.keys())
        example_lists = [field_examples[h] for h in headers]
        all_combos = list(product(*example_lists))

        selected_combos = all_combos[:num_test_cases]

        with open(output_csv_path, 'w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(headers)
            writer.writerows(selected_combos)

        print(f"[+] Generated {len(selected_combos)} test cases in {output_csv_path}")
        return jsonify({
            'status': 'success',
            'csv_path': output_csv_path,
            'count': len(selected_combos),
            'fields': headers
        })

    except Exception as e:
        print(f"[!] Error in generate_test_cases: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/shutdown', methods=['POST'])
def shutdown():
    print("[*] Shutdown request received.")
    threading.Thread(target=lambda: (time.sleep(0.5), os._exit(0))).start()
    return 'Server shutting down...'


if __name__ == '__main__':
    if not check_port_available(server_port):
        print(f"[!] Error: Port {server_port} is already in use!")
        sys.exit(1)

    print(f"\n[+] Server listening on http://localhost:{server_port}")
    print("[+] Ready for Chrome Extension requests.\n")
    try:
        app.run(host='127.0.0.1', port=server_port, debug=False)
    except KeyboardInterrupt:
        print("\n[*] Server stopped by user.")
