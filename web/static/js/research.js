// Модуль вкладки исследований. Можно расширять новыми категориями/эффектами.
window.researchModule = (() => {
  const s = { countries: [], selected: "", tree: {}, active: [] };

  const api = async (u, o = {}) => {
    const r = await fetch(u, {
      headers: {
        "Content-Type": "application/json",
        ...(localStorage.webApiToken ? { "X-API-Key": localStorage.webApiToken } : {}),
      },
      ...o,
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || "error");
    return j;
  };

  const timer = (iso) => {
    let d = Math.max(0, Math.floor((new Date(iso) - Date.now()) / 1000));
    const D = Math.floor(d / 86400); d %= 86400;
    const H = Math.floor(d / 3600); d %= 3600;
    const M = Math.floor(d / 60);
    return `${D}д ${H}ч ${M}м ${d % 60}с`;
  };

  async function load(country) {
    s.countries = await api('/api/countries');
    s.selected = country || s.selected || (s.countries[0] && s.countries[0].country) || "";
    s.tree = s.selected ? await api(`/api/tech_tree?country=${encodeURIComponent(s.selected)}`) : {};
    s.active = await api('/api/research/active');
    render();
    return s.countries;
  }

  function render() {
    const c = s.countries.find((x) => x.country === s.selected);
    const stats = document.getElementById('stats');
    if (stats) stats.innerHTML = c ? `Армия: ${c.army}<br>Бюджет: ${c.budget}<br>Граждане: ${c.citizens}<br>Жизнь: ${c.life_level}<br>Риск: ${c.risk_index}` : '';
    const active = document.getElementById('active');
    if (active) active.innerHTML = s.active.map((a) => `<div>${a.country}: ${a.name}<br><small>${timer(a.end_date)}</small></div>`).join('') || 'Нет';

    const root = document.getElementById('tree');
    const tpl = document.getElementById('techTpl');
    if (!root || !tpl) return;
    root.innerHTML = '';
    for (const [id, t] of Object.entries(s.tree)) {
      const n = tpl.content.firstElementChild.cloneNode(true);
      n.querySelector('.name').textContent = t.name;
      n.querySelector('.desc').textContent = t.description;
      n.querySelector('.meta').textContent = `${t.category} • ${t.duration}д • ${t.cost}`;
      const status = t.status || {};
      const txt = status.unlocked ? 'Уже изучено' : status.can_start ? 'Доступно' : `Недоступно: ${(status.missing_tech || []).join(', ')}`;
      n.querySelector('.status').textContent = txt;
      n.querySelector('.status').className = `status ${status.can_start ? 'ok' : 'warn'}`;
      const b = n.querySelector('button');
      b.disabled = !status.can_start || status.unlocked;
      b.onclick = async () => {
        await api('/api/research/start', { method: 'POST', body: JSON.stringify({ country: s.selected, tech_id: id }) });
        await load(s.selected);
      };
      root.appendChild(n);
    }
  }

  return { load, render };
})();
