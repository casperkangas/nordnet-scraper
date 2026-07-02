let masterData = [];
let currentSortKey = "⭐ Composite Score";
let isAscending = false;
let chartInstance = null;

// --- DYNAMIC COLUMN STATE ---
let allColumns = [];
let visibleColumns = [];
const hiddenForever = ["Date"]; // Never show in table

// Columns to hide by default on first load
const defaultHidden = [
  "Omistajia Nordnetissä*",
  "Buy",
  "Hold",
  "Sell",
  "Worst Case",
  "Probable Case",
  "Best Case",
  "Liikevaihto",
  "PEG",
  "P/E",
  "P/S",
  "P/B",
  "EBIT",
  "EPS",
  "Price ↑",
  "Price ↓",
  "Score ↑",
  "Score ↓",
  "Data Completeness %",
];

const root = document.documentElement;
const themeToggle = document.getElementById("theme-toggle");

let currentTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
  ? "dark"
  : "light";

root.setAttribute("data-theme", currentTheme);

if (themeToggle) {
  themeToggle.addEventListener("click", () => {
    currentTheme = currentTheme === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", currentTheme);

    if (masterData.length) {
      applyFilters();
    }
  });
}

function getThemeColor(name) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
}

async function initDashboard() {
  try {
    const response = await fetch("data/web_today_snapshot.json");
    masterData = await response.json();

    if (masterData.length === 0) return;

    // 1. Extract Date for the Header
    if (masterData[0].Date) {
      document.getElementById("last-updated-date").textContent =
        masterData[0].Date;
    }

    // 2. Setup Columns
    allColumns = Object.keys(masterData[0]).filter(
      (col) => !hiddenForever.includes(col),
    );

    // Initialize visible columns (exclude the default hidden ones)
    visibleColumns = allColumns.filter(
      (col) => !defaultHidden.some((hidden) => col.includes(hidden)),
    );

    buildColumnToggles();
    populateIndustryDropdown(masterData);
    applyFilters();
  } catch (error) {
    console.error("Error loading data:", error);
    document.getElementById("table-body").innerHTML = `
                    <tr><td class="px-4 py-4 text-red-500 font-medium">Failed to load real-time analytics data.</td></tr>`;
  }
}

// --- NEW: COLUMN TOGGLE UI ---
function buildColumnToggles() {
  const container = document.getElementById("column-toggles");
  container.innerHTML = ""; // Clear existing

  allColumns.forEach((col) => {
    const isActive = visibleColumns.includes(col);
    const btn = document.createElement("button");

    // Styling changes based on whether it is active or hidden
    btn.className = `px-3 py-1 text-xs font-medium rounded-full transition-colors border ${
      isActive
        ? "bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100"
        : "bg-slate-50 text-slate-400 border-slate-200 hover:bg-slate-100"
    }`;
    btn.textContent = col;

    btn.onclick = () => {
      if (visibleColumns.includes(col)) {
        // Remove it
        visibleColumns = visibleColumns.filter((c) => c !== col);
      } else {
        // Add it back in the original order
        const originalIndex = allColumns.indexOf(col);
        visibleColumns.splice(originalIndex, 0, col);
        // Sort visible array to match original array order
        visibleColumns.sort(
          (a, b) => allColumns.indexOf(a) - allColumns.indexOf(b),
        );
      }
      buildColumnToggles(); // Redraw buttons
      applyFilters(); // Redraw table
    };

    container.appendChild(btn);
  });
}

function updateSummaryCards(filteredData) {
  document.getElementById("kpi-total").textContent = filteredData.length;

  if (filteredData.length === 0) {
    document.getElementById("kpi-score").textContent = "-";
    document.getElementById("kpi-upside").textContent = "-";
    document.getElementById("kpi-sector").textContent = "-";
    return;
  }

  let totalScore = 0;
  let validScoreCount = 0;
  let totalUpside = 0;
  let validUpsideCount = 0;

  // Map to track industry performance
  const industryScores = {};

  filteredData.forEach((stock) => {
    const score = stock["⭐ Composite Score"];
    const upside = stock["Expected Upside"];
    const ind = stock["Industry"];

    if (typeof score === "number") {
      totalScore += score;
      validScoreCount++;

      if (ind) {
        if (!industryScores[ind]) industryScores[ind] = { total: 0, count: 0 };
        industryScores[ind].total += score;
        industryScores[ind].count++;
      }
    }
    if (typeof upside === "number") {
      totalUpside += upside;
      validUpsideCount++;
    }
  });

  // Find top sector
  let topSector = "-";
  let highestAvg = -1;
  for (const [ind, data] of Object.entries(industryScores)) {
    if (data.count >= 2) {
      // Only count sectors with at least 2 stocks
      const avg = data.total / data.count;
      if (avg > highestAvg) {
        highestAvg = avg;
        topSector = ind;
      }
    }
  }
  if (topSector === "-" && Object.keys(industryScores).length > 0) {
    // Fallback if no sector has 2+ stocks
    topSector = Object.keys(industryScores)[0];
  }

  document.getElementById("kpi-score").textContent =
    validScoreCount > 0 ? (totalScore / validScoreCount).toFixed(1) : "-";
  document.getElementById("kpi-upside").textContent =
    validUpsideCount > 0
      ? (totalUpside / validUpsideCount).toFixed(1) + "%"
      : "-";
  document.getElementById("kpi-sector").textContent = topSector;
}

function buildTableHeaders() {
  const thead = document.querySelector("#snapshot-table thead");
  let headerHTML = "<tr>";

  // Only loop through VISIBLE columns
  visibleColumns.forEach((header) => {
    let arrow = "";
    if (header === currentSortKey) {
      arrow = isAscending ? " ▲" : " ▼";
    }
    headerHTML += `
                    <th onclick="handleSort('${header}')" 
                        class="px-4 py-3 font-semibold tracking-wide text-xs uppercase cursor-pointer select-none hover:bg-slate-100 transition-colors duration-150">
                        ${header}${arrow}
                    </th>`;
  });
  headerHTML += "</tr>";
  thead.innerHTML = headerHTML;
}

function renderTable(dataToRender) {
  const tbody = document.getElementById("table-body");
  let rowsHTML = "";

  dataToRender.forEach((stock) => {
    rowsHTML += '<tr class="hover:bg-slate-50 transition-colors duration-150">';

    // Only render cells for VISIBLE columns
    visibleColumns.forEach((header) => {
      let cellValue = stock[header];
      if (cellValue === null || cellValue === undefined) {
        cellValue = "-";
      } else if (
        typeof cellValue === "number" &&
        !Number.isInteger(cellValue)
      ) {
        cellValue = cellValue.toFixed(2);
      }
      rowsHTML += `<td class="px-4 py-3 whitespace-nowrap">${cellValue}</td>`;
    });
    rowsHTML += "</tr>";
  });

  tbody.innerHTML = rowsHTML;
}

function updateChart(filteredData) {
  const ctx = document.getElementById("topStocksChart").getContext("2d");

  if (chartInstance) {
    chartInstance.destroy();
  }

  const top10 = filteredData.slice(0, 10);

  const labels = top10.map((stock) => stock.Ticker);
  const compositeScores = top10.map(
    (stock) => stock["⭐ Composite Score"] || 0,
  );
  const expectedUpsides = top10.map((stock) => stock["Expected Upside"] || 0);
  const momentumScores = top10.map((stock) => stock["Momentum"] || 0);

  const analystRatings = top10.map((stock) => {
    return stock["Analyst Rating"] !== null &&
      stock["Analyst Rating"] !== undefined
      ? stock["Analyst Rating"] * 20
      : null;
  });

  const chartGrid = getThemeColor("--chart-grid");
  const chartTick = getThemeColor("--chart-tick");
  const chartLegend = getThemeColor("--chart-legend");

  Chart.defaults.color = chartTick;
  Chart.defaults.borderColor = chartGrid;

  chartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Analyst Rating",
          data: analystRatings,
          type: "line",
          borderColor: "#ef4444",
          backgroundColor: "#ef4444",
          pointRadius: 5,
          pointHoverRadius: 6,
          borderWidth: 2,
          tension: 0.25,
          fill: false,
          order: 1,
        },
        {
          label: "Composite Score",
          data: compositeScores,
          backgroundColor: "#22c55e",
          borderRadius: 4,
          order: 2,
        },
        {
          label: "Expected Upside %",
          data: expectedUpsides,
          backgroundColor: "#3b82f6",
          borderRadius: 4,
          order: 3,
        },
        {
          label: "Momentum",
          data: momentumScores,
          backgroundColor: "#a855f7",
          borderRadius: 4,
          order: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          border: {
            display: false,
          },
          ticks: {
            color: chartTick,
            padding: 8,
          },
          grid: {
            color: chartGrid,
            drawBorder: false,
          },
        },
        x: {
          border: {
            display: false,
          },
          ticks: {
            color: chartTick,
            padding: 8,
          },
          grid: {
            display: false,
            drawBorder: false,
          },
        },
      },
      plugins: {
        legend: {
          display: true,
          position: "top",
          labels: {
            color: chartLegend,
            usePointStyle: true,
            boxWidth: 10,
            boxHeight: 10,
            padding: 16,
          },
        },
      },
    },
  });
}

function populateIndustryDropdown(data) {
  const dropdown = document.getElementById("industryFilter");
  const uniqueIndustries = [...new Set(data.map((stock) => stock.Industry))]
    .filter(Boolean)
    .sort();
  uniqueIndustries.forEach((ind) => {
    const option = document.createElement("option");
    option.value = ind;
    option.textContent = ind;
    dropdown.appendChild(option);
  });
}

function applyFilters() {
  const searchTerm = document.getElementById("searchInput").value.toUpperCase();
  const selectedIndustry = document.getElementById("industryFilter").value;

  let filteredData = masterData.filter((stock) => {
    const matchesSearch = stock.Ticker.toUpperCase().includes(searchTerm);
    const matchesIndustry =
      selectedIndustry === "ALL" || stock.Industry === selectedIndustry;
    return matchesSearch && matchesIndustry;
  });

  filteredData.sort((a, b) => {
    let valA = a[currentSortKey];
    let valB = b[currentSortKey];
    if (valA === null || valA === undefined) return 1;
    if (valB === null || valB === undefined) return -1;
    if (typeof valA === "string" && typeof valB === "string") {
      return isAscending ? valA.localeCompare(valB) : valB.localeCompare(valA);
    }
    return isAscending ? valA - valB : valB - valA;
  });

  buildTableHeaders();
  renderTable(filteredData);

  updateSummaryCards(filteredData);
  updateChart(filteredData);
}

function handleSort(headerKey) {
  if (currentSortKey === headerKey) {
    isAscending = !isAscending;
  } else {
    currentSortKey = headerKey;
    isAscending = false;
  }
  applyFilters();
}

document.getElementById("searchInput").addEventListener("input", applyFilters);
document
  .getElementById("industryFilter")
  .addEventListener("change", applyFilters);

initDashboard();
