(() => {
  const card = document.querySelector('[data-activity]');
  if (!card) return;
  const drawer = document.querySelector('#llm-drawer'), entries = document.querySelector('#llm-entries');
  const toggle = document.querySelector('#activity-toggle'), close = document.querySelector('#activity-close');
  const backdrop = document.querySelector('#drawer-backdrop');
  const friendly = value => String(value || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const make = (tag, text, cls) => { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (cls) el.className = cls; return el; };
  drawer.setAttribute('role', 'dialog'); drawer.setAttribute('aria-modal', 'true'); drawer.setAttribute('aria-label', 'LLM activity');
  toggle.setAttribute('aria-controls', 'llm-drawer'); toggle.setAttribute('aria-expanded', 'false'); drawer.inert = true;
  const setOpen = open => { drawer.classList.toggle('open', open); backdrop.classList.toggle('open', open); drawer.inert = !open; drawer.setAttribute('aria-hidden', String(!open)); toggle.setAttribute('aria-expanded', String(open)); (open ? close : toggle).focus(); };
  toggle.addEventListener('click', () => setOpen(true)); close.addEventListener('click', () => setOpen(false)); backdrop.addEventListener('click', () => setOpen(false));
  drawer.addEventListener('keydown', event => {
    if (event.key === 'Escape') setOpen(false);
    if (event.key !== 'Tab') return;
    const items = [...drawer.querySelectorAll('button,input,select,summary')].filter(el => el.getClientRects().length && !el.disabled);
    if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1).focus(); }
    else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0].focus(); }
  });
  const tools = make('div', undefined, 'activity-tools');
  const searchLabel = make('label', 'Find a request or response'); const search = make('input'); search.type = 'search'; search.placeholder = 'Search lesson, stage, or content…'; searchLabel.append(search);
  const filterLabel = make('label', 'Show'); const filter = make('select');
  for (const [value, label] of [['all','All activity'],['request','Prompts'],['response','Responses'],['diagnostic','Errors and retries']]) { const option = make('option', label); option.value = value; filter.append(option); }
  filterLabel.append(filter); tools.append(searchLabel, filterLabel);
  const status = make('p', 'Loading activity…', 'muted'); status.setAttribute('role','status');
  const stageSummary = make('p', '', 'activity-stage-summary');
  entries.before(tools, status, stageSummary); entries.replaceChildren();
  const empty = make('p', 'No activity yet. Requests will appear when generation begins.', 'muted'); entries.append(empty);
  const records = [], liveRecords = new Map(), stages = new Map(), seen = new Set(); let cursor = 0;
  function formatTelemetry(value) {
    if (!value || typeof value !== 'object') return '';
    const exact = Number.isFinite(Number(value.completion_tokens)) ? `${Number(value.completion_tokens)} output tokens` : `~${Number(value.output_tokens_estimate || 0)} output tokens`;
    const prompt = Number.isFinite(Number(value.prompt_tokens)) ? `${Number(value.prompt_tokens)} prompt tokens` : `~${Number(value.prompt_tokens_estimate || 0)} prompt tokens`;
    return `${exact} · ${Number(value.output_characters || value.content_characters || 0)} characters · ${Number(value.elapsed_seconds || 0).toFixed(1)}s · ${Number(value.tokens_per_second || 0).toFixed(1)} tokens/s · ${prompt}`;
  }
  function applyFilter() { let count = 0; for (const r of [...records, ...liveRecords.values()]) { r.node.hidden = !((filter.value === 'all' || r.kind === filter.value) && r.search.includes(search.value.toLowerCase())); if (!r.node.hidden) count++; } empty.hidden = count > 0; empty.textContent = records.length || liveRecords.size ? 'No matching entries. Try another search or filter.' : 'No activity yet. Requests will appear when generation begins.'; }
  search.addEventListener('input', applyFilter); filter.addEventListener('change', applyFilter);
  function addLive(event) {
    const d = event.detail || {}, id = String(d.id || '');
    if (!id) return;
    let record = liveRecords.get(id);
    if (!record) {
      const box = make('details', undefined, 'llm-entry response live-entry'); box.open = true;
      const summary = make('summary');
      summary.append(make('span', 'Live output', 'activity-kind'), make('strong'), make('small'));
      const stats = make('div', '', 'live-stats');
      const pre = make('pre', 'Waiting for the first token…', 'activity-readable');
      box.append(summary, stats, pre); entries.prepend(box);
      record = {node: box, summary, stats, pre, content: '', kind: 'response', search: ''};
      liveRecords.set(id, record);
    }
    if (d.content_delta) record.content += String(d.content_delta);
    const location = card.dataset.tool === 'cblm' ? `LO ${d.lo || '?'} · Topic ${d.topic || '?'}` : `Lesson ${d.lesson || '?'} · Week ${d.week || '?'}`;
    const title = `${location} · ${friendly(d.stage || 'request')} · Attempt ${d.attempt || '?'}`;
    record.summary.querySelector('strong').textContent = title;
    record.summary.querySelector('small').textContent = `${friendly(d.status || 'receiving')} · ${new Date(event.created_at).toLocaleString()}`;
    record.stats.textContent = formatTelemetry(d);
    record.pre.textContent = record.content || 'Waiting for the first token…';
    record.search = `${title} ${record.content}`.toLowerCase();
  }

  function add(event) {
    const d = event.detail || {}; if (d.kind !== 'llm') return;
    const identity = `${d.label}:${d.filename}:${d.content}`; if (seen.has(identity)) return; seen.add(identity);
    let parsed; try { parsed = JSON.parse(d.content); } catch { parsed = null; }
    const value = parsed && typeof parsed === 'object' ? parsed : {};
    const kind = value.errors || value.error || d.label === 'diagnostic' ? 'diagnostic' : d.label === 'request' ? 'request' : 'response';
    const match = (d.filename || '').match(/(?:lo(\d+)-topic(\d+)|lesson-(\d+))-(.+?)-(?:request|response|invalid|failed)-(\d+)/);
    const title = match ? `${match[3] ? 'Lesson '+match[3] : 'Learning outcome '+match[1]+(match[2] !== '0' ? ' · Topic '+match[2] : '')} · ${friendly(match[4])} · Attempt ${match[5]}` : 'Generation details';
    const box = make('details', undefined, `llm-entry ${kind}`), summary = make('summary');
    summary.append(make('span', {request:'Prompt sent',response:'Response received',diagnostic:'Needs attention'}[kind], 'activity-kind'), make('strong', title), make('small', new Date(event.created_at).toLocaleString())); box.append(summary);
    const content = make('div', undefined, 'activity-content');
    if (value.errors || value.error) { const error = make('div', undefined, 'activity-error'); error.append(make('strong', 'What needs attention')); const list = make('ul'); for (const item of [].concat(value.errors || value.error)) list.append(make('li', typeof item === 'string' ? item : JSON.stringify(item))); error.append(list); content.append(error); }
    const telemetry = formatTelemetry(value.telemetry || value.usage); if (telemetry) content.append(make('p', telemetry, 'live-stats'));
    const text = value.rejected_text ?? value.extracted_text ?? value.response ?? value.raw_text ?? value.text ?? value.prompt ?? (typeof parsed === 'string' ? parsed : d.content);
    const readable = typeof text === 'string' ? text : JSON.stringify(text, null, 2);
    const copy = make('button', 'Copy '+(kind === 'request' ? 'prompt' : 'response'), 'button secondary'); copy.type = 'button';
    const pre = make('pre', readable, 'activity-readable');
    copy.addEventListener('click', async () => { copy.disabled = true; try { await navigator.clipboard.writeText(readable); copy.textContent = 'Copied'; } catch { copy.textContent = 'Select the text below to copy'; } finally { setTimeout(() => { copy.disabled = false; copy.textContent = 'Copy '+(kind === 'request' ? 'prompt' : 'response'); }, 2000); } });
    content.append(copy, pre);
    const raw = make('details', undefined, 'activity-raw'); raw.append(make('summary', 'Technical details / raw JSON'), make('pre', typeof parsed === 'object' && parsed ? JSON.stringify(parsed, null, 2) : d.content)); content.append(raw);
    box.addEventListener('toggle', () => { if (box.open && !box.contains(content)) box.append(content); });
    entries.prepend(box); records.push({node:box, kind, search:(title+' '+readable).toLowerCase()});
  }
  async function refresh() {
    try {
      const response = await fetch(`${card.dataset.activity}?after=${cursor}`, {cache:'no-store'}); if (!response.ok) throw Error();
      const data = await response.json();
      for (const event of data.events) { const d = event.detail || {}; if (d.kind === 'stage') { const first = card.dataset.tool === 'cblm' ? d.lo_number : d.lesson_number, second = card.dataset.tool === 'cblm' ? d.topic_number : d.actual_week; stages.set(`${first}:${second}:${d.stage}`, {first,second,...d}); } else if (d.kind === 'llm_progress') addLive(event); else add(event); }
      cursor = data.next;
      const rows = document.querySelector('#stage-rows');
      if (stages.size && rows) rows.replaceChildren(...[...stages.values()].map(s => { const row = make('tr'); for (const v of [s.first,s.second,friendly(s.stage),friendly(s.status),s.attempts,s.message]) row.append(make('td', v)); return row; }));
      const completed = [...stages.values()].filter(s => s.status === 'success').length;
      stageSummary.textContent = stages.size ? `${completed} of ${stages.size} recorded stages complete` : '';
      applyFilter();
      const stateResponse = await fetch(card.dataset.events.replace('/events','/status'), {cache:'no-store'}); if (!stateResponse.ok) throw Error(); const state = await stateResponse.json();
      const done = ['success','finished','failed','cancelled','paused','review'].includes(state.status);
      status.textContent = `${records.length + liveRecords.size} entries · ${done ? 'Saved activity · '+friendly(state.status) : 'Updating automatically'}`;
      if (done) return;
    } catch { status.textContent = 'Activity could not refresh. Retrying shortly…'; }
    setTimeout(refresh, 2000);
  }
  refresh();
})();
