// Оркестрация вкладок и инициализации отдельных UI-модулей (research + map).
document.addEventListener("DOMContentLoaded", async () => {
  const tabMap = document.getElementById("tab-map");
  const tabResearch = document.getElementById("tab-research");
  const mapView = document.getElementById("map-view");
  const researchView = document.getElementById("research-view");
  const countrySelect = document.getElementById("country");

  const setTab = (tab) => {
    const mapActive = tab === "map";
    tabMap.classList.toggle("active", mapActive);
    tabResearch.classList.toggle("active", !mapActive);
    mapView.classList.toggle("hidden", !mapActive);
    researchView.classList.toggle("hidden", mapActive);
  };

  tabMap.onclick = () => setTab("map");
  tabResearch.onclick = () => setTab("research");

  const selectedCountry = await window.researchUI.load();
  countrySelect.value = selectedCountry;
  await window.mapUI.init();

  countrySelect.addEventListener("change", async (event) => {
    await window.researchUI.load(event.target.value);
    await window.mapUI.refreshMap();
  });

  setInterval(() => window.researchUI.render(), 1000);
});
