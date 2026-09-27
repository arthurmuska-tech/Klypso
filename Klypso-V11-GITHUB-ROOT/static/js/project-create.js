(() => {
  'use strict';
  const modeInput = document.getElementById('project-mode');
  const liveLabel = document.getElementById('mode-live-label');
  const explanation = document.getElementById('mode-explanation');
  const createButton = document.getElementById('create-project-btn');
  const input = document.getElementById('video');
  const name = document.getElementById('file-name');

  const modes = {
    ai_clips: {label:'IA · CLIPS', button:'Créer le projet IA', title:'Le moteur va apprendre de tes projets précédents.', body:'Historique, retours conserver/rejeter, durées et types de scènes servent à personnaliser la prochaine sélection.'},
    clip_only: {label:'STANDARD · CLIP', button:'Créer le projet clip', title:'Workflow simple.', body:'KLYPSO prépare un projet de clip sans scoring sémantique avancé.'},
    ai_montage: {label:'IA · MONTAGE', button:'Créer le projet IA', title:'Le moteur construit une structure de montage.', body:'Les scènes retenues sont ordonnées pour éviter les doublons et donner un rythme cohérent.'},
    montage_only: {label:'STANDARD · STUDIO', button:'Ouvrir le projet dans Studio', title:'Tu gardes le contrôle total.', body:'La source est enregistrée comme projet et pourra être reprise manuellement dans Studio.'}
  };

  document.querySelectorAll('[data-creation-mode]').forEach(card => {
    card.addEventListener('click', () => {
      const mode = card.dataset.creationMode;
      if (modeInput) modeInput.value = mode;
      document.querySelectorAll('[data-creation-mode]').forEach(item => item.classList.toggle('active', item === card));
      const config = modes[mode] || modes.ai_clips;
      if (liveLabel) liveLabel.textContent = config.label;
      if (createButton) createButton.innerHTML = config.button + ' <span>→</span>';
      if (explanation) explanation.innerHTML = '<strong>' + config.title + '</strong><span>' + config.body + '</span>';
    });
  });

  input?.addEventListener('change', () => {
    if (name) name.textContent = input.files?.[0]?.name || 'Dépose ta VOD ici';
  });
})();