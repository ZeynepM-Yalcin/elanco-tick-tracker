# Elanco Data Analyst Technical Task - Tick Tracker
**A detailed write up of my architecture decisions, data handling strategy and what I would improve with more time is in the separate Architecture document.** 
- Backend: FastAPI (Python) + SQLite
- Frontend: Vanilla JS + Leaflet.js + Chart.js
- App: http://localhost:8000/app
- API Docs: http://localhost:8000/docs
- Repo: https://github.com/ZeynepM-Yalcin/elanco-tick-tracker

### Overview
This is a full-stack web application for mapping and reporting tick sightings across the UK. It processes the provided Excel dataset and integrates with the Elanco API endpoint, storing everything in a local SQLite database and serving through a REST API built with FastAPI. The frontendis a single page app with an interactive Leaflet map, Chart.js visualisations, a species education section and a sighting report form with an image upload.

### Technical Choices
#### FastAPI for the backend
I chose FastAPI because it auto generates a fully interactive Swagger UI at /docs, so every endpoint can be explored and tested without any extra tooling. It also handles query parameter validation and type checking automatically, which saved a lot of boilerplate. Python felt like the right language for data focused project where I might want to add analytics or ML features later.

#### SQLite for the database
SQLite needs no server, no configuration and no connection string. The database is a single file that gets created automatically on first run. For a dataset of around 1,000 records it is more than fast enough and it means anyone running the project has one less thing to install or set up before the app works.

#### Vanilla Javascript for the frontend
No build step, no node modules, no bundler. The frontend is three files you can read straight through. For a project of this scope a framework like React would have added complexity without adding anything meaningful, the app right now loads instantly and works the same way. Leaflet and Chart.js are fulled fron CDN so there are zero frontend dependencies to install.

#### Serving the frontend through FastAPI
Opening index.html as a file:// URL causes the browser to block API requests due to CORS policy. 

### How to Run
1. Instal dependencies

   `pip install -r requirements.txt`
3. Generate seed data (first time only)
   
   Converts the Excel file into seed_data.json, which the backend loads into SQLite on startup:

    `python backend/excel_to_json.py`
  
6. Start the server

   `uvicorn backend.main:app --reload --port 8000`
   
8. Open the app

•	App: http://localhost:8000/app
•	API docs (Swagger UI): http://localhost:8000/docs

## Requirements Coverage:
### Backend
| Requirement   | Second Header | Notes |
| ------------- | ------------- |-------|
| Data handling: seed data + live API with fallback  | Done  |   INSERT OR IGNORE for deduplication; incomplete records skipped; paginated map endpoint    |
| Search and filtering by time range and location  | Done  |   species, location, start_date, end_date query params on all relevant endpoints    |
| Sightings per region: /stats/by-region | Done | Count + percentage per city, filterable by date range|
| Trends over time: /sightings/timeline/{location} | Done | Month-by-month counts per city; also /stats/seasonal for full 12-month view|
| Error handling for API failures | Done  | Error handling for API failures	Done	try/except with timeout; server continues with seed data if API is unreachable |

### Frontend
| Requirement| Status| Notes |
|--|--|--|
| Interactive map with proportional markers |Done | Leaflet circles sized by count, coloured by dominant species |
|Filter controls: species and date range | Done |Dropdown + date inputs above the map; filters flow through to sidebar chart too |
| Sidebar with sighting detail and timeline chart | Done | Opens on city click; shows stats, monthly bar chart, Directions and Share buttons |
| Species identification guide| Done | Cards with Latin names, descriptions, and risk badges|
|Prevention tips | Done | Six tip cards covering all key prevention guidelines |
|Seasonal activity chart | Done| City + year dropdowns; always shows all 12 months even if some are zero|
|Report form with validation | Done| date, time, location, species fields; inline error messages; success/error banner|
|Image upload| Done| Optional photo; validated server-side for type + size; stored with UUID filename|

### Frontend - extension
|Requirement |Status | Notes|
| --| --| --|
| Accessibility features| Done| Semantic HTML, labels on all inputs, alt text, focus styles, contrast, responsive layout|
| Wireframes|Not done |Layout designed directly in code, no separate wireframe documents produced |

