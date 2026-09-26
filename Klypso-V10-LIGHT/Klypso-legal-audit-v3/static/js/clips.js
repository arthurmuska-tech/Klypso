(function () {
  const input = document.querySelector('#video');
  const fileName = document.querySelector('#file-name');
  if (input && fileName) input.addEventListener('change', () => { fileName.textContent = input.files?.[0]?.name || 'Aucun fichier sélectionné'; });
  window.KlypsoClips = { formatPotential: (value) => Math.round(Number(value) || 0) + ' / 100 — potentiel du moment' };
})();
