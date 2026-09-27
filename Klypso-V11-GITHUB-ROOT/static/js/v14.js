/* KLYPSO V15.0 — stable workspace + cinematic home */
(() => {
  'use strict';
  const root=document.documentElement, body=document.body;
  const $$=(s,p=document)=>[...p.querySelectorAll(s)];
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const storage={get(k,f){try{const v=localStorage.getItem(k);return v===null?f:v}catch{return f}},set(k,v){try{localStorage.setItem(k,v)}catch{}}};

  /* Material personalization */
  const woods=['oak','walnut','birch','cherry','ebony'];
  function applyWood(value){
    if(!woods.includes(value)) value='oak';
    root.dataset.wood=value; storage.set('klypso.wood',value);
    const savedAccent=storage.get('klypso.accent','');
    if(/^#[0-9a-fA-F]{6}$/.test(savedAccent)){
      root.style.setProperty('--accent',savedAccent);
      root.style.setProperty('--k-accent',savedAccent);
      const a2={ '#9b7bff':'#c5b7ff','#63a4ff':'#9dc6ff','#59e6df':'#8af4ed','#ff76c8':'#ff9edb','#d59a62':'#efbdad' }[savedAccent] || savedAccent;
      root.style.setProperty('--k-accent-2',a2);
      root.style.setProperty('--k-accent-soft','color-mix(in srgb, '+savedAccent+' 14%, transparent)');
    } else {
      root.style.removeProperty('--k-accent');
      root.style.removeProperty('--k-accent-2');
      root.style.removeProperty('--k-accent-soft');
    }
    $$('[data-wood]').forEach(el=>{const on=el.dataset.wood===value;el.classList.toggle('selected',on);el.setAttribute('aria-pressed',String(on));});
    const meta=document.querySelector('meta[name="theme-color"]');
    if(meta) meta.content={oak:'#f3efe8',walnut:'#241c18',birch:'#f7f5ef',cherry:'#f5e8e2',ebony:'#111315'}[value];
  }
  applyWood(storage.get('klypso.wood','oak'));
  $$('[data-wood]').forEach(el=>el.addEventListener('click',()=>applyWood(el.dataset.wood)));

  /* Never hijack wheel/scroll. The page must always keep native scrolling. */
  root.style.scrollBehavior='auto';
  body.style.overscrollBehaviorY='auto';
  body.style.overflowY='visible';

  /* Generic reveal: IntersectionObserver is the fallback-safe animation layer. */
  const reveal=$$('.home-feature,.home-intro,.home-capabilities,.capability-grid > div,.home-library,.dash-hero,.quick-card,.panel-v11,.settings-card-v11,.project-row');
  reveal.forEach((el,i)=>{el.classList.add('v14-reveal');el.style.setProperty('--reveal-delay',Math.min(i*35,280)+'ms');});
  if(!reduced && 'IntersectionObserver' in window){
    const io=new IntersectionObserver(entries=>{
      entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('v14-visible');io.unobserve(e.target);}});
    },{threshold:.12,rootMargin:'0px 0px -8% 0px'});
    reveal.forEach(el=>io.observe(el));
  }else reveal.forEach(el=>el.classList.add('v14-visible'));

  /* Cinematic sticky story: scroll remains completely native. */
  const story=document.querySelector('.home-story');
  const steps=$$('.story-step');
  const visuals=$$('.story-visual');
  function updateStory(){
    if(!story||!steps.length) return;
    const r=story.getBoundingClientRect(), travel=Math.max(1,story.offsetHeight-window.innerHeight);
    const p=Math.max(0,Math.min(0.999,(window.innerHeight-r.top)/Math.max(1,window.innerHeight+travel)));
    const index=Math.min(steps.length-1,Math.floor(p*steps.length));
    steps.forEach((el,i)=>el.classList.toggle('is-active',i===index));
    visuals.forEach((el,i)=>{
      const active=i===index;
      el.classList.toggle('is-active',active);
      const local=Math.max(0,Math.min(1,(p*steps.length)-i));
      const phase=p*(steps.length-1);
      const distance=(i-phase)*128;
      const scale=active?1:0.9;
      const opacity=Math.max(.06,1-Math.abs(i-phase)*.72);
      const tilt=i<phase?-5:i>phase?5:0;
      el.style.transform='translate3d('+distance+'%, '+((1-local)*22)+'px, 0) rotate('+tilt+'deg) scale('+scale+')';
      el.style.opacity=opacity;
    });
    story.style.setProperty('--story-progress',(p*100).toFixed(2)+'%');
  }
  let storyRaf=0;
  function onScroll(){
    if(!storyRaf) storyRaf=requestAnimationFrame(()=>{storyRaf=0;updateStory();updateChrome();});
  }
  addEventListener('scroll',onScroll,{passive:true});
  addEventListener('resize',onScroll,{passive:true});
  updateStory();

  /* Fast tactile feedback without pretending to change the monitor refresh rate. */
  $$('.button,.icon-button,.topbar-plan,.topbar-avatar,.v14-wood-option,.choice-card,.seg-btn,.sidebar-nav a').forEach(el=>{
    el.addEventListener('pointerdown',e=>{
      if(e.pointerType==='mouse'&&e.button!==0)return;
      const r=el.getBoundingClientRect();
      el.style.setProperty('--ripple-x',((e.clientX-r.left)/Math.max(1,r.width)*100)+'%');
      el.style.setProperty('--ripple-y',((e.clientY-r.top)/Math.max(1,r.height)*100)+'%');
      el.classList.remove('v14-ripple-active'); void el.offsetWidth; el.classList.add('v14-ripple-active');
    },{passive:true});
  });

  const progressBar=document.createElement('div');progressBar.className='v14-progress';body.appendChild(progressBar);
  const backTop=document.createElement('button');backTop.className='v14-scroll-top';backTop.type='button';backTop.textContent='↑';backTop.setAttribute('aria-label','Retour en haut');body.appendChild(backTop);
  let lastY=window.scrollY,chromeRaf=0;
  function updateChrome(){
    const max=Math.max(1,document.documentElement.scrollHeight-innerHeight);
    progressBar.style.width=Math.min(100,window.scrollY/max*100)+'%';
    backTop.classList.toggle('show',window.scrollY>600);
    const header=document.querySelector('.app-topbar');
    if(header && window.scrollY>110) header.style.transform=window.scrollY>lastY+4?'translateY(-100%)':'translateY(0)';
    lastY=window.scrollY;chromeRaf=0;
  }
  function requestChrome(){if(!chromeRaf)chromeRaf=requestAnimationFrame(updateChrome)}
  addEventListener('scroll',requestChrome,{passive:true});updateChrome();
  backTop.addEventListener('click',()=>window.scrollTo({top:0,behavior:'smooth'}));

  /* Motion preference */
  /* V14.5: animations are enabled by default. Only an explicit user choice can disable them. */
  const saved=storage.get('klypso.motion','1');
  function setMotion(enabled){body.classList.toggle('v14-no-motion',!enabled);storage.set('klypso.motion',enabled?'1':'0');}
  setMotion(saved!=='0');
  $$('[data-setting="motion"]').forEach(input=>input.addEventListener('change',()=>setMotion(input.checked)));

  $$('.choice-card').forEach(card=>card.addEventListener('click',()=>{
    const parent=card.closest('.option-cards')||card.parentElement;
    $$('.choice-card',parent).forEach(x=>x.classList.remove('selected'));card.classList.add('selected');
  }));
  $$('.seg-row').forEach(group=>$$('label',group).forEach(btn=>btn.addEventListener('click',()=>{
    $$('label',group).forEach(x=>x.classList.remove('active'));btn.classList.add('active');
  }));
})();