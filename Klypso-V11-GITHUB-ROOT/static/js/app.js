(() => {
  'use strict';

  const root = document.documentElement;
  const $ = (selector, parent = document) => parent.querySelector(selector);
  const $$ = (selector, parent = document) => Array.from(parent.querySelectorAll(selector));

  const get = (key, fallback) => {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : value;
    } catch (_) {
      return fallback;
    }
  };

  const set = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_) {}
  };

  const palettes = ['paper','linen','clay','ocean','forest','plum','graphite','midnight'];
  function applyPalette(value) {
    const palette = palettes.includes(value) ? value : 'paper';
    root.dataset.palette = palette;
    set('klypso.palette', palette);
    $('[data-setting-group="palette"] [data-palette]').forEach((el) => {
      const selected = el.dataset.palette === palette;
      el.classList.toggle('selected', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
  }

  const accentTheme = {
    '#9b7bff': 'violet',
    '#63a4ff': 'blue',
    '#59e6df': 'cyan',
    '#ff76c8': 'pink',
    '#ffb44c': 'amber',
    '#d59a62': 'amber'
  };

  const accent2 = {
    '#9b7bff': '#c5b7ff',
    '#63a4ff': '#9dc6ff',
    '#59e6df': '#8af4ed',
    '#ff76c8': '#ff9edb',
    '#ffb44c': '#ffd18a',
    '#d59a62': '#efbdad'
  };

  function applyAccent(value) {
    const accent = /^#[0-9a-f]{6}$/i.test(value || '') ? value.toLowerCase() : '#9b7bff';
    root.dataset.theme = accentTheme[accent] || 'violet';
    root.style.setProperty('--accent', accent);
    root.style.setProperty('--k-accent', accent);
    root.style.setProperty('--k-accent-2', accent2[accent] || accent);
    root.style.setProperty('--k-accent-soft', 'color-mix(in srgb, ' + accent + ' 14%, transparent)');
    set('klypso.accent', accent);
    $$('[data-accent]').forEach((el) => {
      el.classList.toggle('selected', el.dataset.accent?.toLowerCase() === accent);
    });
    const live = $('[data-live-accent]');
    if (live) live.textContent = accent.toUpperCase();
  }

  function applyDensity(value) {
    const density = value === 'airy' ? 'spacious' : (['compact', 'comfortable', 'spacious'].includes(value) ? value : 'comfortable');
    root.dataset.density = density;
    set('klypso.density', density);
    $$('[data-setting-group="density"] button, [data-setting-group="density"] .segmented-v11 button').forEach((el) => {
      el.classList.toggle('selected', el.dataset.value === density);
      el.classList.toggle('active', el.dataset.value === density);
    });
    const live = $('[data-live-density]');
    if (live) live.textContent = density === 'spacious' ? 'Aérée' : density === 'compact' ? 'Compact' : 'Confort';
  }

  function applyRadius(value) {
    const radius = ['sharp', 'round', 'soft'].includes(value) ? value : 'round';
    root.dataset.radius = radius;
    set('klypso.radius', radius);
    $$('[data-setting-group="radius"] button, [data-setting-group="radius"] .segmented-v11 button').forEach((el) => {
      el.classList.toggle('selected', el.dataset.value === radius);
      el.classList.toggle('active', el.dataset.value === radius);
    });
  }

  function applyCaption(value) {
    const caption = ['dynamic', 'classic', 'minimal'].includes(value) ? value : 'dynamic';
    set('klypso.caption', caption);
    $$('[data-caption]').forEach((el) => el.classList.toggle('selected', el.dataset.caption === caption));
    const live = $('[data-live-caption]');
    if (live) live.textContent = caption.charAt(0).toUpperCase() + caption.slice(1);
  }

  applyAccent(get('klypso.accent', '#9b7bff'));
  applyDensity(get('klypso.density', 'comfortable'));
  applyPalette(get('klypso.palette', 'paper'));
  applyRadius(get('klypso.radius', 'round'));
  applyCaption(get('klypso.caption', 'dynamic'));

  $$('[data-accent]').forEach((button) => button.addEventListener('click', () => applyAccent(button.dataset.accent)));
  $$('[data-setting-group="density"] button').forEach((button) => button.addEventListener('click', () => applyDensity(button.dataset.value)));
  $('[data-setting-group="radius"] button').forEach((button) => button.addEventListener('click', () => applyRadius(button.dataset.value)));
  $('[data-setting-group="palette"] [data-palette]').forEach((button) => button.addEventListener('click', () => applyPalette(button.dataset.palette)));
  $$('[data-caption]').forEach((button) => button.addEventListener('click', () => applyCaption(button.dataset.caption)));

  /* Sidebar */
  const path = location.pathname;
  $$('.sidebar-nav a[data-nav]').forEach((a) => {
    const n = a.dataset.nav;
    const active =
      (n === 'dashboard' && path === '/dashboard') ||
      (n === 'clips' && path === '/clips') ||
      (n === 'new' && path === '/clips/create') ||
      (n === 'studio' && path === '/studio') ||
      (n === 'brand' && path === '/brand-kit') ||
      (n === 'billing' && (path === '/pricing' || path === '/subscription')) ||
      (n === 'payments' && path === '/payments') ||
      (n === 'account' && path === '/account');
    a.classList.toggle('active', active);
  });

  const sidebar = $('#app-sidebar');
  $('[data-sidebar-open]')?.addEventListener('click', () => sidebar?.classList.add('open'));
  $('[data-sidebar-close]')?.addEventListener('click', () => sidebar?.classList.remove('open'));

  /* Brand preferences */
  const displayName = $('[data-setting="displayName"]');
  if (displayName) displayName.value = get('klypso.displayName', 'Ton créateur');
  const previewName = $('[data-preview-name]');
  if (previewName) previewName.textContent = get('klypso.displayName', 'Ton créateur');

  $('[data-save-settings]')?.addEventListener('click', () => {
    const name = (displayName?.value || '').trim() || 'Ton créateur';
    set('klypso.displayName', name);
    if (previewName) previewName.textContent = name;
    const button = $('[data-save-settings]');
    if (button) {
      const old = button.textContent;
      button.textContent = 'Enregistré ✓';
      setTimeout(() => { button.textContent = old; }, 1400);
    }
  });

  $$('[data-setting="watermark"], [data-setting="motion"]').forEach((input) => {
    const key = 'klypso.' + input.dataset.setting;
    input.checked = get(key, '1') !== '0';
    input.addEventListener('change', () => set(key, input.checked ? '1' : '0'));
  });

  const resetAppearance = () => {
    ['klypso.accent','klypso.density','klypso.radius','klypso.caption','klypso.displayName','klypso.watermark','klypso.motion','klypso.wood','klypso.palette']
      .forEach((key) => { try { localStorage.removeItem(key); } catch (_) {} });
    location.reload();
  };
  $('[data-brand-reset]')?.addEventListener('click', resetAppearance);
  $('[data-appearance-reset]')?.addEventListener('click', resetAppearance);

  /* Clips filters */
  $$('.tab-btn').forEach((button) => {
    button.addEventListener('click', () => {
      $$('.tab-btn').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      const state = button.dataset.listTab || 'all';
      $$('.clip-project-card').forEach((card) => {
        const status = card.dataset.status || '';
        const visible =
          state === 'all' ||
          (state === 'ready' && /completed|done|ready/.test(status)) ||
          (state === 'processing' && /processing|running|queued/.test(status));
        card.style.display = visible ? '' : 'none';
      });
    });
  });

  /* Quick studio controls */
  $$('.editor-tool').forEach((button) => {
    button.addEventListener('click', () => {
      $$('.editor-tool').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      const name = button.dataset.tool;
      const tab = name === 'captions' ? 'captions' : name === 'brand' ? 'brand' : 'properties';
      $$('.inspector-tab').forEach((item) => item.classList.toggle('active', item.dataset.inspectorTab === tab));
      $$('.inspector-content').forEach((item) => item.classList.add('hidden'));
      $('#inspector-' + tab)?.classList.remove('hidden');
    });
  });

  $$('.inspector-tab').forEach((button) => button.addEventListener('click', () => {
    const tab = button.dataset.inspectorTab;
    $$('.inspector-tab').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    $$('.inspector-content').forEach((item) => item.classList.add('hidden'));
    $('#inspector-' + tab)?.classList.remove('hidden');
  }));

  $$('.ratio-grid button').forEach((button) => button.addEventListener('click', () => {
    const ratio = button.dataset.ratio;
    $$('.ratio-grid button').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
    const frame = $('.video-frame');
    if (frame) frame.style.aspectRatio = ratio.replace(':', '/');
    const format = $('[data-format-button]');
    if (format) format.textContent = ratio + ' ▾';
  }));

  $$('.canvas-tab').forEach((button) => button.addEventListener('click', () => {
    $$('.canvas-tab').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
  }));

  $$('.caption-style').forEach((button) => button.addEventListener('click', () => {
    $$('.caption-style').forEach((item) => item.classList.remove('active'));
    button.classList.add('active');
  }));

  $$('.timeline-clip').forEach((clip) => clip.addEventListener('click', () => {
    $$('.timeline-clip').forEach((item) => item.style.outline = 'none');
    clip.style.outline = '1px solid var(--k-accent)';
  }));

  /* Motion preference fallback for old V11 pages */
  root.dataset.motion = get('klypso.motion', '1') === '0' ? 'off' : 'on';

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js').catch(() => {}));
  }
})();
