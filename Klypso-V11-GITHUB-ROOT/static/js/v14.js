/* KLYPSO V15.3 — workspace polish + cinematic public home */
(() => {
  'use strict';

  const root = document.documentElement;
  const body = document.body;
  const $$ = (selector, parent = document) => Array.from(parent.querySelectorAll(selector));
  const getStore = (key, fallback) => {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : value;
    } catch (_) {
      return fallback;
    }
  };
  const setStore = (key, value) => {
    try { localStorage.setItem(key, value); } catch (_) {}
  };

  /* --- Material personalization --- */
  const woods = ['oak', 'walnut', 'birch', 'cherry', 'ebony'];
  const woodTheme = {
    oak: '#f3efe8',
    walnut: '#241c18',
    birch: '#f7f5ef',
    cherry: '#f5e8e2',
    ebony: '#111315'
  };

  function applyWood(value) {
    const safe = woods.includes(value) ? value : 'oak';
    root.dataset.wood = safe;
    setStore('klypso.wood', safe);
    $$('[data-wood]').forEach((el) => {
      const selected = el.dataset.wood === safe;
      el.classList.toggle('selected', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = woodTheme[safe];
  }

  applyWood(getStore('klypso.wood', 'oak'));
  $$('[data-wood]').forEach((el) => {
    el.addEventListener('click', () => applyWood(el.dataset.wood));
  });

  /* --- Native scrolling only. No wheel hijacking. --- */
  root.style.scrollBehavior = 'auto';
  body.style.overscrollBehaviorY = 'auto';
  body.style.overflowY = 'visible';

  /* --- Motion preference --- */
  const motionInput = document.querySelector('[data-setting="motion"]');
  const motionSaved = getStore('klypso.motion', '1');
  const motionEnabled = motionSaved !== '0' && !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  body.classList.toggle('v14-no-motion', !motionEnabled);
  if (motionInput) motionInput.checked = motionSaved !== '0';
  if (motionInput) {
    motionInput.addEventListener('change', () => {
      const enabled = motionInput.checked;
      setStore('klypso.motion', enabled ? '1' : '0');
      body.classList.toggle('v14-no-motion', !enabled);
    });
  }

  /* --- Generic reveal for app pages --- */
  const reveal = $$('.home-feature,.home-intro,.home-capabilities,.capability-grid > div,.home-library,.dash-hero,.quick-card,.panel-v11,.settings-card-v11,.project-row');
  reveal.forEach((el, index) => {
    el.classList.add('v14-reveal');
    el.style.setProperty('--reveal-delay', Math.min(index * 35, 280) + 'ms');
  });

  if (!body.classList.contains('v14-no-motion') && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('v14-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -8% 0px' });
    reveal.forEach((el) => observer.observe(el));
  } else {
    reveal.forEach((el) => el.classList.add('v14-visible'));
  }

  /* --- Landing page: vertical scroll drives a horizontal presentation rail --- */
  const story = document.querySelector('[data-landing-story]');
  const track = document.querySelector('[data-story-track]');
  const slides = track ? $$('.landing-story-slide', track) : [];
  const storyCurrent = document.querySelector('[data-story-current]');
  const storyProgress = document.querySelector('[data-story-progress]');
  let storyRaf = 0;

  function updateLandingStory() {
    if (!story || !track || !slides.length) return;
    const isMobile = window.matchMedia('(max-width: 900px)').matches;
    if (isMobile) {
      track.style.transform = 'none';
      slides.forEach((slide, index) => slide.classList.toggle('is-active', index === 0));
      if (storyCurrent) storyCurrent.textContent = '01';
      if (storyProgress) storyProgress.style.width = '25%';
      return;
    }

    const rect = story.getBoundingClientRect();
    const travel = Math.max(1, story.offsetHeight - window.innerHeight);
    const progress = Math.max(0, Math.min(1, -rect.top / travel));
    const phase = progress * (slides.length - 1);
    const index = Math.min(slides.length - 1, Math.floor(phase + 0.5));

    /* The track travels exactly one slide-width per step. */
    track.style.transform = 'translate3d(' + (-progress * 75) + '%, 0, 0)';
    slides.forEach((slide, i) => {
      const distance = i - phase;
      const abs = Math.abs(distance);
      slide.classList.toggle('is-active', abs < 0.62);
      slide.style.setProperty('--slide-distance', distance.toFixed(3));
      slide.style.setProperty('--slide-abs', Math.min(1.4, abs).toFixed(3));
      slide.style.setProperty('--slide-opacity', Math.max(.28, 1 - abs * .5).toFixed(3));
      slide.style.setProperty('--slide-tilt', Math.max(-4.5, Math.min(4.5, -distance * 3.2)).toFixed(2) + 'deg');
    });

    /* A tiny parallax on the hero gives the first screen depth before the rail. */
    const heroArt = document.querySelector('.landing-v15-hero-art');
    if (heroArt) {
      const heroRect = heroArt.parentElement.getBoundingClientRect();
      const heroProgress = Math.max(-1, Math.min(1, -heroRect.top / Math.max(1, window.innerHeight)));
      heroArt.style.setProperty('--hero-depth-y', (heroProgress * -24).toFixed(2) + 'px');
      heroArt.style.setProperty('--hero-depth-r', (heroProgress * 1.8).toFixed(2) + 'deg');
    }

    if (storyCurrent) storyCurrent.textContent = String(index + 1).padStart(2, '0');
    if (storyProgress) storyProgress.style.width = ((progress * 100).toFixed(2)) + '%';
  }

  function requestLandingStoryUpdate() {
    if (!storyRaf) {
      storyRaf = requestAnimationFrame(() => {
        storyRaf = 0;
        updateLandingStory();
      });
    }
  }

  addEventListener('scroll', requestLandingStoryUpdate, { passive: true });
  addEventListener('resize', requestLandingStoryUpdate, { passive: true });
  updateLandingStory();

  /* --- Tactile controls --- */
  $$('.button,.icon-button,.topbar-plan,.topbar-avatar,.v14-wood-option,.choice-card,.seg-btn,.sidebar-nav a,.landing-secondary').forEach((el) => {
    el.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      const rect = el.getBoundingClientRect();
      el.style.setProperty('--ripple-x', ((event.clientX - rect.left) / Math.max(1, rect.width) * 100) + '%');
      el.style.setProperty('--ripple-y', ((event.clientY - rect.top) / Math.max(1, rect.height) * 100) + '%');
      el.classList.remove('v14-ripple-active');
      void el.offsetWidth;
      el.classList.add('v14-ripple-active');
    }, { passive: true });
  });

  /* --- Scroll progress, top button and smart topbar --- */
  const progressBar = document.createElement('div');
  progressBar.className = 'v14-progress';
  body.appendChild(progressBar);

  const backTop = document.createElement('button');
  backTop.className = 'v14-scroll-top';
  backTop.type = 'button';
  backTop.textContent = '↑';
  backTop.setAttribute('aria-label', 'Retour en haut');
  body.appendChild(backTop);

  let lastY = window.scrollY;
  let chromeRaf = 0;

  function updateChrome() {
    const max = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
    progressBar.style.width = Math.min(100, (window.scrollY / max) * 100) + '%';
    backTop.classList.toggle('show', window.scrollY > 600);
    const header = document.querySelector('.app-topbar');
    if (header && window.scrollY > 110) {
      header.style.transform = window.scrollY > lastY + 4 ? 'translateY(-100%)' : 'translateY(0)';
    }
    lastY = window.scrollY;
  }

  function requestChromeUpdate() {
    if (!chromeRaf) {
      chromeRaf = requestAnimationFrame(() => {
        chromeRaf = 0;
        updateChrome();
      });
    }
  }

  addEventListener('scroll', requestChromeUpdate, { passive: true });
  updateChrome();
  backTop.addEventListener('click', () => window.scrollTo({ top: 0, behavior: 'smooth' }));

  /* --- App choice controls --- */
  $$('.choice-card').forEach((card) => {
    card.addEventListener('click', () => {
      const parent = card.closest('.option-cards') || card.parentElement;
      $$('.choice-card', parent).forEach((item) => item.classList.remove('selected'));
      card.classList.add('selected');
    });
  });

  /* --- Reset / segmented controls from the existing account UI --- */
  $$('.seg-row').forEach((group) => {
    $$('label', group).forEach((button) => {
      button.addEventListener('click', () => {
        $$('label', group).forEach((item) => item.classList.remove('active'));
        button.classList.add('active');
      });
    });
  });
})();