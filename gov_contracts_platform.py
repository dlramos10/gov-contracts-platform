# gov_contracts_platform.py
# Combined: Fetch from SAM.gov and USAspending.gov

import requests
import datetime
import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session
import smtplib
from email.mime.text import MIMEText
from apscheduler.schedulers.background import BackgroundScheduler

# Configuration
SAM_API_KEY = "your_real_sam_api_key_here"  # <-- replace this with your real key
SAM_URL = "https://api.sam.gov/opportunities/v2/search"
USA_API_URL = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
DB_FILE = "contracts.db"
EMAIL_SENDER = "your_email@example.com"
EMAIL_PASSWORD = "your_email_password"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

app = Flask(__name__)
app.secret_key = "your_secret_key_here"

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

def send_email_alert():
    msg = MIMEText("New federal contract opportunities available!")
    msg['Subject'] = 'Gov Contract Alerts'
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_SENDER
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)

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

    results = []

    # ---- SAM.gov ----
    try:
        headers = {"X-API-Key": SAM_API_KEY}
        params = {
            "postedFrom": start_date,
            "postedTo": end_date,
            "ptype": "o",
            "limit": 25
        }
        if keyword:
            params["q"] = keyword
        if naics:
            params["naics"] = naics

        response = requests.get(SAM_URL, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SAM.gov returned: {len(data.get('opportunitiesData', []))} items")
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
                opp_id = item.get("noticeId", "")
                link = f"https://sam.gov/opp/{opp_id}/view" if opp_id else ""
                results.append(("SAM.gov", sol_num, title, agency, date, naics_code, link))
        else:
            print(f"SAM.gov error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error fetching from SAM.gov: {e}")

    # ---- USAspending.gov ----
    try:
        usa_payload = {
            "filters": {
                "time_period": [
                    {
                        "start_date": datetime.datetime.strptime(start_date, "%m/%d/%Y").strftime("%Y-%m-%d"),
                        "end_date": datetime.datetime.strptime(end_date, "%m/%d/%Y").strftime("%Y-%m-%d")
                    }
                ],
                "award_type_codes": ["A", "B", "C", "D"]
            },
            "fields": ["award_id", "recipient_name", "naics_code", "action_date", "awarding_agency_name"],
            "limit": 25,
            "page": 1,
            "sort": "-action_date"
        }

        if keyword:
            usa_payload["filters"]["keywords"] = [keyword]
        if naics:
            usa_payload["filters"]["naics_codes"] = [naics]

        usa_response = requests.post(USA_API_URL, json=usa_payload)
        if usa_response.status_code == 200:
            usa_data = usa_response.json()
            print(f"✅ USAspending returned: {len(usa_data.get('results', []))} items")
            for item in usa_data.get("results", []):
                title = item.get("recipient_name", "N/A")
                agency = item.get("awarding_agency_name", "N/A")
                date = item.get("action_date", "Unknown")
                naics_code = item.get("naics_code", "N/A")
                link = "https://www.usaspending.gov"
                results.append(("USAspending", "Award", title, agency, date, naics_code, link))
        else:
            print(f"USAspending error {usa_response.status_code} - {usa_response.text}")
    except Exception as e:
        print(f"Error fetching from USAspending: {e}")

    if not results:
        print("⚠️ No results found. Try adjusting filters or dates.")

    return render_template('home.html', user=session['user'], opportunities=results)

scheduler = BackgroundScheduler()
scheduler.add_job(send_email_alert, 'interval', days=1)
scheduler.start()

if __name__ == '__main__':
    setup_database()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
