// Простое переключение тёмной/светлой темы с сохранением в localStorage.
(function () {
  const KEY = 'ui_theme';
  const apply = (theme) => {
    document.body.classList.toggle('light', theme === 'light');
  };
  const current = localStorage.getItem(KEY) || 'dark';
  document.addEventListener('DOMContentLoaded', () => {
    apply(current);
    const btn = document.getElementById('themeToggle');
    if (!btn) return;
    btn.addEventListener('click', () => {
      const next = document.body.classList.contains('light') ? 'dark' : 'light';
      apply(next);
      localStorage.setItem(KEY, next);
    });
  });
})();
