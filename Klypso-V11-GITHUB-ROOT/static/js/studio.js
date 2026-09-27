(() => {
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));
  const input = document.getElementById('ai-video-input');
  const fileLabel = document.getElementById('ai-file-label');
  const runButton = document.getElementById('run-ai-edit');
  const progress = document.getElementById('ai-progress');
  const result = document.getElementById('ai-result');
  const status = document.getElementById('ai-status');
  const percent = document.getElementById('ai-percent');
  const bar = document.getElementById('ai-progress-bar');
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';

  const stateNode = document.getElementById('studio-state');
  const shell = document.querySelector('[data-studio-project-id]');
  const saveButton = document.querySelector('[data-save-project]');
  const saveState = document.getElementById('studio-save-state');
  const projectName = document.getElementById('studio-project-name');
  const initial = (() => {
    try { return JSON.parse(stateNode?.textContent || '{}'); } catch (_) { return {}; }
  })();
  let projectId = initial.project_id || shell?.dataset.studioProjectId || null;
  let projectState = initial.timeline || {clips: [], audio_tracks: [], markers: [], settings: {}};
  projectState.clips = Array.isArray(projectState.clips) ? projectState.clips : [];
  projectState.audio_tracks = Array.isArray(projectState.audio_tracks) ? projectState.audio_tracks : [];
  projectState.markers = Array.isArray(projectState.markers) ? projectState.markers : [];
  projectState.settings = (projectState.settings && typeof projectState.settings === 'object') ? projectState.settings : {};
  const undoStack = [];
  const redoStack = [];
  let saveTimer = null;

  const clone = value => JSON.parse(JSON.stringify(value));
  const clipPicker = document.getElementById('studio-clip-select');
  let selectedClipIndex = 0;
  const refreshClipPicker = () => {
    if (!clipPicker) return;
    clipPicker.innerHTML = projectState.clips.map((clip, index) =>
      '<option value="' + index + '">#' + (index + 1) + ' · ' + escapeHtml(clip.name || ('Clip ' + (index + 1))) + ' · ' + Number(clip.duration || 0).toFixed(1) + 's</option>'
    ).join('');
    if (projectState.clips.length) {
      selectedClipIndex = Math.min(selectedClipIndex, projectState.clips.length - 1);
      clipPicker.value = String(selectedClipIndex);
    } else {
      selectedClipIndex = 0;
    }
  };
  const markDirty = () => {
    if (saveState) saveState.textContent = 'Modifications non enregistrées';
    clearTimeout(saveTimer);
    saveTimer = setTimeout(() => saveProject(false), 1200);
  };
  const snapshot = () => {
    undoStack.push(clone(projectState));
    if (undoStack.length > 40) undoStack.shift();
    redoStack.length = 0;
  };
  const applyState = next => {
    projectState = clone(next);
    refreshClipPicker();
    clipPicker?.addEventListener('change', () => {
    selectedClipIndex = Number(clipPicker.value || 0);
  });

  const serverEdit = async operation => {
    if (!projectId) await saveProject(false);
    if (!projectId) throw new Error('Le projet doit être enregistré avant une modification.');
    snapshot();
    const response = await fetch('/api/studio/projects/' + projectId + '/edit', {
      method:'POST',
      headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
      body:JSON.stringify({operation}),
      credentials:'same-origin'
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      undoStack.pop();
      throw new Error(data.error || 'Modification Studio impossible.');
    }
    applyState(data.timeline);
    if (saveState) saveState.textContent = 'Modification enregistrée';
  };

  const askNumber = (message, fallback) => {
    const raw = window.prompt(message, String(fallback));
    if (raw === null) return null;
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  };

  document.querySelectorAll('[data-editor-op]').forEach(btn => btn.addEventListener('click', async () => {
    if (!projectState.clips.length && btn.dataset.editorOp !== 'marker') {
      alert('Ajoute d’abord un clip à la timeline.');
      return;
    }
    const op = btn.dataset.editorOp;
    const index = selectedClipIndex;
    try {
      if (op === 'split') {
        const duration = Number(projectState.clips[index]?.duration || 0);
        const at = askNumber('À quelle seconde couper ce clip ?', Math.max(1, Math.floor(duration / 2)));
        if (at === null) return;
        await serverEdit({type:'split', clip_index:index, at});
      } else if (op === 'trim') {
        const duration = Number(projectState.clips[index]?.duration || 0);
        const inPoint = askNumber('Début du trim (secondes)', 0);
        const outPoint = askNumber('Fin du trim (secondes)', duration);
        if (inPoint === null || outPoint === null) return;
        await serverEdit({type:'trim', clip_index:index, in_point:inPoint, out_point:outPoint});
      } else if (op === 'move') {
        const start = askNumber('Nouvelle position sur la timeline (secondes)', Number(projectState.clips[index]?.start || 0));
        if (start === null) return;
        await serverEdit({type:'move', clip_index:index, new_start:start});
      } else if (op === 'duplicate') {
        await serverEdit({type:'duplicate', clip_index:index});
      } else if (op === 'marker') {
        const time = Number(previewVideo?.currentTime || 0);
        const label = window.prompt('Nom du marker', 'Moment fort');
        if (label === null) return;
        await serverEdit({type:'add_marker', time, label});
      }
    } catch (error) {
      alert(error.message || 'Modification impossible.');
    }
  });

  document.querySelectorAll('[data-ratio]').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.ratio === (projectState.settings.ratio || '9:16'));
    });
  };

  const saveProject = async (showFeedback = true) => {
    if (saveState) saveState.textContent = 'Enregistrement…';
    try {
      let response;
      const payload = {name: projectName?.value || 'Nouveau projet', timeline: projectState};
      if (!projectId) {
        response = await fetch('/api/studio/projects', {
          method:'POST',
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify(payload),
          credentials:'same-origin'
        });
      } else {
        response = await fetch('/api/studio/projects/' + projectId + '/save', {
          method:'POST',
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify(payload),
          credentials:'same-origin'
        });
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'Impossible d’enregistrer le projet.');
      projectId = data.project_id || projectId;
      if (shell && projectId) shell.dataset.studioProjectId = projectId;
      if (projectId && !new URL(window.location.href).searchParams.get('project_id')) {
        const url = new URL(window.location.href);
        url.searchParams.set('project_id', projectId);
        window.history.replaceState({}, '', url);
      }
      if (saveState) saveState.textContent = 'Enregistré · ' + new Date().toLocaleTimeString('fr-FR', {hour:'2-digit', minute:'2-digit'});
      if (showFeedback) saveButton?.classList.add('is-saved');
      setTimeout(() => saveButton?.classList.remove('is-saved'), 900);
      localStorage.removeItem('klypso-studio-draft');
      return true;
    } catch (error) {
      if (saveState) saveState.textContent = 'Erreur · brouillon local conservé';
      localStorage.setItem('klypso-studio-draft', JSON.stringify({projectId, name:projectName?.value || 'Nouveau projet', timeline:projectState}));
      if (showFeedback) alert(error.message);
      return false;
    }
  };

  const restoreLocalDraft = () => {
    if (projectId) return;
    try {
      const draft = JSON.parse(localStorage.getItem('klypso-studio-draft') || 'null');
      if (!draft?.timeline) return;
      projectState = draft.timeline;
      if (projectName && draft.name) projectName.value = draft.name;
      if (saveState) saveState.textContent = 'Brouillon local restauré';
      applyState(projectState);
    } catch (_) {}
  };

  const setRatio = ratio => {
    snapshot();
    projectState.settings.ratio = ratio;
    markDirty();
    applyState(projectState);
    const button = document.querySelector('[data-format-button]');
    if (button) button.textContent = ratio + ' ▾';
  };

  document.querySelectorAll('[data-ratio]').forEach(btn => {
    btn.addEventListener('click', () => setRatio(btn.dataset.ratio));
  });
  document.querySelector('[data-format-button]')?.addEventListener('click', () => {
    const next = (projectState.settings.ratio || '9:16') === '9:16' ? '16:9' : ((projectState.settings.ratio || '9:16') === '16:9' ? '1:1' : '9:16');
    setRatio(next);
  });
  saveButton?.addEventListener('click', () => saveProject(true));
  projectName?.addEventListener('input', markDirty);

  document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      saveProject(true);
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
      event.preventDefault();
      if (undoStack.length) {
        redoStack.push(clone(projectState));
        applyState(undoStack.pop());
        markDirty();
      }
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'y') {
      event.preventDefault();
      if (redoStack.length) {
        undoStack.push(clone(projectState));
        applyState(redoStack.pop());
        markDirty();
      }
    }
  });

  document.querySelectorAll('[data-studio-action="undo"]').forEach(btn => btn.addEventListener('click', () => {
    if (!undoStack.length) return;
    redoStack.push(clone(projectState));
    applyState(undoStack.pop());
    markDirty();
  }));
  document.querySelectorAll('[data-studio-action="redo"]').forEach(btn => btn.addEventListener('click', () => {
    if (!redoStack.length) return;
    undoStack.push(clone(projectState));
    applyState(redoStack.pop());
    markDirty();
  }));

  document.querySelectorAll('[data-studio-action="export"]').forEach(btn => btn.addEventListener('click', async () => {
    await saveProject(false);
    const blob = new Blob([JSON.stringify({version:'20.0', project_id:projectId, name:projectName?.value || 'Klypso project', timeline:projectState}, null, 2)], {type:'application/json'});
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = (projectName?.value || 'klypso-project').replace(/[^a-z0-9-_]+/gi, '-').toLowerCase() + '.klypso.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }));

  restoreLocalDraft();
  applyState(projectState);



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
    if (!previewVideo) return;
    if (btn.classList.contains('playing')) previewVideo.play().catch(() => {});
    else previewVideo.pause();
  }));
  document.querySelector('.transport button:nth-child(2)')?.addEventListener('click', () => {
    if (previewVideo) previewVideo.currentTime = Math.max(0, previewVideo.currentTime - 5);
    syncTimecode();
  });
  document.querySelector('.transport button:nth-child(4)')?.addEventListener('click', () => {
    if (previewVideo) previewVideo.currentTime = Math.min(previewVideo.duration || 0, previewVideo.currentTime + 5);
    syncTimecode();
  });
  document.querySelector('.transport button:nth-child(1)')?.addEventListener('click', () => {
    if (previewVideo) previewVideo.currentTime = 0;
    syncTimecode();
  });
  document.querySelector('.transport button:nth-child(5)')?.addEventListener('click', () => {
    if (previewVideo) previewVideo.currentTime = previewVideo.duration || 0;
    syncTimecode();
  });

  let previewUrl = null;
  let previewVideo = null;
  const frame = document.getElementById('video-frame');
  const timecode = document.querySelector('.timecode');
  const formatTime = seconds => {
    const value = Math.max(0, Number(seconds) || 0);
    const minutes = Math.floor(value / 60);
    const secs = value % 60;
    return String(minutes).padStart(2, '0') + ':' + secs.toFixed(2).padStart(5, '0');
  };
  const syncTimecode = () => {
    if (!timecode) return;
    timecode.textContent = formatTime(previewVideo?.currentTime) + ' / ' + formatTime(previewVideo?.duration);
  };
  const mountPreview = file => {
    if (!frame || !file) return;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(file);
    frame.querySelector('.frame-placeholder')?.remove();
    previewVideo?.remove();
    previewVideo = document.createElement('video');
    previewVideo.id = 'studio-preview';
    previewVideo.controls = false;
    previewVideo.playsInline = true;
    previewVideo.preload = 'metadata';
    previewVideo.src = previewUrl;
    previewVideo.style.cssText = 'width:100%;height:100%;object-fit:contain;border-radius:inherit;background:#07070a;display:block;';
    frame.prepend(previewVideo);
    previewVideo.addEventListener('loadedmetadata', syncTimecode);
    previewVideo.addEventListener('timeupdate', syncTimecode);
    previewVideo.addEventListener('ended', () => document.querySelector('.main-play')?.classList.remove('playing'));
    syncTimecode();
  };

  input?.addEventListener('change', () => {
    const file = input.files?.[0];
    if (fileLabel) fileLabel.textContent = file ? file.name : 'Choisir une vidéo source';
    if (file) mountPreview(file);
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
