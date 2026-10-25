// Small helpers around Chart.js, shared by the seller and admin analytics pages.
const PALETTE = ["#0d6efd", "#20c997", "#fd7e14", "#6f42c1",
                 "#dc3545", "#ffc107", "#198754", "#0dcaf0"];

const inr = v => "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const shortDate = s => new Date(s + "T00:00:00")
    .toLocaleDateString("en-GB", { day: "numeric", month: "short" });

function noData(id) {
  document.getElementById(id).parentElement.innerHTML =
    '<p class="text-muted mb-0">No data for this period.</p>';
}
const hasData = values => values.some(v => v > 0);

function lineChart(id, labels, values, label) {
  if (!labels.length || !hasData(values)) return noData(id);
  new Chart(document.getElementById(id), {
    type: "line",
    data: {
      labels: labels.map(shortDate),
      datasets: [{ label, data: values, borderColor: PALETTE[0],
                   backgroundColor: "rgba(13,110,253,0.12)", fill: true, tension: 0.3,
                   pointRadius: values.length > 40 ? 0 : 3 }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false },
                 tooltip: { callbacks: { label: c => inr(c.parsed.y) } } },
      scales: { y: { beginAtZero: true, ticks: { callback: v => inr(v) } } },
    },
  });
}

function barChart(id, labels, values, label) {      // horizontal bars
  if (!labels.length || !hasData(values)) return noData(id);
  new Chart(document.getElementById(id), {
    type: "bar",
    data: { labels, datasets: [{ label, data: values, backgroundColor: PALETTE[1] }] },
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      plugins: { legend: { display: false },
                 tooltip: { callbacks: { label: c => inr(c.parsed.x) } } },
      scales: { x: { beginAtZero: true, ticks: { callback: v => inr(v) } } },
    },
  });
}

function doughnutChart(id, labels, values, money) {
  if (!labels.length || !hasData(values)) return noData(id);
  new Chart(document.getElementById(id), {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: PALETTE }] },
    options: {
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "bottom" },
        tooltip: { callbacks: { label: c =>
          `${c.label}: ${money ? inr(c.parsed) : c.parsed}` } },
      },
    },
  });
}