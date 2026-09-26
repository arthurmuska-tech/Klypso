(function(){
  const root=document.documentElement;
  const $=(s,p=document)=>p.querySelector(s);
  const $$=(s,p=document)=>Array.from(p.querySelectorAll(s));
  const get=(k,f='')=>{try{return localStorage.getItem(k)??f}catch{return f}};
  const set=(k,v)=>{try{localStorage.setItem(k,v)}catch{}};

  const accent=get('klypso.accent','#9b7bff');
  const theme={"#63a4ff":"blue","#59e6df":"cyan","#ff76c8":"pink"}[accent]||'violet';
  root.dataset.theme=theme;
  root.dataset.density=get('klypso.density','comfortable');
  root.dataset.radius=get('klypso.radius','round');
  root.style.setProperty('--accent',accent);

  const path=location.pathname;
  $$('.sidebar-nav a[data-nav]').forEach(a=>{const n=a.dataset.nav;let active=(n==='dashboard'&&path==='/dashboard')||(n==='clips'&&path==='/clips')||(n==='new'&&path==='/clips/create')||(n==='studio'&&path==='/studio')||(n==='brand'&&path==='/brand-kit')||(n==='billing'&&(path==='/pricing'||path==='/subscription'))||(n==='account'&&path==='/account');a.classList.toggle('active',active)});

  const sidebar=$('#app-sidebar');
  $('[data-sidebar-open]')?.addEventListener('click',()=>sidebar?.classList.add('open'));
  $('[data-sidebar-close]')?.addEventListener('click',()=>sidebar?.classList.remove('open'));

  $$('.swatch-v11[data-accent], [data-accent]').forEach(b=>b.addEventListener('click',()=>{
    const c=b.dataset.accent;root.style.setProperty('--accent',c);root.dataset.theme={"#63a4ff":"blue","#59e6df":"cyan","#ff76c8":"pink"}[c]||'violet';set('klypso.accent',c);
    $$('[data-accent]').forEach(x=>x.classList.toggle('selected',x.dataset.accent===c));
    const out=$('[data-live-accent]');if(out)out.textContent=c.toUpperCase();
  }));
  $$('.segmented-v11[data-setting-group], [data-setting-group]').forEach(group=>{
    $$('button',group).forEach(btn=>btn.addEventListener('click',()=>{
      $$('button',group).forEach(x=>x.classList.remove('selected','active'));btn.classList.add('selected','active');
      const g=group.dataset.settingGroup;if(g==='density'){root.dataset.density=btn.dataset.value;set('klypso.density',btn.dataset.value);const o=$('[data-live-density]');if(o)o.textContent=btn.textContent.trim()}if(g==='radius'){root.dataset.radius=btn.dataset.value;set('klypso.radius',btn.dataset.value)}
    }));
  });
  $$('.caption-style-card,[data-caption]').forEach(btn=>btn.addEventListener('click',()=>{const c=btn.dataset.caption;if(!c)return;set('klypso.caption',c);$$('[data-caption]').forEach(x=>x.classList.toggle('selected',x.dataset.caption===c));const o=$('[data-live-caption]');if(o)o.textContent=c[0].toUpperCase()+c.slice(1)}));
  $$('[data-setting="watermark"],[data-setting="motion"]').forEach(input=>{const k='klypso.'+input.dataset.setting;input.checked=get(k,'1')!=='0';input.addEventListener('change',()=>set(k,input.checked?'1':'0'))});
  const dn=$('[data-setting="displayName"]');if(dn)dn.value=get('klypso.displayName','Ton créateur');
  $('[data-save-settings]')?.addEventListener('click',()=>{set('klypso.displayName',(dn?.value||'').trim()||'Ton créateur');const o=$('[data-preview-name]');if(o)o.textContent=get('klypso.displayName','Ton créateur')});
  const pn=$('[data-preview-name]');if(pn)pn.textContent=get('klypso.displayName','Ton créateur');
  $('[data-brand-reset]')?.addEventListener('click',()=>{['klypso.accent','klypso.density','klypso.radius','klypso.caption','klypso.displayName','klypso.watermark','klypso.motion'].forEach(k=>{try{localStorage.removeItem(k)}catch{}});location.reload()});
  $$('.choice-card').forEach(card=>{card.addEventListener('click',()=>{$$('.choice-card').forEach(x=>x.classList.remove('selected'));card.classList.add('selected')})});
  $$('.seg-row').forEach(group=>$$('button',group).forEach(btn=>btn.addEventListener('click',()=>{$$('button',group).forEach(x=>x.classList.remove('active'));btn.classList.add('active')})));
  $$('.tab-btn').forEach(btn=>btn.addEventListener('click',()=>{$$('.tab-btn').forEach(x=>x.classList.remove('active'));btn.classList.add('active');const state=btn.dataset.listTab;$$('.clip-project-card').forEach(card=>card.style.display=(state==='all'||(state==='ready'&&/completed|done|ready/.test(card.dataset.status))||(state==='processing'&&/processing|running/.test(card.dataset.status)))?'':'none')}));
  $$('.editor-tool').forEach(btn=>btn.addEventListener('click',()=>{$$('.editor-tool').forEach(x=>x.classList.remove('active'));btn.classList.add('active');const name=btn.dataset.tool;const tab=name==='captions'?'captions':name==='brand'?'brand':'properties';$$('.inspector-tab').forEach(x=>x.classList.toggle('active',x.dataset.inspectorTab===tab));$$('.inspector-content').forEach(x=>x.classList.add('hidden'));$('#inspector-'+tab)?.classList.remove('hidden')}));
  $$('.inspector-tab').forEach(btn=>btn.addEventListener('click',()=>{const tab=btn.dataset.inspectorTab;$$('.inspector-tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active');$$('.inspector-content').forEach(x=>x.classList.add('hidden'));$('#inspector-'+tab)?.classList.remove('hidden')}));
  $$('.ratio-grid button').forEach(btn=>btn.addEventListener('click',()=>{const r=btn.dataset.ratio;$$('.ratio-grid button').forEach(x=>x.classList.remove('active'));btn.classList.add('active');const f=$('.video-frame');if(f)f.style.aspectRatio=r.replace(':','/');const top=$('[data-format-button]');if(top)top.textContent=r+' ▾'}));
  $$('.canvas-tab').forEach(btn=>btn.addEventListener('click',()=>{$$('.canvas-tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active')}));
  $$('.caption-style').forEach(btn=>btn.addEventListener('click',()=>{$$('.caption-style').forEach(x=>x.classList.remove('active'));btn.classList.add('active')}));
  $$('.timeline-clip').forEach(clip=>clip.addEventListener('click',()=>{$$('.timeline-clip').forEach(x=>x.style.outline='none');clip.style.outline='1px solid var(--accent)'}));
  let zoom=100;$('[data-zoom-in]')?.addEventListener('click',()=>{zoom=Math.min(160,zoom+10);const z=$('#zoom-label');if(z)z.textContent=zoom+'%'});$('[data-zoom-out]')?.addEventListener('click',()=>{zoom=Math.max(50,zoom-10);const z=$('#zoom-label');if(z)z.textContent=zoom+'%'});
  let playing=false;$$('.play-btn').forEach(b=>b.addEventListener('click',()=>{playing=!playing;b.textContent=playing?'Ⅱ':'▶';b.classList.toggle('playing',playing)}));
  $('[data-studio-action="export"]')?.addEventListener('click',()=>{const toast=document.createElement('div');toast.className='v11-flash success';toast.innerHTML='<span>✓</span> Export configuré : choisis une source et lance le rendu IA pour produire un fichier.';$('#main-content')?.prepend(toast);setTimeout(()=>toast.remove(),4200)});
  $('[data-save-project]')?.addEventListener('click',()=>{const b=$('[data-save-project]');if(!b)return;const old=b.textContent;b.textContent='Enregistré ✓';setTimeout(()=>b.textContent=old,1500)});
})();
