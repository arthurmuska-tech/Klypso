(() => {
  'use strict';
  const buttons = Array.from(document.querySelectorAll('[data-demo-tab]'));
  const panels = Array.from(document.querySelectorAll('[data-demo-panel]'));
  buttons.forEach((button) => button.addEventListener('click', () => {
    const name = button.dataset.demoTab;
    buttons.forEach((item) => item.classList.toggle('active', item === button));
    panels.forEach((panel) => panel.classList.toggle('active', panel.dataset.demoPanel === name));
  }));
})();
