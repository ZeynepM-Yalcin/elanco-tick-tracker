"""
To run:
    uvicorn backend.main:app --reload --port 8000

then visit http://localhost:8000/docs to see all the endpoints
or go to http://localhost:8000/app to open the actual UI
"""

import os
import json
import uuid
import sqlite3
import requests

from fastapi import FastAPI, Query, Form, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Optional


####API SETUP####

app = FastAPI(
    title="UK Tick Tracker API",
    description="Tick sighting data across the UK. Built for the Elanco placement challenge",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
#using __file__ so all paths work regardless of where you run uvicorn from
BASE_DIR     = os.path.dirname(__file__)           # points to backend/
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")  # points to frontend/
DB_PATH      = os.path.join(BASE_DIR, "tick_tracker.db")
SEED_FILE    = os.path.join(BASE_DIR, "seed_data.json")
UPLOAD_DIR   = os.path.join(BASE_DIR, "uploads")
ELANCO_API   = "https://dev-task.elancoapps.com/sightings"

os.makedirs(UPLOAD_DIR, exist_ok=True) #create uploads folder if it doesnt exist yet
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
#serve the frontend JS/CSS/images through /static
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
ALLOWED_IMAGE_TYPES = {"png", "jpg", "jpeg", "gif", "webp"}

#hardcoded coordinates for UK cities in the dataset
#the excel data only has city names, not coordinates so i looked these up
#and mapped them manually so map markers work without any geocoding api
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
    conn.row_factory = sqlite3.Row  #row["column"] instead of row[0], easier to read
    return conn


def init_db():
    db = get_db()
    #safe to call everytime on startup since it only actually creates the table the very first time
    db.execute("""
    CREATE TABLE IF NOT EXISTS sightings (
        id               TEXT PRIMARY KEY,
        date             TEXT NOT NULL,
        location         TEXT NOT NULL,
        species          TEXT,
        latin_name       TEXT,
        lat              REAL,
        lng              REAL,
        image_path       TEXT,
        reported_by_user TEXT DEFAULT 'System'
    )
    """)
    db.commit()
    db.close()


def load_seed_data():
    """load the 1000 sightings from the excel export JSON into the database
    INSERT OR IGNORE means if we restart the server,
    duplicate records won't get added again — the primary key (id) handles that
    """
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
        lat, lng = CITY_COORDS.get(city, (None, None))#return none none if coordinates not found

        db.execute(
            "INSERT OR IGNORE INTO sightings (id, date, location, species, latin_name, lat, lng) VALUES (?,?,?,?,?,?,?)",
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
    #this runs automatically when uvicorn starts, before any requests come in
    #create table the load data into it
    print("Setting up database...")
    init_db()
    print("Loading seed data...")
    load_seed_data()
    print("Fetching external API...")
    fetch_external_api()
    print("\nReady! Docs at http://localhost:8000/docs\n")

####HELPERS####
def where_clause(conditions):
    """turns a list of conditions into a SQL WHERE clause
    returns an empty string if the list is empty, so queries still work with no filters"""
    return ("WHERE " + " AND ".join(conditions)) if conditions else ""

####ROUTERS####
@app.get("/app", include_in_schema=False)
def serve_frontend():
    #serves index.html when you visit /app in the browser
    #include_in_schema=False keeps it out of the /docs page since it's not a real API endpoint
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

@app.get("/", tags=["General"])
def health_check():
    #quick check that the server is running and db is loaded
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

    #build up the WHERE clause dynamically based on whichever filters were passed in
    #using LOWER() on both sides makes the comparison case-insensitive
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

    #rounds up without importing math
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

@app.get("/sightings/timeline/{location}", tags=["Sightings"])
def timeline(location: str, species: Optional[str] = Query(None)):
    """monthly sighting counts for a city - used for the sidebar chart"""
    db     = get_db()
    params = [location]
    extra  = ""

    if species:
        extra = "AND LOWER(species) = LOWER(?)"
        params.append(species)

    rows = db.execute(
        f"SELECT strftime('%Y-%m', date) as month, COUNT(*) as count FROM sightings WHERE LOWER(location) = LOWER(?) {extra} GROUP BY month ORDER BY month",
        params
    ).fetchall()
    db.close()

    return {"location": location, "timeline": [dict(r) for r in rows]}


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
    """sighting counts per species, with optional city filter"""
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

@app.get("/stats/seasonal", tags=["Stats"])
def seasonal(
    location: str           = Query(..., description="City name"),
    year:     Optional[str] = Query(None, description="4-digit year, or leave blank for all years"),
):
    """monthly breakdown for a city - drives the seasonal activity chart"""
    db     = get_db()
    params = [location]
    extra  = ""

    if year:
        extra = "AND strftime('%Y', date) = ?"
        params.append(year)

    rows = db.execute(
        f"SELECT CAST(strftime('%m', date) AS INTEGER) as month_num, COUNT(*) as count FROM sightings WHERE LOWER(location) = LOWER(?) {extra} GROUP BY month_num ORDER BY month_num",
        params
    ).fetchall()
    db.close()

    MONTHS   = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    #convert the rows into a dict keyed by month number so can easily fill in the gaps
    by_month = {r["month_num"]: r["count"] for r in rows}

    return {
        "location": location,
        "year":     year or "all years",
        "data":     [{"month": MONTHS[i], "month_num": i+1, "count": by_month.get(i+1, 0)} for i in range(12)]
    }

@app.post("/report", status_code=201, tags=["Report"])
async def report_sighting(
    date:        str                  = Form(...),
    time:        str                  = Form(...),
    location:    str                  = Form(...),
    species:     str                  = Form(...),
    reported_by: str                  = Form("Anonymous"),
    image:       Optional[UploadFile] = File(None),
):
    """submit a new tick sighting. accepts multipart/form-data so can handle the optional photo"""
    image_filename = None

    if image and image.filename:
        ext = image.filename.rsplit(".", 1)[-1].lower()
        if ext not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(status_code=400, detail="Image must be png, jpg, jpeg, gif, or webp")

        contents = await image.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image must be under 5MB")

        image_filename = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(UPLOAD_DIR, image_filename), "wb") as f:
            f.write(contents)

    lat, lng = CITY_COORDS.get(location, (None, None))
    db = get_db()

    try:
        db.execute(
            "INSERT INTO sightings (id, date, location, species, latin_name, lat, lng, image_path, reported_by_user) VALUES (?,?,?,?,?,?,?,?,?)",
            [uuid.uuid4().hex, f"{date}T{time}:00", location, species, "", lat, lng, image_filename, reported_by]
        )
        db.commit()
    except Exception as e:
        db.close()
        raise HTTPException(status_code=500, detail=str(e))

    db.close()
    return {"success": True, "message": "Sighting recorded - thank you!"}


@app.get("/meta/cities", tags=["Meta"])
def get_cities():
    """list of UK cities with coordinates"""
    return [{"city": city, "lat": lat, "lng": lng} for city, (lat, lng) in sorted(CITY_COORDS.items())]


@app.get("/meta/species", tags=["Meta"])
def get_species():
    """distinct species in the database"""
    db   = get_db()
    rows = db.execute("SELECT DISTINCT species, latin_name FROM sightings ORDER BY species").fetchall()
    db.close()
    return [dict(r) for r in rows]

app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/app", include_in_schema=False)
def serve_frontend():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))
