/* KLYPSO V26 — scroll choreography + tactile public interactions */
(() => {
  'use strict';

  const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
  const $ = (selector, root = document) => root.querySelector(selector);
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const publicPage = $('.v24-landing, .public-demo-v20');
  if (!publicPage) return;

  document.documentElement.classList.add('v26-ready');

  // Do not hijack native touch scrolling or pointer gestures on touch devices.
  const coarsePointer = window.matchMedia('(pointer: coarse)').matches;
  if (coarsePointer) document.documentElement.classList.add('v26-touch');

  // Reading progress: tiny and useful, never blocks clicks.
  const progress = document.createElement('div');
  progress.className = 'v26-progress';
  progress.setAttribute('aria-hidden', 'true');
  document.body.appendChild(progress);

  const updateProgress = () => {
    const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    progress.style.transform = 'scaleX(' + Math.min(1, Math.max(0, window.scrollY / max)) + ')';
    document.body.classList.toggle('v26-scrolled', window.scrollY > 28);
  };

  // Turn the existing landing structure into a cinematic sequence without
  // requiring every template to be rewritten by hand.
  const sections = $$('.v24-hero, .v24-proof, .v24-section, .v24-workflow, .v24-showcase, .v24-faq, .v24-cta, .demo-hero, .demo-panel, .demo-cta');
  sections.forEach((section, index) => {
    section.classList.add('v26-reveal');
    section.style.setProperty('--v26-delay', Math.min(index * 35, 240) + 'ms');
    if (section.matches('.v24-section, .v24-workflow, .v24-showcase, .v24-faq, .demo-panel')) {
      section.classList.add('v26-stagger');
    }
  });

  const revealItems = $$('.v26-reveal');
  if (!reduced && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('v26-visible');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    revealItems.forEach(item => observer.observe(item));
    window.setTimeout(() => revealItems.forEach(item => {
      const r = item.getBoundingClientRect();
      if (r.top < window.innerHeight * 1.08) item.classList.add('v26-visible');
    }), 1100);
  } else {
    revealItems.forEach(item => item.classList.add('v26-visible'));
  }

  // Add a small scroll cue only when the hero is tall enough to benefit from it.
  const hero = $('.v24-hero');
  if (hero && !reduced && window.innerHeight > 650 && !$('.v26-scroll-cue', hero)) {
    const cue = document.createElement('div');
    cue.className = 'v26-scroll-cue';
    cue.innerHTML = '<span>Faire défiler</span><i></i>';
    hero.appendChild(cue);
  }

  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      updateProgress();
      if (!reduced) {
        const frame = $('.v24-product-frame');
        if (frame) {
          const rect = frame.getBoundingClientRect();
          const center = window.innerHeight * .5;
          const delta = (rect.top + rect.height * .5 - center) / Math.max(1, window.innerHeight);
          frame.style.setProperty('--v26-parallax', Math.max(-22, Math.min(22, delta * -28)) + 'px');
          frame.style.setProperty('--v26-float-y', Math.max(-18, Math.min(18, delta * -20)) + 'px');
          frame.style.setProperty('--v26-float-a', Math.max(-10, Math.min(10, delta * 11)) + 'px');
          frame.style.setProperty('--v26-float-b', Math.max(-10, Math.min(10, delta * -9)) + 'px');
        }
      }
      ticking = false;
    });
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', updateProgress, { passive: true });
  updateProgress();
  onScroll();

  // Desktop pointer depth on the hero product window.
  const frame = $('.v24-product-frame');
  const windowCard = $('.v24-window', frame || document);
  if (frame && windowCard && !reduced && window.matchMedia('(hover:hover)').matches) {
    frame.addEventListener('pointermove', event => {
      const rect = frame.getBoundingClientRect();
      const x = (event.clientX - rect.left) / rect.width - .5;
      const y = (event.clientY - rect.top) / rect.height - .5;
      windowCard.style.setProperty('--v24-ry', (x * 5.5).toFixed(2) + 'deg');
      windowCard.style.setProperty('--v24-rx', (y * -4.5).toFixed(2) + 'deg');
      frame.style.setProperty('--mx', ((x + .5) * 100) + '%');
      frame.style.setProperty('--my', ((y + .5) * 100) + '%');
    });
    frame.addEventListener('pointerleave', () => {
      windowCard.style.setProperty('--v24-ry', '0deg');
      windowCard.style.setProperty('--v24-rx', '0deg');
    });
  }

  // Tactile magnetic buttons on desktop only.
  if (!reduced && !coarsePointer && window.matchMedia('(hover:hover)').matches) {
    $$('.v24-primary, .v24-text-button, .v24-inline-link, .public-nav .button').forEach(button => {
      button.classList.add('v26-magnetic');
      button.addEventListener('pointermove', event => {
        const rect = button.getBoundingClientRect();
        const x = (event.clientX - rect.left) / rect.width - .5;
        const y = (event.clientY - rect.top) / rect.height - .5;
        button.style.transform = 'translate(' + (x * 5).toFixed(1) + 'px,' + (y * 4).toFixed(1) + 'px)';
      });
      button.addEventListener('pointerleave', () => { button.style.transform = ''; });
    });
  }

  // Soft cursor spotlight on feature cards; disabled on touch.
  if (!reduced && window.matchMedia('(hover:hover)').matches) {
    $$('.v24-feature-card').forEach(card => {
      card.addEventListener('pointermove', event => {
        const rect = card.getBoundingClientRect();
        card.style.setProperty('--mx', ((event.clientX - rect.left) / rect.width * 100) + '%');
        card.style.setProperty('--my', ((event.clientY - rect.top) / rect.height * 100) + '%');
      });
    });
  }

  // Make anchor scrolling land below the sticky navigation.
  $$('a[href^="#"]').forEach(link => {
    link.addEventListener('click', event => {
      const id = link.getAttribute('href');
      if (!id || id === '#') return;
      const target = document.querySelector(id);
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    });
  });
})();
