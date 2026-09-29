/* KLYPSO V25 — interaction hardening */
(() => {
  'use strict';
  const $ = (s,r=document) => r.querySelector(s);
  const $$ = (s,r=document) => Array.from(r.querySelectorAll(s));
  const sidebar = $('#app-sidebar');
  const setSidebar = (open) => {
    sidebar?.classList.toggle('open', open);
    document.body.classList.toggle('sidebar-open', open);
    if (open) $('[data-sidebar-close]')?.focus({preventScroll:true});
  };

  $('[data-sidebar-open]')?.addEventListener('click', () => setSidebar(true));
  $('[data-sidebar-close]')?.addEventListener('click', () => setSidebar(false));
  $$('.sidebar-nav a').forEach(a => a.addEventListener('click', () => setSidebar(false)));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      if (sidebar?.classList.contains('open')) setSidebar(false);
    }
  });
  document.addEventListener('click', e => {
    if (!sidebar?.classList.contains('open') || window.matchMedia('(min-width:821px)').matches) return;
    if (!sidebar.contains(e.target) && !e.target.closest('[data-sidebar-open]')) setSidebar(false);
  });

  // Keep reveal content fail-safe: if an observer misses an element, it becomes visible.
  const reveals = $$('.v24-reveal');
  if ('IntersectionObserver' in window && reveals.length) {
    const io = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('v24-visible');
          io.unobserve(entry.target);
        }
      });
    }, {threshold:.08, rootMargin:'0px 0px -4% 0px'});
    reveals.forEach(el => io.observe(el));
    window.setTimeout(() => reveals.forEach(el => {
      const r = el.getBoundingClientRect();
      if (r.top < window.innerHeight * 1.15) el.classList.add('v24-visible');
    }), 900);
  } else {
    reveals.forEach(el => el.classList.add('v24-visible'));
  }

  // Avoid accidental duplicate submits on slow/free-tier cold starts.
  $$('form[data-prevent-double-submit]').forEach(form => {
    form.addEventListener('submit', () => {
      if (form.dataset.submitted === '1') return;
      form.dataset.submitted = '1';
      const button = form.querySelector('button[type="submit"],input[type="submit"]');
      if (button) {
        button.dataset.originalText = button.textContent || '';
        button.classList.add('is-loading');
        button.disabled = true;
      }
    });
  });

  // Native file inputs get an immediate, human-readable filename.
  $$('input[type="file"][data-file-label]').forEach(input => {
    input.addEventListener('change', () => {
      const target = document.querySelector(input.dataset.fileLabel);
      if (!target) return;
      const file = input.files?.[0];
      target.textContent = file ? file.name : 'Aucun fichier sélectionné';
    });
  });
})();