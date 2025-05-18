from flask import Flask, request
from flask_cors import CORS
import os
import json
import re
from ollama import chat
import time
import uuid

app = Flask(__name__)
CORS(app)
SAVE_DIR = "snapshots"

# Create a unique run directory inside snapshots for each server run
_run_time = int(time.time())
_run_uid = uuid.uuid4().hex[:8]
RUN_ID = f"run_{_run_time}_{_run_uid}"
RUN_SAVE_DIR = os.path.join(SAVE_DIR, RUN_ID)
os.makedirs(RUN_SAVE_DIR, exist_ok=True)


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

    messages = [{'role': 'system', 'content': '''شما یک تستر هوشمند هستید.

من در ادامه یک کد HTML کامل از یک صفحه وب را برایتان ارسال می‌کنم. لطفاً مراحل زیر را انجام دهید:

1. تمامی فیلدهای ورودی (input, textarea, select) را استخراج کن.
2. برای هر فیلد، اطلاعات زیر را تولید کن:
   - `نام فیلد (name یا id)`
   - `نوع فیلد` (مثلاً: text, email, password, number, date, etc)
   - `برچسب و توضیحات موجود در HTML` (label یا placeholder یا متن اطراف)
   - `رینج و فرمت معتبر ورودی برای این فیلد براساس فهم تو از این ورودی` (مثلاً فقط عدد ۱ تا ۵، یا ایمیل معتبر، یا تاریخ YYYY-MM-DD)(حتما ساخته شود)
   - `۵ مثال مناسب برای مقداردهی تستی`(حتما باید ساخته شود)

لطفاً خروجی به ازای هر فیلد ایجاد کن و آن را فقط به صورت یک JSON به فرمت زیر نمایش بده تا قابل خواندن و پردازش باشد.
[{name:"", id:"", type:"", range:"", examples:["","",...]},{name:"", id:"", type:"", range:"", examples:["","",...]}, ...]
 '''}, {'role': 'user', 'content': f'''این صفحه وب است:
        {html}
        خروجی مورد نظر را به من بده.'''}]

    try:
        response = chat(model="llama3.1", messages=messages, options={
            'num_ctx': 32768  # Use full context window
        })
        return response['message']['content']
    except Exception as e:
        print(f"Error querying Ollama for input suggestions: {e}")
        return json.dumps({'error': str(e)})


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
    data = request.get_json()
    html = data.get('html', '')
    try:
        result = suggest_input_values(html)
        with open(os.path.join(RUN_SAVE_DIR, 'suggested_inputs.json'), 'w', encoding='utf-8') as f:
            f.write(result)
        # extract the JSON part from the response
        try:
            # Try to parse the result as JSON directly
            parsed = json.loads(result)
            return (
                json.dumps(parsed, ensure_ascii=False, indent=2),
                200,
                {'Content-Type': 'application/json'}
            )
        except Exception:
            # If the LLM response is not pure JSON, try to extract the JSON array
            match = re.search(r'(\[.*\])', result, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    return (
                        json.dumps(parsed, ensure_ascii=False, indent=2),
                        200,
                        {'Content-Type': 'application/json'}
                    )
                except Exception as e2:
                    print(f"Error parsing extracted JSON: {e2}")
            # Fallback: return the raw result as a string
            return (
                json.dumps({'raw': result}, ensure_ascii=False, indent=2),
                200,
                {'Content-Type': 'application/json'}
            )
    except Exception as e:
        print(f"Error in suggest_inputs: {e}")
        return (
            create_error_response('Error processing request'),
            500,
            {'Content-Type': 'application/json'}
        )


@app.route('/update_input_suggestion', methods=['POST'])
def update_input_suggestion():
    data = request.get_json()
    field = data.get('field')
    range_ = data.get('range')
    examples = data.get('examples')
    # Save or log the update for next steps (append to a file for now)
    update_path = os.path.join(RUN_SAVE_DIR, 'input_suggestion_updates.json')
    try:
        if os.path.exists(update_path):
            with open(update_path, 'r', encoding='utf-8') as f:
                updates = json.load(f)
        else:
            updates = []
        updates.append({'field': field, 'range': range_, 'examples': examples})
        with open(update_path, 'w', encoding='utf-8') as f:
            json.dump(updates, f, ensure_ascii=False, indent=2)
        # After saving, if range is updated, ask LLM for new examples
        prompt = (
            f"تو یک تستر هوشمند هستی. برای یک فیلد در یک سایت با رینج زیر:\n"
            f"{range_}\n"
            "لطفا ۵ مثال تستی مناسب برای این رینج تولید کن و فقط به صورت یک آرایه JSON خروجی بده:\n"
            "[\"مثال۱\", \"مثال۲\", ...]"
        )
        try:
            response = chat(model="llama3.1", messages=[
                {"role": "user", "content": prompt}
            ])
            match = re.search(
                r'(\[.*\])',
                response['message']['content'],
                re.DOTALL
            )
            if match:
                new_examples = json.loads(match.group(1))
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


def create_error_response(message):
    """Centralized error response function."""
    return json.dumps({'error': message}, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    app.run(port=5000)
