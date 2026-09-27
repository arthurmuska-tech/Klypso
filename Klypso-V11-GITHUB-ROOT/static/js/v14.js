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
  const reveal = $('.home-feature,.home-intro,.home-capabilities,.capability-grid > div,.home-library,.dash-hero,.quick-card,.panel-v11,.settings-card-v11,.project-row,.landing-v15-intro,.landing-v15-feature-grid,.landing-v15-details,.landing-v15-free,.landing-v15-faq,.landing-v15-cta,.landing-product-showcase,.landing-proof > div,.landing-v15-hero-copy,.landing-v15-hero-art');
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

  /* --- V20 deterministic public scroll effects --- */
  const publicObjects = $('.v20-scroll-object');
  const publicScenes = $('.v20-scroll-reveal');
  const updatePublicMotion = () => {
    if (!motionEnabled) return;
    const viewport = window.innerHeight || 800;
    publicObjects.forEach((el, index) => {
      const rect = el.getBoundingClientRect();
      const center = rect.top + rect.height / 2;
      const progress = Math.max(-1, Math.min(1, (viewport / 2 - center) / Math.max(1, viewport * 0.85)));
      const depth = Number(el.dataset.motionDepth || 0);
      const y = progress * (36 + depth * 10);
      const scale = 1 + Math.max(-0.035, Math.min(0.025, progress * 0.025));
      el.style.setProperty('--v20-y', y.toFixed(2) + 'px');
      el.style.setProperty('--v20-scale', scale.toFixed(4));
      el.style.setProperty('--v20-delay', Math.min(index * 35, 280) + 'ms');
      el.classList.toggle('v20-near', Math.abs(progress) < 0.58);
    });
    publicScenes.forEach((el) => {
      const rect = el.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, 1 - Math.abs((rect.top + rect.height / 2 - viewport / 2) / Math.max(1, viewport))));
      el.style.setProperty('--v20-focus', ratio.toFixed(3));
    });
  };
  let publicRaf = 0;
  const requestPublicMotion = () => {
    if (!publicRaf) {
      publicRaf = requestAnimationFrame(() => {
        publicRaf = 0;
        updatePublicMotion();
      });
    }
  };
  if (publicObjects.length || publicScenes.length) {
    addEventListener('scroll', requestPublicMotion, {passive:true});
    addEventListener('resize', requestPublicMotion, {passive:true});
    requestPublicMotion();
  }

  /* --- Landing page: smart scroll choreography --- */
  const story = document.querySelector('[data-landing-story]');
  const track = document.querySelector('[data-story-track]');
  const slides = track ? $$('.landing-story-slide', track) : [];
  const storyCurrent = document.querySelector('[data-story-current]');
  const storyProgress = document.querySelector('[data-story-progress]');
  const storyDots = $$('[data-story-jump]');
  let storyRaf = 0;
  let storyActive = false;

  const clamp01 = (value) => Math.max(0, Math.min(1, value));
  const smoothstep = (value) => {
    const t = clamp01(value);
    return t * t * (3 - 2 * t);
  };
  const easeOut = (value) => 1 - Math.pow(1 - clamp01(value), 3);
  const easeIn = (value) => Math.pow(clamp01(value), 3);

  function prepareStoryWords() {
    slides.forEach((slide) => {
      const copy = slide.querySelector('.story-slide-copy');
      if (!copy || copy.dataset.wordsReady === '1') return;
      ['h3', 'p'].forEach((selector) => {
        const element = copy.querySelector(selector);
        if (!element) return;
        const source = element.textContent.trim();
        element.dataset.originalText = source;
        element.setAttribute('aria-label', source);
        element.innerHTML = source.split(/(\s+)/).map((part) => {
          if (!part.trim()) return part;
          return '<span class="story-word" aria-hidden="true">' + part.replace(/[&<>"]/g, (m) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])) + '</span>';
        }).join('');
      });
      copy.dataset.wordsReady = '1';
    });
  }

  function storyCameraLocal(local) {
    /* First 58% = reading/drawing zone. The camera barely moves while the copy marks in. */
    if (local < 0.58) return 0.055 * easeOut(local / 0.58);
    if (local < 0.74) return 0.055 + 0.105 * smoothstep((local - 0.58) / 0.16);
    return 0.16 + 0.84 * easeIn((local - 0.74) / 0.26);
  }

  function updateStoryWords(slide, local) {
    const words = $$('.story-word', slide);
    if (!words.length) return;
    const reveal = clamp01((local - 0.05) / 0.47);
    const wave = words.length > 1 ? reveal * (words.length + 1) : reveal * 2;
    words.forEach((word, index) => {
      const p = clamp01(wave - index);
      const lift = (1 - easeOut(p)) * 16;
      const blur = (1 - p) * 1.8;
      word.style.setProperty('--word-progress', p.toFixed(3));
      word.style.transform = 'translate3d(0,' + lift.toFixed(2) + 'px,0)';
      word.style.filter = 'blur(' + blur.toFixed(2) + 'px)';
      word.style.opacity = Math.max(0.1, p).toFixed(3);
    });
  }

  function updateStoryCard(slide, local, distance) {
    const card = slide.querySelector('.story-slide-card');
    if (!card) return;
    const read = smoothstep(clamp01((local - 0.06) / 0.58));
    const exit = easeIn(clamp01((local - 0.73) / 0.27));
    const depth = (1 - Math.min(1, Math.abs(distance))) * 1;
    card.style.setProperty('--story-read', read.toFixed(3));
    card.style.setProperty('--story-exit', exit.toFixed(3));
    card.style.setProperty('--story-depth', depth.toFixed(3));
    card.style.transform = 'translate3d(0,' + ((1 - read) * 18 - exit * 10).toFixed(2) + 'px,0) rotateZ(' + (distance * -1.7).toFixed(2) + 'deg) scale(' + (0.975 + read * 0.025 - exit * 0.012).toFixed(4) + ')';
  }

  function updateLandingStory() {
    if (!story || !track || !slides.length) return;

    /* Natural vertical storytelling: the browser owns scrolling.
       Each scene reacts to its viewport position without hijacking the wheel. */
    track.style.transform = 'none';

    let bestIndex = 0;
    let bestFocus = -1;

    slides.forEach((slide, i) => {
      const rect = slide.getBoundingClientRect();
      const center = rect.top + rect.height / 2;
      const viewport = window.innerHeight || 800;
      const distance = Math.abs(center - viewport * 0.55);
      const focus = clamp01(1 - distance / Math.max(viewport * 0.78, 1));
      const reveal = clamp01(1 - Math.max(0, rect.top - viewport * 0.9) / Math.max(rect.height * 1.5, 1));

      if (focus > bestFocus) {
        bestFocus = focus;
        bestIndex = i;
      }

      slide.classList.toggle('is-active', focus > 0.22);
      slide.classList.toggle('is-focused', focus > 0.58);
      slide.style.setProperty('--slide-distance', ((center - viewport * 0.55) / Math.max(viewport, 1)).toFixed(3));
      slide.style.setProperty('--slide-abs', Math.min(1.4, distance / Math.max(viewport, 1)).toFixed(3));
      slide.style.setProperty('--slide-near', focus.toFixed(3));
      slide.style.setProperty('--slide-opacity', Math.max(0.56, 0.58 + focus * 0.42).toFixed(3));
      slide.style.setProperty('--story-viewport-focus', focus.toFixed(3));

      const local = clamp01(reveal);
      updateStoryWords(slide, local);
      updateStoryCard(slide, local, (center - viewport * 0.55) / Math.max(viewport, 1));
    });

    if (storyCurrent) storyCurrent.textContent = String(bestIndex + 1).padStart(2, '0');

    const storyRect = story.getBoundingClientRect();
    const storyVisible = clamp01(1 - Math.max(0, storyRect.top - viewportHeightSafe()) / Math.max(story.offsetHeight, 1));
    if (storyProgress) storyProgress.style.width = (storyVisible * 100).toFixed(2) + '%';
    storyDots.forEach((dot, dotIndex) => {
      dot.classList.toggle('active', dotIndex === bestIndex);
      dot.setAttribute('aria-selected', String(dotIndex === bestIndex));
    });

    storyActive = bestFocus > 0.08;
    story.classList.toggle('is-live', storyActive);

    const heroArt = document.querySelector('.landing-v15-hero-art');
    if (heroArt) {
      const heroRect = heroArt.parentElement.getBoundingClientRect();
      const heroProgress = Math.max(-1, Math.min(1, -heroRect.top / Math.max(1, window.innerHeight)));
      heroArt.style.setProperty('--hero-depth-y', (heroProgress * -12).toFixed(2) + 'px');
      heroArt.style.setProperty('--hero-depth-r', (heroProgress * 0.9).toFixed(2) + 'deg');
    }
  }

  function viewportHeightSafe() {
    return window.innerHeight || 800;
  }

  function requestLandingStoryUpdate() {
    if (!storyRaf) {
      storyRaf = requestAnimationFrame(() => {
        storyRaf = 0;
        updateLandingStory();
      });
    }
  }

  storyDots.forEach((dot) => {
    dot.addEventListener('click', () => {
      if (!story) return;
      const targetStep = Math.max(0, Math.min(slides.length - 1, Number(dot.dataset.storyJump || 0)));
      const travel = Math.max(1, story.offsetHeight - window.innerHeight);
      const ratio = targetStep / Math.max(1, slides.length);
      const target = story.getBoundingClientRect().top + window.scrollY + (travel * ratio);
      window.scrollTo({ top: target, behavior: motionEnabled ? 'smooth' : 'auto' });
    });
  });

  if (story && 'IntersectionObserver' in window) {
    const storyObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => { if (entry.isIntersecting) requestLandingStoryUpdate(); });
    }, { threshold: 0.01 });
    storyObserver.observe(story);
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
  /* --- Premium V20 interaction layer --- */
  const interactiveCards = $('.workspace-start-card,.workspace-metrics article,.landing-v15-feature-grid article,.landing-detail-grid article,.showcase-card,.publisher-card,.publisher-platform,.quick-card,.panel-v11,.choice-card,.studio-tool-card,.pricing-card-v11');
  interactiveCards.forEach((card) => {
    card.classList.add('v20-surface');
    card.addEventListener('pointermove', (event) => {
      if (body.classList.contains('v14-no-motion') || event.pointerType === 'touch') return;
      const rect = card.getBoundingClientRect();
      const px = ((event.clientX - rect.left) / Math.max(1, rect.width)) * 100;
      const py = ((event.clientY - rect.top) / Math.max(1, rect.height)) * 100;
      card.style.setProperty('--mx', px.toFixed(2) + '%');
      card.style.setProperty('--my', py.toFixed(2) + '%');
      card.style.setProperty('--rx', (((py - 50) / 50) * -1.8).toFixed(2) + 'deg');
      card.style.setProperty('--ry', (((px - 50) / 50) * 2.2).toFixed(2) + 'deg');
      card.classList.add('v20-hovering');
    }, { passive: true });
    card.addEventListener('pointerleave', () => {
      card.style.setProperty('--mx', '50%');
      card.style.setProperty('--my', '50%');
      card.style.setProperty('--rx', '0deg');
      card.style.setProperty('--ry', '0deg');
      card.classList.remove('v20-hovering');
    }, { passive: true });
  });

  const ripples = $('.button,.icon-button,.filter-btn,.tab-btn,.canvas-tab,.editor-tool,.small-icon,.zoom-chip,.landing-secondary,.workspace-link,.choice-card');
  ripples.forEach((el) => {
    if (el.dataset.v20PressBound) return;
    el.dataset.v20PressBound = '1';
    el.addEventListener('pointerdown', (event) => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      const rect = el.getBoundingClientRect();
      const wave = document.createElement('span');
      wave.className = 'v20-ripple';
      wave.style.left = (event.clientX - rect.left) + 'px';
      wave.style.top = (event.clientY - rect.top) + 'px';
      el.appendChild(wave);
      window.setTimeout(() => wave.remove(), 650);
    }, { passive: true });
  });

  const pressables = $('.button,.icon-button,.filter-btn,.tab-btn,.canvas-tab,.editor-tool,.small-icon,.zoom-chip');
  pressables.forEach((el) => {
    el.addEventListener('pointerdown', () => el.classList.add('v20-pressed'), { passive: true });
    ['pointerup','pointercancel','pointerleave'].forEach((eventName) => {
      el.addEventListener(eventName, () => el.classList.remove('v20-pressed'), { passive: true });
    });
  });

  /* Keep the public homepage feeling continuous instead of empty between blocks. */
  const stagedSections = $('.landing-v15-intro,.landing-v15-feature-grid,.landing-story,.landing-v15-details,.landing-v15-free,.landing-v15-faq,.landing-v15-cta,.workspace-start-grid,.workspace-flow,.workspace-projects');
  stagedSections.forEach((section) => section.classList.add('v20-stage'));

  const updateStageFocus = () => {
    if (body.classList.contains('v14-no-motion')) return;
    const viewport = window.innerHeight || 800;
    stagedSections.forEach((section) => {
      const rect = section.getBoundingClientRect();
      const distance = Math.abs((rect.top + rect.height * 0.35) - viewport * 0.52);
      const focus = Math.max(0, Math.min(1, 1 - distance / Math.max(viewport * 1.25, 1)));
      section.style.setProperty('--stage-focus', focus.toFixed(3));
    });
  };
  let stageRaf = 0;
  const requestStageFocus = () => {
    if (stageRaf) return;
    stageRaf = requestAnimationFrame(() => {
      stageRaf = 0;
      updateStageFocus();
    });
  };
  addEventListener('scroll', requestStageFocus, { passive: true });
  addEventListener('resize', requestStageFocus, { passive: true });
  requestStageFocus();

  /* A subtle cursor halo gives the page a tangible layer without hijacking scrolling. */
  if (!window.matchMedia('(pointer: coarse)').matches && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const halo = document.createElement('div');
    halo.className = 'v20-cursor-halo';
    body.appendChild(halo);
    let haloX = window.innerWidth * 0.5;
    let haloY = window.innerHeight * 0.35;
    let targetX = haloX;
    let targetY = haloY;
    const moveHalo = (event) => { targetX = event.clientX; targetY = event.clientY; };
    addEventListener('pointermove', moveHalo, { passive: true });
    const tickHalo = () => {
      haloX += (targetX - haloX) * 0.14;
      haloY += (targetY - haloY) * 0.14;
      halo.style.transform = 'translate3d(' + (haloX - 120) + 'px,' + (haloY - 120) + 'px,0)';
      requestAnimationFrame(tickHalo);
    };
    requestAnimationFrame(tickHalo);
  }


  /* --- V20 interactive product spotlights --- */
  const spotlight = document.querySelector('[data-spotlight-dialog]');
  const spotlightCards = $('[data-spotlight]');
  if (spotlight && spotlightCards.length) {
    const data = {
      accueil: {
        kicker: 'WORKSPACE · ACCUEIL',
        title: 'Ton cockpit de création.',
        text: 'Retrouve tes projets, crédits et raccourcis dans une vue qui donne immédiatement le prochain geste à faire.',
        pills: ['Projets', 'Crédits', 'Creator DNA']
      },
      clips: {
        kicker: 'CLIPS IA · VIRAL ENGINE',
        title: 'Détecter, comparer, choisir.',
        text: 'Les signaux média, audio, chat et mémoire créateur servent à préparer une sélection de moments à travailler.',
        pills: ['Scoring', 'Audio', 'Chat']
      },
      studio: {
        kicker: 'KLYPSO STUDIO',
        title: 'Passe du moment au montage.',
        text: 'Canvas, timeline, texte, audio, cadrage et export restent dans le même projet pour éviter les allers-retours.',
        pills: ['Timeline', 'Canvas', 'Export']
      },
      publication: {
        kicker: 'PUBLICATION · DISTRIBUTION',
        title: 'Publie puis apprends.',
        text: 'Programme tes sorties, suis les performances et transforme les résultats en signaux pour les prochaines créations.',
        pills: ['Calendrier', 'Performance', 'DNA']
      }
    };
    const titleEl = spotlight.querySelector('[data-spotlight-title]');
    const textEl = spotlight.querySelector('[data-spotlight-text]');
    const kickerEl = spotlight.querySelector('[data-spotlight-kicker]');
    const pillsEl = spotlight.querySelector('[data-spotlight-pills]');
    const artEl = spotlight.querySelector('[data-spotlight-art]');
    let lastSpotlightTrigger = null;

    const closeSpotlight = () => {
      spotlight.classList.remove('is-open');
      window.setTimeout(() => { spotlight.hidden = true; }, 320);
      document.body.classList.remove('v20-dialog-open');
      if (lastSpotlightTrigger) lastSpotlightTrigger.focus();
    };

    const openSpotlight = (key, trigger) => {
      const item = data[key];
      if (!item) return;
      lastSpotlightTrigger = trigger || null;
      kickerEl.textContent = item.kicker;
      titleEl.textContent = item.title;
      textEl.textContent = item.text;
      pillsEl.innerHTML = item.pills.map(p => '<span>' + p + '</span>').join('');
      artEl.setAttribute('data-kind', key);
      spotlight.hidden = false;
      requestAnimationFrame(() => spotlight.classList.add('is-open'));
      document.body.classList.add('v20-dialog-open');
      const close = spotlight.querySelector('[data-spotlight-close]');
      if (close) close.focus();
    };

    spotlightCards.forEach((card) => {
      const open = () => openSpotlight(card.dataset.spotlight, card);
      card.addEventListener('click', open);
      card.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); open(); }
      });
    });
    $('[data-spotlight-close]', spotlight).forEach((el) => el.addEventListener('click', closeSpotlight));
    addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !spotlight.hidden) closeSpotlight();
    });
  }

  /* Dashboard workflow cards behave like a mini command center. */
  const flowRoutes = {
    '01': '/projects/new',
    '02': '/clips',
    '03': '/studio',
    '04': '/publisher'
  };
  $('.workspace-flow-steps > div').forEach((step) => {
    const number = step.querySelector('span');
    if (!number) return;
    const target = flowRoutes[number.textContent.trim()];
    if (!target) return;
    step.setAttribute('role', 'link');
    step.setAttribute('tabindex', '0');
    const activate = () => { window.location.href = target; };
    step.addEventListener('click', activate);
    step.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate(); }
    });
  });

  /* Scroll-linked active navigation on the public page. */
  const publicAnchors = $('a[href*="#fonctionnalites"]');
  const featureSection = document.getElementById('fonctionnalites');
  if (featureSection && publicAnchors.length && 'IntersectionObserver' in window) {
    const featureObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => publicAnchors.forEach((a) => a.classList.toggle('is-context-active', entry.isIntersecting)));
    }, { threshold: 0.28 });
    featureObserver.observe(featureSection);
  }

})();