// Модуль интерактивной карты ресурсов. TODO: заменить ручной refresh на WebSocket.
window.mapModule = (() => {
  const state = {
    resources: [],
    regions: [],
    country: '',
    filters: { territories: true, resources: true, animals: true, capitals: true },
  };

  const animalTypes = new Set(['корова', 'свинья', 'курица', 'рыба', 'олень', 'заяц', 'обезьяна']);

  const api = async (u, o = {}) => {
    const r = await fetch(u, {
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.webApiToken ? { 'X-API-Key': localStorage.webApiToken } : {}),
      },
      ...o,
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'error');
    return j;
  };

  function renderLegend() {
    const legend = document.getElementById('legend');
    if (!legend) return;
    const byType = new Map();
    state.resources.forEach((p) => { if (!byType.has(p.type)) byType.set(p.type, p.icon || '⛏️'); });
    legend.innerHTML = [...byType.entries()].map(([type, icon]) => `<div class="legend-item"><span>${icon}</span><span>${type}</span></div>`).join('');
  }

  function showPopup(point, x, y) {
    const popup = document.getElementById('point-popup');
    if (!popup) return;
    popup.innerHTML = `<b>${point.name || point.id}</b><br>Тип: ${point.type}<br>Владелец: ${point.owner}<br>Количество: ${point.amount}<br>Добыча: ${point.can_mine ? 'Да' : 'Нет'}`;
    popup.style.left = `${x + 10}px`;
    popup.style.top = `${y + 10}px`;
    popup.classList.remove('hidden');
  }

  function draw() {
    const svg = document.getElementById('map-overlay');
    if (!svg) return;
    svg.innerHTML = '';

    if (state.filters.capitals) {
      state.regions
        .filter((r) => !state.country || r.owner === state.country)
        .forEach((r) => {
          if (!r.capital) return;
          const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          c.setAttribute('cx', r.capital.x);
          c.setAttribute('cy', r.capital.y);
          c.setAttribute('r', '6');
          c.setAttribute('fill', '#facc15');
          svg.appendChild(c);
        });
    }

    const points = state.resources.filter((p) => {
      if (state.country && p.owner !== state.country) return false;
      if (!state.filters.resources && !animalTypes.has((p.type || '').toLowerCase())) return false;
      if (!state.filters.animals && animalTypes.has((p.type || '').toLowerCase())) return false;
      return true;
    });

    points.forEach((p) => {
      const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', p.x);
      c.setAttribute('cy', p.y);
      c.setAttribute('r', '10');
      c.setAttribute('fill', '#38bdf8');
      c.setAttribute('stroke', '#0c4a6e');
      c.setAttribute('stroke-width', '2');
      const t = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      t.setAttribute('x', p.x - 6);
      t.setAttribute('y', p.y + 4);
      t.textContent = p.icon || '⛏️';
      g.appendChild(c);
      g.appendChild(t);
      g.style.cursor = 'pointer';
      g.addEventListener('click', async (ev) => {
        showPopup(p, ev.offsetX, ev.offsetY);
        await api('/api/resource/claim', {
          method: 'POST',
          body: JSON.stringify({
            point_id: p.id,
            action: 'mine',
            click_x: ev.offsetX,
            click_y: ev.offsetY,
            country: state.country || p.owner,
            user_id: 123,
            frame_ok: true,
          }),
        });
        await load(state.country);
      });
      svg.appendChild(g);
    });

    const territoryLayer = document.getElementById('territory-layer');
    if (territoryLayer) {
      territoryLayer.style.display = state.filters.territories ? 'block' : 'none';
    }
  }

  async function load(country) {
    state.country = country || state.country;
    const resources = await api('/api/resources');
    const territories = await api('/api/territories');
    state.resources = resources.points || [];
    state.regions = territories.regions || [];
    renderLegend();
    draw();
  }

  function bind() {
    document.getElementById('filter-territories')?.addEventListener('change', (e) => { state.filters.territories = e.target.checked; draw(); });
    document.getElementById('filter-resources')?.addEventListener('change', (e) => { state.filters.resources = e.target.checked; draw(); });
    document.getElementById('filter-animals')?.addEventListener('change', (e) => { state.filters.animals = e.target.checked; draw(); });
    document.getElementById('filter-capitals')?.addEventListener('change', (e) => { state.filters.capitals = e.target.checked; draw(); });
    document.getElementById('map-refresh')?.addEventListener('click', async () => load(state.country));

    document.getElementById('admin-apply')?.addEventListener('click', async () => {
      const raw = document.getElementById('admin-json').value;
      const data = JSON.parse(raw || '{}');
      if (data.mode === 'territory') {
        await api('/api/admin/territory', { method: 'POST', body: JSON.stringify(data) });
      } else {
        await api('/api/admin/resource', { method: 'POST', body: JSON.stringify(data) });
      }
      await load(state.country);
    });
  }

  return { load, bind };
})();
