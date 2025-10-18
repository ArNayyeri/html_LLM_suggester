from flask import Flask, request
from flask_cors import CORS
import os
import json
import re
from ollama import chat
import time
import uuid
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup
from openai import OpenAI
import tiktoken
from deep_translator import GoogleTranslator
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import webbrowser
import csv
import math
from collections import defaultdict
from itertools import product
from urllib.parse import urlparse
import socket
import sys


def check_port_available(port):
    """Check if a port is available for use"""
    try:
        # Create a socket object
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)  # 1 second timeout

        # Try to bind to the port
        result = sock.bind(('localhost', port))
        sock.close()
        return True
    except OSError:
        return False


# Use cl100k_base encoding (close approximation for Llama)
encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text):
    return len(encoding.encode(text))


ollama_url = 'http://localhost:11434/v1'
openrouter_url = 'https://openrouter.ai/api/v1'
cerebras_url = "https://api.cerebras.ai/v1"

site = input(
    "Do you want to use local or api? (local/api): "
).strip().lower()

if site == 'local':
    token = 'ollama'
    url = ollama_url
    model_name = 'llama3.1'
    is_local = True

elif site == 'api':
    model = input("Cerebras/OpenRouter: ").strip()
    token = input("Enter your API token: ").strip()
    if model.lower() == 'openrouter':
        url = openrouter_url
        model_name = 'mistralai/mistral-small-3.2-24b-instruct:free'
    else:
        url = cerebras_url
        model_name="llama-3.3-70b"
    is_local = False

else:
    print("Invalid input. Please enter 'local' or 'api'.")
    exit(1)

app = Flask(__name__)
CORS(app)
SAVE_DIR = "snapshots"

# Create a unique run directory inside snapshots for each server run
_run_time = int(time.time())
_run_uid = uuid.uuid4().hex[:8]
RUN_ID = f"run_{_run_time}_{_run_uid}"
RUN_SAVE_DIR = os.path.join(SAVE_DIR, RUN_ID)
os.makedirs(RUN_SAVE_DIR, exist_ok=True)

client = OpenAI(
    base_url=url,
    api_key=token)


class FormField(BaseModel):
    name: str = Field(...,
                      description="The 'name' attribute of the input or textarea")
    id: str = Field(..., description="The 'id' attribute of the element")
    type: str = Field(...,
                      description="Input type (text, password, etc.) or 'textarea'")
    limitations: str = Field(
        ..., description="Validation rules inferred from attributes like minlength, maxlength, pattern, placeholder in English")
    examples: list[str] = Field(...,
                                description="Five example values that satisfy the limitations")
    bad_examples: list[str] = Field(...,
                                    description="Five example values that violate the limitations for negative testing")


class ExampleSchema(BaseModel):
    examples: list[str] = Field(...,
                                description="Five example values that satisfy the range")
    bad_examples: list[str] = Field(...,
                                    description="Five example values that violate the range for negative testing")


def translate_to_persian(english_text):
    """Translate English limitations to Persian using deep_translator"""
    try:
        translator = GoogleTranslator(source='en', target='fa')
        return translator.translate(english_text)
    except Exception as e:
        print(f"Translation error: {e}")
        return english_text  # Return original if translation fails


def translate_to_english(persian_text):
    """Translate Persian text to English using deep_translator"""
    try:
        translator = GoogleTranslator(source='fa', target='en')
        return translator.translate(persian_text)
    except Exception as e:
        print(f"Translation error: {e}")
        return persian_text  # Return original if translation fails


@app.route('/snapshot', methods=['POST'])
def snapshot():
    data = request.get_json()
    print("Received snapshot:", data['eventType'], data['time'])
    base = f"{data['eventType']}_{data['time']}"
    html_path = os.path.join(RUN_SAVE_DIR, f"{base}.html")
    css_path = os.path.join(RUN_SAVE_DIR, f"{base}.css")
    event_path = os.path.join(RUN_SAVE_DIR, f"{base}_event.json")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(data['html'])
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(data['css'])

    if data['eventType'] == 'pageload':
        with open(event_path, "w", encoding="utf-8") as f:
            json.dump({"eventType": "pageload",
                       "time": data['time'],
                       "url": data['url'], }, f, ensure_ascii=False, indent=2)
    elif 'event' in data and data['event'] is not None:
        with open(event_path, "w", encoding="utf-8") as f:
            json.dump(data['event'], f, ensure_ascii=False, indent=2)

    return 'ok'


def preserve_structure(soup, target_element):
    """Preserve parent structure up to target element"""
    parents = []
    current = target_element.parent

    while current and current.name:
        parents.append(current)
        current = current.parent

    return list(reversed(parents))


def truncate_with_context(soup, target_element, max_tokens=100000):
    """Try to keep target element with as much context as possible"""
    # Get parent structure
    parents = preserve_structure(soup, target_element)

    # Start with target element
    essential_html = str(target_element)
    token_count = count_tokens(essential_html)

    if token_count >= max_tokens:
        return None  # Target element itself is too large

    # Add parent structure
    for parent in parents:
        # Create a copy of parent with minimal content
        parent_copy = soup.new_tag(parent.name)
        for attr_name, attr_value in parent.attrs.items():
            parent_copy[attr_name] = attr_value

        # Test if adding this parent keeps us under limit
        temp_structure = str(parent_copy).replace(
            '></', f'>{essential_html}</')
        # Leave room for siblings
        if count_tokens(temp_structure) < max_tokens * 0.8:
            essential_html = temp_structure
            token_count = count_tokens(essential_html)

    # Try to add siblings and other content
    remaining_tokens = max_tokens - token_count

    # Add content before target
    before_content = get_content_before(
        soup, target_element, remaining_tokens // 2)

    # Add content after target
    after_content = get_content_after(
        soup, target_element, remaining_tokens // 2)

    # Combine everything
    if before_content or after_content:
        # Create new soup with combined content
        new_soup = BeautifulSoup(
            f"{before_content}{essential_html}{after_content}", 'html.parser')
        return str(new_soup)

    return essential_html


def get_content_before(soup, target_element, max_tokens):
    """Get content before target element within token limit"""
    # Find all elements before target
    all_elements = soup.find_all()
    target_index = all_elements.index(target_element)

    before_elements = all_elements[:target_index]
    before_elements.reverse()  # Start from closest to target

    collected_content = []
    current_tokens = 0

    for element in before_elements:
        element_html = str(element)
        element_tokens = count_tokens(element_html)

        if current_tokens + element_tokens <= max_tokens:
            collected_content.insert(0, element_html)  # Insert at beginning
            current_tokens += element_tokens
        else:
            break

    return ''.join(collected_content)


def get_content_after(soup, target_element, max_tokens):
    """Get content after target element within token limit"""
    # Find all elements after target
    all_elements = soup.find_all()
    target_index = all_elements.index(target_element)

    after_elements = all_elements[target_index + 1:]

    collected_content = []
    current_tokens = 0

    for element in after_elements:
        element_html = str(element)
        element_tokens = count_tokens(element_html)

        if current_tokens + element_tokens <= max_tokens:
            collected_content.append(element_html)
            current_tokens += element_tokens
        else:
            break

    return ''.join(collected_content)


def is_element_visible(element):
    style = element.get('style', '')
    if style:
        style_lower = style.lower()
        # Check for display:none or visibility:hidden
        if 'display:none' in style_lower.replace(' ', '') or 'display: none' in style_lower:
            return False
        if 'visibility:hidden' in style_lower.replace(' ', '') or 'visibility: hidden' in style_lower:
            return False

    # Check for hidden attribute
    if element.get('hidden') is not None:
        return False

    return True


def suggest_input_values(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Find all <input> and <textarea> elements
    elements = soup.find_all(['input', 'textarea'])
    valid_types = [
        'text',
        'password',
        'email',
        'number',
        'date',
        'datetime-local',
        'month',
        'range',
        'search',
        'tel',
        'time',
        'url',
        'week'
    ]
    # Filter out elements with invalid types and invisible elements
    elements = [
        el for el in elements if (
            el.name == 'textarea' or
            (el.name ==
             'input' and 'type' in el.attrs and el['type'] in valid_types)
        ) and is_element_visible(el)
    ]

    # Extract IDs and names (only if they exist)
    target_identifiers = []
    for el in elements:
        if 'id' in el.attrs:
            target_identifiers.append(('id', el['id']))
        elif 'name' in el.attrs:
            target_identifiers.append(('name', el['name']))

    extracted_data = []
    for identifier_type, identifier_value in target_identifiers:
        if identifier_type == 'id':
            target_element = soup.find(id=identifier_value)
        else:  # name
            target_element = soup.find(attrs={'name': identifier_value})
        # If the web is more than 100k tokens,
        # it will be considered as an input within 100k tokens from where the desired input ID is.
        if count_tokens(html) > 100000:
            target_html = truncate_with_context(
                soup, target_element,max_tokens=100000)
        else:
            target_html = html
        # Build the prompt for structured extraction

        system_msg = {
            "role": "system",
            "content": (
                "You are an HTML parser. You receive HTML below and process only the element whose id or name equals the specified value. "
                "For that element, create a JSON object with keys: name, id, type, limitations, examples, and bad_examples. "
                "- name: The value of the 'name' attribute.\n"
                "- id: The value of the 'id' attribute (use the name if id doesn't exist).\n"
                "- type: Input type (text, password, etc.) or 'textarea'.\n"
                "- limitations: Validation rules extracted from attributes like minlength, maxlength, pattern, or placeholder. This description should be written in English as complete sentences.\n"
                "- examples: 5 example values that match these limitations and would be ACCEPTED by the field validation.\n"
                "- bad_examples: 5 example values that VIOLATE these limitations and would be REJECTED by the field validation (for negative testing).\n"
                "Keep the keys constant but write limitation values in English.\n"
                "Provide output only as a JSON object matching the Pydantic schema.\n"
                f"Process only and exclusively the element with {'id' if identifier_type == 'id' else 'name'} equal to '{identifier_value}'. Do not include any other element in the output.\n"
                "Here are examples for understanding:\n\n"

                "Example 1:\n"
                "Input:\n"
                "<input id=\"password\" name=\"password\" type=\"password\" minlength=\"8\" />\n"
                "Output:\n"
                "{\n"
                "  \"name\": \"password\",\n"
                "  \"id\": \"password\",\n"
                "  \"type\": \"password\",\n"
                "  \"examples\": [\"password123\", \"MySecure2024\", \"TestPass99\", \"AdminLogin1\", \"UserAccess88\"],\n"
                "  \"bad_examples\": [\"123\", \"pass\", \"1234567\", \"a\", \"\"],\n"
                "  \"limitations\": \"The password must be at least 8 characters long. English lowercase or uppercase letters are allowed. Numbers and other common characters can also be used to increase security.\"\n"
                "}\n\n"

                "Example 2:\n"
                "Input:\n"
                "<input id=\"email\" name=\"email\" type=\"email\" />\n"
                "Output:\n"
                "{\n"
                "  \"name\": \"email\",\n"
                "  \"id\": \"email\",\n"
                "  \"type\": \"email\",\n"
                "  \"examples\": [\"user@example.com\", \"test.email@domain.org\", \"admin@company.co.uk\", \"developer@site.net\", \"contact@business.info\"],\n"
                "  \"bad_examples\": [\"invalid-email\", \"@domain.com\", \"user@\", \"plaintext\", \"user.domain.com\"],\n"
                "  \"limitations\": \"Must be a valid email address with @ symbol and proper domain format.\"\n"
                "}\n\n"

                "Example 3:\n"
                "Input:\n"
                "<input id=\"phone\" name=\"phone\" type=\"text\" pattern=\"\\d{11}\" />\n"
                "Output:\n"
                "{\n"
                "  \"name\": \"phone\",\n"
                "  \"id\": \"phone\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"09123456789\", \"09351234567\", \"09221234567\", \"09901234567\", \"09111111111\"],\n"
                "  \"bad_examples\": [\"0912345678\", \"091234567890\", \"abc1234567\", \"09-123-456\", \"123456789\"],\n"
                "  \"limitations\": \"The phone number must contain exactly 11 numeric digits with no spaces, symbols, or letters allowed.\"\n"
                "}\n"
            )
        }

        user_msg = {"role": "user", "content": target_html}

        # Call the LLM with the JSON schema
        if is_local:
            response = chat(model="llama3.1",
                            messages=[system_msg, user_msg],
                            format=FormField.model_json_schema(),
                            options={"num_ctx": 32768}
                            )
            raw = response['message']['content']
        else:
            response = client.beta.chat.completions.parse(
                model=model_name,
                messages=[system_msg, user_msg],
                response_format=FormField,
            )
            raw = response.choices[0].message.content

            # Parse the structured JSON content
        data = json.loads(raw)

        # Translate limitations to Persian
        data['limitations'] = translate_to_persian(data['limitations'])

        extracted_data.append(data)
    return {'fields': extracted_data}


class KatalonTestImprover:
    def __init__(self, katalon_html, katalon_path, events_data):
        self.katalon_html = katalon_html
        self.katalon_path = katalon_path
        self.events_data = events_data
        self.current_katalon = katalon_html

        # Add chat history to maintain context
        self.chat_history = []

        # Create the main window
        self.root = tk.Tk()
        self.root.title("Katalon Test Improver")
        self.root.geometry("1200x800")

        # Handle window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.setup_ui()
        self.get_initial_suggestions()

    def on_closing(self):
        """Handle window close event and shutdown all applications"""
        try:
            # Ask for confirmation
            if messagebox.askokcancel("Quit", "Do you want to quit? This will close all applications."):
                print(
                    "KatalonTestImprover window closed. Shutting down all applications...")

                # Destroy the tkinter window
                self.root.destroy()

                # Shutdown the Flask server and exit the entire application
                import threading

                def shutdown_app():
                    try:
                        # Send shutdown signal to Flask server
                        import requests
                        requests.post(
                            'http://localhost:5000/shutdown', timeout=1)
                    except:
                        pass

                    # Force exit the entire application
                    os._exit(0)

                # Run shutdown in a separate thread to avoid blocking
                threading.Thread(target=shutdown_app, daemon=True).start()

        except Exception as e:
            print(f"Error during shutdown: {e}")
            # Force exit if normal shutdown fails
            os._exit(0)

    def add_to_chat_history(self, role, content):
        """Add message to chat history for context"""
        self.chat_history.append({"role": role, "content": content})
        # Keep only last 20 messages to avoid token limit issues
        if len(self.chat_history) > 20:
            self.chat_history = self.chat_history[-20:]

    def setup_ui(self):
        # Create main frame
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Title
        title_label = ttk.Label(main_frame, text="Katalon Test Improvement Assistant",
                                font=('Arial', 16, 'bold'))
        title_label.pack(pady=(0, 10))

        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Current Test
        test_frame = ttk.Frame(notebook)
        notebook.add(test_frame, text="Current Test")

        # Current test display
        ttk.Label(test_frame, text="Current Katalon Test:", font=(
            'Arial', 12, 'bold')).pack(anchor=tk.W, pady=(0, 5))

        self.test_display = scrolledtext.ScrolledText(
            test_frame, height=15, wrap=tk.WORD)
        self.test_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.test_display.insert(
            tk.END, self.extract_table_content(self.katalon_html))

        # Buttons frame for test tab
        test_buttons_frame = ttk.Frame(test_frame)
        test_buttons_frame.pack(fill=tk.X, pady=5)

        ttk.Button(test_buttons_frame, text="Open in Browser",
                   command=self.open_in_browser).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(test_buttons_frame, text="Save Current Test",
                   command=self.save_current_test).pack(side=tk.LEFT, padx=5)
        ttk.Button(test_buttons_frame, text="Regenerate Test",
                   command=self.regenerate_test).pack(side=tk.LEFT, padx=5)

        # Tab 2: Chat with AI
        chat_frame = ttk.Frame(notebook)
        notebook.add(chat_frame, text="AI Assistant")

        # AI suggestions display
        ttk.Label(chat_frame, text="AI Suggestions & Chat:", font=(
            'Arial', 12, 'bold')).pack(anchor=tk.W, pady=(0, 5))

        self.chat_display = scrolledtext.ScrolledText(
            chat_frame, height=20, wrap=tk.WORD, state=tk.DISABLED)
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # User input frame
        input_frame = ttk.Frame(chat_frame)
        input_frame.pack(fill=tk.X, pady=5)

        ttk.Label(input_frame, text="Your message:").pack(anchor=tk.W)

        self.user_input = tk.Text(input_frame, height=3, wrap=tk.WORD)
        self.user_input.pack(fill=tk.X, pady=(5, 5))

        # Buttons frame for chat
        chat_buttons_frame = ttk.Frame(input_frame)
        chat_buttons_frame.pack(fill=tk.X, pady=5)

        ttk.Button(chat_buttons_frame, text="Send Message",
                   command=self.send_message).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(chat_buttons_frame, text="Apply AI Suggestions",
                   command=self.apply_suggestions).pack(side=tk.LEFT, padx=5)
        ttk.Button(chat_buttons_frame, text="Get New Suggestions",
                   command=self.get_new_suggestions).pack(side=tk.LEFT, padx=5)
        ttk.Button(chat_buttons_frame, text="Clear History",
                   command=self.clear_chat_history).pack(side=tk.LEFT, padx=5)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, pady=(10, 0))

        # Bind Enter key to send message
        self.user_input.bind('<Control-Return>', lambda e: self.send_message())

    def extract_table_content(self, html):
        """Extract just the table content for display"""
        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table')
        if table:
            rows = table.find_all('tr')
            content = []
            for row in rows[1:]:  # Skip header row
                cells = row.find_all('td')
                if len(cells) >= 3:
                    command = cells[0].get_text().strip()
                    target = cells[1].get_text().strip()
                    value = cells[2].get_text().strip()
                    content.append(f"{command:<15} | {target:<30} | {value}")
            return '\n'.join(content)
        return "No table found"

    def add_chat_message(self, sender, message, color="black"):
        """Add a message to the chat display"""
        self.chat_display.config(state=tk.NORMAL)
        self.chat_display.insert(tk.END, f"\n{sender}: ", f"{sender.lower()}")
        self.chat_display.insert(tk.END, f"{message}\n")

        # Configure tags for different senders
        self.chat_display.tag_configure(
            "ai", foreground="blue", font=('Arial', 10, 'bold'))
        self.chat_display.tag_configure(
            "user", foreground="green", font=('Arial', 10, 'bold'))
        self.chat_display.tag_configure(
            "system", foreground="red", font=('Arial', 10, 'bold'))

        self.chat_display.config(state=tk.DISABLED)
        self.chat_display.see(tk.END)

    def get_initial_suggestions(self):
        """Get initial AI suggestions for the test"""
        self.status_var.set("Getting AI suggestions...")
        self.add_chat_message(
            "System", "Analyzing your Katalon test and generating suggestions...")

        def get_suggestions():
            try:
                current_test = self.extract_table_content(self.current_katalon)

                prompt = f"""You are a test automation expert. Analyze this Katalon Recorder test and provide specific suggestions for improvement:

Current Test:
{current_test}

Please analyze and suggest improvements in these areas:
1. **Wait Times**: Are the pause commands appropriate? Too long or too short?
2. **Element Locators**: Are xpath selectors reliable? Should we use id or css selectors instead?
3. **Test Structure**: Is the test flow logical and maintainable?
4. **Missing Steps**: Are there any verification steps or assertions missing?
5. **Optimization**: Can any steps be combined or simplified?

Provide specific, actionable suggestions in Katalon command format only. Do not provide explanations or code - just suggest commands in this format:
command | target | value

Example suggestions:
- assertTitle | Google | 
- verifyElementPresent | id=search-button |
- pause | 2000 | Wait 2s
- type | id=username | testuser
- click | css=.submit-btn |"""

                # Add system context to chat history
                system_context = f"I am analyzing a Katalon test with the following structure:\n{current_test}"
                self.add_to_chat_history("system", system_context)
                self.add_to_chat_history("user", prompt)

                if is_local:
                    response = chat(model="llama3.1",
                                    messages=self.chat_history)
                    suggestions = response['message']['content']
                else:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=self.chat_history,
                        temperature=0.7,
                        max_tokens=1000
                    )
                    suggestions = response.choices[0].message.content

                # Add AI response to history
                self.add_to_chat_history("assistant", suggestions)

                self.root.after(
                    0, lambda: self.add_chat_message("AI", suggestions))
                self.root.after(0, lambda: self.status_var.set("Ready"))

            except Exception as e:
                self.root.after(0, lambda: self.add_chat_message(
                    "System", f"Error getting suggestions: {str(e)}"))
                self.root.after(0, lambda: self.status_var.set("Error"))

        threading.Thread(target=get_suggestions, daemon=True).start()

    def send_message(self):
        """Send user message to AI"""
        message = self.user_input.get(1.0, tk.END).strip()
        if not message:
            return

        self.add_chat_message("User", message)
        self.user_input.delete(1.0, tk.END)
        self.status_var.set("AI is thinking...")

        def get_response():
            try:
                current_test = self.extract_table_content(self.current_katalon)

                # Create context-aware prompt that includes current test state
                contextual_prompt = f"""{message}"""

                # Add user message to history
                self.add_to_chat_history("user", contextual_prompt)

                if is_local:
                    response = chat(model="llama3.1",
                                    messages=self.chat_history)
                    ai_response = response['message']['content']
                else:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=self.chat_history,
                        temperature=0.7,
                        max_tokens=1000
                    )
                    ai_response = response.choices[0].message.content

                # Add AI response to history
                self.add_to_chat_history("assistant", ai_response)

                self.root.after(
                    0, lambda: self.add_chat_message("AI", ai_response))
                self.root.after(0, lambda: self.status_var.set("Ready"))

            except Exception as e:
                self.root.after(0, lambda: self.add_chat_message(
                    "System", f"Error: {str(e)}"))
                self.root.after(0, lambda: self.status_var.set("Error"))

        threading.Thread(target=get_response, daemon=True).start()

    def apply_suggestions(self):
        """Let AI apply its suggestions to improve the test"""
        self.status_var.set("Applying AI suggestions...")

        def apply_improvements():
            try:
                current_test = self.extract_table_content(self.current_katalon)

                prompt = f"""Based on our previous conversation and suggestions, please improve this Katalon test by applying the best practices we discussed:

Current Test:
{current_test}

Please generate an improved version of this test considering:
1. Our previous suggestions and discussion
2. Better element locators (prefer id > css > xpath)
3. Appropriate wait times (not too long, not too short)
4. Added verification steps where appropriate
5. Better test structure

Return the improved test in the same format as the input, with each line containing:
command | target | value

Only return the improved test commands, nothing else."""

                # Add to chat history
                self.add_to_chat_history("user", prompt)

                if is_local:
                    response = chat(model="llama3.1",
                                    messages=self.chat_history)
                    improved_test = response['message']['content']
                else:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=self.chat_history,
                        temperature=0.3,
                        max_tokens=2000
                    )
                    improved_test = response.choices[0].message.content

                # Add AI response to history
                self.add_to_chat_history("assistant", improved_test)

                # Convert improved test back to HTML format
                new_html = self.convert_text_to_katalon_html(improved_test)
                self.current_katalon = new_html

                self.root.after(0, lambda: self.update_test_display())
                self.root.after(0, lambda: self.add_chat_message(
                    "AI", "Test has been improved based on our previous discussion! Check the 'Current Test' tab to see the changes."))
                self.root.after(
                    0, lambda: self.status_var.set("Test improved"))

            except Exception as e:
                self.root.after(0, lambda: self.add_chat_message(
                    "System", f"Error applying suggestions: {str(e)}"))
                self.root.after(0, lambda: self.status_var.set("Error"))

        threading.Thread(target=apply_improvements, daemon=True).start()

    def get_new_suggestions(self):
        """Get fresh AI suggestions while maintaining context"""
        self.status_var.set("Getting new suggestions...")

        def get_fresh_suggestions():
            try:
                current_test = self.extract_table_content(self.current_katalon)

                prompt = f"""Based on our previous conversation, please analyze the current state of this Katalon test and provide new suggestions:

Current Test:
{current_test}

Considering our previous discussion and any changes made, please provide fresh suggestions for further improvements. Focus on areas we haven't addressed yet or new issues you notice.

Provide specific, actionable suggestions in Katalon command format:
command | target | value"""

                # Add to chat history
                self.add_to_chat_history("user", prompt)

                if is_local:
                    response = chat(model="llama3.1",
                                    messages=self.chat_history)
                    suggestions = response['message']['content']
                else:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=self.chat_history,
                        temperature=0.7,
                        max_tokens=1000
                    )
                    suggestions = response.choices[0].message.content

                # Add AI response to history
                self.add_to_chat_history("assistant", suggestions)

                self.root.after(
                    0, lambda: self.add_chat_message("AI", f"Fresh suggestions based on our conversation:\n{suggestions}"))
                self.root.after(0, lambda: self.status_var.set("Ready"))

            except Exception as e:
                self.root.after(0, lambda: self.add_chat_message(
                    "System", f"Error getting new suggestions: {str(e)}"))
                self.root.after(0, lambda: self.status_var.set("Error"))

        threading.Thread(target=get_fresh_suggestions, daemon=True).start()

    def convert_text_to_katalon_html(self, text_commands):
        """Convert text commands back to Katalon HTML format"""
        lines = text_commands.strip().split('\n')
        rows = []

        for line in lines:
            line = line.strip()
            if '|' in line:
                parts = [part.strip() for part in line.split('|')]
                if len(parts) >= 3:
                    command, target, value = parts[0], parts[1], parts[2]
                    rows.append(f'''<tr>
    <td>{command}</td>
    <td>{target}</td>
    <td>{value}</td>
</tr>''')

        # Get base URL from original HTML
        soup = BeautifulSoup(self.katalon_html, 'html.parser')
        base_link = soup.find('link', rel='selenium.base')
        base_url = base_link['href'] if base_link else "http://localhost:3000"

        html_template = '''<!DOCTYPE html>
<html>
<head>
    <meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
    <link rel="selenium.base" href="{base_url}">
    <title>Improved Katalon Test</title>
</head>
<body>
<table cellpadding="1" cellspacing="1" border="1">
<thead>
<tr><td rowspan="1" colspan="3">Improved Katalon Test</td></tr>
</thead>
<tbody>
{rows}
</tbody>
</table>
</body>
</html>'''

        return html_template.format(base_url=base_url, rows='\n'.join(rows))

    def update_test_display(self):
        """Update the test display with current HTML"""
        self.test_display.delete(1.0, tk.END)
        self.test_display.insert(
            tk.END, self.extract_table_content(self.current_katalon))

    def open_in_browser(self):
        """Open the current test in browser"""
        temp_path = os.path.join(RUN_SAVE_DIR, 'temp_katalon_test.html')
        with open(temp_path, 'w', encoding='utf-8') as f:
            f.write(self.current_katalon)
        webbrowser.open(f'file://{os.path.abspath(temp_path)}')

    def save_current_test(self):
        """Save the current improved test"""
        with open(self.katalon_path, 'w', encoding='utf-8') as f:
            f.write(self.current_katalon)
        self.add_chat_message("System", "Test saved successfully!")
        self.status_var.set("Test saved")

    def regenerate_test(self):
        """Regenerate the test from original events"""
        try:
            new_katalon = convert_to_katalon_format(self.events_data)
            self.current_katalon = new_katalon
            self.update_test_display()
            self.add_chat_message(
                "System", "Test regenerated from original events.")
            self.status_var.set("Test regenerated")
        except Exception as e:
            self.add_chat_message(
                "System", f"Error regenerating test: {str(e)}")

    def clear_chat_history(self):
        """Clear chat history and start fresh"""
        self.chat_history = []
        self.add_chat_message(
            "System", "Chat history cleared. Starting fresh conversation.")
        self.status_var.set("History cleared")

    def show(self):
        """Show the window"""
        self.root.mainloop()


def show_katalon_improver(katalon_html, katalon_path, events_data):
    """Show the Katalon test improver window"""
    def run_improver():
        improver = KatalonTestImprover(katalon_html, katalon_path, events_data)
        improver.show()

    # Run in a separate thread to not block the Flask server
    threading.Thread(target=run_improver, daemon=True).start()


@app.route('/events', methods=['POST'])
def events():
    data = request.get_json()
    events_path = os.path.join(RUN_SAVE_DIR, 'recorded_events.json')
    with open(events_path, 'w', encoding='utf-8') as f:
        json.dump(data['events'], f, ensure_ascii=False, indent=2)

    # Create Katalon Recorder table
    katalon_table = convert_to_katalon_format(data['events'])
    katalon_path = os.path.join(RUN_SAVE_DIR, 'katalon_test.html')
    with open(katalon_path, 'w', encoding='utf-8') as f:
        f.write(katalon_table)

    print(f"Saved {len(data['events'])} events to recorded_events.json")
    print(f"Saved Katalon Recorder table to katalon_test.html")

    # Show the Katalon test improver window
    show_katalon_improver(katalon_table, katalon_path, data['events'])

    return 'ok'


def convert_to_katalon_format(events):
    """Convert recorded events to Katalon Recorder HTML table format"""

    # Filter out extension-specific events
    extension_events = [
        'suggest_inputs_start',
        'suggest_inputs_complete',
        'suggestion_question_mark_click',
        'suggestion_modal_open',
        'suggestion_modal_cancel',
        'suggestion_modal_confirm',
        'suggestion_modal_submit_start',
        'suggestion_modal_submit_success',
        'suggestion_modal_submit_failure'
    ]

    # Extension-specific element IDs or prefixes
    extension_element_ids = [
        'edit-range',
        'edit-examples',
        'edit-cancel',
        'edit-confirm',
        'edit-submit',
        'input-suggestion-modal',
        'suggest-inputs'
    ]

    # Filter valid events and calculate extension durations
    valid_events = []
    extension_durations = {}  # Track extension processing times between events

    for i, event in enumerate(events):
        event_type = event.get('type', '')
        element_id = event.get('id', '')

        # Skip extension-specific event types
        if event_type in extension_events:
            continue

        # Skip clicks on extension-specific elements
        if event_type == 'click' and any(element_id.startswith(prefix) for prefix in extension_element_ids):
            continue

        # Skip typing in extension-specific elements
        if event_type == 'change' and any(element_id.startswith(prefix) for prefix in extension_element_ids):
            continue

        # Skip events from the extension's popup
        if event.get('url', '').startswith('chrome-extension://'):
            continue

        # Calculate extension duration since last valid event
        extension_duration = 0
        if len(valid_events) > 0:
            last_valid_time = valid_events[-1]['time']
            current_time = event.get('time')

            # Find extension events between last valid event and current event
            for check_event in events:
                check_time = check_event.get('time', 0)
                check_type = check_event.get('type', '')

                if last_valid_time < check_time < current_time and check_type in extension_events:
                    if 'duration_ms' in check_event:
                        extension_duration += check_event['duration_ms']

        # Store the extension duration for this event
        extension_durations[len(valid_events)] = extension_duration
        valid_events.append(event)

    # Generate Katalon commands with proper timing
    katalon_commands = []
    previous_time = None

    for i, event in enumerate(valid_events):
        event_type = event.get('type', '')
        tag = event.get('tag', '').lower()
        element_id = event.get('id', '')
        xpath = event.get('xpath', '')
        value = event.get('value', '')
        url = event.get('url', '')
        current_time = event.get('time')

        # Add wait command if there's a significant time gap between actions
        if previous_time and current_time and len(katalon_commands) > 0:
            raw_time_diff = current_time - previous_time
            extension_duration = extension_durations.get(i, 0)
            actual_time_diff = raw_time_diff - extension_duration

            # Only add wait if actual time difference is more than 1 second
            if actual_time_diff > 1000:
                wait_seconds = round(actual_time_diff / 1000, 1)
                katalon_commands.append({
                    'command': 'pause',
                    'target': str(int(actual_time_diff)),
                    'value': f'Wait {wait_seconds}s'
                })

        # Determine target locator
        target = ""
        if element_id:
            target = f"id={element_id}"
        elif xpath:
            target = f"xpath={xpath}"
        else:
            target = f"css={tag}"

        # Convert event types to Katalon commands
        command_added = False

        # Handle verification commands - they already have the target as XPath
        if event_type == 'verification_command':
            command = event.get('command', '')
            # Use the target directly from the event (it's already formatted as xpath=...)
            verification_target = event.get('target', '')
            verification_value = event.get('value', '')

            katalon_commands.append({
                'command': command,
                'target': verification_target,  # This is already xpath=...
                'value': verification_value
            })
            command_added = True

        elif event_type == 'click':
            katalon_commands.append({
                'command': 'click',
                'target': target,
                'value': ''
            })
            command_added = True

        elif event_type == 'change':
            if tag == 'input' or tag == 'textarea':
                katalon_commands.append({
                    'command': 'type',
                    'target': target,
                    'value': value or ''
                })
                command_added = True

        elif event_type == 'submit':
            katalon_commands.append({
                'command': 'submit',
                'target': target,
                'value': ''
            })
            command_added = True

        elif event_type in ['pageload', 'popstate', 'hashchange']:
            if url:
                katalon_commands.append({
                    'command': 'open',
                    'target': url,
                    'value': ''
                })
                command_added = True

        # Update previous_time only if we added a command
        if command_added:
            previous_time = current_time

    # Generate HTML table
    html_template = '''<!DOCTYPE html>
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
{rows}
</tbody>
</table>
</body>
</html>'''

    # Get base URL from first event
    base_url = "http://localhost:3000"
    if valid_events:
        first_url = valid_events[0].get('url', '')
        if first_url:

            parsed = urlparse(first_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Generate table rows
    rows = []
    for cmd in katalon_commands:
        rows.append(f'''<tr>
    <td>{cmd['command']}</td>
    <td>{cmd['target']}</td>
    <td>{cmd['value']}</td>
</tr>''')

    return html_template.format(
        base_url=base_url,
        rows='\n'.join(rows)
    )


@app.route('/suggest_inputs', methods=['POST'])
def suggest_inputs():
    print("Received suggest_inputs request")
    run_time_temp = int(time.time())
    data = request.get_json()
    html = data.get('html', '')
    with open(os.path.join(RUN_SAVE_DIR, f'html_suggest_inputs_{run_time_temp}.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    # return (f"HTML length: {len(html)}")
    try:
        result = suggest_input_values(html)

        result = fix_json_text(result, html)

        with open(os.path.join(RUN_SAVE_DIR, f'result_suggested_inputs_{run_time_temp}.json'), 'w', encoding='utf-8') as f:
            f.write(json.dumps(result, ensure_ascii=False, indent=2))
        return (
            json.dumps(result, ensure_ascii=False, indent=2),
            200,
            {'Content-Type': 'application/json'}
        )
    except Exception as e:
        print(f"Error in suggest_inputs: {e}")
        return (
            json.dumps({'error': 'Error processing request'}),
            500,
            {'Content-Type': 'application/json'}
        )


@app.route('/update_input_suggestion', methods=['POST'])
def update_input_suggestion():
    print("Received update_input_suggestion request")
    run_time_temp = int(time.time())
    data = request.get_json()
    field = data.get('field')
    range_ = data.get('range')
    examples_ = data.get('examples')
    bad_examples_ = data.get('bad_examples', [])
    update_path = os.path.join(
        RUN_SAVE_DIR, f'input_suggestion_updates_{run_time_temp}_{field}.json')

    # --- Load previous update for this field, if any ---
    previous_range = None
    previous_examples = None
    previous_bad_examples = None
    try:
        # Find all previous update files for this field in RUN_SAVE_DIR
        files = [f for f in os.listdir(RUN_SAVE_DIR) if f.startswith(
            'input_suggestion_updates_') and f.endswith(f'_{field}.json')]
        files = sorted(files)  # sort by name (timestamp in name)
        if files:
            last_file = files[-1]
            with open(os.path.join(RUN_SAVE_DIR, last_file), 'r', encoding='utf-8') as f:
                prev = json.load(f)
                previous_range = prev.get('range')
                previous_examples = prev.get('examples')
                previous_bad_examples = prev.get('bad_examples', [])
    except Exception as e:
        print(f"Could not load previous update for field {field}: {e}")

    # --- If range is empty but examples exist, generate range first ---
    if not range_ and (examples_ or bad_examples_):
        try:
            range_generation_prompt = (
                "You are a data analysis expert. Based on the examples below, identify their patterns and limitations "
                "and write a precise and concise description in English about these limitations. "
                "Write only a short phrase in one or two sentences, no more. Example: 'minimum 8 English characters with at least one number and one uppercase letter' or 'valid email' or '10-digit national ID'"
                f"\n\nGood Examples: {json.dumps(examples_, ensure_ascii=False)}"
                f"\n\nBad Examples: {json.dumps(bad_examples_, ensure_ascii=False)}"
                "\n\nPlease write only a short phrase in English that explains the limitations of this data, without any additional explanation."
            )

            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": range_generation_prompt}],
                temperature=0.3,
                max_tokens=100
            )

            english_range = response.choices[0].message.content.strip()
            range_ = translate_to_persian(english_range)
            print(f"Generated range based on examples: {range_}")
            new_examples = examples_
            new_bad_examples = bad_examples_
        except Exception as e:
            print(f"Error generating range from examples: {e}")
            range_ = "محدودیت نامشخص"
    else:
        # First translate Persian range to English for processing
        english_range = range_
        if any('\u0600' <= c <= '\u06FF' for c in range_):  # Check if contains Persian characters
            english_range = translate_to_english(range_)

        # --- Build prompt with previous info if available ---
        prompt = (
            f"You are an intelligent tester. Your job is to generate test data for form fields on websites. "
            f"Here you are given a new limitation (range) for a field:\n"
            f"{english_range}\n"
            "Examples should be similar to values that real users would enter in the form, not just random or artificial data.\n"
            "Bad examples should be invalid inputs that would trigger validation errors and be rejected by the form."
        )
        if examples_ or bad_examples_:
            prompt += (
                f"\nGood examples that users have entered: {json.dumps(examples_, ensure_ascii=False)}\n"
                f"Bad examples provided: {json.dumps(bad_examples_, ensure_ascii=False)}\n"
                "New examples should be similar in style and realism to these examples."
            )
        if previous_range and (previous_examples or previous_bad_examples):
            # Translate previous range to English if needed
            prev_english_range = previous_range
            if any('\u0600' <= c <= '\u06FF' for c in previous_range):
                prev_english_range = translate_to_english(previous_range)

            prompt += (
                "\nSee the previous limitation and examples and generate new examples that are compatible with the new limitation and are not repetitive.\n"
                f"Previous limitation: {prev_english_range}\n"
                f"Previous good examples: {json.dumps(previous_examples, ensure_ascii=False)}\n"
                f"Previous bad examples: {json.dumps(previous_bad_examples, ensure_ascii=False)}\n"
            )
        prompt += (
            "Please generate 5 appropriate GOOD examples and 5 appropriate BAD examples that match this limitation. "
            "Good examples should be valid inputs that would be ACCEPTED by the form validation. "
            "Bad examples should be invalid inputs that would be REJECTED by the form validation and trigger errors. "
            "Output should be in JSON format:\n"
            "{\n"
            "  \"examples\": [\"good1\", \"good2\", \"good3\", \"good4\", \"good5\"],\n"
            "  \"bad_examples\": [\"bad1\", \"bad2\", \"bad3\", \"bad4\", \"bad5\"]\n"
            "}\n\n"

            "Examples:\n\n"

            "Range: minimum 8 English characters\n"
            "Output:\n"
            "{\n"
            "  \"examples\": [\"password\", \"openai123\", \"machinelearning\", \"SecurePass1\", \"AIengineer\"],\n"
            "  \"bad_examples\": [\"pass\", \"123\", \"short\", \"a\", \"1234567\"]\n"
            "}\n\n"

            "Range: valid email address\n"
            "Output:\n"
            "{\n"
            "  \"examples\": [\"test@example.com\", \"user123@gmail.com\", \"admin@company.org\", \"info@site.ir\", \"dev@domain.net\"],\n"
            "  \"bad_examples\": [\"invalid-email\", \"@domain.com\", \"user@\", \"plaintext\", \"email.domain.com\"]\n"
            "}\n\n"

            "Range: exactly 11 numeric digits\n"
            "Output:\n"
            "{\n"
            "  \"examples\": [\"09123456789\", \"09987654321\", \"09335557766\", \"09221234567\", \"09001112233\"],\n"
            "  \"bad_examples\": [\"0912345678\", \"091234567890\", \"abc1234567\", \"09-123-456\", \"123456789\"]\n"
            "}\n"
        )
        try:
            response = client.beta.chat.completions.parse(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format=ExampleSchema,
            )
            raw = response.choices[0].message.content
            data = json.loads(raw)
            new_examples = data['examples']
            new_bad_examples = data['bad_examples']

            if examples_:
                new_examples.extend(examples_)
            if bad_examples_:
                new_bad_examples.extend(bad_examples_)

            # Remove duplicates
            new_examples = list(set(new_examples))
            new_bad_examples = list(set(new_bad_examples))
        except Exception as e:
            return (
                json.dumps({'error': str(e)}),
                500,
                {'Content-Type': 'application/json'}
            )

    updates = {
        'field': field,
        'range': range_,
        'examples': new_examples,
        'bad_examples': new_bad_examples
    }
    with open(update_path, 'w', encoding='utf-8') as f:
        json.dump(updates, f, ensure_ascii=False, indent=2)
    return (
        json.dumps(
            {
                'status': 'ok',
                'new_examples': new_examples,
                'new_bad_examples': new_bad_examples,
                'range': range_
            },
            ensure_ascii=False, indent=2
        ),
        200,
        {'Content-Type': 'application/json'}
    )


def fix_json_text(text, html):
    result = text['fields']
    # Only keep fields that exist as <input> or <textarea> in the HTML
    filtered = []
    for field in result:
        field['range'] = field.pop('limitations')
        if not any(f['id'] == field['id'] or f['name'] == field['name'] for f in filtered):
            filtered.append(field)
    return filtered


@app.route('/confirm_suggestion', methods=['POST'])
def confirm_suggestion():
    data = request.get_json()
    print("Received confirmation for:", data.get('field'))

    # Create a unique filename based on timestamp, field and URL
    field_name = data.get('field', 'unknown_field')
    timestamp = data.get('time', int(time.time()))
    url_part = data.get('url', '')[-30:].replace('/', '_').replace(':', '_')

    # Create a filename and path
    filename = f"confirmation_{timestamp}_{field_name}_{url_part}.json"
    save_path = os.path.join(RUN_SAVE_DIR, filename)

    # Save the confirmation data
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return json.dumps({
        'status': 'success',
        'message': f'Confirmation saved to {filename}',
        'timestamp': timestamp,
        'field': field_name,
    }), 200, {'Content-Type': 'application/json'}


def generate_test_cases_from_katalon(katalon_path, output_csv_path, num_test_cases):
    """
    Generate test cases from Katalon test file using LLM with combinations of all field examples

    Args:
        katalon_path (str): Path to the Katalon test HTML file
        output_csv_path (str): Path to save the output CSV file
        num_test_cases (int): Number of test cases to generate
    """
    try:
        # Read the Katalon test file
        with open(katalon_path, 'r', encoding='utf-8') as f:
            katalon_html = f.read()

        # Parse the HTML to extract test commands
        soup = BeautifulSoup(katalon_html, 'html.parser')
        table = soup.find('table')

        if not table:
            print("No table found in Katalon test file")
            return

        # Extract commands and group by type
        rows = table.find_all('tr')[1:]  # Skip header row
        type_commands = defaultdict(list)

        for row in rows:
            cells = row.find_all('td')
            if len(cells) >= 3:
                command = cells[0].get_text().strip()
                target = cells[1].get_text().strip()
                value = cells[2].get_text().strip()

                # Only process 'type' commands that have values
                if command == 'type' and value:
                    type_commands[target].append({
                        'command': command,
                        'target': target,
                        'value': value
                    })

        if not type_commands:
            print("No 'type' commands with values found in Katalon test")
            return

        print(f"Found {len(type_commands)} different input fields with values")

        # Calculate number of examples per field
        total_fields = len(type_commands)
        examples_per_field = max(1, math.ceil(math.log(
            num_test_cases, total_fields)) if total_fields > 1 else num_test_cases)

        print(f"Generating {examples_per_field} examples per field")

        # Get the directory containing the Katalon file to look for confirmations
        katalon_dir = os.path.dirname(katalon_path)

        # Collect all field data with examples
        field_data = {}
        field_order = []  # To maintain order for CSV headers

        # Process each field
        for target, commands in type_commands.items():
            print(f"Processing field: {target}")

            # Get the original value (use the first one if multiple)
            original_value = commands[0]['value']

            # Determine field type from target
            field_type = "text"  # default
            if "password" in target.lower():
                field_type = "password"
            elif "email" in target.lower():
                field_type = "email"
            elif "phone" in target.lower() or "tel" in target.lower():
                field_type = "tel"
            elif "date" in target.lower():
                field_type = "date"
            elif "number" in target.lower() or "age" in target.lower():
                field_type = "number"

            # Look for confirmation files for this field
            confirmation_data = find_confirmation_for_field(
                katalon_dir, target)

            if confirmation_data:
                print(f"Found confirmation data for field: {target}")
                # Use confirmation data to generate examples
                generated_examples = generate_examples_from_confirmation(
                    target, field_type, original_value, confirmation_data.get(
                        'suggestion', {}), examples_per_field
                )
                description = confirmation_data.get(
                    'range', 'No description available')
                confirmation_found = True
            else:
                print(
                    f"No confirmation found for field: {target}, using default generation")
                # Generate examples using default method
                generated_examples = generate_examples_for_field(
                    target, field_type, original_value, examples_per_field
                )
                description = f"Generated based on field type: {field_type}"
                confirmation_found = False

            # Store field data
            field_name = extract_field_identifier(target)
            field_data[field_name] = {
                'target': target,
                'type': field_type,
                'original_value': original_value,
                'confirmation_found': confirmation_found,
                'description': description,
                'examples': generated_examples
            }
            field_order.append(field_name)

        # Generate all combinations of examples

        # Extract examples lists in order
        examples_lists = [field_data[field]['examples']
                          for field in field_order]

        # Generate all combinations
        combinations = list(product(*examples_lists))

        print(
            f"Generated {len(combinations)} total combinations from {len(field_order)} fields")

        # Limit combinations if too many
        if len(combinations) > num_test_cases:
            print(f"Limiting to first {num_test_cases} combinations")
            combinations = combinations[:num_test_cases]

        # Prepare CSV headers (field names)
        csv_headers = field_order

        # Prepare CSV data (combinations)
        csv_data = combinations

        # Save to CSV
        with open(output_csv_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(csv_headers)
            writer.writerows(csv_data)

        print(f"Test case combinations saved to: {output_csv_path}")
        print(
            f"Generated {len(csv_data)} test case combinations with {len(field_order)} fields")

        # Print summary
        print("\nField Summary:")
        for field in field_order:
            data = field_data[field]
            print(
                f"  {field}: {len(data['examples'])} examples ({'with confirmation' if data['confirmation_found'] else 'generated'})")

    except Exception as e:
        print(f"Error generating test cases: {e}")


def find_confirmation_for_field(katalon_dir, target):
    """
    Find confirmation files for a specific field target

    Args:
        katalon_dir (str): Directory containing the Katalon file
        target (str): Target selector (e.g., "id=username", "xpath=//input[@name='email']")

    Returns:
        dict: Confirmation data if found, None otherwise
    """
    try:
        # Extract field identifier from target
        field_identifier = extract_field_identifier(target)

        # Look for confirmation files in the directory
        confirmation_files = []
        for file in os.listdir(katalon_dir):
            if file.startswith('confirmation_') and file.endswith('.json'):
                confirmation_files.append(file)

        # Search through confirmation files for matching field
        for conf_file in confirmation_files:
            try:
                with open(os.path.join(katalon_dir, conf_file), 'r', encoding='utf-8') as f:
                    conf_data = json.load(f)

                # Check if this confirmation matches our target field
                conf_field = conf_data.get('field', '')
                if field_identifier in conf_field or conf_field in field_identifier:
                    print(f"Found matching confirmation file: {conf_file}")
                    return conf_data

            except Exception as e:
                print(f"Error reading confirmation file {conf_file}: {e}")
                continue

        return None

    except Exception as e:
        print(f"Error finding confirmation for field {target}: {e}")
        return None


def extract_field_identifier(target):
    """
    Extract field identifier from target selector

    Args:
        target (str): Target selector (e.g., "id=username", "xpath=//input[@name='email']")

    Returns:
        str: Field identifier
    """
    try:
        if target.startswith('id='):
            return target.replace('id=', '')
        elif target.startswith('name='):
            return target.replace('name=', '')
        elif 'id=' in target:
            # Extract from xpath or css selector
            id_match = re.search(r'id=[\'"]([^\'"]+)[\'"]', target)
            if id_match:
                return id_match.group(1)
        elif 'name=' in target:
            # Extract from xpath or css selector
            name_match = re.search(r'name=[\'"]([^\'"]+)[\'"]', target)
            if name_match:
                return name_match.group(1)

        return target  # Return as-is if can't extract

    except Exception as e:
        print(f"Error extracting field identifier from {target}: {e}")
        return target


def generate_examples_for_field(target, field_type, original_value, num_examples):
    """
    Generate test examples for a specific field using LLM

    Args:
        target (str): The target selector of the field
        field_type (str): The type of the field (text, password, email, etc.)
        original_value (str): The original value from Katalon test
        num_examples (int): Number of examples to generate

    Returns:
        list: Generated example values
    """
    try:
        # Create prompt based on field type and original value
        prompt = f"""You are a test data generation expert. Generate {num_examples} realistic test examples for a form field.

Field Information:
- Target: {target}
- Type: {field_type}
- Original Example: {original_value}

Requirements:
1. Generate {num_examples} different realistic values
2. Values should be appropriate for the field type
3. Include both valid and edge case examples
4. Make examples diverse and practical for testing
5. Consider the original example as a reference for format/style

Field Type Guidelines:
- text: Various text inputs with different lengths
- password: Strong passwords with different patterns
- email: Valid email addresses from different domains
- tel/phone: Phone numbers in different formats
- date: Dates in various formats
- number: Numbers with different ranges

Return only a JSON array of strings:
["example1", "example2", "example3", ...]

Examples should be realistic and usable for actual testing."""

        # Generate examples using LLM
        if is_local:
            response = chat(model="llama3.1",
                            messages=[{"role": "user", "content": prompt}],
                            options={"num_ctx": 8192})
            raw_response = response['message']['content']
        else:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=800
            )
            raw_response = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extract JSON array from response
            json_match = re.search(r'\[.*\]', raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                examples = json.loads(json_str)

                # Ensure we have the right number of examples
                if len(examples) >= num_examples:
                    return examples[:num_examples]
                else:
                    # Pad with variations if needed
                    while len(examples) < num_examples:
                        examples.append(f"{original_value}_{len(examples)}")
                    return examples
            else:
                raise ValueError("No JSON array found in response")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing LLM response for {target}: {e}")
            # Fallback: generate simple variations
            return [f"{original_value}_{i+1}" for i in range(num_examples)]

    except Exception as e:
        print(f"Error generating examples for {target}: {e}")
        # Fallback: return variations of original value
        return [f"{original_value}_{i+1}" for i in range(num_examples)]


def generate_examples_from_confirmation(target, field_type, original_value, confirmation_data, num_examples):
    """
    Generate test examples using confirmation data (description and existing examples)

    Args:
        target (str): The target selector of the field
        field_type (str): The type of the field
        original_value (str): The original value from Katalon test
        confirmation_data (dict): Confirmation data containing range and examples
        num_examples (int): Number of examples to generate

    Returns:
        list: Generated example values
    """
    try:
        # Get description and existing examples from confirmation
        description = confirmation_data.get('range', '')
        existing_examples = confirmation_data.get('examples', [])

        # Translate Persian description to English for LLM processing
        english_description = description
        if any('\u0600' <= c <= '\u06FF' for c in description):
            english_description = translate_to_english(description)

        print(f"Using confirmation description: {description}")
        print(f"Existing examples: {existing_examples}")

        # If we have enough examples from confirmation, use them directly
        if len(existing_examples) >= num_examples:
            print(f"Using existing examples from confirmation")
            return existing_examples[:num_examples]

        # If we have some examples but need more, generate additional ones
        examples_needed = num_examples - len(existing_examples)

        prompt = f"""You are a test data generation expert. Generate {examples_needed} additional realistic test examples for a form field.

Field Information:
- Target: {target}
- Type: {field_type}
- Original Example: {original_value}
- Field Description/Limitations: {english_description}

Existing Examples from User Confirmations:
{json.dumps(existing_examples, ensure_ascii=False)}

Requirements:
1. Generate {examples_needed} NEW examples that are DIFFERENT from the existing ones
2. Follow the same pattern and style as the existing examples
3. Respect the field description/limitations: {english_description}
4. Make examples realistic and practical for testing
5. Ensure examples are compatible with the field type: {field_type}

Guidelines based on existing examples:
- Analyze the format, length, and pattern of existing examples
- Generate similar but not identical values
- Maintain consistency with the field's purpose and limitations

Return only a JSON array of {examples_needed} NEW strings:
["new_example1", "new_example2", ...]

The new examples should complement the existing ones while following the same validation rules."""

        # Generate additional examples using LLM
        if is_local:
            response = chat(model="llama3.1",
                            messages=[{"role": "user", "content": prompt}],
                            options={"num_ctx": 8192})
            raw_response = response['message']['content']
        else:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=800
            )
            raw_response = response.choices[0].message.content

        # Parse JSON response
        try:
            # Extract JSON array from response
            json_match = re.search(r'\[.*\]', raw_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                new_examples = json.loads(json_str)

                # Combine existing examples with new ones
                all_examples = existing_examples + \
                    new_examples[:examples_needed]

                # Remove duplicates while preserving order
                seen = set()
                unique_examples = []
                for example in all_examples:
                    if example not in seen:
                        seen.add(example)
                        unique_examples.append(example)

                return unique_examples[:num_examples]
            else:
                raise ValueError("No JSON array found in response")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing LLM response for {target}: {e}")
            # Fallback: combine existing examples with simple variations
            fallback_examples = existing_examples[:]
            for i in range(examples_needed):
                if existing_examples:
                    # Create variations of existing examples
                    base_example = existing_examples[i % len(
                        existing_examples)]
                    fallback_examples.append(f"{base_example}_{i+1}")
                else:
                    fallback_examples.append(f"{original_value}_{i+1}")

            return fallback_examples[:num_examples]

    except Exception as e:
        print(f"Error generating examples from confirmation for {target}: {e}")
        # Fallback to default generation method
        return generate_examples_for_field(target, field_type, original_value, num_examples)


# Add a route to trigger test case generation
@app.route('/generate_test_cases', methods=['POST'])
def generate_test_cases_endpoint():
    """API endpoint to generate test cases from Katalon file"""
    try:
        data = request.get_json()
        katalon_path = data.get('katalon_path')
        output_csv_path = data.get('output_csv_path')
        num_test_cases = data.get('num_test_cases', 10)

        if not katalon_path or not output_csv_path:
            return json.dumps({
                'error': 'katalon_path and output_csv_path are required'
            }), 400, {'Content-Type': 'application/json'}

        # Generate test cases
        generate_test_cases_from_katalon(
            katalon_path, output_csv_path, num_test_cases)

        return json.dumps({
            'status': 'success',
            'message': f'Test cases generated and saved to {output_csv_path}',
            'num_test_cases': num_test_cases
        }), 200, {'Content-Type': 'application/json'}

    except Exception as e:
        return json.dumps({
            'error': f'Error generating test cases: {str(e)}'
        }), 500, {'Content-Type': 'application/json'}


# Add shutdown route to Flask app
@app.route('/shutdown', methods=['POST'])
def shutdown():
    """Shutdown the Flask application"""
    try:
        print("Shutdown request received. Closing Flask server...")
        func = request.environ.get('werkzeug.server.shutdown')
        if func is None:
            # Alternative shutdown method
            os._exit(0)
        else:
            func()
        return 'Server shutting down...'
    except Exception as e:
        print(f"Error during Flask shutdown: {e}")
        os._exit(0)


if __name__ == '__main__':
    port = 5000

    # Check if port is available
    if not check_port_available(port):
        print(f"Error: Port {port} is already in use!")
        print(
            f"Please close the application using port {port} or use a different port.")
        exit(1)

    print(f"Starting server on port {port}...")

    try:
        app.run(port=port, debug=False)
    except KeyboardInterrupt:
        print("\nApplication interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"Error running Flask app: {e}")
        sys.exit(1)
