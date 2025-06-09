# gov_contracts_platform.py
# Phase 3: Backend with SQLite + Flask UI + Email Scheduler + Basic Login System

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

# Set up database and table
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            solicitationNumber TEXT PRIMARY KEY,
            title TEXT,
            agency TEXT,
            postedDate TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Save opportunity to the database
def save_opportunity(sol_num, title, agency, date):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO opportunities (solicitationNumber, title, agency, postedDate)
            VALUES (?, ?, ?, ?)
        ''', (sol_num, title, agency, date))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

# Fetch and save opportunities
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
            save_opportunity(sol_num, title, agency, date)
    else:
        print(f"Failed to fetch data: {response.status_code} - {response.text}")

# Send email alerts (placeholder logic)
def send_email_alert():
    msg = MIMEText("New federal contract opportunities available!")
    msg['Subject'] = 'Gov Contract Alerts'
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_SENDER

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

# Flask routes
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
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    if keyword:
        cursor.execute("SELECT * FROM opportunities WHERE title LIKE ?", (f"%{keyword}%",))
    else:
        cursor.execute("SELECT * FROM opportunities ORDER BY postedDate DESC LIMIT 10")
    results = cursor.fetchall()
    conn.close()
    return render_template('home.html', user=session['user'], opportunities=results)

# Schedule job
scheduler = BackgroundScheduler()
scheduler.add_job(fetch_and_store_opportunities, 'interval', hours=24)
scheduler.add_job(send_email_alert, 'interval', days=1)
scheduler.start()

# Main runner
if __name__ == '__main__':
    setup_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
