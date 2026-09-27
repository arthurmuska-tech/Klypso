(() => {
  'use strict';
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
  const api = (url, options = {}) => fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...(options.body ? {'Content-Type':'application/json'} : {}),
      ...(options.headers || {}),
      'X-CSRF-Token': csrf
    }
  });
  const statusBox = document.querySelector('[data-publisher-status]');
  const queueBox = document.querySelector('[data-publisher-queue]');
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));

  const renderQueue = items => {
    if (!queueBox) return;
    if (!items.length) {
      queueBox.innerHTML = '<div class="publisher-empty"><span>↗</span><div><strong>Aucune publication programmée.</strong><p>Choisis des clips, une cadence et des réseaux pour remplir ton calendrier.</p></div></div>';
      return;
    }
    queueBox.innerHTML = items.map(item => {
      const action = ['scheduled','needs_connection','failed'].includes(item.status)
        ? '<button class="filter-btn" type="button" data-publish-now="' + item.id + '">Publier maintenant</button>' : '';
      const metrics = item.status === 'published'
        ? '<button class="filter-btn" type="button" data-metrics-open="' + item.id + '">Ajouter métriques</button>' : '';
      const remote = item.remote_url
        ? '<a class="filter-btn" href="' + escapeHtml(item.remote_url) + '" target="_blank" rel="noopener">Voir →</a>' : '';
      return '<article class="publisher-queue-row">' +
        '<div class="publisher-queue-date"><strong>' + escapeHtml(item.scheduled_for) + '</strong><span>' + escapeHtml(String(item.platform || '').toUpperCase()) + '</span></div>' +
        '<div class="publisher-queue-main"><b>' + escapeHtml(item.title) + '</b><small>' + escapeHtml(item.caption) + '</small><span class="publisher-status ' + escapeHtml(item.status) + '">' + escapeHtml(item.status) + '</span></div>' +
        '<div class="publisher-queue-actions">' + action + metrics + remote + '</div>' +
        '<div class="publisher-metrics-panel" data-metrics-panel="' + item.id + '" hidden>' +
          '<label>Vues<input type="number" min="0" value="0" data-metric-views></label>' +
          '<label>Likes<input type="number" min="0" value="0" data-metric-likes></label>' +
          '<label>Commentaires<input type="number" min="0" value="0" data-metric-comments></label>' +
          '<label>Partages<input type="number" min="0" value="0" data-metric-shares></label>' +
          '<label>Complétion %<input type="number" min="0" max="100" step="0.1" value="0" data-metric-completion></label>' +
          '<button class="button small" type="button" data-save-metrics="' + item.id + '">Apprendre de cette publication</button><span data-metrics-status></span>' +
        '</div></article>';
    }).join('');
  };

  const refreshAnalytics = async () => {
    const response = await api('/api/publisher/analytics');
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Impossible de charger les analytics.');
    const totals = data.totals || {};
    document.querySelector('[data-analytics-views]')?.replaceChildren(document.createTextNode(Number(totals.views || 0).toLocaleString('fr-FR')));
    document.querySelector('[data-analytics-likes]')?.replaceChildren(document.createTextNode(Number(totals.likes || 0).toLocaleString('fr-FR')));
    document.querySelector('[data-analytics-shares]')?.replaceChildren(document.createTextNode(Number(totals.shares || 0).toLocaleString('fr-FR')));
    document.querySelector('[data-analytics-completion]')?.replaceChildren(document.createTextNode(Number(totals.completion_rate || 0) + '%'));
    const box = document.querySelector('[data-analytics-platforms]');
    if (box) {
      const entries = Object.entries(data.by_platform || {});
      box.innerHTML = entries.length ? entries.map(([platform, values]) =>
        '<article class="publisher-platform"><div><strong>' + escapeHtml(platform.toUpperCase()) + '</strong><small>' +
        Number(values.views || 0).toLocaleString('fr-FR') + ' vues · ' + Number(values.engagement_rate || 0) + '% engagement</small></div>' +
        '<span class="publisher-connection is-on">' + Number(values.completion_rate || 0) + '%</span></article>'
      ).join('') : '<div class="publisher-empty"><span>◎</span><div><strong>Pas encore de données.</strong><p>Ajoute les métriques des publications pour alimenter la mémoire Klypso.</p></div></div>';
    }
  };

  const refresh = async () => {
    const response = await api('/api/publisher/queue');
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || 'Impossible de charger la file.');
    renderQueue(data.queue || []);
  };

  document.addEventListener('click', async event => {
    const cadence = event.target.closest('[data-create-cadence]');
    if (cadence) {
      const media = [...document.querySelector('[data-publisher-media]')?.selectedOptions || []].map(option => Number(option.value));
      const platforms = [...document.querySelectorAll('[data-platform-check]:checked')].map(input => input.value);
      const frequency = document.querySelector('[data-publisher-frequency]')?.value || 'daily';
      const startAt = document.querySelector('[data-publisher-start]')?.value || '';
      const count = Number(document.querySelector('[data-publisher-count]')?.value || 7);
      const title = document.querySelector('[data-publisher-title]')?.value || '';
      const caption = document.querySelector('[data-publisher-caption]')?.value || '';
      if (!media.length || !platforms.length || !startAt) {
        alert('Choisis au moins un clip, un réseau et une date de départ.');
        return;
      }
      cadence.disabled = true;
      cadence.textContent = 'Programmation…';
      try {
        const response = await api('/api/publisher/cadence', {
          method:'POST',
          body:JSON.stringify({media_ids:media, platforms, frequency, start_at:new Date(startAt).toISOString(), count, title, caption})
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Cadence impossible.');
        if (statusBox) statusBox.textContent = data.created + ' publication(s) programmée(s).';
        cadence.textContent = 'Cadence créée ✓';
        await refresh();
      } catch (error) {
        cadence.disabled = false;
        cadence.textContent = 'Créer la cadence →';
        alert(error.message);
      }
      return;
    }

    const publish = event.target.closest('[data-publish-now]');
    if (publish) {
      publish.disabled = true;
      publish.textContent = 'Publication…';
      try {
        const response = await api('/api/publisher/publish/' + publish.dataset.publishNow, {method:'POST'});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Publication impossible.');
        publish.textContent = data.status === 'published' ? 'Publié ✓' : 'À configurer';
        await refresh();
      } catch (error) {
        publish.disabled = false;
        publish.textContent = 'Publier maintenant';
        alert(error.message);
      }
      return;
    }

    const metricsOpen = event.target.closest('[data-metrics-open]');
    if (metricsOpen) {
      document.querySelector('[data-metrics-panel="' + metricsOpen.dataset.metricsOpen + '"]')?.toggleAttribute('hidden');
      return;
    }

    const save = event.target.closest('[data-save-metrics]');
    if (save) {
      const panel = document.querySelector('[data-metrics-panel="' + save.dataset.saveMetrics + '"]');
      if (!panel) return;
      const body = {
        views:Number(panel.querySelector('[data-metric-views]')?.value || 0),
        likes:Number(panel.querySelector('[data-metric-likes]')?.value || 0),
        comments:Number(panel.querySelector('[data-metric-comments]')?.value || 0),
        shares:Number(panel.querySelector('[data-metric-shares]')?.value || 0),
        completion_rate:Number(panel.querySelector('[data-metric-completion]')?.value || 0)
      };
      save.disabled = true;
      try {
        const response = await api('/api/publisher/metrics/' + save.dataset.saveMetrics, {method:'POST',body:JSON.stringify(body)});
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || 'Métriques non enregistrées.');
        panel.querySelector('[data-metrics-status]').textContent = '✓ Performance ajoutée au Creator DNA';
        save.textContent = 'Apprise ✓';
      } catch (error) {
        save.disabled = false;
        alert(error.message);
      }
      return;
    }

    if (event.target.closest('[data-refresh-queue]')) {
      try { await refresh(); } catch (error) { alert(error.message); }
    }
    if (event.target.closest('[data-refresh-analytics]')) {
      try { await refreshAnalytics(); } catch (error) { alert(error.message); }
    }
  });

  refreshAnalytics().catch(() => {});
  refresh().catch(() => {});
})();
