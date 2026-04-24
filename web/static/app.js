(async function bootstrap() {
  const authState = document.getElementById('auth-state');
  const authApi = async (url, payload) => {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'auth error');
    return j;
  };
  const authGet = async (url) => {
    const r = await fetch(url, {
      headers: localStorage.webAuthToken ? { Authorization: `Bearer ${localStorage.webAuthToken}` } : {},
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || 'auth error');
    return j;
  };

  async function loginFlow(registerMode = false) {
    const tg = Number(document.getElementById('auth-tg')?.value || 0);
    const pass = String(document.getElementById('auth-pass')?.value || '');
    const twofa = String(document.getElementById('auth-2fa')?.value || '');
    try {
      if (registerMode) {
        await authApi('/api/auth/register', { telegram_id: tg, password: pass, twofa_pin: twofa });
      }
      const login = await authApi('/api/auth/login', { telegram_id: tg, password: pass });
      let token = login.token;
      if (login.requires_2fa) {
        const v = await authApi('/api/auth/verify_2fa', { pre_token: login.pre_token, twofa_pin: twofa });
        token = v.token;
      }
      localStorage.webAuthToken = token;
      authState.textContent = `Вход выполнен: ${tg}`;
    } catch (e) {
      authState.textContent = `Ошибка авторизации: ${e.message}`;
    }
  }

  document.getElementById('auth-login')?.addEventListener('click', async () => loginFlow(false));
  document.getElementById('auth-register')?.addEventListener('click', async () => loginFlow(true));
  document.getElementById('auth-logout')?.addEventListener('click', async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: localStorage.webAuthToken ? { Authorization: `Bearer ${localStorage.webAuthToken}` } : {},
      });
    } finally {
      localStorage.removeItem('webAuthToken');
      authState.textContent = 'Выход выполнен';
    }
  });
  try {
    const me = await authGet('/api/auth/me');
    authState.textContent = `Вход: ${me.telegram_id} (${me.role})`;
  } catch (_e) {}

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
