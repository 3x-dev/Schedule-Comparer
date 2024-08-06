import os
import json
import base64
from flask import render_template, request, redirect, url_for
from werkzeug.utils import secure_filename
from app import app, db
from app.schedules import Schedule
from openai import OpenAI
import time
import boto3
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI API key
openai_api_key = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key=openai_api_key)

# AWS S3 configuration
s3 = boto3.client('s3')
BUCKET_NAME = os.getenv('S3_BUCKET_NAME')

PASTEL_COLORS = [
    "#FFB3BA",  # light red
    "#FFDFBA",  # light orange
    "#FFFFBA",  # light yellow
    "#BAFFC9",  # light green
    "#BAE1FF",  # light blue
    "#E3BAFF",  # light purple
]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def load_json_schema(schema_file: str) -> dict:
    schema_path = os.path.join(os.path.dirname(__file__), schema_file)
    with open(schema_path, 'r') as file:
        return json.load(file)

def get_gpt_response(image_path, schema, retries=3):
    with open(image_path, 'rb') as image_file:
        image_base64 = base64.b64encode(image_file.read()).decode('utf-8')

    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model='gpt-4o-mini',
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Provide a JSON file that represents this document. Use this JSON Schema: " +
                                json.dumps(schema)},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=500,
            )

            return json.loads(response.choices[0].message.content)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < retries - 1:
                time.sleep(2)  # wait before retrying
            else:
                raise
    raise Exception("Maximum retry attempts reached")

def generate_color(index):
    return PASTEL_COLORS[index % len(PASTEL_COLORS)]

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/verify', methods=['POST'])
def verify():
    try:
        start_time = time.time()
        if 'scheduleImage' not in request.files:
            return 'No file part', 400

        file = request.files['scheduleImage']
        if file.filename == '':
            return 'No selected file', 400

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join('/tmp', filename)  # Use /tmp directory
            file.save(filepath)

            schema = load_json_schema('schedule_schema.json')
            for attempt in range(3):
                try:
                    schedule = get_gpt_response(filepath, schema)
                    break
                except Exception as e:
                    logger.error(f"GPT API call failed, retrying... (Attempt {attempt + 1}): {e}")
                    if attempt == 2:
                        return 'Failed to process the image. Please ensure it is a correct schedule image and try again.', 500

            schedule['studentName'] = request.form['name']
            schedule['grade'] = request.form['grade']

            formatted_schedule = json.dumps(schedule)
            logger.info(f"Verification completed in {time.time() - start_time} seconds")
            return render_template('verify.html', schedule=schedule, formatted_schedule=formatted_schedule)

        return 'File not allowed', 400
    except Exception as e:
        logger.error(f"An error occurred during verification: {e}")
        return 'Internal Server Error', 500

@app.route('/confirm', methods=['POST'])
def confirm():
    name = request.form['name']
    grade = request.form['grade']
    schedule = json.loads(request.form['formatted_schedule'])

    new_schedule = Schedule(name=name, grade=grade, schedule=json.dumps(schedule))
    db.session.add(new_schedule)
    db.session.commit()

    return redirect(url_for('schedules'))

@app.route('/schedules')
def schedules():
    all_schedules = Schedule.query.all()

    # Create a dictionary to track shared classes
    shared_classes = {}
    index_counter = 0
    
    for schedule in all_schedules:
        schedule_data = json.loads(schedule.schedule)
        for period, entry in schedule_data['semester1'].items():
            key = f"{entry['class']}_{period}"
            if key not in shared_classes:
                shared_classes[key] = generate_color(index_counter)
                index_counter += 1

        for period, entry in schedule_data['semester2'].items():
            key = f"{entry['class']}_{period}"
            if key not in shared_classes:
                shared_classes[key] = generate_color(index_counter)
                index_counter += 1

    schedules_list = [
        {
            "name": schedule.name,
            "grade": schedule.grade,
            "schedule": json.loads(schedule.schedule),
            "colors": shared_classes
        }
        for schedule in all_schedules
    ]

    return render_template('schedules.html', schedules=schedules_list)
