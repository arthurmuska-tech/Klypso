(() => {
  'use strict';
  const button = document.querySelector('[data-copy-callback]');
  button?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copyCallback);
      const original = button.textContent;
      button.textContent = 'Copié ✓';
      setTimeout(() => { button.textContent = original; }, 1400);
    } catch (_) {
      button.textContent = 'Copie manuelle';
      setTimeout(() => { button.textContent = 'Copier le callback'; }, 1500);
    }
  });
})();
