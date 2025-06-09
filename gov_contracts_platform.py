import requests
import datetime
import sqlite3
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler

# Make sure your existing code has these variables set:
# SAM_API_KEY, DB_FILE, SAM_URL, USA_API_URL

# Initialize logging
logging.basicConfig(level=logging.INFO)

# Extend your setup_database() to create new tables if not existing
def setup_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opportunities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            solicitation_number TEXT,
            title TEXT,
            agency TEXT,
            date TEXT,
            naics_code TEXT,
            link TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS awards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            award_id TEXT,
            recipient_name TEXT,
            agency TEXT,
            date TEXT,
            naics_code TEXT,
            link TEXT
        )
    ''')
    # Insert default user if none
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", ("admin", "admin123"))
    conn.commit()
    conn.close()


def fetch_and_store_data():
    logging.info("Starting scheduled data fetch...")

    # Connect to DB
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # Clear previous data
    cursor.execute("DELETE FROM opportunities")
    cursor.execute("DELETE FROM awards")
    conn.commit()

    # ---- Fetch from SAM.gov ----
    try:
        headers = {"X-API-Key": SAM_API_KEY}
        params = {
            "postedFrom": (datetime.date.today() - datetime.timedelta(days=30)).strftime("%m/%d/%Y"),
            "postedTo": datetime.date.today().strftime("%m/%d/%Y"),
            "ptype": "o",
            "limit": 50
        }
        response = requests.get(SAM_URL, headers=headers, params=params)
        if response.status_code == 200:
            data = response.json()
            for item in data.get("opportunitiesData", []):
                sol_num = item.get("solicitationNumber", "")
                title = item.get("title", "")
                agency = item.get("departmentName", "")
                raw_date = item.get("postedDate", "")
                try:
                    date_obj = datetime.datetime.strptime(raw_date[:10], "%m/%d/%Y")
                    date_str = date_obj.strftime("%Y-%m-%d")
                except:
                    date_str = ""
                naics_code = item.get("naics", {}).get("code", "")
                opp_id = item.get("noticeId", "")
                link = f"https://sam.gov/opp/{opp_id}/view" if opp_id else ""
                cursor.execute('''
                    INSERT INTO opportunities (source, solicitation_number, title, agency, date, naics_code, link)
                    VALUES (?, ?, ?, ?, ?, ?, ?)''',
                    ("SAM.gov", sol_num, title, agency, date_str, naics_code, link))
            conn.commit()
        else:
            logging.warning(f"SAM.gov API error: {response.status_code}")
    except Exception as e:
        logging.error(f"Error fetching SAM.gov data: {e}")

    # ---- Fetch from USAspending.gov ----
    try:
        start_date = (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = datetime.date.today().strftime("%Y-%m-%d")
        usa_payload = {
            "filters": {
                "time_period": [
                    {
                        "start_date": start_date,
                        "end_date": end_date
                    }
                ],
                "award_type_codes": ["A", "B", "C", "D"]
            },
            "fields": ["award_id", "recipient_name", "naics_code", "action_date", "awarding_agency_name"],
            "limit": 50,
            "page": 1,
            "sort": "-action_date"
        }
        # Optional filters if variables exist
        if 'keyword' in globals() and 'keyword' in globals() and keyword:
            usa_payload["filters"]["keywords"] = [keyword]
        if 'naics' in globals() and naics:
            usa_payload["filters"]["naics
