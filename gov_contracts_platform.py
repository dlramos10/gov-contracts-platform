# gov_contracts_platform.py
# Phase 3: Backend with SQLite + Flask UI + Email Scheduler + Basic Login System

import requests
import datetime
import sqlite3
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
        print(f"Failed
