(() => {
  'use strict';
  document.documentElement.classList.add('v24-motion-ready');
  const $$ = (s, root=document) => Array.from(root.querySelectorAll(s));

  const reveals = $$('.v24-reveal');
  if ('IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('v24-visible');
          observer.unobserve(entry.target);
        }
      });
    }, {threshold:.12, rootMargin:'0px 0px -6% 0px'});
    reveals.forEach((el) => observer.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add('v24-visible'));
  }

  const tilt = document.querySelector('[data-v24-tilt]');
  if (tilt && !matchMedia('(pointer: coarse)').matches && !matchMedia('(prefers-reduced-motion: reduce)').matches) {
    const win = tilt.querySelector('.v24-window');
    tilt.addEventListener('pointermove', (event) => {
      const r = tilt.getBoundingClientRect();
      const x = ((event.clientX-r.left)/Math.max(1,r.width))-.5;
      const y = ((event.clientY-r.top)/Math.max(1,r.height))-.5;
      win.style.setProperty('--v24-ry',(x*4.5).toFixed(2)+'deg');
      win.style.setProperty('--v24-rx',(y*-3.2).toFixed(2)+'deg');
    }, {passive:true});
    tilt.addEventListener('pointerleave', () => {
      win.style.setProperty('--v24-ry','0deg');
      win.style.setProperty('--v24-rx','0deg');
    });
  }
})();