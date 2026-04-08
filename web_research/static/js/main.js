const state = { countries: [], selectedCountryId: null, techTree: {}, active: [], opened: [], history: [] };
const categoryOrder = ["drones", "rockets", "aviation", "navy", "armor", "technology"];
const categoryTitles = {drones:"🛸 Дроны", rockets:"💥 Ракеты", aviation:"✈️ Авиация", navy:"🚤 Флот", armor:"🛡️ Бронетехника", technology:"📡 Технологии"};

async function api(path, options={}) {
  const headers = {"Content-Type":"application/json", ...(options.headers || {})};
  const token = localStorage.getItem("web_api_key") || "";
  if (token) headers["X-API-Key"] = token;
  const res = await fetch(path, {...options, headers});
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function fmtTimer(end) {
  let sec = Math.max(0, Math.floor((new Date(end).getTime() - Date.now()) / 1000));
  const d = Math.floor(sec / 86400); sec %= 86400;
  const h = Math.floor(sec / 3600); sec %= 3600;
  const m = Math.floor(sec / 60); const s = sec % 60;
  return `${d}д ${h}ч ${m}м ${s}с`;
}

function renderCountries() {
  const sel = document.getElementById("countrySelect");
  sel.innerHTML = state.countries.map((c) => `<option value="${c.id}">${c.name}</option>`).join("");
  if (state.selectedCountryId === null && state.countries.length) state.selectedCountryId = state.countries[0].id;
  sel.value = String(state.selectedCountryId || "");

  const country = state.countries.find((c) => Number(c.id) === Number(state.selectedCountryId));
  const stats = document.getElementById("countryStats");
  if (!country) { stats.innerHTML = ""; return; }
  const items = [["Армия", country.army],["Бюджет", country.budget],["Граждане", country.citizens],["Уровень жизни", country.life_quality],["Риск", country.risk_index]];
  stats.innerHTML = items.map(([k,v]) => `<div class="stat"><small>${k}</small><div><b>${v}</b></div></div>`).join("");

  const opened = document.getElementById("openedTech");
  opened.innerHTML = state.opened.length ? state.opened.map((t) => `<span class="chip">${t.tech_id}</span>`).join("") : `<span class="chip">Пока пусто</span>`;
}

function renderActive() {
  const root = document.getElementById("activeResearch");
  if (!state.active.length) { root.innerHTML = "<p>Нет активных исследований</p>"; return; }
  root.innerHTML = state.active.map((r) => {
    const p = Math.max(0, Math.min(100, Number(r.progress_percent || 0)));
    return `<div class="active-item">
      <b>${r.name}</b> • ${r.country_name || "Страна"}<br>
      <small>Старт: ${new Date(r.start_date).toLocaleString()} | Финиш: ${new Date(r.end_date).toLocaleString()}</small><br>
      <small>Осталось: ${fmtTimer(r.end_date)}</small>
      <div class="bar"><i style="width:${p}%"></i></div>
      <small>${p.toFixed(1)}%</small><br>
      <button class=\"start cancel\" data-id=\"${r.id}\">Отменить (админ)</button>
    </div>`;
  }).join("");
  root.querySelectorAll(".cancel").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await api(`/api/admin/research/${btn.dataset.id}/cancel`, {method: "POST"});
        await loadAll();
      } catch (e) {
        alert(e.message);
      }
    });
  });

  const hist = document.getElementById("historyResearch");
  hist.innerHTML = state.history.length
    ? state.history.map((h) => `<div class=\"active-item\"><b>${h.tech_id}</b> • ${h.action}<br><small>${h.created_at}</small></div>`).join("")
    : "<p>История пуста</p>";
}

function renderTech() {
  const grouped = {};
  for (const [id, tech] of Object.entries(state.techTree)) {
    const cat = tech.category || "technology";
    grouped[cat] ||= [];
    grouped[cat].push({id, ...tech});
  }
  const root = document.getElementById("techGroups");
  root.innerHTML = "";
  const tpl = document.getElementById("techCardTemplate");

  categoryOrder.forEach((cat) => {
    const items = grouped[cat] || [];
    if (!items.length) return;
    const section = document.createElement("section");
    section.className = "group";
    section.innerHTML = `<h3>${categoryTitles[cat] || cat}</h3><div class="grid"></div>`;
    const grid = section.querySelector(".grid");

    items.forEach((t) => {
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.querySelector(".title").textContent = t.name;
      node.querySelector(".desc").textContent = t.description;
      node.querySelector(".meta").textContent = `Длительность: ${t.duration} дн. • Стоимость: ${t.cost}`;
      node.querySelector(".req").textContent = `Требования: ${(t.requirements || []).join(", ") || "нет"}`;
      const status = t.status || {opened:false, available:true, missing_requirements:[]};
      const statusEl = node.querySelector(".status");
      if (status.opened) {
        statusEl.textContent = "Уже исследовано"; statusEl.classList.add("ok");
      } else if (status.available) {
        statusEl.textContent = "Доступно"; statusEl.classList.add("ok");
      } else {
        const reasons = [];
        if ((status.missing_requirements || []).length) reasons.push(`нужны: ${status.missing_requirements.join(", ")}`);
        if (status.has_budget === false) reasons.push("не хватает бюджета");
        if (status.has_factories === false) reasons.push(`заводы: ${status.needed_factories}+`);
        statusEl.textContent = `Недоступно: ${reasons.join("; ") || "требования"}`;
        statusEl.classList.add("warn");
      }

      const btn = node.querySelector(".start");
      btn.disabled = !!status.opened || !status.available || !state.selectedCountryId;
      btn.onclick = async () => {
        try {
          await api("/api/research/start", {method: "POST", body: JSON.stringify({country_id: Number(state.selectedCountryId), tech_id: t.id})});
          await loadAll();
        } catch (e) {
          alert(e.message);
        }
      };
      grid.appendChild(node);
    });
    root.appendChild(section);
  });
}

async function loadAll() {
  state.countries = await api("/api/countries");
  if (!state.selectedCountryId && state.countries.length) state.selectedCountryId = state.countries[0].id;
  state.techTree = await api(`/api/tech_tree?country_id=${encodeURIComponent(state.selectedCountryId || "")}`);
  state.active = await api("/api/research/active");
  state.opened = state.selectedCountryId ? await api(`/api/country_tech/${state.selectedCountryId}`) : [];
  state.history = state.selectedCountryId ? await api(`/api/research/history/${state.selectedCountryId}`) : [];
  renderCountries();
  renderActive();
  renderTech();
}

document.getElementById("countrySelect").addEventListener("change", async (e) => {
  state.selectedCountryId = Number(e.target.value);
  await loadAll();
});

setInterval(renderActive, 1000);
setInterval(async () => {
  state.active = await api("/api/research/active");
}, 15000);

loadAll().catch((err) => {
  console.error(err);
  alert("Не удалось загрузить панель исследований");
});
