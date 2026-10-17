const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));
const money = (value) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value ?? 0);

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Request failed (${response.status})`);
  return data;
}

function showNotice(message, isError = false) {
  const notice = $("#notice");
  notice.textContent = message;
  notice.classList.toggle("error", isError);
}

function renderMetrics(portfolio, performance) {
  const values = [
    ["VIRTUAL EQUITY", money(portfolio.equity)],
    ["AVAILABLE CASH", money(portfolio.cash)],
    ["TOTAL RETURN", `${performance.total_return}%`],
    ["OPEN POSITIONS", String(portfolio.holdings.length)],
  ];
  $("#metrics").innerHTML = values.map(([label, value]) =>
    `<div class="metric"><div class="metric-label">${label}</div><div class="metric-value">${escapeHtml(value)}</div></div>`
  ).join("");
}

function renderMarket(quotes) {
  $("#market").innerHTML = quotes.map((quote) => `
    <div class="market-row"><strong>${escapeHtml(quote.symbol)}</strong>
      <span>${money(quote.price)}</span>
      <span>${quote.change_percent >= 0 ? "+" : ""}${escapeHtml(quote.change_percent)}%</span></div>`
  ).join("");
}

function renderSignals(signals) {
  $("#signals").innerHTML = signals.length ? signals.map((signal) => `
    <div class="signal-card"><h3>${escapeHtml(signal.title)}</h3>
      <div class="signal-meta"><span>${escapeHtml(signal.symbols.join(", "))} · ${escapeHtml(signal.category)}</span>
        <span class="action ${escapeHtml(signal.action)}">${escapeHtml(signal.action)}</span>
        <span>${Math.round(signal.confidence * 100)}% confidence</span></div></div>`
  ).join("") : '<div class="empty">No sample articles are available.</div>';
}

function renderHoldings(holdings) {
  if (!holdings.length) return '<div class="empty">No open positions. Try a simulated buy above.</div>';
  return `<table><thead><tr><th>SYMBOL</th><th>SHARES</th><th>MARK</th><th>UNREALIZED</th></tr></thead><tbody>${holdings.map((item) =>
    `<tr><td>${escapeHtml(item.symbol)}</td><td>${item.quantity}</td><td>${money(item.price)}</td><td>${money(item.unrealized_pnl)}</td></tr>`
  ).join("")}</tbody></table>`;
}

function renderTrades(trades) {
  if (!trades.length) return '<div class="empty">No simulated orders yet.</div>';
  return `<table><thead><tr><th>TIME</th><th>ORDER</th><th>VALUE</th></tr></thead><tbody>${trades.map((trade) =>
    `<tr><td>${escapeHtml(new Date(trade.timestamp).toLocaleTimeString())}</td><td>${escapeHtml(trade.side.toUpperCase())} ${trade.quantity} ${escapeHtml(trade.symbol)}</td><td>${money(trade.value)}</td></tr>`
  ).join("")}</tbody></table>`;
}

async function refreshDashboard() {
  try {
    const [quotes, signals, portfolio, performance] = await Promise.all([
      api("/api/market"), api("/api/signals"), api("/api/portfolio"), api("/api/performance"),
    ]);
    renderMarket(quotes);
    renderSignals(signals);
    renderMetrics(portfolio, performance);
    $("#holdings").innerHTML = renderHoldings(portfolio.holdings);
    $("#trades").innerHTML = renderTrades(portfolio.recent_trades);
    showNotice("All orders are simulated. No broker connection or real trades.");
  } catch (error) {
    showNotice(`Could not load dashboard: ${error.message}`, true);
  }
}

$("#refresh").addEventListener("click", refreshDashboard);
$("#trade-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  try {
    const trade = await api("/api/trades", {
      method: "POST",
      body: JSON.stringify({ symbol: form.get("symbol"), side: form.get("side"), quantity: Number(form.get("quantity")) }),
    });
    showNotice(`Simulated ${trade.side} order: ${trade.quantity} ${trade.symbol} at ${money(trade.price)}.`);
    await refreshDashboard();
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    button.disabled = false;
  }
});

$("#backtest").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  try {
    const result = await api("/api/backtest?days=90");
    $("#backtest-result").textContent = `${result.days} synthetic days · ending equity ${money(result.ending_equity)} · return ${result.return_percent}% · max drawdown ${result.max_drawdown_percent}%`;
  } catch (error) {
    showNotice(error.message, true);
  } finally {
    button.disabled = false;
  }
});

refreshDashboard();
