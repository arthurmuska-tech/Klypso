/* KLYPSO V14.2 — tactile 160Hz-style interactions + scroll storytelling */
(() => {
  const root=document.documentElement;
  const body=document.body;
  const $=(s,p=document)=>p.querySelector(s);
  const $$=(s,p=document)=>[...p.querySelectorAll(s)];
  const get=(k,f='')=>{try{return localStorage.getItem(k)??f}catch{return f}};
  const set=(k,v)=>{try{localStorage.setItem(k,v)}catch{}};
  const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finePointer=matchMedia('(pointer:fine)').matches;

  // ---------- Material personalization ----------
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

  // ---------- Smooth scene entry ----------
  const scenes=$$('.dash-page > *, .pricing-v11-page > *, .project-create-page > *, .settings-page-v11 > *, .panel-v11, .quick-card, .activity-panel, .workflow-side, .upload-studio-card');
  scenes.forEach((el,i)=>{
    el.classList.add('v14-scroll-scene','v14-scene-enter');
    el.dataset.v14Depth=String(i%3);
  });

  // ---------- Scroll storytelling ----------
  // Objects enter from above as the visitor reaches the scene.
  const objects=$$('.quick-icon, .project-thumb, .drop-orb, .profile-avatar-big, .hero-actions, .usage-ring, .tip-card');
  objects.forEach((el,i)=>{
    el.classList.add('v14-scroll-object');
    if(i%2)el.classList.add('v14-object-late');
  });

  // Headings and short copy are progressively "written" as their scene enters.
  const writeTargets=$$('.dash-hero h1, .dash-hero p, .quick-card h2, .quick-card p, .panel-v11 h2, .panel-v11 h3, .settings-page-v11 h1, .settings-card-v11 h2, .pricing-v11-page h1');
  writeTargets.forEach(el=>{
    if(el.children.length===0)el.classList.add('v14-write-target');
  });

  const metrics=scenes.map(el=>({el}));
  const updateChoreography=()=>{
    const vh=innerHeight;
    metrics.forEach(({el})=>{
      const r=el.getBoundingClientRect();
      const center=vh*.62;
      const distance=Math.abs(r.top-center);
      const inRange=Math.max(0,Math.min(1,1-distance/(vh*.72)));
      el.style.setProperty('--scene-progress',(inRange*100).toFixed(1));
      if(r.top<vh*.92&&r.bottom>vh*.08)el.classList.add('v14-inview');
    });

    objects.forEach(el=>{
      const r=el.getBoundingClientRect();
      const p=Math.max(0,Math.min(1,(vh-r.top)/(vh*.72)));
      if(r.top<vh*.86&&r.bottom>vh*.14){
        el.classList.add('v14-object-in');
        el.style.setProperty('--object-progress',(p*100).toFixed(1));
      }
    });

    writeTargets.forEach(el=>{
      const r=el.getBoundingClientRect();
      const p=Math.max(0,Math.min(1,(vh*.84-r.top)/(vh*.62)));
      // Once the text is well inside the viewport it is fully written.
      const progress=Math.max(0,Math.min(100,p*115));
      el.style.setProperty('--write-progress',progress.toFixed(1));
    });
  };

  if(reduced){
    scenes.forEach(el=>el.classList.add('v14-inview'));
    objects.forEach(el=>el.classList.add('v14-object-in'));
    writeTargets.forEach(el=>el.style.setProperty('--write-progress','100'));
  }else{
    let ticking=false;
    addEventListener('scroll',()=>{
      if(ticking)return;
      ticking=true;
      requestAnimationFrame(()=>{updateChoreography();ticking=false;});
    },{passive:true});
    addEventListener('resize',updateChoreography,{passive:true});
    updateChoreography();
  }

  // ---------- Buttons: tactile feedback / high-refresh feel ----------
  // Uses requestAnimationFrame and a tiny spring-like lift instead of heavy effects.
  const clickable=$$('.button,.icon-button,.topbar-plan,.topbar-avatar,.v14-wood-option,.choice-card,.seg-btn,.sidebar-nav a');
  clickable.forEach(el=>{
    el.addEventListener('pointerdown',e=>{
      if(e.button!==0)return;
      const r=el.getBoundingClientRect();
      el.style.setProperty('--ripple-x',((e.clientX-r.left)/r.width*100)+'%');
      el.style.setProperty('--ripple-y',((e.clientY-r.top)/r.height*100)+'%');
      el.classList.remove('v14-ripple-active');
      void el.offsetWidth;
      el.classList.add('v14-ripple-active');
    });
    el.addEventListener('animationend',()=>el.classList.remove('v14-ripple-active'));
  });

  // Add a quiet hover line to major action buttons.
  $$('.button,.quick-card').forEach(el=>{
    if(!el.querySelector('.v14-hover-line')){
      const line=document.createElement('span');
      line.className='v14-hover-line';
      line.setAttribute('aria-hidden','true');
      el.appendChild(line);
    }
  });

  // ---------- Pointer depth ----------
  if(!reduced&&finePointer){
    const glow=document.createElement('div');
    glow.className='v14-cursor-glow';
    body.appendChild(glow);
    let tx=innerWidth/2,ty=innerHeight/2,cx=tx,cy=ty;
    addEventListener('pointermove',e=>{tx=e.clientX;ty=e.clientY},{passive:true});
    const follow=()=>{
      cx+=(tx-cx)*.11;
      cy+=(ty-cy)*.11;
      glow.style.left=cx+'px';
      glow.style.top=cy+'px';
      requestAnimationFrame(follow);
    };
    follow();

    $$('.button,.quick-card,.choice-card,.seg-btn').forEach(el=>{
      el.addEventListener('pointermove',e=>{
        const r=el.getBoundingClientRect();
        const x=(e.clientX-r.left)/r.width-.5;
        const y=(e.clientY-r.top)/r.height-.5;
        el.style.transform='translate3d('+x*3+'px,'+y*2+'px,0) translateY(-2px)';
      });
      el.addEventListener('pointerleave',()=>{el.style.transform=''});
    });
  }

  // ---------- Navigation chrome ----------
  const progress=document.createElement('div');
  progress.className='v14-progress';
  body.appendChild(progress);

  const back=document.createElement('button');
  back.className='v14-scroll-top';
  back.type='button';
  back.textContent='↑';
  back.setAttribute('aria-label','Retour en haut');
  body.appendChild(back);

  const updateProgress=()=>{
    const max=document.documentElement.scrollHeight-innerHeight;
    progress.style.width=(max>0?Math.min(100,scrollY/max*100):0)+'%';
    back.classList.toggle('show',scrollY>650);
  };
  addEventListener('scroll',updateProgress,{passive:true});
  updateProgress();
  back.addEventListener('click',()=>scrollTo({top:0,behavior:'smooth'}));

  let lastY=scrollY,headerTick=false;
  addEventListener('scroll',()=>{
    if(headerTick)return;
    headerTick=true;
    requestAnimationFrame(()=>{
      const header=$('.app-topbar');
      const y=scrollY;
      if(header&&y>100)header.style.transform=y>lastY+3?'translateY(-100%)':'translateY(0)';
      lastY=y;
      headerTick=false;
    });
  },{passive:true});

  // ---------- Motion preference ----------
  const applyMotion=enabled=>body.classList.toggle('v14-no-motion',!enabled);
  applyMotion(get('klypso.motion','1')!=='0');
  $$('[data-setting="motion"]').forEach(input=>input.addEventListener('change',()=>{
    set('klypso.motion',input.checked?'1':'0');
    applyMotion(input.checked);
  }));

  // Existing controls remain functional.
  $$('.choice-card').forEach(card=>card.addEventListener('click',()=>{
    const group=card.closest('.option-cards');
    $$('.choice-card',group||document).forEach(x=>x.classList.remove('selected'));
    card.classList.add('selected');
  }));

  $$('.seg-row').forEach(group=>$$('label',group).forEach(btn=>btn.addEventListener('click',()=>{
    $$('label',group).forEach(x=>x.classList.remove('active'));
    btn.classList.add('active');
  })));

  addEventListener('keydown',e=>{
    if(['INPUT','TEXTAREA','SELECT'].includes(document.activeElement?.tagName))return;
    if(e.key.toLowerCase()==='n')$('[href*="/clips/create"]')?.click();
    if(e.key==='/'){$('[data-search-open]')?.click();e.preventDefault();}
  });
})();
