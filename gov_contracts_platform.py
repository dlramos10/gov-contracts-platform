```python
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
    level=getattr(logging, "INFO"),  # Default LOG_LEVEL until config is initialized
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
    DB_FILE: str = os.getenv("DB_FILE", "/tmp/contract_data.db")  # Default to Render's writable /tmp
    SAM_URL: str = "https://api.sam.gov/prod/opportunities/v2/search"
    USA_API_URL: str = "https://api.usaspending.gov/api/v2/search/spending_by_transaction/"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    def validate(self):
        if not self.SAM_API_KEY:
            logger.error("SAM_API_KEY is not set. Please configure it in your environment variables.")
            raise ValueError("SAM_API_KEY is not set")
        # Update logging level based on config after validation
        logging.getLogger(__name__).setLevel(getattr(logging, self.LOG_LEVEL))

# Initialize configuration
config = Config()
config.validate()

# Reconfigure logging with the validated LOG_LEVEL
logging.getLogger(__name__).setLevel(getattr(logging, config.LOG_LEVEL))

# Set current date and time (07:55 PM EDT, June 09, 2025)
current_datetime = datetime.datetime(2025, 6, 9, 19, 55, tzinfo=datetime.timezone(datetime.timedelta(hours=-4)))  # EDT is UTC-4

# Log startup with current date and time
logger.info(f"Application starting at {current_datetime.strftime('%Y-%m-%d %I:%M %p %Z')}")

@contextmanager
def database_connection():
    """Context manager for database connections"""
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
    """Initialize database schema and default user"""
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
                    ("admin", "admin123")  # Use hashed passwords in production
                )
            conn.commit()
            logger.info("Database setup completed successfully")
    except sqlite3.Error as e:
        logger.error(f"Database setup failed: {e}")
        raise

def fetch_sam_data(params: Dict) -> List[Dict]:
    """Fetch opportunities from SAM.gov"""
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
    """Fetch awards from USAspending.gov"""
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
        logger.error(f"Failed to fetch USAspending.gov data: {e}")
        return []

def store_opportunities(opportunities: List[Dict]):
    """Store SAM.gov opportunities in database"""
    with database_connection() as conn:
        cursor = conn.cursor()
        for item in opportunities:
            try:
                date_str = ""
                raw_date = item.get("postedDate", "")
                if raw_date:
                    date_obj = datetime.datetime.strptime(raw_date[:10], "%Y-%m-%d")
                    date_str = date_obj.strftime("%Y-%m-%d")
                cursor.execute('''
                    INSERT OR IGNORE INTO opportunities 
                    (source, solicitation_number, title, agency, date, naics_code, link)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    "SAM.gov",
                    item.get("solicitationNumber", ""),
                    item.get("title", ""),
                    item.get("departmentName", ""),
                    date_str,
                    item.get("naics", {}).get("code", ""),
                    f"https://sam.gov/opp/{quote(item.get('noticeId', ''))}/view"
                ))
            except (ValueError, sqlite3.Error) as e:
                logger.warning(f"Failed to process opportunity {item.get('solicitationNumber', '')}: {e}")
                continue
        conn.commit()

def store_awards(awards: List[Dict]):
    """Store USAspending.gov awards in database"""
    with database_connection() as conn:
        cursor = conn.cursor()
        for item in awards:
            try:
                date_str = ""
                raw_date = item.get("action_date", "")
                if raw_date:
                    date_obj = datetime.datetime.strptime(raw_date[:10], "%Y-%m-%d")
                    date_str = date_obj.strftime("%Y-%m-%d")
                cursor.execute('''
                    INSERT OR IGNORE INTO awards 
                    (source, award_id, recipient_name, agency, date, naics_code, link)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    "USAspending.gov",
                    item.get("award_id", ""),
                    item.get("recipient_name", ""),
                    item.get("awarding_agency_name", ""),
                    date_str,
                    item.get("naics_code", ""),
                    f"https://www.usaspending.gov/award/{quote(item.get('award_id', ''))}"
                ))
            except (ValueError, sqlite3.Error) as e:
                logger.warning(f"Failed to process award {item.get('award_id', '')}: {e}")
                continue
        conn.commit()

def fetch_and_store_data(keyword: Optional[str] = None, naics: Optional[str] = None):
    """Main function to fetch and store data from both sources"""
    logger.info("Starting scheduled data fetch at %s", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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
        "fields": ["award_id", "recipient_name", "naics_code", "action_date", "awarding_agency_name"],
        "limit": 50,
        "page": 1,
        "sort": "-action_date"
    }
    if keyword:
        usa_payload["filters"]["keywords"] = [keyword]
    if naics:
        usa_payload["filters"]["naics_codes"] = [naics]
    
    try:
        with database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM opportunities")
            cursor.execute("DELETE FROM awards")
            conn.commit()
        
        sam_data = fetch_sam_data(sam_params)
        store_opportunities(sam_data)
        
        usa_data = fetch_usa_data(usa_payload)
        store_awards(usa_data)
        
        logger.info("Data fetch and store completed successfully")
    except Exception as e:
        logger.error(f"Data fetch failed: {e}")
        raise

def schedule_jobs():
    """Setup scheduled jobs"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        fetch_and_store_data,
        'interval',
        hours=24,
        next_run_time=current_datetime  # Start immediately at the specified time
    )
    scheduler.start()
    logger.info("Scheduled jobs initialized")

@app.route('/')
def home():
    """Render the home page with opportunities and awards"""
    try:
        with database_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM opportunities ORDER BY date DESC")
            opportunities = [dict(row) for row in cursor.fetchall()]
            cursor.execute("SELECT * FROM awards ORDER BY date DESC")
            awards = [dict(row) for row in cursor.fetchall()]
        return render_template('home.html', opportunities=opportunities, awards=awards)
    except sqlite3.Error as e:
        logger.error(f"Database query failed: {e}")
        return "Error loading data. Check logs.", 500

if __name__ == "__main__":
    try:
        setup_database()
        schedule_jobs()
        port = int(os.getenv("PORT", 5000))  # Use Render's PORT or default to 5000
        app.run(debug=True, host='0.0.0.0', port=port)
    except Exception as e:
        logger.error(f"Application initialization failed: {e}")
        raise
```
