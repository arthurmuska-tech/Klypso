/* KLYPSO V14 — motion, intelligent scrolling and personalization */
(() => {
  const root=document.documentElement;
  const $=(s,p=document)=>p.querySelector(s);
  const $$=(s,p=document)=>[...p.querySelectorAll(s)];
  const reduced=window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const candidates=$$('.dash-page > *, .pricing-v11-page > *, .project-create-page > *, .panel-v11, .quick-card, .activity-panel, .workflow-side, .upload-studio-card');
  candidates.forEach((el,i)=>{if(el.dataset.v14Reveal===undefined){el.dataset.v14Reveal='';el.dataset.v14Delay=String(Math.min(i%5,4));}});
  if(!reduced && 'IntersectionObserver' in window){
    const io=new IntersectionObserver(entries=>{entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('v14-visible');io.unobserve(e.target)}})},{threshold:.08,rootMargin:'0px 0px -50px'});
    $$('[data-v14-reveal]').forEach(el=>io.observe(el));
  } else $$('[data-v14-reveal]').forEach(el=>el.classList.add('v14-visible'));

  const bar=document.createElement('div');bar.className='v14-progress';document.body.appendChild(bar);
  const top=document.createElement('button');top.className='v14-scroll-top';top.type='button';top.textContent='↑';top.setAttribute('aria-label','Retour en haut');document.body.appendChild(top);
  const updateScroll=()=>{const max=document.documentElement.scrollHeight-innerHeight;bar.style.width=(max>0?Math.min(100,scrollY/max*100):0)+'%';top.classList.toggle('show',scrollY>650);};
  addEventListener('scroll',updateScroll,{passive:true});updateScroll();
  top.addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));

  let lastY=scrollY;
  addEventListener('scroll',()=>{
    const y=scrollY,header=$('.app-topbar');
    if(header&&y>120) header.style.transform=(y>lastY+4?'translateY(-100%)':'translateY(0)');
    if(header) header.style.transition='transform .35s cubic-bezier(.2,.8,.2,1)';
    lastY=y;
  },{passive:true});

  if(!reduced && matchMedia('(pointer:fine)').matches){
    const glow=document.createElement('div');glow.className='v14-cursor-glow';document.body.appendChild(glow);
    let tx=innerWidth/2,ty=innerHeight/2,cx=tx,cy=ty;
    addEventListener('pointermove',e=>{tx=e.clientX;ty=e.clientY},{passive:true});
    const tick=()=>{cx+=(tx-cx)*.12;cy+=(ty-cy)*.12;glow.style.left=cx+'px';glow.style.top=cy+'px';requestAnimationFrame(tick)};tick();
    $$('.button,.quick-card,.choice-card,.seg-btn,.icon-button').forEach(el=>{
      el.addEventListener('pointermove',e=>{
        const r=el.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
        el.style.transform='translate('+x*5+'px,'+y*4+'px) translateY(-2px)';
      });
      el.addEventListener('pointerleave',()=>{el.style.transform=''});
    });
  }

  if(!reduced)addEventListener('scroll',()=>{const hero=$('.dash-hero');if(hero){const y=Math.min(scrollY,500);hero.style.backgroundPosition='center '+y*.08+'px';}},{passive:true});

  addEventListener('keydown',e=>{
    if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName)) return;
    if(e.key.toLowerCase()==='n'){$('[href*="/clips/create"]')?.click();}
    if(e.key==='/'){$('[data-search-open]')?.click();e.preventDefault();}
  });

  if(localStorage.getItem('klypso.motion')==='0') root.classList.add('v14-no-motion');
  $$('[data-setting="motion"]').forEach(input=>input.addEventListener('change',()=>root.classList.toggle('v14-no-motion',!input.checked)));
})();
