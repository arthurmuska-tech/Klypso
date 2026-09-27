(function () {
  const root = document.documentElement;
  const get = (key, fallback) => {
    try { const value = localStorage.getItem(key); return value === null ? fallback : value; } catch (_) { return fallback; }
  };
  const set = (key, value) => { try { localStorage.setItem(key, value); } catch (_) {} };

  root.dataset.theme = get('klypso.accent', '#9b7bff')
    .replace('#', '') === '63a4ff' ? 'blue'
    : get('klypso.accent', '#9b7bff').replace('#', '') === '59e6df' ? 'cyan'
    : get('klypso.accent', '#9b7bff').replace('#', '') === 'ff76c8' ? 'pink' : 'violet';
  root.dataset.density = get('klypso.density', 'comfortable');
  root.dataset.radius = get('klypso.radius', 'round');

  function applyAccent(accent) {
    const safe = /^#[0-9a-fA-F]{6}$/.test(accent) ? accent : '#9b7bff';
    root.style.setProperty('--accent', safe);
    root.style.setProperty('--k-accent', safe);
    const accentMap = {
      '#9b7bff':'#c5b7ff',
      '#63a4ff':'#9dc6ff',
      '#59e6df':'#8af4ed',
      '#ff76c8':'#ff9edb',
      '#d59a62':'#efbdad'
    };
    root.style.setProperty('--k-accent-2', accentMap[safe] || safe);
    root.style.setProperty('--k-accent-soft', 'color-mix(in srgb, ' + safe + ' 14%, transparent)');
    set('klypso.accent', safe);
    document.querySelectorAll('[data-accent]').forEach((el) => el.classList.toggle('selected', el.dataset.accent === safe));
  }
  applyAccent(get('klypso.accent', '#9b7bff'));

  document.querySelectorAll('[data-accent]').forEach((button) => button.addEventListener('click', () => applyAccent(button.dataset.accent)));
  document.querySelectorAll('[data-setting-group="accent"] [data-accent]').forEach((button) => {
    button.addEventListener('click', () => applyAccent(button.dataset.accent));
  });
  document.querySelectorAll('[data-setting-group="density"] button').forEach((button) => button.addEventListener('click', () => {
    root.dataset.density = button.dataset.value; set('klypso.density', button.dataset.value);
    document.querySelectorAll('[data-setting-group="density"] button').forEach((b) => b.classList.toggle('selected', b === button));
  }));
  document.querySelectorAll('[data-setting-group="radius"] button').forEach((button) => button.addEventListener('click', () => {
    root.dataset.radius = button.dataset.value; set('klypso.radius', button.dataset.value);
    document.querySelectorAll('[data-setting-group="radius"] button').forEach((b) => b.classList.toggle('selected', b === button));
  }));
  document.querySelectorAll('[data-setting-group="density"] button').forEach((b) => b.classList.toggle('selected', b.dataset.value === root.dataset.density));
  document.querySelectorAll('[data-setting-group="radius"] button').forEach((b) => b.classList.toggle('selected', b.dataset.value === root.dataset.radius));
  document.querySelectorAll('[data-caption]').forEach((button) => button.addEventListener('click', () => {
    set('klypso.caption', button.dataset.caption);
    document.querySelectorAll('[data-caption]').forEach((b) => b.classList.toggle('selected', b === button));
  }));

  const displayName = document.querySelector('[data-setting="displayName"]');
  const previewName = document.querySelector('[data-preview-name]');
  const savedName = get('klypso.displayName', 'Ton créateur');
  if (displayName) displayName.value = savedName;
  if (previewName) previewName.textContent = savedName;
  document.querySelector('[data-save-settings]')?.addEventListener('click', () => {
    const value = (displayName?.value || '').trim() || 'Ton créateur'; set('klypso.displayName', value); if (previewName) previewName.textContent = value;
  });

  document.querySelector('[data-brand-reset]')?.addEventListener('click', () => {
    try { ['klypso.accent','klypso.density','klypso.radius','klypso.caption','klypso.displayName','klypso.watermark','klypso.motion'].forEach((k) => localStorage.removeItem(k)); } catch (_) {}
    window.location.reload();
  });

  document.querySelectorAll('[data-setting="watermark"],[data-setting="motion"]').forEach((input) => {
    const key = 'klypso.' + input.dataset.setting; input.checked = get(key, '1') !== '0';
    input.addEventListener('change', () => set(key, input.checked ? '1' : '0'));
  });

  if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js').catch(() => {}));
})();
