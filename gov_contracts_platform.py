# gov_contracts_platform.py
# Expanded: Adds USAspending.gov integration alongside SAM.gov and date filters on dashboard

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
USASPENDING_API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DB_FILE = "contracts.db"
EMAIL_SENDER = "your_email@example.com"
EMAIL_PASSWORD = "your_email_password"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

# Set up database and table
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            solicitationNumber TEXT PRIMARY KEY,
            title TEXT,
            agency TEXT,
            postedDate TEXT,
            naicsCode TEXT
        )
    ''')
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

# Save opportunity to the database
def save_opportunity(sol_num, title, agency, date, naicsCode=""):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO opportunities (solicitationNumber, title, agency, postedDate, naicsCode)
            VALUES (?, ?, ?, ?, ?)
        ''', (sol_num, title, agency, date, naicsCode))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

# Fetch from SAM.gov
def fetch_and_store_opportunities():
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    headers = {"X-API-Key": SAM_API_KEY}
    params = {
        "postedFrom": week_ago.strftime("%m/%d/%Y"),
        "postedTo": today.strftime("%m/%d/%Y"),
        "ptype": "o",
        "limit": 20
    }
    response = requests.get(SAM_URL, headers=headers, params=params)
    if response.status_code == 200:
        data = response.json()
        for item in data.get("opportunitiesData", []):
            title = item.get("title", "N/A")
            sol_num = item.get("solicitationNumber", "N/A")
            agency = item.get("departmentName", "N/A")
            date = item.get("postedDate", "N/A")
            naics = item.get("naics", {}).get("code", "")
            save_opportunity(sol_num, title, agency, date, naics)
    else:
        print(f"Failed to fetch SAM data: {response.status_code} - {response.text}")

# Fetch from USAspending.gov
def fetch_usaspending():
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    payload = {
        "filters": {
            "time_period": [{
                "start_date": week_ago.isoformat(),
                "end_date": today.isoformat()
            }],
            "award_type_codes": ["A", "B", "C", "D"]
        },
        "fields": ["Award ID", "Recipient Name", "Awarding Agency", "Start Date"],
        "limit": 20,
        "page": 1
    }
    response = requests.post(USASPENDING_API, json=payload)
    if response.status_code == 200:
        data = response.json()
        for result in data.get("results", []):
            sol_num = result.get("Award ID", "N/A")
            title = result.get("Recipient Name", "N/A")
            agency = result.get("Awarding Agency", {}).get("name", "N/A")
            date = result.get("Start Date", "N/A")
            save_opportunity(sol_num, title, agency, date, "")
    else:
        print(f"Failed to fetch USAspending data: {response.status_code} - {response.text}")

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

    query = "SELECT * FROM opportunities WHERE 1=1"
    params = []

    if keyword:
        query += " AND title LIKE ?"
        params.append(f"%{keyword}%")

    if start_date:
        query += " AND postedDate >= ?"
        params.append(start_date)
    if end_date:
        query += " AND postedDate <= ?"
        params.append(end_date)

    naics = request.args.get('naics', '')
    if naics:
        query += " AND naicsCode = ?"
        params.append(naics)

    query += " ORDER BY postedDate DESC LIMIT 50"

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()

    return render_template('home.html', user=session['user'], opportunities=results)

# Scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_store_opportunities, 'interval', hours=24)
scheduler.add_job(fetch_usaspending, 'interval', hours=24)
scheduler.add_job(send_email_alert, 'interval', days=1)
scheduler.start()

# Run
if __name__ == '__main__':
    setup_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
