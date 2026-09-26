/* KLYPSO V14.3 — deterministic scroll choreography + tactile UI */
(() => {
  'use strict';

  const root = document.documentElement;
  const body = document.body;
  const $ = (s, p=document) => p.querySelector(s);
  const $$ = (s, p=document) => [...p.querySelectorAll(s)];
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer = matchMedia('(pointer:fine)').matches;

  const storage = {
    get(k, fallback) { try { const v=localStorage.getItem(k); return v === null ? fallback : v; } catch { return fallback; } },
    set(k,v) { try { localStorage.setItem(k,v); } catch {} }
  };

  /* ---------------- MATERIAL PERSONALIZATION ---------------- */
  const validWoods = ['oak','walnut','birch','cherry','ebony'];
  const savedWood = validWoods.includes(storage.get('klypso.wood','oak')) ? storage.get('klypso.wood','oak') : 'oak';

  function applyWood(value) {
    root.dataset.wood = value;
    storage.set('klypso.wood', value);
    $$('[data-wood]').forEach(el => {
      const selected = el.dataset.wood === value;
      el.classList.toggle('selected', selected);
      el.setAttribute('aria-pressed', String(selected));
    });
    const meta = $('meta[name="theme-color"]');
    if (meta) {
      const colors = {oak:'#f3efe8',walnut:'#241c18',birch:'#f7f5ef',cherry:'#f5e8e2',ebony:'#111315'};
      meta.content = colors[value] || colors.oak;
    }
  }

  applyWood(savedWood);
  $$('[data-wood]').forEach(button => {
    button.addEventListener('click', () => applyWood(button.dataset.wood));
  });

  /* ---------------- SCROLL STORY ENGINE ----------------
     Nothing is left to chance: progress is calculated from the real viewport
     position on every animation frame. Elements enter from above and text is
     revealed progressively while scrolling. */
  const scenes = $$('.dash-page > *, .pricing-v11-page > *, .project-create-page > *, .settings-page-v11 > *, .clips-page-v11 > *, .studio-v11-page > *, .brand-page-v11 > *, .panel-v11, .quick-card, .activity-panel, .workflow-side, .upload-studio-card');
  scenes.forEach((el,i) => {
    el.classList.add('v14-scroll-scene');
    el.dataset.v14Index = String(i);
  });

  const objects = $$('.quick-icon, .project-thumb, .drop-orb, .profile-avatar-big, .hero-actions, .usage-ring, .tip-card, .spotlight-glow');
  objects.forEach((el,i) => {
    el.classList.add('v14-scroll-object');
    if (i % 2) el.classList.add('v14-object-late');
  });

  const writeTargets = $$('.dash-hero h1, .dash-hero p, .page-title-row h1, .page-title-row p, .quick-card h2, .quick-card p, .panel-v11 h2, .panel-v11 h3, .studio-header h1, .studio-header p, .settings-page-v11 h1, .settings-card-v11 h2, .pricing-v11-page h1');
  writeTargets.forEach(el => {
    if (!el.children.length && el.textContent.trim()) el.classList.add('v14-write-target');
  });

  let raf = 0;
  function updateScrollScenes() {
    raf = 0;
    if (reduced || body.classList.contains('v14-no-motion')) {
      scenes.forEach(el => el.classList.add('v14-inview'));
      objects.forEach(el => el.classList.add('v14-object-in'));
      writeTargets.forEach(el => { el.style.setProperty('--v14-write','100%'); el.classList.add('v14-written'); });
      return;
    }

    const vh = innerHeight;
    const sceneEnter = vh * .92;
    const sceneExit = vh * .08;

    scenes.forEach(el => {
      const r = el.getBoundingClientRect();
      const visible = r.top < sceneEnter && r.bottom > sceneExit;
      const progress = Math.max(0, Math.min(1, (vh*.90 - r.top) / (vh*.66)));
      el.classList.toggle('v14-inview', visible);
      el.classList.toggle('v14-future', r.top >= sceneEnter);
      el.classList.toggle('v14-past', r.bottom <= sceneExit);
      el.style.setProperty('--scene-progress', (progress*100).toFixed(1) + '%');
    });

    objects.forEach((el,i) => {
      const r = el.getBoundingClientRect();
      const start = vh * .96;
      const end = vh * .42;
      const progress = Math.max(0, Math.min(1, (start-r.top)/(start-end)));
      const y = -90 * (1-progress);
      const scale = .88 + progress*.12;
      const opacity = progress;
      const rotate = -1.2 * (1-progress);
      el.classList.toggle('v14-object-in', progress >= .92);
      el.style.opacity = opacity.toFixed(3);
      el.style.transform = 'translate3d(0,' + y.toFixed(1) + 'px,0) scale(' + scale.toFixed(3) + ') rotate(' + rotate.toFixed(2) + 'deg)';
      el.style.filter = 'blur(' + ((1-progress)*5).toFixed(2) + 'px)';
    });

    writeTargets.forEach(el => {
      const r = el.getBoundingClientRect();
      const start = vh * .90;
      const end = vh * .48;
      const progress = Math.max(0, Math.min(1, (start-r.top)/(start-end)));
      el.style.setProperty('--v14-write', (progress*100).toFixed(1) + '%');
      el.classList.toggle('v14-written', progress >= .98);
    });
  }

  function requestScrollUpdate() {
    if (!raf) raf = requestAnimationFrame(updateScrollScenes);
  }

  addEventListener('scroll', requestScrollUpdate, {passive:true});
  addEventListener('resize', requestScrollUpdate, {passive:true});
  requestScrollUpdate();

  /* ---------------- TACTILE BUTTON ENGINE ---------------- */
  const clickables = $$('.button, .icon-button, .topbar-plan, .topbar-avatar, .v14-wood-option, .choice-card, .seg-btn, .sidebar-nav a');
  clickables.forEach(el => {
    el.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty('--ripple-x', ((event.clientX-r.left)/Math.max(1,r.width)*100) + '%');
      el.style.setProperty('--ripple-y', ((event.clientY-r.top)/Math.max(1,r.height)*100) + '%');
      el.classList.remove('v14-ripple-active');
      void el.offsetWidth;
      el.classList.add('v14-ripple-active');
    }, {passive:true});
    el.addEventListener('animationend', () => el.classList.remove('v14-ripple-active'));
  });

  /* ---------------- SUBTLE POINTER DEPTH ---------------- */
  if (!reduced && finePointer) {
    const glow = document.createElement('div');
    glow.className = 'v14-cursor-glow';
    body.appendChild(glow);
    let tx=innerWidth/2, ty=innerHeight/2, x=tx, y=ty;
    addEventListener('pointermove', e => { tx=e.clientX; ty=e.clientY; }, {passive:true});
    const follow=()=>{
      x += (tx-x)*.14; y += (ty-y)*.14;
      glow.style.left=x+'px'; glow.style.top=y+'px';
      requestAnimationFrame(follow);
    };
    follow();
  }

  /* ---------------- PROGRESS + SMART TOPBAR ---------------- */
  const progressBar = document.createElement('div');
  progressBar.className='v14-progress';
  body.appendChild(progressBar);

  const backTop=document.createElement('button');
  backTop.className='v14-scroll-top';
  backTop.type='button';
  backTop.textContent='↑';
  backTop.setAttribute('aria-label','Retour en haut');
  body.appendChild(backTop);

  let lastY=scrollY, navRaf=0;
  function updateChrome(){
    navRaf=0;
    const max=document.documentElement.scrollHeight-innerHeight;
    progressBar.style.width=(max>0 ? Math.min(100,scrollY/max*100) : 0)+'%';
    backTop.classList.toggle('show',scrollY>600);
    const header=$('.app-topbar');
    if(header && scrollY>110) header.style.transform = scrollY > lastY+4 ? 'translateY(-100%)' : 'translateY(0)';
    lastY=scrollY;
  }
  addEventListener('scroll',()=>{if(!navRaf)navRaf=requestAnimationFrame(updateChrome)},{passive:true});
  updateChrome();
  backTop.addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));

  /* ---------------- MOTION SETTING ---------------- */
  function setMotion(enabled) {
    body.classList.toggle('v14-no-motion', !enabled);
    storage.set('klypso.motion', enabled?'1':'0');
    requestScrollUpdate();
  }
  setMotion(storage.get('klypso.motion','1') !== '0');
  $$('[data-setting="motion"]').forEach(input => input.addEventListener('change',()=>setMotion(input.checked)));

  /* Existing selection controls */
  $$('.choice-card').forEach(card => card.addEventListener('click',()=>{
    const parent=card.closest('.option-cards') || card.parentElement;
    $$('.choice-card',parent).forEach(x=>x.classList.remove('selected'));
    card.classList.add('selected');
  }));
  $$('.seg-row').forEach(group => $$('label',group).forEach(btn => btn.addEventListener('click',()=>{
    $$('label',group).forEach(x=>x.classList.remove('active'));
    btn.classList.add('active');
  })));
})();
