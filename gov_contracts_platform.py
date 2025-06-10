import requests
import datetime
import sqlite3
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from typing import Optional, List, Dict
from dataclasses import dataclass
from contextlib import contextmanager
from urllib.parse import quote
from dotenv import load_dotenv
from flask import Flask, render_template

# Load environment variables
load_dotenv()

# Configure logging before any other operations
logging.basicConfig(
    level=getattr(logging, "INFO"),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('contract_fetcher.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder='templates', static_folder='static')

# Configuration class for environment variables
@dataclass
class Config:
    SAM_API_KEY: str = os.getenv("SAM_API_KEY")
    DB_FILE: str = os.getenv("DB_FILE", "/tmp/contract_data.db")
    SAM_URL: str = "https://api.sam.gov/prod/opportunities/v2/search"
    USA_API_URL: str = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    def validate(self):
        if not self.SAM_API_KEY:
            logger.error("SAM_API_KEY is not set. Please configure it in your environment variables.")
            raise ValueError("SAM_API_KEY is not set")
        logging.getLogger(__name__).setLevel(getattr(logging, self.LOG_LEVEL))

# Initialize configuration
config = Config()
config.validate()

# Reconfigure logging with the validated LOG_LEVEL
logging.getLogger(__name__).setLevel(getattr(logging, config.LOG_LEVEL))

@contextmanager
def database_connection():
    conn = sqlite3.connect(config.DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise
    finally:
        conn.close()

def setup_database():
    try:
        with database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS opportunities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    solicitation_number TEXT,
                    title TEXT,
                    agency TEXT,
                    date TEXT,
                    naics_code TEXT,
                    link TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(solicitation_number, source)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS awards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL,
                    award_id TEXT,
                    recipient_name TEXT,
                    agency TEXT,
                    date TEXT,
                    naics_code TEXT,
                    link TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(award_id, source)
                )
            ''')
            cursor.execute("SELECT COUNT(*) as count FROM users")
            if cursor.fetchone()['count'] == 0:
                cursor.execute(
                    "INSERT OR IGNORE INTO users (username, password) VALUES (?, ?)",
                    ("admin", "admin123")
                )
            conn.commit()
            logger.info("Database setup completed successfully")
    except sqlite3.Error as e:
        logger.error(f"Database setup failed: {e}")
        raise

def fetch_sam_data(params: Dict) -> List[Dict]:
    try:
        headers = {"X-API-Key": config.SAM_API_KEY}
        response = requests.get(
            config.SAM_URL,
            headers=headers,
            params=params,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        opportunities = data.get("opportunitiesData", [])
        logger.info(f"Fetched {len(opportunities)} opportunities from SAM.gov")
        return opportunities
    except requests.RequestException as e:
        logger.error(f"Failed to fetch SAM.gov data: {e}")
        return []

def fetch_usa_data(payload: Dict) -> List[Dict]:
    try:
        response = requests.post(
            config.USA_API_URL,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        awards = data.get("results", [])
        logger.info(f"Fetched {len(awards)} awards from USAspending.gov")
        return awards
    except requests.RequestException as e:
        logger.error(f"Failed to fetch USAspending.gov data: {e}\nPayload sent: {payload}")
        return []

def fetch_and_store_data(keyword: Optional[str] = None, naics: Optional[str] = None):
    logger.info("Starting data fetch at %s", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=30)

    sam_params = {
        "postedFrom": start_date.strftime("%m/%d/%Y"),
        "postedTo": end_date.strftime("%m/%d/%Y"),
        "ptype": "o",
        "limit": 50
    }
    if keyword:
        sam_params["keyword"] = keyword
    if naics:
        sam_params["naics"] = naics

    usa_payload = {
        "filters": {
            "time_period": [{"start_date": start_date.strftime("%Y-%m-%d"), "end_date": end_date.strftime("%Y-%m-%d")}],
            "award_type_codes": ["A", "B", "C", "D"]
        },
        "fields": ["Award ID", "Recipient Name", "NAICS Code", "Action Date", "Awarding Agency Name"],
        "limit": 50,
        "page": 1,
        "sort": "-Action Date"
    }
    if keyword:
        usa_payload["filters"]["keywords"] = [keyword]
    if naics:
        usa_payload["filters"]["naics_codes"] = [naics]

    sam_data = fetch_sam_data(sam_params)
    store_opportunities(sam_data)

    usa_data = fetch_usa_data(usa_payload)
    store_awards(usa_data)

    logger.info("Data fetch and store completed successfully")

def schedule_jobs():
    scheduler = BackgroundScheduler()
    scheduler.add_job(fetch_and_store_data, 'interval', hours=24)
    scheduler.start()
    logger.info("Scheduled jobs initialized")

if __name__ == "__main__":
    try:
        setup_database()
        fetch_and_store_data()
        schedule_jobs()
        port = int(os.getenv("PORT", 5000))
        app.run(debug=True, host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
        raise
