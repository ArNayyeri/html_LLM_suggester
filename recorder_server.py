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

# Use cl100k_base encoding (close approximation for Llama)
encoding = tiktoken.get_encoding("cl100k_base")


def count_tokens(text):
    return len(encoding.encode(text))


ollama_url = 'http://localhost:11434/v1'
openrouter_url = 'https://openrouter.ai/api/v1'

site = input(
    "Do you want to use local or api? (local/api): "
).strip().lower()

if site == 'local':
    token = 'ollama'
    url = ollama_url
    model_name = 'llama3.1'
    is_local = True

elif site == 'api':
    token = input("Enter your OpenRouter API token: ").strip()
    url = openrouter_url
    model_name = 'meta-llama/llama-3.3-8b-instruct:free'
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


class ExampleSchema(BaseModel):
    examples: list[str] = Field(...,
                                description="Five example values that satisfy the range")


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
    # Filter out elements with invalid types
    elements = [
        el for el in elements if el.name == 'textarea' or
        (el.name ==
         'input' and 'type' in el.attrs and el['type'] in valid_types)
    ]

    # Extract IDs (only if they exist)
    ids = [el['id'] for el in elements if 'id' in el.attrs]
    # print(f"Found IDs: {ids}")

    extracted_data = []
    for target_id in ids:
        # If the web is more than 128k tokens,
        # it will be considered as an input within 100k tokens from where the desired input ID is.
        if count_tokens(html) > 128 * 1024:
            target_html = truncate_with_context(soup, soup.find(id=target_id))
        else:
            target_html = html
        # Build the prompt for structured extraction

        system_msg = {
            "role": "system",
            "content": (
                "You are an HTML parser. You receive HTML below and process only the element whose id equals the specified value. "
                "For that element, create a JSON object with keys: name, id, type, limitations, and examples. "
                "- name: The value of the 'name' attribute.\n"
                "- id: The value of the 'id' attribute.\n"
                "- type: Input type (text, password, etc.) or 'textarea'.\n"
                "- limitations: Validation rules extracted from attributes like minlength, maxlength, pattern, or placeholder. This description should be written in English as complete sentences. Instead of using short phrases like 'minimum 8 English characters', provide a complete explanation. For example: 'The password must be at least 8 characters long. English lowercase or uppercase letters are allowed. Numbers and other common characters can also be used to increase security.'\n"
                "- examples: 5 example values that match these limitations. Examples should be appropriate for the field context (English or Persian based on the field purpose).\n"
                "Keep the keys constant but write limitation values in English.\n"
                "Provide output only as a JSON object matching the Pydantic schema.\n"
                f"Process only and exclusively the element with id equal to '{target_id}'. Do not include any other element in the output.\n"
                "Here are 5 complete examples for understanding:\n\n"

                "Example 1:\n"
                "Input:\n"
                "<form>\n"
                "  <label for=\"input-0\">Username:</label>\n"
                "  <input id=\"input-0\" name=\"username\" type=\"text\" placeholder=\"e.g. ali123\" />\n"
                "  <label for=\"input-1\">Email:</label>\n"
                "  <input id=\"input-1\" name=\"email\" type=\"email\" />\n"
                "  <label for=\"input-2\">Password:</label>\n"
                "  <input id=\"input-2\" name=\"password\" type=\"password\" minlength=\"8\" />\n"
                "</form>\n"
                "Output (for input-2):\n"
                "{\n"
                "  \"name\": \"password\",\n"
                "  \"id\": \"input-2\",\n"
                "  \"type\": \"password\",\n"
                "  \"examples\": [\"12345678\", \"password123\", \"adminadmin\", \"abcDEFghiJ\", \"userpass2024\"],\n"
                "  \"limitations\": \"The password must be at least 8 characters long. English lowercase or uppercase letters are allowed. Numbers and other common characters can also be used to increase security.\"\n"
                "}\n\n"

                "Example 2:\n"
                "Input:\n"
                "<form>\n"
                "  <label for=\"input-3\">Phone Number:</label>\n"
                "  <input id=\"input-3\" name=\"phone\" type=\"text\" pattern=\"\\d{11}\" />\n"
                "  <label for=\"input-4\">Security Code:</label>\n"
                "  <input id=\"input-4\" name=\"security_code\" type=\"text\" maxlength=\"6\" />\n"
                "</form>\n"
                "Output (for input-3):\n"
                "{\n"
                "  \"name\": \"phone\",\n"
                "  \"id\": \"input-3\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"09123456789\", \"09351234567\", \"09221234567\", \"09901234567\", \"09111111111\"],\n"
                "  \"limitations\": \"The phone number must contain exactly 11 numeric digits with no spaces, symbols, or letters allowed. It typically starts with 09 and follows the format of Iranian mobile phone numbers.\"\n"
                "}\n\n"

                "Example 3:\n"
                "Input:\n"
                "<form>\n"
                "  <label for=\"input-5\">Preferred Language:</label>\n"
                "  <input id=\"input-5\" name=\"language\" type=\"text\" placeholder=\"fa\" />\n"
                "  <label for=\"input-6\">Last Name:</label>\n"
                "  <input id=\"input-6\" name=\"lastname\" type=\"text\" />\n"
                "</form>\n"
                "Output (for input-5):\n"
                "{\n"
                "  \"name\": \"language\",\n"
                "  \"id\": \"input-5\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"fa\", \"en\", \"de\", \"fr\", \"ar\"],\n"
                "  \"limitations\": \"This field should contain the abbreviation code of a language such as 'fa' for Persian or 'en' for English. Only lowercase English letters are allowed and the language code is typically entered in two-letter format.\"\n"
                "}\n\n"

                "Example 4:\n"
                "Input:\n"
                "<form>\n"
                "  <label for=\"input-7\">Description:</label>\n"
                "  <textarea id=\"input-7\" name=\"description\" minlength=\"10\" maxlength=\"100\"></textarea>\n"
                "  <label for=\"input-8\">Location:</label>\n"
                "  <input id=\"input-8\" name=\"location\" type=\"text\" />\n"
                "</form>\n"
                "Output (for input-7):\n"
                "{\n"
                "  \"name\": \"description\",\n"
                "  \"id\": \"input-7\",\n"
                "  \"type\": \"textarea\",\n"
                "  \"examples\": [\n"
                "    \"This is a test text.\",\n"
                "    \"User describes their experience.\",\n"
                "    \"Please enter more information.\",\n"
                "    \"Test message for form validation.\",\n"
                "    \"Description about website features.\"\n"
                "  ],\n"
                "  \"limitations\": \"The entered description must be at least 10 and at most 100 characters long. Users can write free text, but should avoid writing very short or very long text. The text should be meaningful and contain letters, words, and possibly punctuation marks.\"\n"
                "}\n\n"

                "Example 5:\n"
                "Input:\n"
                "<form>\n"
                "  <label for=\"input-9\">National ID:</label>\n"
                "  <input id=\"input-9\" name=\"national_id\" type=\"text\" pattern=\"\\d{10}\" />\n"
                "  <label for=\"input-10\">Address:</label>\n"
                "  <input id=\"input-10\" name=\"address\" type=\"text\" />\n"
                "</form>\n"
                "Output (for input-9):\n"
                "{\n"
                "  \"name\": \"national_id\",\n"
                "  \"id\": \"input-9\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"0012345678\", \"1234567890\", \"9876543210\", \"1122334455\", \"2233445566\"],\n"
                "  \"limitations\": \"The national ID must be exactly 10 numeric digits. Letters or non-numeric characters are not allowed. This is a unique numeric identifier assigned to each person and must be entered correctly.\"\n"
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

        self.setup_ui()
        self.get_initial_suggestions()

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
        if event_type == 'click':
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
            from urllib.parse import urlparse
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
    update_path = os.path.join(
        RUN_SAVE_DIR, f'input_suggestion_updates_{run_time_temp}_{field}.json')

    # --- Load previous update for this field, if any ---
    previous_range = None
    previous_examples = None
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
    except Exception as e:
        print(f"Could not load previous update for field {field}: {e}")

    # --- If range is empty but examples exist, generate range first ---
    if not range_ and examples_:
        try:
            range_generation_prompt = (
                "You are a data analysis expert. Based on the examples below, identify their patterns and limitations "
                "and write a precise and concise description in English about these limitations. "
                "Write only a short phrase in one or two sentences, no more. Example: 'minimum 8 English characters with at least one number and one uppercase letter' or 'valid email' or '10-digit national ID'"
                f"\n\nExamples: {json.dumps(examples_, ensure_ascii=False)}"
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
            "Examples should be similar to values that real users would enter in the form, not just random or artificial data."
        )
        if examples_:
            prompt += (
                f"\nExamples that users have actually entered (as samples): {json.dumps(examples_, ensure_ascii=False)}\n"
                "New examples should be similar in style and realism to these examples."
            )
        if previous_range and previous_examples:
            # Translate previous range to English if needed
            prev_english_range = previous_range
            if any('\u0600' <= c <= '\u06FF' for c in previous_range):
                prev_english_range = translate_to_english(previous_range)

            prompt += (
                "\nSee the previous limitation and examples and generate new examples that are compatible with the new limitation and are not repetitive.\n"
                f"Previous limitation: {prev_english_range}\n"
                f"Previous examples: {json.dumps(previous_examples, ensure_ascii=False)}\n"
            )
        prompt += (
            "Please generate 5 appropriate and valid input values that match this limitation. "
            "Each value should be a realistic and practical string that can be used in a real form. "
            "Output should only be in the form of a JSON array:\n"
            "[\"example1\", \"example2\", \"example3\", \"example4\", \"example5\"]\n\n"
            "Examples:\n\n"

            "Range: minimum 8 English characters\n"
            "Output:\n[\"password\", \"openai123\", \"machinelearning\", \"SecurePass1\", \"AIengineer\"]\n\n"

            "Range: exactly 11 numeric digits\n"
            "Output:\n[\"09123456789\", \"09987654321\", \"09335557766\", \"09221234567\", \"09001112233\"]\n\n"

            "Range: between 5 to 15 characters\n"
            "Output:\n[\"hello\", \"chatbot2024\", \"1234567890\", \"formTesting\", \"userinput\"]\n\n"

            "Range: 10-digit national ID\n"
            "Output:\n[\"1234567890\", \"0011223344\", \"9876543210\", \"1122334455\", \"5566778899\"]\n\n"

            "Range: only lowercase English letters\n"
            "Output:\n[\"hello\", \"username\", \"password\", \"openai\", \"testcase\"]\n\n"

            "Range: only Persian letters with minimum 3 characters\n"
            "Output:\n[\"سلام\", \"کاربر\", \"تست\", \"برنامه\", \"مثال\"]\n\n"

            "Range: date with yyyy-mm-dd format\n"
            "Output:\n[\"2023-01-01\", \"2024-12-31\", \"1999-07-15\", \"2025-05-21\", \"2000-10-10\"]\n\n"

            "Range: valid email\n"
            "Output:\n[\"test@example.com\", \"user123@gmail.com\", \"name.lastname@yahoo.com\", \"info@site.ir\", \"developer@domain.dev\"]\n\n"

            "Range: numbers only between 1 to 100\n"
            "Output:\n[\"5\", \"42\", \"100\", \"1\", \"73\"]\n\n"

            "Range: Iranian car license plate format\n"
            "Output:\n[\"12ب34567\", \"45د12345\", \"98س87654\", \"11الف22222\", \"21ج67890\"]"
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
            if examples_:
                new_examples.extend(examples_)        # check for duplicates
            new_examples = list(set(new_examples))
        except Exception as e:
            return (
                json.dumps({'error': str(e)}),
                500,
                {'Content-Type': 'application/json'}
            )
    updates = {'field': field, 'range': range_,
               'examples': new_examples}
    with open(update_path, 'w', encoding='utf-8') as f:
        json.dump(updates, f, ensure_ascii=False, indent=2)
    return (
        json.dumps(
            {'status': 'ok', 'new_examples': new_examples, 'range': range_},
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
        # Check if the field exists in HTML as input or textarea
        field_id = field.get('id', '').replace('#', '')
        name = field.get('name', '')
        # Look for <input ... id="..."> or <textarea ... id="...">
        input_pattern = (
            rf'<input[^>]*((id=[\'"]{field_id}[\'"])|(name=[\'"]{re.escape(name)}[\'"]))'
        )
        textarea_pattern = (
            rf'<textarea[^>]*((id=[\'"]{field_id}[\'"])|(name=[\'"]{re.escape(name)}[\'"]))'
        )
        valid_types = [
            'text',
            'password',
            'email',
            'number',
            'date',
            'textarea',
            'datetime-local',
            'month',
            'range',
            'search',
            'tel',
            'time',
            'url',
            'week'
        ]
        exists = (
            re.search(input_pattern, html)
            or re.search(textarea_pattern, html)
        )
        if exists and field['type'] in valid_types:
            # check not duplicate ID
            if not any(f['id'] == field['id'] for f in filtered):
                filtered.append(field)
    return filtered


if __name__ == '__main__':
    app.run(port=5000)
