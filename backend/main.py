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
    try to get extra records from the Elanco API and merge them in
    if it fails for any reason - carry on, the seed data is enough.
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

####HELPERS####
def where_clause(conditions):
    """turns a list of conditions into a SQL WHERE clause."""
    return ("WHERE " + " AND ".join(conditions)) if conditions else ""

####ROUTERS####
@app.get("/", tags=["General"])
def health_check():
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
    db.close()
    return {"status": "running", "sightings_in_database": count}


@app.get("/sightings", tags=["Sightings"])
def get_sightings(
    location:   Optional[str] = Query(None),
    species:    Optional[str] = Query(None),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    page:       int           = Query(1,  ge=1),
    per_page:   int           = Query(50, ge=1, le=200),
):
    """list of sightings with optional filters."""
    db = get_db()
    conditions, params = [], []

    if location:
        conditions.append("LOWER(location) = LOWER(?)")
        params.append(location)
    if species:
        conditions.append("LOWER(species) = LOWER(?)")
        params.append(species)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date + "T23:59:59")

    w = where_clause(conditions)
    total  = db.execute(f"SELECT COUNT(*) FROM sightings {w}", params).fetchone()[0]
    offset = (page - 1) * per_page
    rows   = db.execute(
        f"SELECT * FROM sightings {w} ORDER BY date DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    db.close()

    return {
        "data":        [dict(r) for r in rows],
        "total":       total,
        "page":        page,
        "total_pages": max(1, -(-total // per_page)),
    }

@app.get("/sightings/map", tags=["Sightings"])
def map_data(
    species:    Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date:   Optional[str] = Query(None),
):
    """
    one summary point for each city for the map markers
    groups everything by city so the frontend can draw one
    proportional circle per city rather than 1000 individual pins
    """
    db = get_db()
    conditions, params = [], []

    if species:
        conditions.append("LOWER(species) = LOWER(?)")
        params.append(species)
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date + "T23:59:59")

    w    = where_clause(conditions)
    rows = db.execute(
        f"SELECT location, COUNT(*) as total, MAX(date) as latest, lat, lng FROM sightings {w} GROUP BY location ORDER BY total DESC",
        params
    ).fetchall()

    result = []
    for row in rows:
        #SQLite doesn't have a "most common value" function so:
        #extra query to find the dominant species per city
        top = db.execute(
            f"SELECT species FROM sightings WHERE location = ? {('AND ' + ' AND '.join(conditions)) if conditions else ''} GROUP BY species ORDER BY COUNT(*) DESC LIMIT 1",
            [row["location"]] + params
        ).fetchone()

        result.append({
            "location":         row["location"],
            "lat":              row["lat"],
            "lng":              row["lng"],
            "total":            row["total"],
            "latest_sighting":  row["latest"],
            "dominant_species": top["species"] if top else "Unknown",
        })

    db.close()
    return result


@app.get("/stats/by-region", tags=["Stats"])
def stats_by_region(start_date: Optional[str] = Query(None), end_date: Optional[str] = Query(None)):
    """total sightings per city with percentage of overall total"""
    db = get_db()
    conditions, params = [], []

    if start_date:
        conditions.append("date >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date + "T23:59:59")

    w    = where_clause(conditions)
    rows = db.execute(f"SELECT location, COUNT(*) as count FROM sightings {w} GROUP BY location ORDER BY count DESC", params).fetchall()
    db.close()

    total = sum(r["count"] for r in rows)
    return {
        "total": total,
        "by_region": [
            {"location": r["location"], "count": r["count"], "percentage": round(r["count"] / total * 100, 1)}
            for r in rows
        ]
    }


@app.get("/stats/by-species", tags=["Stats"])
def stats_by_species(location: Optional[str] = Query(None)):
    """sighting counts per species, with optional city filter."""
    db     = get_db()
    params = []
    w      = ""

    if location:
        w = "WHERE LOWER(location) = LOWER(?)"
        params.append(location)

    rows  = db.execute(f"SELECT species, latin_name, COUNT(*) as count FROM sightings {w} GROUP BY species ORDER BY count DESC", params).fetchall()
    db.close()

    total = sum(r["count"] for r in rows)
    return {
        "total": total,
        "by_species": [
            {"species": r["species"], "latin_name": r["latin_name"], "count": r["count"], "percentage": round(r["count"] / total * 100, 1)}
            for r in rows
        ]
    }
