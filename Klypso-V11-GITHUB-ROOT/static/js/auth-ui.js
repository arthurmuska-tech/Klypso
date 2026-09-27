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

  const googleWrap = document.querySelector('[data-google-signin]');
  const googleButton = document.querySelector('[data-google-button]');
  const googleStatus = document.querySelector('[data-google-status]');

  function setGoogleState(loading, message = '') {
    if (googleWrap) {
      googleWrap.toggleAttribute('aria-busy', Boolean(loading));
      googleWrap.classList.toggle('is-loading', Boolean(loading));
    }
    if (googleStatus) googleStatus.textContent = message;
  }

  window.handleGoogleCredential = async (response) => {
    const credential = response?.credential;
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    if (!credential) {
      setGoogleState(false, 'Google n’a pas renvoyé de jeton.');
      return;
    }

    setGoogleState(true, '');

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
      setGoogleState(false, error?.message || 'Connexion Google impossible.');
    }
  };

  let googleInitialized = false;
  let attempts = 0;

  function initGoogle() {
    if (googleInitialized || !googleButton || !googleWrap) return true;

    const clientId = googleWrap.dataset.googleClientId || '';
    const googleId = window.google?.accounts?.id;
    if (!clientId || !googleId) return false;

    googleInitialized = true;
    googleId.initialize({
      client_id: clientId,
      context: 'signin',
      ux_mode: 'popup',
      auto_select: false,
      use_fedcm_for_button: true,
      callback: window.handleGoogleCredential
    });
    googleId.renderButton(googleButton, {
      type: 'standard',
      theme: 'outline',
      size: 'large',
      text: 'continue_with',
      shape: 'rectangular',
      logo_alignment: 'left',
      width: Math.min(380, Math.max(260, googleWrap.clientWidth || 380))
    });
    return true;
  }

  function waitForGoogle() {
    if (initGoogle()) return;
    attempts += 1;
    if (attempts < 120) {
      window.setTimeout(waitForGoogle, 100);
    } else {
      setGoogleState(false, 'Le service Google n’a pas pu être chargé. Réessaie dans un instant.');
    }
  }

  if (googleWrap) {
    waitForGoogle();
    window.addEventListener('load', initGoogle, { once: true });
  }
})();