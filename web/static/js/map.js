// Модуль интерактивной карты. Содержит только map-логику и работу с webhook-claim API.
const mapState = {
  resources: [],
  territories: [],
  filters: { countries: true, resources: true, animals: true, capitals: true },
};

const ALL_RESOURCE_TYPES = [
  "дерево","камень","уголь","железо","медь","алюминий","золото","серебро","нефть","газ","вода","еда","медикаменты","химикаты","электроника","ткань","стройматериалы",
  "корова","свинья","курица","рыба","олень","заяц","обезьяна",
];
const ANIMAL_TYPES = new Set(["корова", "свинья", "курица", "рыба", "олень", "заяц", "обезьяна"]);
const byId = (id) => document.getElementById(id);
const isAnimal = (type) => ANIMAL_TYPES.has(String(type || "").toLowerCase());

function renderLegend() {
  const legend = byId("legend");
  legend.innerHTML = ALL_RESOURCE_TYPES.map((t) => `<div>◼ ${t}</div>`).join("");
}

function renderResourceList() {
  const list = byId("resourceList");
  if (!list) return;
  list.innerHTML = mapState.resources
    .map((p) => `<button data-id="${p.id}">${p.icon || "📦"} ${p.name || p.id} (${p.owner})</button>`)
    .join("");
  list.querySelectorAll("button[data-id]").forEach((node) => {
    node.addEventListener("click", () => {
      const point = mapState.resources.find((p) => String(p.id) === String(node.dataset.id));
      if (!point) return;
      openPointPopup(point, { offsetX: point.x, offsetY: point.y });
    });
  });
}

async function loadMapData() {
  const resourcesPayload = await webApi("/api/resources");
  const territoriesPayload = await webApi("/api/territories");
  mapState.resources = resourcesPayload.points || [];
  mapState.territories = territoriesPayload.regions || [];
}

function drawMapOverlay() {
  const svg = byId("mapSvg");
  svg.innerHTML = "";
  const selectedCountry = window.researchUI.getSelectedCountry();

  if (mapState.filters.countries) {
    mapState.territories.forEach((region) => {
      const polygon = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
      polygon.setAttribute("points", (region.points || []).map((p) => p.join(",")).join(" "));
      polygon.setAttribute("fill", region.color || "#ffffff55");
      polygon.setAttribute("stroke", "#111827");
      polygon.setAttribute("stroke-width", "2");
      polygon.style.opacity = selectedCountry && region.owner !== selectedCountry ? "0.35" : "0.8";
      svg.appendChild(polygon);
    });
  }

  if (mapState.filters.capitals) {
    mapState.territories.forEach((region) => {
      if (!region.capital) return;
      const capital = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      capital.setAttribute("cx", region.capital.x);
      capital.setAttribute("cy", region.capital.y);
      capital.setAttribute("r", "8");
      capital.setAttribute("fill", "#ffd60a");
      capital.setAttribute("stroke", "#000");
      svg.appendChild(capital);
    });
  }

  mapState.resources.forEach((point) => {
    if (!mapState.filters.resources) return;
    if (isAnimal(point.type) && !mapState.filters.animals) return;

    const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
    const bg = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    bg.setAttribute("cx", point.x);
    bg.setAttribute("cy", point.y);
    bg.setAttribute("r", "16");
    bg.setAttribute("fill", "#00000099");
    bg.setAttribute("stroke", "#fff");

    const icon = document.createElementNS("http://www.w3.org/2000/svg", "text");
    icon.setAttribute("x", point.x);
    icon.setAttribute("y", Number(point.y) + 6);
    icon.setAttribute("text-anchor", "middle");
    icon.setAttribute("font-size", "16");
    icon.textContent = point.icon || "📦";

    g.appendChild(bg);
    g.appendChild(icon);
    g.style.cursor = "pointer";
    g.onclick = (event) => openPointPopup(point, event);
    svg.appendChild(g);
  });
}

function openPointPopup(point, clickEvent) {
  const popup = byId("pointPopup");
  popup.classList.remove("hidden");
  popup.innerHTML = `
    <b>${point.name || point.id}</b><br>
    Тип: ${point.type}<br>
    Владелец: ${point.owner}<br>
    Количество: ${point.amount}<br>
    Можно добывать: ${point.can_mine ? "Да" : "Нет"}<br><br>
    <button id="btnMine">Добыть</button>
    <button id="btnColonize">Колонизировать регион</button>
  `;

  // Пробрасываем координаты клика в webhook payload.
  const clickX = Math.round(clickEvent?.offsetX || 0);
  const clickY = Math.round(clickEvent?.offsetY || 0);

  byId("btnMine").onclick = async () => sendClaim(point, "mine", clickX, clickY);
  byId("btnColonize").onclick = async () => sendClaim(point, "colonize", clickX, clickY);

  // Автозаполнение админ-формы для удобства.
  byId("adminPointId").value = point.id;
  byId("adminPointOwner").value = point.owner;
  byId("adminPointAmount").value = point.amount;
}

async function sendClaim(point, action, clickX, clickY) {
  const selectedCountry = window.researchUI.getSelectedCountry();
  try {
    await webApi("/api/resource/claim", {
      method: "POST",
      body: JSON.stringify({
        point_id: point.id,
        action,
        country: selectedCountry,
        user_id: 123, // TODO: подставить реальный user_id из auth/session.
        click_x: clickX,
        click_y: clickY,
        frame_ok: true,
      }),
    });
    await refreshMap();
  } catch (error) {
    alert(error.message);
  }
}

async function refreshMap() {
  await loadMapData();
  drawMapOverlay();
  renderResourceList();
}

function wireFilters() {
  ["countries", "resources", "animals", "capitals"].forEach((f) => {
    byId(`filter-${f}`).addEventListener("change", (event) => {
      mapState.filters[f] = Boolean(event.target.checked);
      drawMapOverlay();
    });
  });
}

function wireAdmin() {
  byId("adminSavePoint").onclick = async () => {
    await webApi("/api/admin/resource", {
      method: "POST",
      body: JSON.stringify({
        id: byId("adminPointId").value,
        owner: byId("adminPointOwner").value,
        amount: Number(byId("adminPointAmount").value),
      }),
    });
    await refreshMap();
  };

  byId("adminSaveRegion").onclick = async () => {
    await webApi("/api/admin/territory", {
      method: "POST",
      body: JSON.stringify({
        id: byId("adminRegionId").value,
        owner: byId("adminRegionOwner").value,
        color: byId("adminRegionColor").value,
      }),
    });
    await refreshMap();
  };

  byId("adminAddPoint").onclick = async () => {
    const type = byId("adminNewType").value;
    const id = `point_${Date.now()}`;
    await webApi("/api/admin/resource", {
      method: "POST",
      body: JSON.stringify({
        action: "add",
        point: {
          id,
          name: byId("adminNewName").value || id,
          x: Number(byId("adminNewX").value),
          y: Number(byId("adminNewY").value),
          type,
          amount: Number(byId("adminNewAmount").value || 100),
          owner: byId("adminNewOwner").value,
          can_mine: true,
          region_id: byId("adminNewRegionId").value,
        },
      }),
    });
    await refreshMap();
  };

  byId("adminNewType").innerHTML = ALL_RESOURCE_TYPES.map((t) => `<option value="${t}">${t}</option>`).join("");
}

window.mapUI = {
  async init() {
    renderLegend();
    wireFilters();
    wireAdmin();
    byId("refreshMap").onclick = refreshMap;
    byId("closePopup").onclick = () => byId("pointPopup").classList.add("hidden");
    byId("exportJson").onclick = async () => {
      const data = await webApi("/api/resources");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "resources_export.json"; a.click();
      URL.revokeObjectURL(url);
    };
    byId("exportCsv").onclick = async () => {
      const data = await webApi("/api/resources");
      const points = data.points || [];
      const header = "id,name,type,owner,amount,can_mine,x,y\\n";
      const rows = points.map((p) => [p.id, p.name, p.type, p.owner, p.amount, p.can_mine, p.x, p.y].join(",")).join("\\n");
      const blob = new Blob([header + rows], { type: "text/csv" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "resources_export.csv"; a.click();
      URL.revokeObjectURL(url);
    };
    await refreshMap();
  },
  refreshMap,
};
