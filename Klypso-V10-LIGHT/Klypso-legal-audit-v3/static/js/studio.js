(() => {
  const input = document.getElementById('ai-video-input');
  const fileLabel = document.getElementById('ai-file-label');
  const runButton = document.getElementById('run-ai-edit');
  const progress = document.getElementById('ai-progress');
  const result = document.getElementById('ai-result');
  const status = document.getElementById('ai-status');
  const percent = document.getElementById('ai-percent');
  const bar = document.getElementById('ai-progress-bar');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

  document.querySelectorAll('[data-studio-action="manual-focus"]').forEach(btn => btn.addEventListener('click', () => {
    document.getElementById('manual-editor')?.scrollIntoView({behavior: 'smooth', block: 'start'});
  }));

  document.querySelectorAll('[data-tool]').forEach(btn => btn.addEventListener('click', () => {
    document.querySelectorAll('[data-tool]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
  }));

  document.querySelectorAll('.seg-btn, .pill-v9').forEach(btn => btn.addEventListener('click', () => {
    const group = btn.parentElement;
    group?.querySelectorAll('.seg-btn, .pill-v9').forEach(x => x.classList.remove('active'));
    btn.classList.add('active');
  }));

  document.querySelectorAll('.play-btn').forEach(btn => btn.addEventListener('click', () => {
    btn.classList.toggle('playing');
    btn.textContent = btn.classList.contains('playing') ? 'Ⅱ' : '▶';
  }));

  input?.addEventListener('change', () => {
    const file = input.files?.[0];
    if (fileLabel) fileLabel.textContent = file ? file.name : 'Choisir une vidéo source';
  });

  const setStep = (name) => document.querySelectorAll('[data-ai-step]').forEach(el => {
    el.classList.toggle('done', el.dataset.aiStep === name);
  });
  const setProgress = (value, text) => {
    if (progress) progress.hidden = false;
    if (bar) bar.style.width = `${value}%`;
    if (percent) percent.textContent = `${value}%`;
    if (status) status.textContent = text;
  };

  runButton?.addEventListener('click', async () => {
    const file = input?.files?.[0];
    if (!file) { input?.focus(); return; }

    runButton.disabled = true;
    result.hidden = true;
    setProgress(6, 'Import de la vidéo…');
    setStep('analyze');

    const form = new FormData();
    form.append('video', file);
    form.append('remove_silence', document.getElementById('ai-silence')?.checked ? '1' : '0');
    form.append('normalize_audio', document.getElementById('ai-audio')?.checked ? '1' : '0');
    form.append('prepare_captions', document.getElementById('ai-captions')?.checked ? '1' : '0');
    if (csrf) form.append('csrf_token', csrf);

    try {
      setProgress(18, 'Analyse du fichier…');
      setStep('analyze');
      const response = await fetch('/studio/ai-edit', {method: 'POST', body: form, credentials: 'same-origin'});
      setProgress(62, 'Rendu vidéo en cours…');
      setStep('cleanup');
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Le montage n’a pas pu être créé.');

      setProgress(86, 'Finalisation du rendu…');
      setStep('render');
      result.innerHTML = `<div class="ai-result-head-v9"><span class="mode-icon-v9 success">✓</span><div><b>Première version créée</b><small>${data.duration_label || ''} · ${data.operations?.join(' · ') || 'Traitements appliqués'}</small></div></div><div class="ai-result-actions-v9"><a class="button" href="${data.download_url}">Télécharger le MP4 →</a><button class="button ghost" type="button" data-continue-editor>Continuer dans Studio</button></div>`;
      result.hidden = false;
      result.querySelector('[data-continue-editor]')?.addEventListener('click', () => document.getElementById('manual-editor')?.scrollIntoView({behavior:'smooth'}));
      setProgress(100, 'Montage prêt.');
      setStep('render');
    } catch (error) {
      result.innerHTML = `<div class="ai-error-v9"><b>Le rendu n’a pas pu être terminé.</b><span>${error.message}</span></div>`;
      result.hidden = false;
      setProgress(100, 'Erreur');
    } finally {
      runButton.disabled = false;
    }
  });
})();
