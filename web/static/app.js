(async function bootstrap() {
  const tabs = document.querySelectorAll('.tab');
  const panes = {
    map: document.getElementById('tab-map'),
    research: document.getElementById('tab-research'),
  };

  tabs.forEach((btn) => btn.addEventListener('click', () => {
    tabs.forEach((b) => b.classList.toggle('active', b === btn));
    Object.entries(panes).forEach(([name, node]) => node.classList.toggle('active', name === btn.dataset.tab));
  }));

  const countries = await window.researchModule.load();
  const selector = document.getElementById('country');
  selector.innerHTML = countries.map((c) => `<option value="${c.country}">${c.country}</option>`).join('');
  const current = countries[0] ? countries[0].country : '';
  selector.value = current;
  await window.mapModule.load(current);
  window.mapModule.bind();

  selector.addEventListener('change', async () => {
    await window.researchModule.load(selector.value);
    await window.mapModule.load(selector.value);
  });

  setInterval(() => window.researchModule.render(), 1000);
})();
