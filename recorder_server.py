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
                                description="Five example values that satisfy the limitations")


class ExampleSchema(BaseModel):
    examples: list[str] = Field(...,
                                description="Five example values that satisfy the range")


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
        # Build the prompt for structured extraction

        system_msg = {
            "role": "system",
            "content": (
                "شما یک پارسر HTML هستید. HTML زیر را دریافت می‌کنید و فقط عنصری که id آن برابر با مقدار مشخص‌شده است را پردازش می‌کنید. "
                "برای آن عنصر، یک شی JSON با کلیدهای name، id، type، limitations و examples بسازید. "
                "- name: مقدار attribute 'name'.\n"
                "- id: مقدار attribute 'id'.\n"
                "- type: نوع input (text، password و غیره) یا 'textarea'.\n"
                "- limitations: قواعد اعتبارسنجی استخراج‌شده از attributes مانند minlength، maxlength، pattern یا placeholder. (مثلاً: 'حداقل دارای 8 حرف انگلیسی')\n"
                "- examples: 5 مقدار مثال که با این محدودیت‌ها مطابقت داشته باشند.\n"
                "کلیدها را ثابت نگه دار ولی مقادیر محدودیت‌ها را به زبان فارسی بنویس.\n"
                "خروجی را فقط به صورت یک شی JSON مطابق با schema پایدانتیک ارائه بده.\n"
                f"فقط و فقط عنصری با id برابر با '{target_id}' را پردازش کن. هیچ عنصر دیگری را در خروجی قرار نده.\n"
                "در ادامه 5 مثال کامل برای فهم این مورد به تو پیشنهاد شده است\n\n"
                "مثال 1:\n"
                "ورودی:\n"
                "<form>\n"
                "  <label for=\"input-0\">نام کاربری:</label>\n"
                "  <input id=\"input-0\" name=\"نام کاربری\" type=\"text\" placeholder=\"مثلاً ali123\" />\n"
                "  <label for=\"input-1\">ایمیل:</label>\n"
                "  <input id=\"input-1\" name=\"ایمیل\" type=\"email\" />\n"
                "  <label for=\"input-2\">رمز عبور:</label>\n"
                "  <input id=\"input-2\" name=\"رمز عبور\" type=\"password\" minlength=\"8\" />\n"
                "</form>\n"
                "خروجی (برای input-2):\n"
                "[{\n"
                "  \"name\": \"رمز عبور\",\n"
                "  \"id\": \"input-2\",\n"
                "  \"type\": \"password\",\n"
                "  \"examples\": [\"12345678\", \"password123\", \"adminadmin\", \"abcDEFghiJ\", \"userpass2024\"],\n"
                "  \"limitations\": \"حداقل 8 حرف انگلیسی\"\n"
                "}]\n\n"

                "مثال 2:\n"
                "ورودی:\n"
                "<form>\n"
                "  <label for=\"input-3\">شماره تماس:</label>\n"
                "  <input id=\"input-3\" name=\"شماره تماس\" type=\"text\" pattern=\"\\d{11}\" />\n"
                "  <label for=\"input-4\">کد امنیتی:</label>\n"
                "  <input id=\"input-4\" name=\"کد امنیتی\" type=\"text\" maxlength=\"6\" />\n"
                "</form>\n"
                "خروجی (برای input-3):\n"
                "[{\n"
                "  \"name\": \"شماره تماس\",\n"
                "  \"id\": \"input-3\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"09123456789\", \"09351234567\", \"09221234567\", \"09901234567\", \"09111111111\"],\n"
                "  \"limitations\": \"دقیقاً 11 رقم عددی\"\n"
                "}]\n\n"

                "مثال 3:\n"
                "ورودی:\n"
                "<form>\n"
                "  <label for=\"input-5\">زبان ترجیحی:</label>\n"
                "  <input id=\"input-5\" name=\"زبان\" type=\"text\" placeholder=\"fa\" />\n"
                "  <label for=\"input-6\">نام خانوادگی:</label>\n"
                "  <input id=\"input-6\" name=\"نام خانوادگی\" type=\"text\" />\n"
                "</form>\n"
                "خروجی (برای input-5):\n"
                "[{\n"
                "  \"name\": \"زبان\",\n"
                "  \"id\": \"input-5\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"fa\", \"en\", \"de\", \"fr\", \"ar\"],\n"
                "  \"limitations\": \"پیوند فارسی\"\n"
                "}]\n\n"

                "مثال 4:\n"
                "ورودی:\n"
                "<form>\n"
                "  <label for=\"input-7\">توضیحات:</label>\n"
                "  <textarea id=\"input-7\" name=\"توضیحات\" minlength=\"10\" maxlength=\"100\"></textarea>\n"
                "  <label for=\"input-8\">موقعیت جغرافیایی:</label>\n"
                "  <input id=\"input-8\" name=\"موقعیت\" type=\"text\" />\n"
                "</form>\n"
                "خروجی (برای input-7):\n"
                "[{\n"
                "  \"name\": \"توضیحات\",\n"
                "  \"id\": \"input-7\",\n"
                "  \"type\": \"textarea\",\n"
                "  \"examples\": [\n"
                "    \"این یک متن آزمایشی است.\",\n"
                "    \"کاربر درباره تجربه کاربری توضیح می‌دهد.\",\n"
                "    \"لطفاً اطلاعات بیشتری وارد نمایید.\",\n"
                "    \"پیام تست برای بررسی فرم.\",\n"
                "    \"توضیح در مورد امکانات سایت.\"\n"
                "  ],\n"
                "  \"limitations\": \"حداقل 10 و حداکثر 100 کاراکتر\"\n"
                "}]\n\n"

                "مثال 5:\n"
                "ورودی:\n"
                "<form>\n"
                "  <label for=\"input-9\">کد ملی:</label>\n"
                "  <input id=\"input-9\" name=\"کد ملی\" type=\"text\" pattern=\"\\d{10}\" />\n"
                "  <label for=\"input-10\">آدرس:</label>\n"
                "  <input id=\"input-10\" name=\"آدرس\" type=\"text\" />\n"
                "</form>\n"
                "خروجی (برای input-9):\n"
                "[{\n"
                "  \"name\": \"کد ملی\",\n"
                "  \"id\": \"input-9\",\n"
                "  \"type\": \"text\",\n"
                "  \"examples\": [\"0012345678\", \"1234567890\", \"9876543210\", \"1122334455\", \"2233445566\"],\n"
                "  \"limitations\": \"10 رقم عددی\"\n"
                "}]\n"
            )
        }

        user_msg = {"role": "user", "content": html}

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
        extracted_data.append(data)
    return {'fields': extracted_data}


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

    # --- Build prompt with previous info if available ---
    prompt = (
        f"تو یک تستر هوشمند هستی. وظیفه تو تولید داده‌های تستی برای فیلدهای فرم در وب‌سایت‌ها است. "
        f"در اینجا یک محدودیت (رینج) جدید برای یک فیلد به تو داده شده:\n"
        f"{range_}\n"
        "مثال‌ها باید شبیه مقادیری باشند که کاربران واقعی در فرم وارد می‌کنند، نه فقط داده‌های تصادفی یا ساختگی."
    )
    if examples_:
        prompt += (
            f"\nمثال‌هایی که کاربران واقعاً وارد کرده‌اند (به عنوان نمونه): {json.dumps(examples_, ensure_ascii=False)}\n"
            "مثال‌های جدید باید از نظر سبک و واقع‌گرایی شبیه این مثال‌ها باشند."
        )
    if previous_range and previous_examples:
        prompt += (
            "\nمحدودیت قبلی و مثال‌های قبلی را ببین و مثال‌های جدیدی تولید کن که با محدودیت جدید سازگار باشند و تکراری نباشند.\n"
            f"محدودیت قبلی: {previous_range}\n"
            f"مثال‌های قبلی: {json.dumps(previous_examples, ensure_ascii=False)}\n"
        )
    prompt += (
        "لطفاً 5 مقدار ورودی مناسب و معتبر که با این محدودیت مطابقت داشته باشند تولید کن. "
        "هر مقدار باید یک رشته واقع‌گرایانه و کاربردی باشد که بتوان در فرم واقعی استفاده کرد. "
        "خروجی فقط باید به صورت یک آرایه JSON باشد:\n"
        "[\"مثال۱\", \"مثال۲\", \"مثال۳\", \"مثال۴\", \"مثال۵\"]\n\n"
        "مثال‌ها:\n\n"

        "رینج: حداقل 8 حرف انگلیسی\n"
        "خروجی:\n[\"password\", \"openai123\", \"machinelearning\", \"SecurePass1\", \"AIengineer\"]\n\n"

        "رینج: دقیقاً 11 رقم عددی\n"
        "خروجی:\n[\"09123456789\", \"09987654321\", \"09335557766\", \"09221234567\", \"09001112233\"]\n\n"

        "رینج: بین 5 تا 15 کاراکتر\n"
        "خروجی:\n[\"hello\", \"chatbot2024\", \"1234567890\", \"formTesting\", \"userinput\"]\n\n"

        "رینج: کد ملی 10 رقمی\n"
        "خروجی:\n[\"1234567890\", \"0011223344\", \"9876543210\", \"1122334455\", \"5566778899\"]\n\n"

        "رینج: فقط حروف کوچک انگلیسی\n"
        "خروجی:\n[\"hello\", \"username\", \"password\", \"openai\", \"testcase\"]"

        ": فقط حروف فارسی با حداقل 3 کاراکتر\n"
        "خروجی:\n[\"سلام\", \"کاربر\", \"تست\", \"برنامه\", \"مثال\"]\n\n"

        "رینج: تاریخ با فرمت yyyy-mm-dd\n"
        "خروجی:\n[\"2023-01-01\", \"2024-12-31\", \"1999-07-15\", \"2025-05-21\", \"2000-10-10\"]\n\n"

        "رینج: ایمیل معتبر\n"
        "خروجی:\n[\"test@example.com\", \"user123@gmail.com\", \"name.lastname@yahoo.com\", \"info@site.ir\", \"developer@domain.dev\"]\n\n"

        "رینج: فقط اعداد بین 1 تا 100\n"
        "خروجی:\n[\"5\", \"42\", \"100\", \"1\", \"73\"]\n\n"

        "رینج: شماره پلاک خودرو (فرمت ایرانی)\n"
        "خروجی:\n[\"12ب34567\", \"45د12345\", \"98س87654\", \"11الف22222\", \"21ج67890\"]"
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
            new_examples.extend(examples_)
        # check for duplicates
        new_examples = list(set(new_examples))
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
