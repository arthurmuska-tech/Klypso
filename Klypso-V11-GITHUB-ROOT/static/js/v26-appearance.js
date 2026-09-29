/* KLYPSO V26 — persistent appearance controls */
(() => {
  'use strict';
  const root = document.documentElement;
  const $ = (s, r=document) => r.querySelector(s);
  const $$ = (s, r=document) => Array.from(r.querySelectorAll(s));
  const store = {
    get(key, fallback) { try { const v=localStorage.getItem(key); return v===null?fallback:v; } catch(_) { return fallback; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch(_) {} }
  };

  const allowed = {
    wood: ['oak','walnut','birch','cherry','ebony'],
    accent: ['#9b7bff','#63a4ff','#59e6df','#ff76c8','#d59a62'],
    density: ['compact','comfortable','spacious'],
    radius: ['sharp','round','soft'],
    palette: ['paper','linen','clay','ocean','forest','plum','graphite','midnight','sage','sand','lavender','slate']
  };

  function safe(group, value, fallback) {
    return allowed[group].includes(value) ? value : fallback;
  }

  function apply(group, value, persist=true) {
    const fallback = {wood:'oak',accent:'#9b7bff',density:'comfortable',radius:'round',palette:'paper'}[group];
    const valueSafe = safe(group, value, fallback);
    root.dataset[group] = valueSafe.replace('#','');
    if (group === 'accent') root.style.setProperty('--k-accent', valueSafe);
    if (persist) store.set('klypso.appearance.' + group, valueSafe);

    $$('[data-' + group + ']').forEach(el => {
      const key = el.dataset[group] || el.dataset.value;
      const selected = key === valueSafe;
      el.classList.toggle('selected', selected);
      el.classList.toggle('active', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
    $$('[data-setting-group="' + group + '"] [data-value]').forEach(el => {
      const selected = el.dataset.value === valueSafe;
      el.classList.toggle('selected', selected);
      el.classList.toggle('active', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
    $$('[data-setting-group="' + group + '"] [data-' + group + ']').forEach(el => {
      const selected = el.dataset[group] === valueSafe;
      el.classList.toggle('selected', selected);
      el.classList.toggle('active', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
  }

  ['wood','accent','density','radius','palette'].forEach(group => {
    const fallback = {wood:'oak',accent:'#9b7bff',density:'comfortable',radius:'round',palette:'paper'}[group];
    apply(group, store.get('klypso.appearance.' + group, fallback), false);
    $$('[data-' + group + ']').forEach(el => {
      const value = el.dataset[group];
      if (!allowed[group].includes(value)) return;
      el.addEventListener('click', () => apply(group, value, true));
    });
    $$('[data-setting-group="' + group + '"] [data-value]').forEach(el => {
      const value = el.dataset.value;
      if (!allowed[group].includes(value)) return;
      el.addEventListener('click', () => apply(group, value, true));
    });
  });

  const motion = $('[data-setting="motion"]');
  const motionValue = store.get('klypso.appearance.motion', '1');
  if (motion) {
    motion.checked = motionValue !== '0';
    motion.addEventListener('change', () => {
      const enabled = motion.checked;
      store.set('klypso.appearance.motion', enabled ? '1' : '0');
      document.body.classList.toggle('v14-no-motion', !enabled);
      root.dataset.motion = enabled ? 'on' : 'off';
    });
  }
  root.dataset.motion = motionValue !== '0' ? 'on' : 'off';

  const reset = $('[data-appearance-reset]');
  reset?.addEventListener('click', () => {
    const defaults = {wood:'oak',accent:'#9b7bff',density:'comfortable',radius:'round',palette:'paper'};
    Object.entries(defaults).forEach(([group,value]) => apply(group,value,true));
    store.set('klypso.appearance.motion','1');
    if (motion) motion.checked = true;
    document.body.classList.remove('v14-no-motion');
    root.dataset.motion='on';
    reset.textContent='Apparence réinitialisée ✓';
    window.setTimeout(() => { reset.textContent='Réinitialiser l’apparence'; }, 1500);
  });

  // Avoid broken visual state when another script changes a theme value.
  window.KlypsoAppearance = { apply };
})();
