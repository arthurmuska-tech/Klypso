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

  /* V16 Command Center */
  const commandPalette = $('[data-command-palette]');
  const commandInput = $('[data-command-input]', commandPalette || document);
  const commandItems = $('[data-command-item]', commandPalette || document);
  let commandIndex = 0;
  function commandOpen() {
    if (!commandPalette) return;
    commandPalette.classList.add('open');
    commandPalette.setAttribute('aria-hidden', 'false');
    commandIndex = 0;
    if (commandInput) {
      commandInput.value = '';
      commandItems.forEach((item) => { item.hidden = false; item.classList.remove('is-active'); });
      requestAnimationFrame(() => commandInput.focus());
    }
    document.body.classList.add('command-open');
  }
  function commandClose() {
    if (!commandPalette) return;
    commandPalette.classList.remove('open');
    commandPalette.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('command-open');
  }
  function visibleCommandItems() { return commandItems.filter((item) => !item.hidden); }
  function setCommandIndex(next) {
    const items = visibleCommandItems();
    if (!items.length) return;
    commandIndex = (next + items.length) % items.length;
    items.forEach((item, i) => item.classList.toggle('is-active', i === commandIndex));
    items[commandIndex].scrollIntoView({ block: 'nearest' });
  }
  function filterCommands(value) {
    const query = (value || '').trim().toLowerCase();
    commandItems.forEach((item) => {
      const haystack = ((item.dataset.commandTitle || '') + ' ' + item.textContent).toLowerCase();
      item.hidden = query && !haystack.includes(query);
      item.classList.remove('is-active');
    });
    commandIndex = 0;
    setCommandIndex(0);
  }
  $('[data-search-open]')?.addEventListener('click', commandOpen);
  $('[data-command-close]').forEach((el) => el.addEventListener('click', commandClose));
  commandInput?.addEventListener('input', () => filterCommands(commandInput.value));
  commandInput?.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); setCommandIndex(commandIndex + 1); }
    if (event.key === 'ArrowUp') { event.preventDefault(); setCommandIndex(commandIndex - 1); }
    if (event.key === 'Enter') {
      const items = visibleCommandItems();
      if (items[commandIndex]) items[commandIndex].click();
    }
    if (event.key === 'Escape') { event.preventDefault(); commandClose(); }
  });
  document.addEventListener('keydown', (event) => {
    const mod = event.ctrlKey || event.metaKey;
    if (mod && event.key.toLowerCase() === 'k') { event.preventDefault(); commandOpen(); return; }
    if (event.key === 'Escape' && commandPalette?.classList.contains('open')) commandClose();
    if (mod && event.key.toLowerCase() === 's' && document.querySelector('[data-save-project]')) {
      event.preventDefault();
      document.querySelector('[data-save-project]')?.click();
    }
  });
  commandItems.forEach((item) => item.addEventListener('mousemove', () => {
    const items = visibleCommandItems(); const index = items.indexOf(item);
    if (index >= 0) setCommandIndex(index);
  }));

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

  /* V16 Clips library: search + sort */
  const clipsGrid = $('.clip-project-grid');
  const clipsSearch = $('[data-clips-search]');
  const clipsSearchToggle = $('[data-clips-search-toggle]');
  const clipsSort = $('[data-clips-sort]');
  const clipsResultCount = $('[data-clips-result-count]');
  const clipsEmpty = $('[data-clips-no-results]');
  const clipCards = clipsGrid ? $('.clip-project-card', clipsGrid) : [];
  let activeClipTab = 'all';
  let activeClipQuery = '';
  let activeClipSort = 'recent';

  function syncClipLibrary() {
    if (!clipCards.length) return;
    const query = activeClipQuery.toLowerCase();
    const filtered = clipCards.filter((card) => {
      const status = card.dataset.status || '';
      const title = (card.textContent || '').toLowerCase();
      const stateOK = activeClipTab === 'all' ||
        (activeClipTab === 'ready' && /completed|done|ready/.test(status)) ||
        (activeClipTab === 'processing' && /processing|running|queued/.test(status));
      return stateOK && (!query || title.includes(query));
    });
    const sorted = [...filtered].sort((a, b) => {
      const aa = a.dataset.created || '';
      const bb = b.dataset.created || '';
      if (activeClipSort === 'oldest') return aa.localeCompare(bb);
      if (activeClipSort === 'status') return (a.dataset.status || '').localeCompare(b.dataset.status || '') || bb.localeCompare(aa);
      return bb.localeCompare(aa);
    });
    sorted.forEach((card) => { card.style.display = ''; clipsGrid.appendChild(card); });
    clipCards.forEach((card) => { if (!sorted.includes(card)) card.style.display = 'none'; });
    if (clipsResultCount) clipsResultCount.textContent = String(filtered.length);
    if (clipsEmpty) clipsEmpty.hidden = filtered.length !== 0;
  }
  clipsSearchToggle?.addEventListener('click', () => {
    const visible = clipsSearch?.classList.toggle('is-open');
    if (visible) clipsSearch?.querySelector('input')?.focus();
  });
  clipsSearch?.querySelector('input')?.addEventListener('input', (event) => {
    activeClipQuery = event.target.value || '';
    syncClipLibrary();
  });
  clipsSort?.addEventListener('click', () => {
    const modes = ['recent','oldest','status'];
    activeClipSort = modes[(modes.indexOf(activeClipSort) + 1) % modes.length];
    clipsSort.textContent = activeClipSort === 'recent' ? '⇅ Récent' : activeClipSort === 'oldest' ? '⇅ Plus ancien' : '⇅ Statut';
    syncClipLibrary();
  });

  /* Clips filters */
  $$('.tab-btn').forEach((button) => {
    button.addEventListener('click', () => {
      $$('.tab-btn').forEach((item) => item.classList.remove('active'));
      button.classList.add('active');
      const state = button.dataset.listTab || 'all';
      activeClipTab = state;
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

  /* V16 draft save */
  const saveProjectButton = $('[data-save-project]');
  saveProjectButton?.addEventListener('click', () => {
    const state = {
      savedAt: new Date().toISOString(),
      ratio: $('[data-format-button]')?.textContent?.trim() || '9:16',
      zoom: $('#zoom-label')?.textContent?.trim() || '100%',
      tool: $('.editor-tool.active')?.dataset.tool || 'select'
    };
    set('klypso.studio.draft', JSON.stringify(state));
    const previous = saveProjectButton.textContent;
    saveProjectButton.textContent = 'Enregistré ✓';
    saveProjectButton.classList.add('saved');
    setTimeout(() => { saveProjectButton.textContent = previous; saveProjectButton.classList.remove('saved'); }, 1600);
  });

  /* V16 OTP countdown */
  const otpCard = $('[data-otp-card]');
  const otpCountdown = $('[data-otp-countdown]');
  const resendButton = $('[data-resend-code]');
  if (otpCard && resendButton) {
    let remaining = Number(otpCard.dataset.otpCooldown || 0);
    const tick = () => {
      if (remaining > 0) {
        resendButton.disabled = true;
        resendButton.textContent = 'Renvoyer dans ' + remaining + 's';
        if (otpCountdown) otpCountdown.textContent = 'Nouvelle demande bientôt disponible';
        remaining -= 1;
      } else {
        resendButton.disabled = false;
        resendButton.textContent = 'Renvoyer un code';
        if (otpCountdown) otpCountdown.textContent = 'Tu peux demander un nouveau code';
        clearInterval(timer);
      }
    };
    const timer = setInterval(tick, 1000);
    tick();
  }

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
  syncClipLibrary();

  if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => navigator.serviceWorker.register('/static/sw.js').catch(() => {}));
  }
})();
