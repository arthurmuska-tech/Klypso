(() => {
  const tabs = document.querySelectorAll('.billing-tab');
  const monthly = document.querySelectorAll('.price-monthly');
  const annual = document.querySelectorAll('.price-annual');
  const inputs = document.querySelectorAll('[data-billing-input]');
  const buttons = document.querySelectorAll('[data-plan-button]');
  const note = document.querySelector('[data-annual-note]');

  function apply(interval) {
    const isAnnual = interval === 'annual';
    tabs.forEach(t => t.classList.toggle('active', t.dataset.billing === interval));
    monthly.forEach(el => { el.hidden = isAnnual; });
    annual.forEach(el => { el.hidden = !isAnnual; });
    inputs.forEach(input => { input.value = interval; });
    buttons.forEach(btn => {
      const ready = isAnnual ? btn.dataset.annualReady === 'true' : btn.dataset.monthlyReady === 'true';
      btn.disabled = !ready;
      if (isAnnual && !ready) btn.textContent = 'Annuel à configurer';
      else if (!isAnnual) btn.textContent = btn.closest('.ultra-price') ? 'Choisir Ultra →' : 'Choisir Pro →';
      else btn.textContent = btn.closest('.ultra-price') ? 'Choisir Ultra annuel →' : 'Choisir Pro annuel →';
    });
    if (note) note.textContent = isAnnual
      ? 'Les boutons annuels restent désactivés tant que leurs vrais Price IDs Stripe ne sont pas configurés.'
      : 'Passe en annuel pour afficher la configuration tarifaire correspondante.';
  }
  tabs.forEach(tab => tab.addEventListener('click', () => apply(tab.dataset.billing)));
  apply('monthly');
})();
