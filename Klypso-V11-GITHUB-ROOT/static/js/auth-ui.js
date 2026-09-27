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

  window.handleGoogleCredential = async (response) => {
    const credential = response?.credential;
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    if (!credential) return;

    const buttons = document.querySelectorAll('[data-google-signin]');
    buttons.forEach((el) => {
      el.setAttribute('aria-busy', 'true');
      el.classList.add('is-loading');
    });

    try {
      const result = await fetch('/oauth/google/credential', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrf
        },
        credentials: 'same-origin',
        body: JSON.stringify({ credential })
      });
      const data = await result.json().catch(() => ({}));
      if (!result.ok || !data.ok) {
        throw new Error(data.error || 'Connexion Google impossible.');
      }
      window.location.assign(data.redirect || '/dashboard');
    } catch (error) {
      buttons.forEach((el) => {
        el.removeAttribute('aria-busy');
        el.classList.remove('is-loading');
        const status = el.querySelector('[data-google-status]');
        if (status) status.textContent = error.message;
      });
    }
  };
})();
