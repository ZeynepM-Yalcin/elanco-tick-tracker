const API = "http://localhost:8000";

//shortcut so i dont have to write document.getElementById everywhere
function el(id) { return document.getElementById(id); }

//colours for each tick species — used on the map circles and charts
const speciesColours = {
  "Marsh tick":           "#43a047",
  "Southern rodent tick": "#fb8c00",
  "Passerine tick":       "#e53935",
  "Tree-hole tick":       "#8e24aa",
  "Fox/badger tick":      "#3949ab",
};

function getColour(species) {
  return speciesColours[species] || "#757575";
}

//helper to fetch json from the api without repeating try/catch everywhere
async function fetchJSON(url) {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (err) {
    console.error("API call failed:", url, err);
    return null;
  }
}

//formats a date string into something nicer like "14 Mar 2023"
function formatDate(dateStr) {
  if (!dateStr) return "Unknown";
  return new Date(dateStr).toLocaleDateString("en-GB", {
    day: "numeric", month: "short", year: "numeric"
  });
}



// MAP : leaflet setup and marker rendering


const map = L.map("map", { center: [53.5, -2.0], zoom: 6 });

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap contributors",
}).addTo(map);

//layer group so can clear and redraw markers easily
const markerLayer = L.layerGroup().addTo(map);

//reads the current filter values and builds query params from them
function getFilterParams() {
  const params = new URLSearchParams();
  const species = el("filter-species").value;
  const start = el("filter-start").value;
  const end = el("filter-end").value;

  if (species) params.set("species", species);
  if (start) params.set("start_date", start);
  if (end) params.set("end_date", end);

  return params;
}

//calculates how big a city circle should be based on its count
//biggest city gets radius 40, smallest gets 12
function calcRadius(count, maxCount) {
  return 12 + (count / maxCount) * 28;
}

async function refreshMap() {
  const params = getFilterParams();
  const cities = await fetchJSON(`${API}/sightings/map?${params}`);
  if (!cities) return;

  markerLayer.clearLayers();

  //need the max count to scale the circles proportionally
  const highest = Math.max(...cities.map(c => c.total), 1);

  cities.forEach(city => {
    if (!city.lat || !city.lng) return;

    const circle = L.circleMarker([city.lat, city.lng], {
      radius: calcRadius(city.total, highest),
      fillColor: getColour(city.dominant_species),
      color: "white",
      weight: 2,
      fillOpacity: 0.75,
    });

    circle.bindTooltip(`<strong>${city.location}</strong><br>${city.total} sightings`);
    circle.on("click", () => showCityPanel(city, params));
    markerLayer.addLayer(circle);
  });
}



// SIDEBAR : city detail panel that opens when a marker is clicked


//keeping track of chart instances so they can be destroyed them before making new ones
//(chart.js gets upset if you don't do this lol)
let cityChart = null;

async function showCityPanel(city, filterParams) {
  el("sidebar").classList.remove("hidden");

  //grab the timeline data for the mini bar chart
  const speciesParam = filterParams.get("species") || "";
  let timelineUrl = `${API}/sightings/timeline/${encodeURIComponent(city.location)}`;
  if (speciesParam) timelineUrl += `?species=${encodeURIComponent(speciesParam)}`;

  const timelineData = await fetchJSON(timelineUrl);
  const months = timelineData ? timelineData.timeline : [];

  //build the sidebar html
  const col = getColour(city.dominant_species);

  el("sidebar-content").innerHTML = `
    <p class="city-name">${city.location}</p>
    <p class="city-meta">Latest sighting: ${formatDate(city.latest_sighting)}</p>

    <div class="city-stats">
      <div class="city-stat">
        <div class="city-stat-num">${city.total}</div>
        <div class="city-stat-label">Sightings</div>
      </div>
      <div class="city-stat">
        <div class="city-stat-num" style="font-size:.9rem; color:${col}">${city.dominant_species}</div>
        <div class="city-stat-label">Top species</div>
      </div>
    </div>

    ${months.length > 0 ? `
      <div class="chart-wrap">
        <h4>Monthly activity</h4>
        <canvas id="sidebar-chart" height="130"></canvas>
      </div>
    ` : ""}

    <div class="action-row">
      <button class="action-btn" onclick="window.open('https://www.google.com/maps/dir/?api=1&destination=${city.lat},${city.lng}','_blank')">🗺 Directions</button>
      <button class="action-btn" onclick="navigator.clipboard.writeText(window.location.href).then(()=>alert('Link copied!'))">🔗 Share</button>
    </div>
  `;

  //draw the mini chart if there is a timeline data
  if (months.length > 0) {
    if (cityChart) cityChart.destroy();
    cityChart = new Chart(el("sidebar-chart").getContext("2d"), {
      type: "bar",
      data: {
        labels: months.map(m => m.month),
        datasets: [{
          data: months.map(m => m.count),
          backgroundColor: col + "99",
          borderColor: col,
          borderWidth: 1,
          borderRadius: 3,
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { font: { size: 9 }, maxRotation: 60 }, grid: { display: false } },
          y: { ticks: { font: { size: 9 } }, beginAtZero: true }
        }
      }
    });
  }
}


// TABS : switches between species guide / prevention / seasonal


function setupTabs() {
  const buttons = document.querySelectorAll(".tab-btn");
  const panels = document.querySelectorAll(".tab-panel");

  buttons.forEach(btn => {
    btn.addEventListener("click", () => {
      //deactivate all tabs first
      buttons.forEach(b => b.classList.remove("active"));
      panels.forEach(p => p.classList.add("hidden"));

      //then activate the one that was clicked
      btn.classList.add("active");
      el("tab-" + btn.dataset.tab).classList.remove("hidden");
    });
  });
}


// SEASONAL CHART : bar chart showing monthly sightings per city


let yearlyChart = null;

async function loadSeasonalChart() {
  const city = el("s-city").value;
  const year = el("s-year").value;

  const params = new URLSearchParams({ location: city });
  if (year) params.set("year", year);

  const data = await fetchJSON(`${API}/stats/seasonal?${params}`);
  if (!data) return;

  //destroy old chart before creating a new one
  if (yearlyChart) yearlyChart.destroy();

  const chartLabel = year ? `${city} ${year}` : city;

  yearlyChart = new Chart(el("seasonal-chart").getContext("2d"), {
    type: "bar",
    data: {
      labels: data.data.map(d => d.month),
      datasets: [{
        label: chartLabel,
        data: data.data.map(d => d.count),
        backgroundColor: "#2d7a4f99",
        borderColor: "#2d7a4f",
        borderWidth: 1.5,
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "top" } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true, ticks: { stepSize: 1 } }
      }
    }
  });
}

// STARTUP : wire everything up when the page loads


document.addEventListener("DOMContentLoaded", async () => {

  //filter buttons
  el("apply-filters").addEventListener("click", refreshMap);
  el("reset-filters").addEventListener("click", () => {
    el("filter-species").value = "";
    el("filter-start").value = "2012-01-01";
    el("filter-end").value = "2024-12-31";
    refreshMap();
  });

  //close sidebar button
  el("close-sidebar").addEventListener("click", () => {
    el("sidebar").classList.add("hidden");
  });

  //seasonal chart
  el("load-seasonal").addEventListener("click", loadSeasonalChart);

  //set up the tabs
  setupTabs();

  //load the map straight away
  refreshMap();

  // etch the total count for the hero section
  const stats = await fetchJSON(`${API}/`);
  if (stats) {
    el("stat-total").textContent = stats.sightings_in_database.toLocaleString();
  }

  //load the seasonal chart with default values
  loadSeasonalChart();
});
