/* KLYPSO V14.1 — cinematic scroll + material personalization */
(() => {
  const root=document.documentElement;
  const body=document.body;
  const $=(s,p=document)=>p.querySelector(s);
  const $$=(s,p=document)=>[...p.querySelectorAll(s)];
  const get=(k,f='')=>{try{return localStorage.getItem(k)??f}catch{return f}};
  const set=(k,v)=>{try{localStorage.setItem(k,v)}catch{}};
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Material themes. The UI remains the same; only the atmosphere changes.
  const wood=get('klypso.wood','oak');
  root.dataset.wood=wood;
  $$('[data-wood]').forEach(b=>b.classList.toggle('selected',b.dataset.wood===wood));
  $$('[data-wood]').forEach(button=>button.addEventListener('click',()=>{
    const value=button.dataset.wood;
    if(!value)return;
    root.dataset.wood=value;
    set('klypso.wood',value);
    $$('[data-wood]').forEach(x=>x.classList.toggle('selected',x.dataset.wood===value));
  }));

  // Cinematic scroll: sections feel like scenes transitioning into one another.
  const scenes=$$('.dash-page > *, .pricing-v11-page > *, .project-create-page > *, .settings-page-v11 > *, .panel-v11, .quick-card, .activity-panel, .workflow-side, .upload-studio-card');
  scenes.forEach((el,i)=>{
    el.classList.add('v14-scroll-scene');
    el.dataset.v14Depth=String(i%3);
  });

  const observeScene=()=>{
    if(reduced){scenes.forEach(el=>el.classList.add('v14-inview'));return;}
    if('IntersectionObserver' in window){
      const io=new IntersectionObserver(entries=>{
        entries.forEach(entry=>{
          if(entry.isIntersecting) entry.target.classList.add('v14-inview');
          else if(entry.boundingClientRect.top>innerHeight) entry.target.classList.remove('v14-inview');
        });
      },{threshold:.08,rootMargin:'-7% 0px -10% 0px'});
      scenes.forEach(el=>io.observe(el));
    }else scenes.forEach(el=>el.classList.add('v14-inview'));
  };
  observeScene();

  // Smooth progress indicator.
  const progress=document.createElement('div');progress.className='v14-progress';body.appendChild(progress);
  const back=document.createElement('button');back.className='v14-scroll-top';back.type='button';back.textContent='↑';back.setAttribute('aria-label','Retour en haut');body.appendChild(back);
  const update=()=>{
    const max=document.documentElement.scrollHeight-innerHeight;
    progress.style.width=(max>0?Math.min(100,scrollY/max*100):0)+'%';
    back.classList.toggle('show',scrollY>650);
  };
  addEventListener('scroll',update,{passive:true});update();
  back.addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));

  // Intelligent chrome: top bar gently leaves the stage while scrolling down.
  let lastY=scrollY, ticking=false;
  addEventListener('scroll',()=>{
    if(ticking)return;
    ticking=true;
    requestAnimationFrame(()=>{
      const y=scrollY,header=$('.app-topbar');
      if(header&&y>100) header.style.transform=y>lastY+3?'translateY(-100%)':'translateY(0)';
      lastY=y;ticking=false;
    });
  },{passive:true});

  // Mouse depth: tiny magnetic movement, no exaggerated 3D.
  if(!reduced && matchMedia('(pointer:fine)').matches){
    const glow=document.createElement('div');glow.className='v14-cursor-glow';body.appendChild(glow);
    let tx=0,ty=0,cx=0,cy=0;
    addEventListener('pointermove',e=>{tx=e.clientX;ty=e.clientY},{passive:true});
    const animate=()=>{cx+=(tx-cx)*.08;cy+=(ty-cy)*.08;glow.style.left=cx+'px';glow.style.top=cy+'px';requestAnimationFrame(animate)};animate();
    $$('.button,.quick-card,.choice-card,.seg-btn').forEach(el=>{
      el.addEventListener('pointermove',e=>{
        const r=el.getBoundingClientRect(),x=(e.clientX-r.left)/r.width-.5,y=(e.clientY-r.top)/r.height-.5;
        el.style.transform='translate('+x*3+'px,'+y*2+'px) translateY(-2px)';
      });
      el.addEventListener('pointerleave',()=>{el.style.transform=''});
    });
  }

  if(get('klypso.motion','1')==='0')body.classList.add('v14-no-motion');
  $$('[data-setting="motion"]').forEach(input=>input.addEventListener('change',()=>{body.classList.toggle('v14-no-motion',!input.checked);}));

  // Existing V11 controls remain active.
  $$('.choice-card').forEach(card=>card.addEventListener('click',()=>{$$('.choice-card').forEach(x=>x.classList.remove('selected'));card.classList.add('selected')}));
  $$('.seg-row').forEach(group=>$$('label',group).forEach(btn=>btn.addEventListener('click',()=>{$$('label',group).forEach(x=>x.classList.remove('active'));btn.classList.add('active')})));
})();
