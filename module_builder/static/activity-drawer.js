(() => {
  const script = document.currentScript;
  const jobId = script.dataset.jobId;
  const drawer = document.getElementById('activity-drawer');
  const backdrop = document.getElementById('drawer-backdrop');
  const entries = document.getElementById('activity-entries');
  const summary = document.getElementById('activity-summary');
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const setOpen = (open) => { drawer.classList.toggle('open', open); backdrop.classList.toggle('open', open); drawer.setAttribute('aria-hidden', String(!open)); document.getElementById('activity-toggle').setAttribute('aria-expanded', String(open)); localStorage.setItem('module-builder-activity-open', open ? '1' : '0'); };
  document.getElementById('activity-toggle').addEventListener('click', () => setOpen(true));
  document.getElementById('activity-close').addEventListener('click', () => setOpen(false));
  backdrop.addEventListener('click', () => setOpen(false));
  if (localStorage.getItem('module-builder-activity-open') === '1') setOpen(true);

  async function openEntry(button) {
    const box = button.parentElement, existing = box.querySelector('.log-detail');
    if (existing) { existing.hidden = !existing.hidden; return; }
    button.disabled = true;
    try { const response = await fetch(button.dataset.url); const value = await response.json(); const pre = document.createElement('pre'); pre.className = 'log-detail'; pre.textContent = JSON.stringify(value, null, 2); box.appendChild(pre); }
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
      document.getElementById('stage-rows').innerHTML = data.stages.map(s => `<tr><td>${s.lesson_number}</td><td>${s.actual_week}</td><td>${escapeHtml(s.stage)}</td><td>${escapeHtml(s.status)}</td><td>${s.attempts}</td><td>${escapeHtml(s.message)}</td></tr>`).join('');
      summary.innerHTML = data.stages.length ? data.stages.map(s => `<div class="stage-line"><strong>L${s.lesson_number}</strong><span>${escapeHtml(s.stage)}</span><span>${escapeHtml(s.status)}</span><span>×${s.attempts}</span></div>`).join('') : '<div class="activity-empty">Waiting for the first stage…</div>';
      const known = new Set([...entries.children].map(e => e.dataset.name));
      data.entries.slice().reverse().forEach(item => { if (known.has(item.name)) return; const box=document.createElement('div'); box.className=`log-entry ${item.kind}`; box.dataset.name=item.name; const button=document.createElement('button'); button.type='button'; button.dataset.url=`/api/jobs/${jobId}/llm-logs/${item.bucket}/${encodeURIComponent(item.name)}`; button.innerHTML=`<span>${escapeHtml(item.kind.toUpperCase())}</span><span>${escapeHtml(item.name.replace(jobId+'-',''))}</span>`; button.addEventListener('click',()=>openEntry(button)); box.appendChild(button); const meta=document.createElement('div'); meta.className='log-meta'; meta.textContent=`${new Date(item.updated_at).toLocaleTimeString()} · ${Math.ceil(item.size/1024)} KB`; box.appendChild(meta); entries.prepend(box); });
      if (['success','finished'].includes(data.job.status)) location.href=`/jobs/${jobId}/result`;
    } catch (_) { summary.textContent = 'Live update temporarily unavailable. Retrying…'; }
  }
  refresh(); setInterval(refresh, 3000);
})();
