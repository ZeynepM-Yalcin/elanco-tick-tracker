"""
To run:
    uvicorn main:app --reload --port 8000

then visit http://localhost:8000/docs to see all the endpoints.
"""

import os
import json
import sqlite3
import requests

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional


####API SETUP####

app = FastAPI(
    title="UK Tick Tracker API",
    description="Crowdsourced tick sighting data across the UK. Built for the Elanco placement challenge",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR     = os.path.dirname(__file__)
DB_PATH      = os.path.join(BASE_DIR, "tick_tracker.db")
SEED_FILE    = os.path.join(BASE_DIR, "seed_data.json")
ELANCO_API   = "https://dev-task.elancoapps.com/sightings"

#coordinates for UK cities in the dataset
CITY_COORDS = {
    "London":      (51.5074, -0.1278),
    "Manchester":  (53.4808, -2.2426),
    "Birmingham":  (52.4862, -1.8904),
    "Leeds":       (53.8008, -1.5491),
    "Edinburgh":   (55.9533, -3.1883),
    "Glasgow":     (55.8642, -4.2518),
    "Bristol":     (51.4545, -2.5879),
    "Liverpool":   (53.4084, -2.9916),
    "Sheffield":   (53.3811, -1.4701),
    "Newcastle":   (54.9783, -1.6178),
    "Nottingham":  (52.9548, -1.1581),
    "Cardiff":     (51.4816, -3.1791),
    "Southampton": (50.9097, -1.4044),
    "Leicester":   (52.6369, -1.1398),
}


####DATABASE####

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  #row["column"] instead of row[0]
    return conn


def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS sightings (
            id               TEXT PRIMARY KEY,
            date             TEXT NOT NULL,
            location         TEXT NOT NULL,
            species          TEXT,
            latin_name       TEXT,
            lat              REAL,
            lng              REAL
        )
    """)
    db.commit()
    db.close()


def load_seed_data():
    """load the 1000 sightings from the excel export JSON into the database"""
    if not os.path.exists(SEED_FILE):
        print("  seed_data.json not found, skipping")
        return

    with open(SEED_FILE) as f:
        records = json.load(f)

    db = get_db()
    inserted = 0

    for r in records:
        if not r.get("id") or not r.get("date") or not r.get("location"):
            continue  #skipping incomplete records

        city = r["location"]
        lat, lng = CITY_COORDS.get(city, (None, None))

        db.execute(
            "insert or ignore into sightings (id, date, location, species, latin_name, lat, lng) VALUES (?,?,?,?,?,?,?)",
            [r["id"], r["date"][:19], city, r.get("species", "Unknown"), r.get("latinName", ""), lat, lng]
        )
        inserted += 1

    db.commit()
    db.close()
    print(f"  Seed data: {inserted} records loaded")

def fetch_external_api():
    """
    Try to get extra records from the Elanco API and merge them in.
    If it fails for any reason we just carry on - the seed data is enough.
    """
    try:
        resp = requests.get(ELANCO_API, timeout=6)
        resp.raise_for_status()
        records = resp.json()

        if isinstance(records, dict):
            records = records.get("data") or records.get("sightings") or []

        db = get_db()
        inserted = 0

        for r in records:
            if not r.get("id") or not r.get("date") or not r.get("location"):
                continue
            city = r["location"]
            lat, lng = CITY_COORDS.get(city, (None, None))
            db.execute(
                "INSERT OR IGNORE INTO sightings (id, date, location, species, latin_name, lat, lng, reported_by_user) VALUES (?,?,?,?,?,?,?,?)",
                [r["id"], r["date"][:19], city, r.get("species","Unknown"), r.get("latinName",""), lat, lng, "API"]
            )
            inserted += 1

        db.commit()
        db.close()
        print(f"  External API: {inserted} new records added")

    except requests.exceptions.ConnectionError:
        print("  External API unreachable - continuing with seed data only")
    except Exception as e:
        print(f"  External API error: {e} - continuing with seed data only")


####STARTUP####

@app.on_event("startup")
def startup():
    print("Setting up database...")
    init_db()
    print("Loading seed data...")
    load_seed_data()
    print("Fetching external API...")
    fetch_external_api()
    print("\nReady! Docs at http://localhost:8000/docs\n")
