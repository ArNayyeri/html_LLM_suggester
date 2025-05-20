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
        ..., description="Validation rules inferred from attributes like minlength, maxlength, pattern, placeholder")
    examples: list[str] = Field(...,
                                description="Two example values that satisfy the limitations")


class FormSchema(BaseModel):
    fields: list[FormField]


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


def suggest_input_values(html):
    soup = BeautifulSoup(html, 'html.parser')

    # Find all <input> and <textarea> elements
    elements = soup.find_all(['input', 'textarea'])

    # Extract IDs (only if they exist)
    ids = [el['id'] for el in elements if 'id' in el.attrs]
    # print(f"Found IDs: {ids}")

    # Build the prompt for structured extraction
    system_msg = {
        "role": "system",
        "content": (
            "شما یک پارسر HTML هستید. HTML زیر را دریافت می‌کنید و فقط عناصری که id آن‌ها در لیست مشخص‌شده است را پردازش می‌کنید. "
            "برای هر عنصر، یک شی JSON با کلیدهای name، id، type، limitations و examples بسازید. "
            "- name: مقدار attribute 'name'. "
            "- id: مقدار attribute 'id'. "
            "- type: نوع input (text، password و غیره) یا 'textarea'. "
            "- limitations: قواعد اعتبارسنجی استخراج‌شده از attributes مانند minlength، maxlength، pattern یا placeholder. (مثل 'حداقل دارای 8 حرف انگلیسی')"
            "- examples: 5 مقدار مثال که با این محدودیت‌ها مطابقت داشته باشند. "
            "لطفاً کلیدها را ثابت نگه دارید ولی مقادیر محدودیت ها را به زبان فارسی بنویسید. "
            "خروجی را به صورت یک شی JSON مطابق با schema پایدانتیک و هیچ متن اضافی ندهید. "
            f"فقط این id ها را پردازش کن: {', '.join(ids)}"
        )
    }

    user_msg = {"role": "user", "content": html}

    # Call the LLM with the JSON schema
    if is_local:
        response = chat(model="llama3.1",
                        messages=[system_msg, user_msg],
                        format=FormSchema.model_json_schema(),
                        options={"num_ctx": 32768}
                        )
        raw = response['message']['content']
    else:
        response = client.beta.chat.completions.parse(
            model=model_name,
            messages=[system_msg, user_msg],
            response_format=FormSchema,
        )
        raw = response.choices[0].message.content

    # Parse the structured JSON content
    data = json.loads(raw)
    # print(f"Parsed JSON: {data}")
    return data


@app.route('/events', methods=['POST'])
def events():
    data = request.get_json()
    events_path = os.path.join(RUN_SAVE_DIR, 'recorded_events.json')
    with open(events_path, 'w', encoding='utf-8') as f:
        json.dump(data['events'], f, ensure_ascii=False, indent=2)
    print(
        f"Saved {len(data['events'])} events to recorded_events.json"
    )
    return 'ok'


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
    # Save or log the update for next steps (append to a file for now)
    update_path = os.path.join(
        RUN_SAVE_DIR, f'input_suggestion_updates_{run_time_temp}_{field}.json')
    try:
        # After saving, if range is updated, ask LLM for new examples
        prompt = (
            f"تو یک تستر هوشمند هستی. برای یک فیلد در یک سایت با رینج زیر:\n"
            f"{range_}\n"
            "لطفا 5 مثال تستی مناسب برای این رینج تولید کن و فقط به صورت یک آرایه JSON خروجی بده:\n"
            "[\"مثال۱\", \"مثال۲\", ...]"
        )
        try:
            # response = chat(model="llama3.1", messages=[
            #     {"role": "user", "content": prompt}
            # ])
            # raw = response['message']['content']

            response = client.beta.chat.completions.parse(
                model=model_name,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = response.choices[0].message.content
            match = re.search(
                r'(\[.*\])',
                raw,
                re.DOTALL
            )
            if match:
                new_examples = json.loads(match.group(1))
                updates = {'field': field, 'range': range_,
                           'examples': new_examples}
                with open(update_path, 'w', encoding='utf-8') as f:
                    json.dump(updates, f, ensure_ascii=False, indent=2)
                return (
                    json.dumps(
                        {'status': 'ok', 'new_examples': new_examples},
                        ensure_ascii=False, indent=2
                    ),
                    200,
                    {'Content-Type': 'application/json'}
                )
            else:
                new_examples = []
        except Exception:
            new_examples = []
        else:
            new_examples = []
        return (
            json.dumps(
                {'status': 'ok'},
                ensure_ascii=False, indent=2
            ),
            200,
            {'Content-Type': 'application/json'}
        )
    except Exception as e:
        return (
            json.dumps({'error': str(e)}),
            500,
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
            'select'
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
