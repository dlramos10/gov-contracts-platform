# Government Contracts Platform

A Python Flask application to fetch and display government contract opportunities (SAM.gov) and awards (USAspending.gov) in a SQLite database, with a web interface featuring the Titan Government Services logo. Deployed on Render at https://titan-gov-services.onrender.com.

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/dlramos10/gov-contracts-platform.git


Install dependencies:pip install -r requirements.txt


Create a .env file based on .env.example:cp .env.example .env

Edit .env with your SAM.gov API key and other settings.

Usage
Run locally:
python gov_contracts_platform.py

Visit http://localhost:5000.
Deployed instance: https://titan-gov-services.onrender.com (may sleep on free tier).
Environment Variables
See .env.example:

SAM_API_KEY: Required. Obtain from https://api.sam.gov.
DB_FILE: SQLite database file (default: /tmp/contract_data.db on Render).
LOG_LEVEL: Logging level (e.g., INFO, DEBUG).

Project Structure
gov-contracts-platform/
├── gov_contracts_platform.py  # Main Flask application
├── requirements.txt          # Python dependencies
├── .gitignore               # Git ignore rules
├── .env.example             # Environment variable template
├── templates/
│   └── home.html            # HTML template for web interface
├── static/
│   └── logo.png             # Titan Government Services logo
└── README.md                # Project documentation

Notes

Default admin user: admin/admin123. For production, implement password hashing.
Data is fetched for the past 30 days, limited to 50 records per source.
Logs are saved to contract_fetcher.log.
Bootstrap is used for styling (loaded via CDN).
Render free tier may sleep after inactivity; consider upgrading for continuous operation.
Uses dynamic port (PORT) for Render compatibility.

License
MIT License```
