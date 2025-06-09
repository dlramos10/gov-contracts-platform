# gov_contracts_platform.py
# Expanded: Real-time fetch from SAM.gov on each request to /home

import requests
import datetime
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session
import smtplib
from email.mime.text import MIMEText
from apscheduler.schedulers.background import BackgroundScheduler

# Configuration
SAM_API_KEY = "your_sam_api_key_here"
SAM_URL = "https://api.sam.gov/opportunities/v2/search"
DB_FILE = "contracts.db"
EMAIL_SENDER = "your_email@example.com"
EMAIL_PASSWORD = "your_email_password"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Set up database and users table only
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "admin123"))
    conn.commit()
    conn.close()

# Email alerts
def send_email_alert():
    msg = MIMEText("New federal contract opportunities available!")
    msg['Subject'] = 'Gov Contract Alerts'
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_SENDER
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

# Routes
@app.route('/health')
def health_check():
    return "OK", 200

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = cursor.fetchone()
        conn.close()
        if user:
            session['user'] = username
            return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/home')
def home():
    if 'user' not in session:
        return redirect(url_for('login'))

    keyword = request.args.get('keyword', '')
    start_date = request.args.get('start_date', '')
    end_date = request.args.get('end_date', '')
    naics = request.args.get('naics', '')

    # Convert dates to MM/DD/YYYY for SAM.gov API
    today = datetime.date.today()
    if not end_date:
        end_date = today.strftime("%m/%d/%Y")
    else:
        try:
            end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").strftime("%m/%d/%Y")
        except:
            end_date = today.strftime("%m/%d/%Y")

    if not start_date:
        start_date = (today - datetime.timedelta(days=7)).strftime("%m/%d/%Y")
    else:
        try:
            start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").strftime("%m/%d/%Y")
        except:
            start_date = (today - datetime.timedelta(days=7)).strftime("%m/%d/%Y")

    # Set up API request
    headers = {"X-API-Key": SAM_API_KEY}
    params = {
        "postedFrom": start_date,
        "postedTo": end_date,
        "ptype": "o",
        "limit": 50
    }

    if keyword:
        params["q"] = keyword
    if naics:
        params["naics"] = naics

    response = requests.get(SAM_URL, headers=headers, params=params)
    results = []

    if response.status_code == 200:
        data = response.json()
        for item in data.get("opportunitiesData", []):
            sol_num = item.get("solicitationNumber", "N/A")
            title = item.get("title", "N/A")
            agency = item.get("departmentName", "N/A")
            raw_date = item.get("postedDate", "")
            try:
                date_obj = datetime.datetime.strptime(raw_date[:10], "%m/%d/%Y")
                date = date_obj.strftime("%Y-%m-%d")
            except:
                date = "Unknown"
            naics_code = item.get("naics", {}).get("code", "N/A")
            results.append((sol_num, title, agency, date, naics_code))
    else:
        print(f"API Error: {response.status_code} - {response.text}")

    return render_template('home.html', user=session['user'], opportunities=results)

# Scheduler (optional if not saving to DB)
scheduler = BackgroundScheduler()
scheduler.add_job(send_email_alert, 'interval', days=1)
scheduler.start()

# Run
if __name__ == '__main__':
    setup_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
