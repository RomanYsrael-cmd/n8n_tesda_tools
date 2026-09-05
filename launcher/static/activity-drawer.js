(() => {
  const script = document.currentScript;
  const jobId = script.dataset.jobId;
  const redirectOnSuccess = script.dataset.redirectOnSuccess === 'true';
  const drawer = document.getElementById('activity-drawer');
  const backdrop = document.getElementById('drawer-backdrop');
  const entries = document.getElementById('activity-entries');
  const summary = document.getElementById('activity-summary');
  const liveStreams = document.getElementById('live-streams');
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const setOpen = (open) => { drawer.classList.toggle('open', open); backdrop.classList.toggle('open', open); drawer.setAttribute('aria-hidden', String(!open)); document.getElementById('activity-toggle').setAttribute('aria-expanded', String(open)); localStorage.setItem('module-builder-activity-open', open ? '1' : '0'); };
  document.getElementById('activity-toggle').addEventListener('click', () => { setOpen(true); document.getElementById('activity-close').focus(); });
  document.getElementById('activity-close').addEventListener('click', () => setOpen(false));
  backdrop.addEventListener('click', () => setOpen(false));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && drawer.classList.contains('open')) setOpen(false); });
  if (localStorage.getItem('module-builder-activity-open') === '1') setOpen(true);

  function readableLog(value) {
    if (!value || typeof value !== 'object') return String(value ?? '');
    const telemetry = formatTelemetry(value.telemetry || value.usage);
    if (value.rejected_text !== undefined) {
      const errors = Array.isArray(value.errors) ? value.errors.map(e => `• ${e}`).join('\n') : String(value.errors || 'Unknown validation error');
      return `${telemetry ? telemetry + '\n\n' : ''}VALIDATION ERRORS\n${errors}\n\nREJECTED LLM RESPONSE\n${value.rejected_text}`;
    }
    if (value.extracted_text !== undefined) {
      return `${telemetry ? telemetry + '\n\n' : ''}ACCEPTED CONTENT\n${value.extracted_text}\n\nRAW LLM RESPONSE\n${value.raw_text || ''}`;
    }
    if (value.text !== undefined) return `${telemetry ? telemetry + '\n\n' : ''}LLM RESPONSE\n${value.text}`;
    if (value.prompt !== undefined) {
      const details = [`PROMPT SENT TO THE LLM`, value.prompt];
      if (value.model) details.push(`MODEL\n${value.model}`);
      if (value.base_url) details.push(`BASE URL\n${value.base_url}`);
      if (value.request_options && Object.keys(value.request_options).length) details.push(`GENERATION FEATURES\n${JSON.stringify(value.request_options, null, 2)}`);
      return details.join('\n\n');
    }
    if (value.error !== undefined) {
      return `ERROR\n${value.error}${value.traceback ? `\n\nTECHNICAL DETAILS\n${value.traceback}` : ''}`;
    }
    return JSON.stringify(value, null, 2);
  }

  function formatTelemetry(value) {
    if (!value || typeof value !== 'object') return '';
    const exact = Number.isFinite(Number(value.completion_tokens)) ? Number(value.completion_tokens) : null;
    const estimated = Number(value.output_tokens_estimate || value.completion_tokens_estimate || 0);
    const tokens = exact !== null ? `${exact} output tokens` : `~${estimated} output tokens`;
    const chars = Number(value.output_characters || value.content_characters || 0);
    const elapsed = Number(value.elapsed_seconds || 0).toFixed(1);
    const speed = Number(value.tokens_per_second || 0).toFixed(1);
    const prompt = Number.isFinite(Number(value.prompt_tokens)) ? `${Number(value.prompt_tokens)} prompt tokens` : `~${Number(value.prompt_tokens_estimate || 0)} prompt tokens`;
    return `TOKEN USAGE\n${tokens} · ${chars} characters · ${elapsed}s · ${speed} tokens/s · ${prompt}`;
  }

  function liveTelemetry(item) {
    const usage = item.usage || {};
    const exact = Number.isFinite(Number(usage.completion_tokens)) ? `${Number(usage.completion_tokens)} output tokens` : `~${Number(item.output_tokens_estimate || 0)} output tokens`;
    const prompt = Number.isFinite(Number(usage.prompt_tokens)) ? `${Number(usage.prompt_tokens)} prompt tokens` : `~${Number(item.prompt_tokens_estimate || 0)} prompt tokens`;
    return `${exact} · ${Number(item.output_characters || 0)} characters · ${Number(item.elapsed_seconds || 0).toFixed(1)}s · ${Number(item.tokens_per_second || 0).toFixed(1)} tokens/s · ${prompt}`;
  }

  async function openEntry(button) {
    const box = button.parentElement, existing = box.querySelector('.log-detail');
    if (existing) { existing.hidden = !existing.hidden; return; }
    button.disabled = true;
    try { const response = await fetch(button.dataset.url); const value = await response.json(); const pre = document.createElement('pre'); pre.className = 'log-detail'; pre.textContent = readableLog(value); box.appendChild(pre); }
    catch (_) { const pre = document.createElement('pre'); pre.className = 'log-detail'; pre.textContent = 'Could not load this entry.'; box.appendChild(pre); }
    finally { button.disabled = false; }
  }

  async function refresh() {
    try {
      const response = await fetch(`/api/jobs/${jobId}/llm-logs`, {cache:'no-store'}), data = await response.json();
      document.getElementById('job-status').textContent = data.job.status;
      document.getElementById('job-message').textContent = data.job.message || '';
      document.getElementById('job-progress').style.width = `${data.job.progress || 0}%`;
      const error = document.getElementById('job-error'); error.hidden = !data.job.error; error.querySelector('span').textContent = data.job.error || '';
      liveStreams.innerHTML = (data.live || []).map(item => `<div class="log-entry response live-entry"><div style="display:flex;justify-content:space-between;gap:.5rem;padding:.65rem .8rem;background:#ecfdf3;font-size:.78rem"><strong>LIVE · Lesson ${item.lesson} · ${escapeHtml(item.stage)}</strong><span>${escapeHtml(item.status)} · attempt ${item.attempt}</span></div><div class="live-stats">${escapeHtml(liveTelemetry(item))}</div><pre class="log-detail" style="max-height:34vh">${escapeHtml(item.content || 'Waiting for the first token…')}</pre></div>`).join('');
      const stageRows = document.getElementById('stage-rows');
      if (stageRows) stageRows.innerHTML = data.stages.map(s => `<tr><td>${s.lesson_number}</td><td>${s.actual_week}</td><td>${escapeHtml(s.stage)}</td><td>${escapeHtml(s.status)}</td><td>${s.attempts}</td><td>${escapeHtml(s.message)}</td></tr>`).join('');
      summary.innerHTML = data.stages.length ? data.stages.map(s => `<div class="stage-line"><strong>L${s.lesson_number}</strong><span>${escapeHtml(s.stage)}</span><span>${escapeHtml(s.status)}</span><span>×${s.attempts}</span></div>`).join('') : '<div class="activity-empty">Waiting for the first stage…</div>';
      const known = new Set([...entries.children].map(e => e.dataset.name));
      data.entries.slice().reverse().forEach(item => { if (known.has(item.name)) return; const box=document.createElement('div'); box.className=`log-entry ${item.kind}`; box.dataset.name=item.name; const button=document.createElement('button'); button.type='button'; button.dataset.url=`/api/jobs/${jobId}/llm-logs/${item.bucket}/${encodeURIComponent(item.name)}`; button.innerHTML=`<span>${escapeHtml(item.kind.toUpperCase())}</span><span>${escapeHtml(item.name.replace(jobId+'-',''))}</span>`; button.addEventListener('click',()=>openEntry(button)); box.appendChild(button); const meta=document.createElement('div'); meta.className='log-meta'; meta.textContent=`${new Date(item.updated_at).toLocaleTimeString()} · ${Math.ceil(item.size/1024)} KB`; box.appendChild(meta); entries.prepend(box); });
      if (['success','finished'].includes(data.job.status)) {
        if (redirectOnSuccess) location.href=`/jobs/${jobId}/result`;
        return false;
      }
      if (['failed','cancelled','paused'].includes(data.job.status)) return false;
    } catch (_) { summary.textContent = 'Live update temporarily unavailable. Retrying…'; }
    return true;
  }
  async function poll() {
    const shouldContinue = await refresh();
    if (shouldContinue) setTimeout(poll, 1000);
  }
  poll();
})();
