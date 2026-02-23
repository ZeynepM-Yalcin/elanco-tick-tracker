# Elanco Data Analyst Technical Task - Tick Tracker
**A detailed write up of my architecture decisions, data handling strategy and what I would improve with more time is in the separate Architecture document.** 

Demo video: https://www.youtube.com/watch?v=L6GflDgTeuM 
- Backend: FastAPI (Python) + SQLite
- Frontend: Vanilla JS + Leaflet.js + Chart.js
- App: http://localhost:8000/app
- API Docs: http://localhost:8000/docs
- Repo: https://github.com/ZeynepM-Yalcin/elanco-tick-tracker
- I also uploaded the database to the backend, but this is actually in the gitignore. The database is created when the program runs

### Overview
This is my full-stack web application for mapping and reporting tick sightings across the UK. It processes the provided Excel dataset and integrates with the Elanco API endpoint, storing everything in a local SQLite database and serving through a REST API built with FastAPI. The frontendis a single page app with an interactive Leaflet map, Chart.js visualisations, a species education section and a sighting report form with an image upload.

### Technical Choices
#### FastAPI for the backend
I chose FastAPI because it auto generates a fully interactive Swagger UI at /docs, so every endpoint can be explored and tested without any extra tooling. It also handles query parameter validation and type checking automatically, which saved a lot of boilerplate. Python felt like the right language for data focused project where I might want to add analytics or ML features later.

#### SQLite for the database
SQLite needs no server, no configuration and no connection string. The database is a single file that gets created automatically on first run. For a dataset of around 1,000 records it is more than fast enough and it means anyone running the project has one less thing to install or set up before the app works.

#### Vanilla Javascript for the frontend
No build step, no node modules, no bundler. The frontend is three files you can read straight through. For a project of this scope a framework like React would have added complexity without adding anything meaningful, the app right now loads instantly and works the same way. Leaflet and Chart.js are fulled fron CDN so there are zero frontend dependencies to install.

#### Serving the frontend through FastAPI
Opening index.html as a file:// URL causes the browser to block API requests due to CORS policy. Rather than running a separate dev server, I mounted the frontend folder as a static directory in FastAPI and added a /app route that serves index.html. One server handles both the API and th UI thus, simpler to run and simpler to explain.

#### Data handling - seed data strategy
The Excel file is the dataset provided in the brief, so I treated it as the guaranteed data source. The API endpoint has 'dev' in its URL, which indicates a development environment rather than a production system. Dev environments get restarted, go down for maintanance, or could be retired. There is also no guarantee that the person evaluating the submission will have internet access or will not be behind a firewall. Depending on the API being available at runtime would be a fragile design.

Instead, I pre-converted the Excel file into seed_data.json using a separate script and committed to the repository. This is only done once. The backend loads this as its guaranteed baseline on every startup. The live API is still fetched on startup and any new records are merged in, but it's not a dependency. If it fails for any reason the app continues working normally. 

#### Data handling - duplicated and incomplete records
Both the seed loader and the API fetcher use INSERT OR IGNORE rather than a plain INSERT. SQLite enforeces the id column as a primary key, so any duplicate is silently skipped. Restarting the server never creates duplicate records and API records that overlap with seed data are not double counted. Before any insert, the code also checks that the three minimum required fields are present (id, date, location) and skips the record entirely if any are missing, rather than inserting a row with NULL values that would break the frontend.

#### Search and filtering
Filters are built as a dynamic WHERE clause, each filter parameter is only added to the conditions list if it was actually passed in, so requests with no filters return all records without any unnecessary SQL. LOWER() is applied to both sides of string comparisons so filtering is always case-insensitive. The end date filter appends T23:59:59 server-side so filtering to a specific date includes the entire day, not just records from midnight.

#### Data reporting - endpoint design
The brief was the starting point - it explicitly asked for 'number of sightings per region' and 'trends over time', which mapped directly to /stats/by-region and /sightings/timeline. From there, standard REST conventions guided the naming: endpoints are nouns not verbs, grouped by what they represent. Raw sighting records live under /sightings, aggregate insights under /stats. The map gets its own endpoint (/sightings/map) because it needs a different shape of data - one summary object per city rather than individual records - so grouping 1,000 rows in the browser would have been wasteful.

#### Error handling
The external API call uses a two-layer try/except — ConnectionError is caught specifically for a clear log message, and a broad Exception catches everything else so no edge case can crash the startup sequence. Using a 6second timeout prevents the server hanging if the API is slow rather than fully down. On the frontend, all API calls go through a single fetchJSON() helper that wraps fetch() in a try/catch and returns null on failure, every caller treats null as a no-op so a broken endpoint never causes a white screen

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

### What I would do better with more time
#### Wireframes
I designed the UI directly in HTML and CSS using the brief's example screenshot as a rough reference point. In a real project I would sketch wireframes in Figma first, agreeing on layout and information hierarchy before writing code is faster overall, especially once stakeholder feedback is involved.
#### Automated tests
This is a practice I'm trying to do more in my projects. I would write pytest unit tests for the database functions, particularly the duplicate handling, date slicing, and zero-filling logic, and integration tests for each API endpoint using FastAPI's built-in TestClient. The fetchJSON() helper in the frontend would also be worth a Jest unit test.
#### AI / ML insights
The backend brief lists AI/ML insights as an extension task. I think the dataset has enough information to make this interesting. A linear regression on monthly sighting counts per city would tell you whether activity is trending up or down year on year, and a seasonal decomposition would let you predict likely high activity months. Python's scikit-learn could fit into the existing FastAPI stack for this and I think it is the kind of addition that would directly support Elanco's public health awareness goals for the tool.

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






