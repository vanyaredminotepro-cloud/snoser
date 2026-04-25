// Модуль исследований оставлен отдельным файлом для расширяемости UI.
const researchState = { countries: [], selected: "", tree: {}, active: [], category: "all" };
const CATEGORY_LABELS = {
  all: "Все",
  aviation: "✈️ Авиация",
  navy: "🚤 Флот",
  drones: "🛸 Дроны",
  rockets: "💥 Ракеты",
  armor: "🛡️ Бронетехника",
  technology: "📡 Технологии",
};

const api = async (url, options = {}) => {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(localStorage.webApiToken ? { "X-API-Key": localStorage.webApiToken } : {}),
    },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "error");
  return payload;
};

const timer = (iso) => {
  let d = Math.max(0, Math.floor((new Date(iso) - Date.now()) / 1000));
  const D = Math.floor(d / 86400);
  d %= 86400;
  const H = Math.floor(d / 3600);
  d %= 3600;
  const M = Math.floor(d / 60);
  return `${D}д ${H}ч ${M}м ${d % 60}с`;
};

window.researchUI = {
  async load(selectedCountry = "") {
    if (selectedCountry) researchState.selected = selectedCountry;
    researchState.countries = await api("/api/countries");
    if (!researchState.selected && researchState.countries.length) {
      researchState.selected = researchState.countries[0].country;
    }
    const countrySelect = document.getElementById("country");
    countrySelect.innerHTML = researchState.countries
      .map((c) => `<option value="${c.country}">${c.country}</option>`)
      .join("");
    countrySelect.value = researchState.selected;

    researchState.tree = await api(`/api/tech_tree?country=${encodeURIComponent(researchState.selected)}`);
    researchState.active = await api(`/api/research/active/${encodeURIComponent(researchState.selected)}`);
    this.render();
    return researchState.selected;
  },

  render() {
    this.renderCategories();
    const current = researchState.countries.find((c) => c.country === researchState.selected);
    document.getElementById("stats").innerHTML = current
      ? `Армия: ${current.army}<br>Бюджет: ${current.budget}<br>Граждане: ${current.citizens}<br>Жизнь: ${current.life_level}<br>Риск: ${current.risk_index}`
      : "";

    document.getElementById("active").innerHTML =
      researchState.active
        .map((a) => `<div>${a.country}: ${a.name}<br><small>${timer(a.end_date)}</small><div class="progress"><i style="width:${a.progress || 0}%"></i></div></div>`)
        .join("") || "Нет";

    const root = document.getElementById("tree");
    root.innerHTML = "";
    const tpl = document.getElementById("techTpl");

    for (const [techId, tech] of Object.entries(researchState.tree)) {
      if (researchState.category !== "all" && tech.category !== researchState.category) continue;
      const node = tpl.content.firstElementChild.cloneNode(true);
      node.querySelector(".name").textContent = tech.name;
      node.querySelector(".desc").textContent = tech.description;
      node.querySelector(".meta").textContent = `${tech.category} • ${tech.duration}д • ${tech.cost}`;
      const status = tech.status || {};
      const statusText = status.unlocked
        ? "Уже изучено"
        : status.can_start
        ? "Доступно"
        : `Недоступно: ${(status.missing_tech || []).join(", ")} ${status.missing_factories ? `заводы +${status.missing_factories}` : ""}`;
      node.querySelector(".status").textContent = statusText;
      node.querySelector(".status").className = `status ${status.can_start ? "ok" : "warn"}`;
      const button = node.querySelector("button");
      button.disabled = !status.can_start || status.unlocked;
      button.onclick = async () => {
        try {
          await api("/api/research/start", {
            method: "POST",
            body: JSON.stringify({ country: researchState.selected, tech_id: techId }),
          });
          await this.load(researchState.selected);
        } catch (error) {
          alert(error.message);
        }
      };
      root.appendChild(node);
    }
  },
  renderCategories() {
    const wrap = document.getElementById("researchCategories");
    wrap.innerHTML = Object.entries(CATEGORY_LABELS)
      .map(([key, label]) => `<button data-cat="${key}" ${researchState.category===key?"style='background:#4a2a6a'":""}>${label}</button>`)
      .join("");
    wrap.querySelectorAll("button[data-cat]").forEach((btn) => {
      btn.onclick = () => {
        researchState.category = btn.dataset.cat || "all";
        this.render();
      };
    });
  },

  getSelectedCountry() {
    return researchState.selected;
  },
};

window.webApi = api;
