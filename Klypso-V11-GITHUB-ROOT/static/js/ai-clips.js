(() => {
  'use strict';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[char]));

  const scoreBars = (clip) => {
    const scores = clip.scores || {};
    const rows = [
      ['Hook', scores.hook_score],
      ['Payoff', scores.payoff_score],
      ['Émotion', scores.emotion_score],
      ['Partage', scores.shareability_score],
      ['Style créateur', scores.creator_fit_score],
      ['Replay', scores.replay_score]
    ];
    return rows.map(([label, value]) => '<div class="ai-score-row"><span>' + label + '</span><div><i style="width:' + Math.max(0, Math.min(100, Number(value) || 0)) + '%"></i></div><b>' + (Number(value) || 0) + '</b></div>').join('');
  };

  const resultBox = (jobId) => document.querySelector('[data-ai-result="' + jobId + '"]');

  const renderAnalysis = (jobId, data) => {
    const box = resultBox(jobId);
    if (!box) return;
    const ai = data?.result?.ai || {};
    const clips = ai.clips || [];
    const memory = data?.result?.ai?.creator_memory_used || data?.result?.creator_memory_used || {};
    box.innerHTML =
      '<div class="ai-result-title"><div><span class="eyebrow-v11">KLYPSO VIRAL ENGINE · V1</span><h3>Sélection éditoriale prête.</h3><p>' +
      escapeHtml(ai.summary || data.message || 'Scènes classées.') +
      '</p></div><div class="ai-memory-chip">DNA · ' + escapeHtml(memory.projects_analyzed || 0) + ' projets appris</div></div>' +
      '<div class="ai-result-actions"><button class="button" type="button" data-render-clips="' + jobId + '">Rendre les clips avec ce preset →</button><button class="button ghost" type="button" data-render-montage="' + jobId + '">Créer le montage IA →</button></div>' +
      '<div class="ai-clip-list">' +
      clips.map((clip, index) =>
        '<article class="ai-clip-row"><div class="ai-clip-rank">0' + (index + 1) + '</div><div class="ai-clip-main"><div class="ai-clip-head"><span class="ai-archetype">' + escapeHtml(clip.archetype || 'moment fort') + '</span><b>' + escapeHtml(clip.title) + '</b><strong>' + escapeHtml(clip.opportunity_score) + '/100</strong></div>' +
        '<p class="ai-clip-hook">“' + escapeHtml(clip.hook) + '”</p><p class="ai-clip-reason">' + escapeHtml(clip.reason) + '</p><div class="ai-score-grid">' + scoreBars(clip) + '</div>' +
        '<div class="ai-clip-feedback"><button type="button" class="filter-btn" data-feedback="keep" data-job-id="' + jobId + '" data-candidate-id="' + escapeHtml(clip.id) + '">✓ Je garde</button><button type="button" class="filter-btn" data-feedback="reject" data-job-id="' + jobId + '" data-candidate-id="' + escapeHtml(clip.id) + '">× Je rejette</button><button type="button" class="filter-btn" data-performance-open="' + jobId + ':' + escapeHtml(clip.id) + '">↗ Performance</button><span>' + Number(clip.start || 0).toFixed(1) + 's → ' + Number(clip.end || 0).toFixed(1) + 's</span></div>' +
        '<div class="performance-panel" data-performance-panel="' + jobId + ':' + escapeHtml(clip.id) + '" hidden><div><span>APRÈS PUBLICATION</span><strong>Apprends à KLYPSO ce qui a vraiment marché.</strong></div><label>Plateforme<select data-performance-platform><option value="youtube">YouTube</option><option value="tiktok">TikTok</option><option value="instagram">Instagram</option><option value="x">X</option><option value="other">Autre</option></select></label><label>Vues<input type="number" min="0" value="0" data-performance-views></label><label>Likes<input type="number" min="0" value="0" data-performance-likes></label><label>Commentaires<input type="number" min="0" value="0" data-performance-comments></label><label>Partages<input type="number" min="0" value="0" data-performance-shares></label><label>Complétion %<input type="number" min="0" max="100" step="0.1" value="0" data-performance-completion></label><button class="button small" type="button" data-performance-save="' + jobId + ':' + escapeHtml(clip.id) + '">Enregistrer la performance</button><span data-performance-status></span></div></div></div></article>'
      ).join('') +
      '</div><div class="ai-render-output" data-ai-render-output="' + jobId + '"></div>';
    const agents = ai.agents || {};
    const agentItems = (agents.agents || []).map(agent =>
      '<span class="agent-chip"><span title="' + escapeHtml(agent.note || '') + '">' + escapeHtml(agent.name || 'agent') + '</span><b>' + Number(agent.score || 0) + '</b></span>'
    ).join('');
    box.querySelector('.ai-result-actions')?.insertAdjacentHTML('afterend',
      '<div class="agent-grid-v18"><div class="agent-grid-head"><b>15 agents ont croisé le dossier</b><span>CONSENSUS ' + Number(agents.consensus_score || 0) + '/100</span></div><div class="agent-grid-list">' + agentItems + '</div></div>' +
      '<div class="social-render-controls"><span>RENDU SOCIAL</span><label>Preset<select data-social-preset><option value="dynamic">Dynamic</option><option value="gaming">Gaming</option><option value="story">Story</option><option value="clean">Clean</option></select></label><label>Captions<select data-caption-style><option value="dynamic">Dynamic</option><option value="classic">Classic</option><option value="minimal">Minimal</option></select></label></div>'
    );
    box.hidden = false;
    box.scrollIntoView({behavior:'smooth', block:'center'});
  };

  document.addEventListener('click', async (event) => {
    const performanceOpen = event.target.closest('[data-performance-open]');
    if (performanceOpen) {
      document.querySelector('[data-performance-panel="' + performanceOpen.dataset.performanceOpen + '"]')?.toggleAttribute('hidden');
      return;
    }

    const performanceSave = event.target.closest('[data-performance-save]');
    if (performanceSave) {
      const panel = document.querySelector('[data-performance-panel="' + performanceSave.dataset.performanceSave + '"]');
      if (!panel) return;
      const [jobId, candidateId] = performanceSave.dataset.performanceSave.split(':');
      const payload = {
        job_id: jobId,
        candidate_id: candidateId,
        platform: panel.querySelector('[data-performance-platform]')?.value || 'unknown',
        views: Number(panel.querySelector('[data-performance-views]')?.value || 0),
        likes: Number(panel.querySelector('[data-performance-likes]')?.value || 0),
        comments: Number(panel.querySelector('[data-performance-comments]')?.value || 0),
        shares: Number(panel.querySelector('[data-performance-shares]')?.value || 0),
        completion_rate: Number(panel.querySelector('[data-performance-completion]')?.value || 0)
      };
      performanceSave.disabled = true;
      performanceSave.textContent = 'Enregistrement…';
      try {
        const response = await fetch('/clips/performance', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf}, body:JSON.stringify(payload), credentials:'same-origin'});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Performance non enregistrée.');
        const status = panel.querySelector('[data-performance-status]');
        if (status) status.textContent = '✓ Performance mémorisée';
        performanceSave.textContent = 'Mémorisée ✓';
      } catch(error) {
        performanceSave.disabled = false;
        performanceSave.textContent = 'Enregistrer la performance';
        alert(error.message);
      }
      return;
    }

    const standardOpen = event.target.closest('[data-standard-open]');
    if (standardOpen) {
      document.querySelector('[data-standard-panel="' + standardOpen.dataset.standardOpen + '"]')?.toggleAttribute('hidden');
      return;
    }

    const standardRender = event.target.closest('[data-standard-render]');
    if (standardRender) {
      const jobId = standardRender.dataset.standardRender;
      const panel = document.querySelector('[data-standard-panel="' + jobId + '"]');
      const output = panel?.querySelector('[data-standard-output]');
      const start = Number(panel?.querySelector('[data-standard-start]')?.value || 0);
      const end = Number(panel?.querySelector('[data-standard-end]')?.value || 30);
      if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
        alert('Le début et la fin du clip sont invalides.');
        return;
      }
      standardRender.disabled = true;
      standardRender.textContent = 'Rendu…';
      try {
        const response = await fetch('/api/clips/render-standard/' + jobId, {
          method:'POST',
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify({start,end,output_format:'9:16'}),
          credentials:'same-origin'
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Rendu impossible.');
        if (output) output.innerHTML = '<a class="ai-download-card" href="' + data.download_url + '"><span>MP4</span><b>Clip standard prêt</b><small>' + data.start.toFixed(1) + 's → ' + data.end.toFixed(1) + 's · Télécharger →</small></a>';
        standardRender.textContent = 'Clip prêt ✓';
      } catch(error) {
        standardRender.disabled = false;
        standardRender.textContent = 'Rendre le MP4';
        alert(error.message);
      }
      return;
    }

    const analyze = event.target.closest('.ai-run-job');
    if (analyze) {
      analyze.disabled = true;
      analyze.textContent = 'Analyse en cours…';
      try {
        const response = await fetch('/api/ai/analyze/' + analyze.dataset.jobId, {method:'POST', headers:{'X-CSRF-Token':csrf}, credentials:'same-origin'});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Analyse impossible.');
        analyze.textContent = 'Analyse terminée ✓';
        renderAnalysis(analyze.dataset.jobId, data);
      } catch (error) {
        analyze.disabled = false;
        analyze.textContent = 'Relancer l’IA';
        alert(error.message);
      }
      return;
    }

    const renderClips = event.target.closest('[data-render-clips]');
    if (renderClips) {
      renderClips.disabled = true;
      renderClips.textContent = 'Rendu des clips…';
      const box = resultBox(renderClips.dataset.renderClips);
      const output = box?.querySelector('[data-ai-render-output]');
      try {
        const socialPreset = box?.querySelector('[data-social-preset]')?.value || 'dynamic';
        const captionStyle = box?.querySelector('[data-caption-style]')?.value || 'dynamic';
        const response = await fetch('/api/ai/render-clips/' + renderClips.dataset.renderClips, {
          method:'POST',
          headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},
          body:JSON.stringify({social_preset:socialPreset,caption_style:captionStyle}),
          credentials:'same-origin'
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Rendu impossible.');
        if (output) output.innerHTML = '<div class="ai-download-grid">' + (data.clips || []).map(clip => '<a class="ai-download-card" href="' + clip.download_url + '"><span>MP4</span><b>' + escapeHtml(clip.title) + '</b><small>' + clip.score + '/100 · Télécharger →</small></a>').join('') + '</div>';
        renderClips.textContent = 'Clips rendus ✓';
      } catch (error) {
        renderClips.disabled = false;
        renderClips.textContent = 'Rendre les 5 meilleurs clips →';
        alert(error.message);
      }
      return;
    }

    const renderMontage = event.target.closest('[data-render-montage]');
    if (renderMontage) {
      renderMontage.disabled = true;
      renderMontage.textContent = 'Montage en cours…';
      const box = resultBox(renderMontage.dataset.renderMontage);
      const output = box?.querySelector('[data-ai-render-output]');
      try {
        const response = await fetch('/api/ai/render-montage/' + renderMontage.dataset.renderMontage, {method:'POST', headers:{'X-CSRF-Token':csrf}, credentials:'same-origin'});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Montage impossible.');
        if (output) output.innerHTML = '<div class="ai-download-grid"><a class="ai-download-card featured" href="' + data.montage.download_url + '"><span>MONTAGE IA</span><b>Exporter la séquence complète</b><small>' + data.montage.clip_count + ' scènes · Télécharger →</small></a></div>';
        renderMontage.textContent = 'Montage IA prêt ✓';
      } catch (error) {
        renderMontage.disabled = false;
        renderMontage.textContent = 'Créer le montage IA →';
        alert(error.message);
      }
      return;
    }

    const feedback = event.target.closest('[data-feedback]');
    if (feedback) {
      const form = new URLSearchParams();
      form.set('csrf_token', csrf);
      form.set('job_id', feedback.dataset.jobId);
      form.set('candidate_id', feedback.dataset.candidateId);
      form.set('decision', feedback.dataset.feedback);
      feedback.disabled = true;
      try {
        const response = await fetch('/clips/feedback', {method:'POST', body:form, credentials:'same-origin'});
        if (!response.ok) throw new Error('Feedback non enregistré.');
        feedback.textContent = feedback.dataset.feedback === 'keep' ? '✓ Gardé' : '× Rejeté';
      } catch (error) {
        feedback.disabled = false;
        alert(error.message);
      }
    }
  });
})();