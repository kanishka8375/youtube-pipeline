// ChatterBox Studio v2 — vanilla JS, ComfyUI-style multi-model TTS.

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

const PARAM_SCHEMAS = {
  tts_turbo: [
    { key: 'temperature', label: 'Temperature', min: 0.05, max: 2.0, step: 0.05, default: 0.8, hint: 'randomness' },
    { key: 'top_p', label: 'Top P', min: 0, max: 1, step: 0.01, default: 0.95 },
    { key: 'top_k', label: 'Top K', min: 0, max: 1000, step: 10, default: 1000 },
    { key: 'repetition_penalty', label: 'Repetition Penalty', min: 1.0, max: 2.0, step: 0.05, default: 1.2 },
    { key: 'min_p', label: 'Min P', min: 0, max: 1, step: 0.01, default: 0.0, hint: '0 = off' },
    { key: 'norm_loudness', label: 'Normalize Loudness (−27 LUFS)', type: 'toggle', default: true },
  ],
  tts: [
    { key: 'exaggeration', label: 'Exaggeration', min: 0.25, max: 2.0, step: 0.05, default: 0.5, hint: 'neutral = 0.5' },
    { key: 'cfg_weight', label: 'CFG / Pace', min: 0, max: 1, step: 0.05, default: 0.5, hint: 'lower = slower' },
    { key: 'temperature', label: 'Temperature', min: 0.05, max: 5, step: 0.05, default: 0.8 },
    { key: 'min_p', label: 'Min P', min: 0, max: 1, step: 0.01, default: 0.05 },
    { key: 'top_p', label: 'Top P', min: 0, max: 1, step: 0.01, default: 1.0 },
    { key: 'repetition_penalty', label: 'Repetition Penalty', min: 1.0, max: 2.0, step: 0.1, default: 1.2 },
  ],
  mtl_tts: [
    { key: 'exaggeration', label: 'Exaggeration', min: 0.25, max: 2.0, step: 0.05, default: 0.5, hint: 'neutral = 0.5' },
    { key: 'cfg_weight', label: 'CFG / Pace', min: 0.2, max: 1.0, step: 0.05, default: 0.5, hint: '0 = lang transfer' },
    { key: 'temperature', label: 'Temperature', min: 0.05, max: 5, step: 0.05, default: 0.8 },
  ],
  onnx: [
    { key: 'temperature', label: 'Temperature', min: 0.05, max: 2.0, step: 0.05, default: 0.8 },
    { key: 'top_p', label: 'Top P', min: 0, max: 1, step: 0.01, default: 0.95 },
    { key: 'top_k', label: 'Top K', min: 0, max: 1000, step: 10, default: 1000 },
    { key: 'repetition_penalty', label: 'Repetition Penalty', min: 1.0, max: 2.0, step: 0.05, default: 1.2 },
  ],
};

const state = {
  models: [],          // from /api/models
  languages: [],
  device: 'cuda',
  activeModelId: localStorage.getItem('cb_active') || 'chatterbox-multilingual',
  text: '',
  params: {},
  language: 'fr',
  refName: null,       // saved server-side ref name
  refFile: null,       // pending unsaved upload (object URL only)
  seed: 0,
  jobId: null,
  jobPoll: null,
  statusPoll: null,
  audioBuf: null,
  audioCtx: null,
  // UI panels
  leftTab: 'voices',
  managerOpen: false,
  managerModel: null,
  managerTab: 'install',
  history: [],
  // waveform animation
  wavState: 'idle',
  wavRaf: null,
};

// ─── tiny helpers ───────────────────────────────────────────────────────────
async function api(path, opts) {
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;" }[c]));
}

function showToast(msg, type = 'info') {
  const el = $('#toast');
  el.textContent = msg;
  el.className = 'toast ' + type;
  el.classList.remove('hidden');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.add('hidden'), 2800);
}

function activeModel() { return state.models.find(m => m.id === state.activeModelId) || state.models[0]; }
function isInstalled(id) { const m = state.models.find(x => x.id === id); return !!(m && m.status && m.status.installed); }

// ─── Topbar status loop ─────────────────────────────────────────────────────
async function refreshTopStatus() {
  try {
    const s = await api('/api/status');
    state.device = (s.device || {}).device || 'cpu';
    const sel = $('#device-select');
    if (sel.value !== state.device) sel.value = state.device;
    const dot = $('#device-dot');
    dot.classList.toggle('muted', state.device === 'cpu');
    sel.title = (s.device.name || '') + (s.device.vram_free_gb != null ? ` · ${s.device.vram_free_gb} GB free` : '');
  } catch {}
}

// ─── Models load + render ──────────────────────────────────────────────────
async function loadModels() {
  const data = await api('/api/models');
  state.models = data.models;
  // ensure activeModelId is valid
  if (!state.models.find(m => m.id === state.activeModelId)) {
    state.activeModelId = state.models[0]?.id;
  }
  renderLeft();
  renderModelHeader();
  renderParams();
  renderFolderInfo();
  renderStatusCard();
  if (state.managerOpen) renderManagerList();
}

function renderLeft() {
  const body = $('#left-body');
  if (state.leftTab === 'voices') {
    const installed = state.models.filter(m => m.status?.installed).length;
    body.innerHTML = `
      <div class="section-title">Available Models · ${installed}/${state.models.length} installed</div>
      <div id="voice-cards"></div>
      <button class="add-models" id="add-models-btn">+ Add / Manage Models</button>`;
    const host = $('#voice-cards');
    host.innerHTML = '';
    state.models.forEach(m => host.appendChild(renderVoiceCard(m)));
    $('#add-models-btn').addEventListener('click', () => openManager());
  } else {
    const items = state.history;
    body.innerHTML = `
      <div class="section-title">
        Generation History
        ${items.length ? '<button class="clear-btn" id="clear-history">clear</button>' : ''}
      </div>
      <div id="history-rows"></div>
      ${items.length ? '' : '<div class="empty-state">No generations yet</div>'}
    `;
    const rows = $('#history-rows');
    items.forEach(it => rows.appendChild(renderHistoryEntry(it)));
    if (items.length) {
      $('#clear-history').addEventListener('click', async () => {
        await Promise.all(items.map(i => api(`/api/history/${i.id}`, { method: 'DELETE' }).catch(() => {})));
        await loadHistory();
      });
    }
  }
}

function renderVoiceCard(m) {
  const inst = !!m.status?.installed;
  const active = state.activeModelId === m.id;
  const card = document.createElement('div');
  card.className = 'voice-card' + (active ? ' active' : '') + (inst ? '' : ' uninstalled');
  card.style.borderColor = active ? m.variant_color : '';
  card.innerHTML = `
    <div class="voice-card-head">
      <span class="variant-pill" style="color:${m.variant_color}; background:${m.variant_color}22">${escapeHtml(m.variant)}</span>
      <span class="install-tag ${inst ? 'ok' : 'no'}">${inst ? '✓ installed' : 'not installed'}</span>
    </div>
    <div class="voice-card-name">${escapeHtml(m.label)}</div>
    <div class="voice-card-desc">${escapeHtml(m.desc)}</div>
    <div class="voice-card-meta">
      <span>${escapeHtml(m.size)}</span><span class="sep">·</span>
      <span>${escapeHtml(m.lang)}</span><span class="sep">·</span>
      <span>${escapeHtml(m.total_gb)}</span>
    </div>
    ${inst ? '' : '<div class="voice-card-cta">⬇ Download required</div>'}
  `;
  card.addEventListener('click', () => {
    state.activeModelId = m.id;
    localStorage.setItem('cb_active', m.id);
    state.text = m.default_text || state.text;
    state.params = { ...m.params };
    syncTextInput();
    renderLeft();
    renderModelHeader();
    renderParams();
    renderFolderInfo();
    renderStatusCard();
    if (!inst) openManager(m.id);
  });
  return card;
}

function renderHistoryEntry(it) {
  const m = state.models.find(x => x.id === it.model_id) || {};
  const div = document.createElement('div');
  div.className = 'history-entry';
  const variant = m.variant || it.model_id || '';
  const vc = m.variant_color || '#888';
  div.innerHTML = `
    <div class="history-head">
      <span class="variant-pill" style="color:${vc}; background:${vc}22">${escapeHtml(variant)}</span>
      <span class="history-meta" style="margin-left:auto">${(it.duration_sec ?? '-')}s</span>
      <span class="history-meta">·</span>
      <span class="history-meta">24kHz</span>
      <button class="iconbtn play-h" title="Play">▶</button>
      <button class="iconbtn dim dl-h" title="Download">↓</button>
    </div>
    <div class="history-snippet">${escapeHtml(it.text || '')}</div>
    <div class="history-time">${new Date((it.finished_at || it.enqueued_at || 0) * 1000).toLocaleString()}</div>
  `;
  div.querySelector('.play-h').addEventListener('click', e => {
    e.stopPropagation();
    if (!it.audio_url) return;
    const a = new Audio(it.audio_url); a.play();
  });
  div.querySelector('.dl-h').addEventListener('click', e => {
    e.stopPropagation();
    if (!it.audio_url) return;
    const a = document.createElement('a'); a.href = it.audio_url; a.download = `chatterbox-${it.id}.wav`; a.click();
  });
  div.addEventListener('click', () => {
    state.text = it.text;
    state.activeModelId = it.model_id || state.activeModelId;
    state.params = { ...(it.params || {}) };
    state.leftTab = 'voices';
    setTab('voices');
    syncTextInput();
    renderModelHeader();
    renderParams();
    renderFolderInfo();
  });
  return div;
}

// ─── Center: model header + tag/lang bars ──────────────────────────────────
function renderModelHeader() {
  const m = activeModel();
  if (!m) return;
  $('#mh-pill').textContent = m.variant;
  $('#mh-pill').style.color = m.variant_color;
  $('#mh-pill').style.background = m.variant_color + '22';
  $('#mh-name').textContent = m.label;
  $('#mh-desc').textContent = m.desc;

  const cta = $('#mh-cta-slot');
  cta.innerHTML = '';
  const inst = !!m.status?.installed;
  if (inst) {
    const span = document.createElement('span'); span.className = 'model-ready'; span.textContent = '✓ Ready';
    cta.appendChild(span);
  } else {
    const btn = document.createElement('button'); btn.className = 'btn danger'; btn.textContent = '⬇ Download model';
    btn.addEventListener('click', () => openManager(m.id));
    cta.appendChild(btn);
  }

  // Tags bar (Turbo / ONNX)
  const tags = m.tags || [];
  const tagsBar = $('#tags-bar');
  if ((m.type === 'tts_turbo' || m.type === 'onnx') && tags.length) {
    tagsBar.innerHTML = '<span class="subbar-label">TAGS</span>';
    tags.forEach(t => {
      const b = document.createElement('button');
      b.className = 'tag-chip';
      b.textContent = t;
      b.addEventListener('click', () => {
        const ta = $('#text-input');
        ta.value = (ta.value + ' ' + t).trim();
        state.text = ta.value;
        updateCharCount();
      });
      tagsBar.appendChild(b);
    });
    tagsBar.classList.remove('hidden');
  } else {
    tagsBar.classList.add('hidden');
  }

  // Language bar (MTL)
  const langBar = $('#lang-bar');
  if (m.type === 'mtl_tts') {
    const sel = $('#lang-select');
    sel.innerHTML = '';
    state.languages.forEach(l => {
      const o = document.createElement('option');
      o.value = l.code; o.textContent = `${l.name} (${l.code})`;
      sel.appendChild(o);
    });
    sel.value = state.params.language_id || 'en';
    sel.onchange = () => { state.params.language_id = sel.value; };
    langBar.classList.remove('hidden');
  } else {
    langBar.classList.add('hidden');
  }
}

// ─── Right panel: parameters ───────────────────────────────────────────────
function renderParams() {
  const m = activeModel(); if (!m) return;
  const schema = PARAM_SCHEMAS[m.type] || [];
  const host = $('#params-host');
  host.innerHTML = '';
  schema.forEach(sp => {
    if (sp.type === 'toggle') host.appendChild(renderToggle(sp));
    else host.appendChild(renderSlider(sp));
  });
}

function renderSlider(sp) {
  const wrap = document.createElement('div'); wrap.className = 'slider-row';
  const cur = state.params[sp.key] ?? sp.default;
  const pct = ((cur - sp.min) / (sp.max - sp.min)) * 100;
  wrap.innerHTML = `
    <div class="slider-head">
      <span class="slider-label">${escapeHtml(sp.label)}</span>
      <span class="slider-value" data-key="${sp.key}">${formatVal(cur, sp.step)}</span>
    </div>
    ${sp.hint ? `<div class="slider-hint">${escapeHtml(sp.hint)}</div>` : ''}
    <div class="slider-track">
      <div class="slider-fill" style="width:${pct}%"></div>
      <input type="range" min="${sp.min}" max="${sp.max}" step="${sp.step}" value="${cur}" />
    </div>
  `;
  const input = wrap.querySelector('input[type="range"]');
  const fill = wrap.querySelector('.slider-fill');
  const valEl = wrap.querySelector('.slider-value');
  input.addEventListener('input', () => {
    const v = parseFloat(input.value);
    state.params[sp.key] = v;
    fill.style.width = ((v - sp.min) / (sp.max - sp.min)) * 100 + '%';
    valEl.textContent = formatVal(v, sp.step);
  });
  // click-to-edit value
  valEl.addEventListener('click', () => {
    const inputEl = document.createElement('input');
    inputEl.className = 'slider-value-input';
    inputEl.value = formatVal(state.params[sp.key] ?? sp.default, sp.step);
    valEl.replaceWith(inputEl); inputEl.focus(); inputEl.select();
    const commit = () => {
      let v = parseFloat(inputEl.value);
      if (!isNaN(v)) {
        v = Math.max(sp.min, Math.min(sp.max, v));
        state.params[sp.key] = v;
        input.value = v;
        fill.style.width = ((v - sp.min) / (sp.max - sp.min)) * 100 + '%';
      }
      const newVal = document.createElement('span');
      newVal.className = 'slider-value';
      newVal.dataset.key = sp.key;
      newVal.textContent = formatVal(state.params[sp.key] ?? sp.default, sp.step);
      newVal.addEventListener('click', valEl.onclick);
      inputEl.replaceWith(newVal);
      // re-bind click handler since we replaced the node
      renderParams();
    };
    inputEl.addEventListener('blur', commit);
    inputEl.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === 'Escape') { e.preventDefault(); commit(); }
    });
  });
  return wrap;
}

function renderToggle(sp) {
  const cur = state.params[sp.key] ?? sp.default;
  const wrap = document.createElement('div'); wrap.className = 'toggle-row';
  wrap.innerHTML = `
    <span class="slider-label">${escapeHtml(sp.label)}</span>
    <div class="toggle-pill ${cur ? 'on' : ''}"></div>
  `;
  wrap.querySelector('.toggle-pill').addEventListener('click', e => {
    state.params[sp.key] = !state.params[sp.key];
    e.currentTarget.classList.toggle('on', state.params[sp.key]);
  });
  return wrap;
}

function formatVal(v, step) {
  if (step >= 1) return String(parseInt(v, 10));
  if (step >= 0.1) return v.toFixed(1);
  return v.toFixed(2);
}

// ─── Folder + status cards ─────────────────────────────────────────────────
function renderFolderInfo() {
  const m = activeModel(); if (!m) return;
  $('#folder-path').textContent = (m.local_folder || '').replace(/\/$/, '') + '/';
  const host = $('#folder-files'); host.innerHTML = '';
  const present = new Set(m.status?.files_present || []);
  (m.required_files || []).forEach(f => {
    const div = document.createElement('div');
    div.className = 'file' + (present.has(f) ? ' present' : '');
    div.textContent = (present.has(f) ? '✓ ' : '· ') + f;
    host.appendChild(div);
  });
  $('#folder-help').onclick = () => openManager(m.id);
}

function renderStatusCard() {
  const m = activeModel(); if (!m) return;
  const st = m.status || {};
  const card = $('#status-card');
  card.classList.toggle('ok', !!st.installed);
  card.classList.toggle('bad', !st.installed);
  $('#status-head').textContent = st.installed ? '✓ Model installed' : '✗ Model not found';
  $('#status-body').innerHTML = st.installed
    ? `Found in <code style="color:#5a7a4a">${escapeHtml(st.where_path || st.where || '')}</code>`
    : `Place files in:<br/><code style="color:#5a3a2a">${escapeHtml(m.local_folder)}</code><br/>then click Refresh Models`;
}

// ─── Reference voice (single ad-hoc upload, design v2 pattern) ─────────────
$('#ref-browse').addEventListener('click', () => $('#ref-file').click());
$('#refzone').addEventListener('click', () => $('#ref-file').click());
$('#ref-clear').addEventListener('click', e => {
  e.stopPropagation();
  state.refName = null; state.refFile = null;
  setRefUI(null);
});
$('#ref-file').addEventListener('change', async e => {
  const f = e.target.files?.[0]; if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  fd.append('name', f.name.replace(/\.[^.]+$/, '').slice(0, 64));
  try {
    const r = await api('/api/refs', { method: 'POST', body: fd });
    state.refName = r.ref.name;
    setRefUI(r.ref);
    showToast(`Voice reference: ${r.ref.name}`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
});

function setRefUI(ref) {
  const z = $('#refzone'), icon = $('#ref-icon'), name = $('#ref-name'), sub = $('#ref-sub'), browse = $('#ref-browse'), clear = $('#ref-clear');
  if (ref) {
    z.classList.add('has-ref');
    icon.textContent = '🎵';
    name.textContent = ref.name;
    name.classList.add('has-ref');
    sub.textContent = `Click to change · ${(ref.duration_sec || 0).toFixed(1)}s · WAV / MP3 / FLAC`;
    browse.classList.add('hidden');
    clear.classList.remove('hidden');
  } else {
    z.classList.remove('has-ref');
    icon.textContent = '🎤';
    name.textContent = 'Upload reference audio clip';
    name.classList.remove('has-ref');
    sub.textContent = '~10 seconds · WAV / MP3 / FLAC · Leave empty for default voice';
    browse.classList.remove('hidden');
    clear.classList.add('hidden');
  }
}

// ─── Text input + char counter ─────────────────────────────────────────────
const textEl = $('#text-input');
textEl.addEventListener('input', () => {
  state.text = textEl.value;
  updateCharCount();
});
function updateCharCount() {
  const len = state.text.length;
  const limit = 300;
  const el = $('#char-count');
  el.textContent = `${len}/${limit}`;
  el.classList.toggle('over', len > limit);
  textEl.classList.toggle('over', len > limit);
}
function syncTextInput() { textEl.value = state.text; updateCharCount(); }

// ─── Seed ──────────────────────────────────────────────────────────────────
$('#seed-input').addEventListener('input', e => { state.seed = parseInt(e.target.value, 10) || 0; });
$('#seed-die').addEventListener('click', () => {
  state.seed = Math.floor(Math.random() * 99999);
  $('#seed-input').value = state.seed;
});

// ─── Generate ──────────────────────────────────────────────────────────────
$('#generate-btn').addEventListener('click', generate);

async function generate() {
  const m = activeModel(); if (!m) return;
  if (!isInstalled(m.id)) { openManager(m.id); showToast(`Download ${m.label} first`, 'warn'); return; }
  if (!state.text.trim()) { showToast('Type some text first', 'warn'); return; }

  setGenButton('gen');
  startWavAnim('gen', m.variant_color);
  $('#output-empty').classList.add('hidden');
  $('#output-loading').classList.remove('hidden');
  $('#output-actions').classList.add('hidden');
  $('#output-player').classList.add('hidden');
  $('#output-model').textContent = m.label;
  $('#output-device').textContent = state.device;

  const payload = {
    text: state.text,
    model_id: m.id,
    ref_name: state.refName,
    seed: state.seed || null,
    ...state.params,
  };
  try {
    const r = await api('/api/synthesize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.jobId = r.job_id;
    showToast(`Queued · ${r.chunks} chunk${r.chunks === 1 ? '' : 's'}`, 'info');
    if (state.jobPoll) clearInterval(state.jobPoll);
    state.jobPoll = setInterval(pollJob, 800);
  } catch (e) {
    setGenButton('idle');
    startWavAnim('idle', m.variant_color);
    $('#output-loading').classList.add('hidden');
    $('#output-empty').classList.remove('hidden');
    showToast(e.message, 'error');
  }
}

async function pollJob() {
  if (!state.jobId) return;
  try {
    const j = await api(`/api/status/${state.jobId}`);
    if (j.state === 'complete') {
      clearInterval(state.jobPoll); state.jobPoll = null;
      onComplete(j);
    } else if (j.state === 'error') {
      clearInterval(state.jobPoll); state.jobPoll = null;
      onError(j);
    }
  } catch {}
}

async function onComplete(j) {
  setGenButton('idle');
  $('#output-loading').classList.add('hidden');
  $('#output-actions').classList.remove('hidden');
  $('#output-stats').textContent = `✓ ${j.duration_sec}s · 24 kHz`;
  $('#output-player').classList.remove('hidden');

  const audio = $('#audio-el'); audio.src = j.audio_url + '?t=' + Date.now(); audio.load();
  $('#dl-wav').onclick = () => {
    const a = document.createElement('a'); a.href = j.audio_url; a.download = `chatterbox-${j.id}.wav`; a.click();
  };
  await drawCompleteWaveform(j.audio_url);
  loadHistory();
  showToast(`✓ Generated ${j.duration_sec}s of speech`, 'success');
}

function onError(j) {
  setGenButton('idle');
  startWavAnim('idle', activeModel()?.variant_color);
  $('#output-loading').classList.add('hidden');
  $('#output-empty').classList.remove('hidden');
  showToast(j.error?.split('\n')[0] || 'Generation failed', 'error');
}

function setGenButton(mode) {
  state.wavState = mode;
  const btn = $('#generate-btn');
  const m = activeModel();
  btn.classList.remove('dim', 'stop', 'disabled-state');
  if (!m) return;
  if (mode === 'gen') {
    btn.textContent = '⏹ Generating…';
    btn.classList.add('stop');
  } else if (!isInstalled(m.id)) {
    btn.textContent = `⬇ Download ${m.label} to Generate`;
    btn.classList.add('dim');
  } else {
    btn.textContent = `${m.variant}  Generate Speech`;
  }
}

// ─── Waveform rendering ────────────────────────────────────────────────────
function startWavAnim(mode, color) {
  state.wavState = mode;
  const c = $('#waveform');
  const ctx = c.getContext('2d');
  const accent = color || '#c96a2e';
  const bars = startWavAnim._bars ||= Array.from({ length: 90 }, () => ({
    phase: Math.random() * Math.PI * 2, speed: 0.4 + Math.random(), h: 2 + Math.random() * 28,
  }));
  if (state.wavRaf) cancelAnimationFrame(state.wavRaf);
  function draw(ts) {
    const W = c.width, H = c.height, N = bars.length, bw = W / N;
    ctx.clearRect(0, 0, W, H);
    bars.forEach((b, i) => {
      let h;
      if (state.wavState === 'gen') h = 6 + Math.abs(Math.sin(ts / 350 * b.speed + b.phase)) * (H * 0.72);
      else if (state.wavState === 'done') h = b.h * Math.sin((i / N) * Math.PI) + 2;
      else h = 1 + Math.abs(Math.sin(ts / 2400 + b.phase)) * 4;
      const x = i * bw + bw * 0.1, y = (H - h) / 2;
      const a = state.wavState === 'gen' ? 0.25 + (h / H) * 0.75 : state.wavState === 'done' ? 0.82 : 0.12;
      ctx.fillStyle = accent + Math.round(a * 255).toString(16).padStart(2, '0');
      if (ctx.roundRect) { ctx.beginPath(); ctx.roundRect(x, y, bw * 0.8, h, 1.5); ctx.fill(); }
      else { ctx.fillRect(x, y, bw * 0.8, h); }
    });
    state.wavRaf = requestAnimationFrame(draw);
  }
  state.wavRaf = requestAnimationFrame(draw);
}

async function drawCompleteWaveform(url) {
  state.wavState = 'done';
  try {
    if (!state.audioCtx) state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const buf = await state.audioCtx.decodeAudioData(await (await fetch(url)).arrayBuffer());
    const c = $('#waveform'); const ctx = c.getContext('2d');
    const W = c.width, H = c.height;
    const ch = buf.getChannelData(0);
    const step = Math.max(1, Math.floor(ch.length / W));
    if (state.wavRaf) cancelAnimationFrame(state.wavRaf);
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = activeModel()?.variant_color || '#c96a2e';
    for (let x = 0; x < W; x++) {
      let min = 1, max = -1;
      for (let i = 0; i < step; i++) {
        const v = ch[x * step + i] || 0;
        if (v < min) min = v;
        if (v > max) max = v;
      }
      const yMin = (1 + min) * 0.5 * H;
      const yMax = (1 + max) * 0.5 * H;
      ctx.fillRect(x, yMin, 1, Math.max(1, yMax - yMin));
    }
  } catch (e) {
    startWavAnim('done', activeModel()?.variant_color);
  }
}

// ─── Player ────────────────────────────────────────────────────────────────
const audio = $('#audio-el');
$('#play-btn').addEventListener('click', () => {
  if (audio.paused) audio.play(); else audio.pause();
});
audio.addEventListener('play', () => $('#play-btn').textContent = '❚❚');
audio.addEventListener('pause', () => $('#play-btn').textContent = '▶');
audio.addEventListener('ended', () => $('#play-btn').textContent = '▶');
audio.addEventListener('timeupdate', () => {
  const t = audio.currentTime || 0, d = audio.duration || 0;
  $('#time-cur').textContent = clock(t);
  $('#time-tot').textContent = clock(d);
  $('#seek-fill').style.width = d ? (t / d) * 100 + '%' : '0%';
});
$('#seek-track').addEventListener('click', e => {
  const r = e.currentTarget.getBoundingClientRect();
  const p = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width));
  if (audio.duration) audio.currentTime = p * audio.duration;
});
function clock(s) { const m = Math.floor(s / 60), r = Math.floor(s % 60); return `${m}:${String(r).padStart(2, '0')}`; }

// ─── Reset defaults ────────────────────────────────────────────────────────
$('#reset-defaults').addEventListener('click', () => {
  const m = activeModel(); if (!m) return;
  state.params = { ...m.params };
  renderParams();
});

// ─── Tabs (left panel) ─────────────────────────────────────────────────────
$$('.tab').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
function setTab(name) {
  state.leftTab = name;
  $$('.tab').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === name);
    b.setAttribute('aria-selected', b.dataset.tab === name ? 'true' : 'false');
  });
  if (name === 'history') loadHistory();
  renderLeft();
}

async function loadHistory() {
  try { const d = await api('/api/history'); state.history = d.entries || []; if (state.leftTab === 'history') renderLeft(); }
  catch {}
}

// ─── Topbar buttons ────────────────────────────────────────────────────────
$('#device-select').addEventListener('change', e => { state.device = e.target.value; });

$('#refresh-btn').addEventListener('click', refreshModels);
async function refreshModels() {
  const icon = $('#refresh-icon');
  icon.classList.add('active');
  try {
    await api('/api/models/refresh', { method: 'POST' });
    await loadModels();
    showToast('Models refreshed — scanning ' + (activeModel()?.local_folder || ''), 'success');
  } catch (e) {
    showToast(e.message, 'error');
  } finally {
    setTimeout(() => icon.classList.remove('active'), 600);
  }
}

$('#manager-btn').addEventListener('click', () => openManager());

// ─── Manager modal ─────────────────────────────────────────────────────────
function openManager(modelId) {
  state.managerOpen = true;
  state.managerModel = modelId || state.activeModelId;
  state.managerTab = 'install';
  $('#manager-modal').classList.remove('hidden');
  renderManagerList();
  renderManagerDetail();
}

function closeManager() {
  state.managerOpen = false;
  $('#manager-modal').classList.add('hidden');
}

$('#mm-close').addEventListener('click', closeManager);
$('#manager-modal').addEventListener('click', e => {
  if (e.target.id === 'manager-modal') closeManager();
});
$$('.mm-tab').forEach(b => b.addEventListener('click', () => {
  state.managerTab = b.dataset.mmTab;
  $$('.mm-tab').forEach(x => x.classList.toggle('active', x === b));
  renderManagerDetail();
}));

function renderManagerList() {
  const host = $('#mm-list'); host.innerHTML = '';
  state.models.forEach(m => {
    const inst = !!m.status?.installed;
    const item = document.createElement('div');
    item.className = 'mm-list-item' + (state.managerModel === m.id ? ' active' : '');
    item.innerHTML = `
      <div class="mm-item-row1">
        <span class="variant-pill" style="color:${m.variant_color}; background:${m.variant_color}22">${escapeHtml(m.variant)}</span>
        <span class="mm-item-dot ${inst ? 'ok' : 'no'}" title="${inst ? 'Installed' : 'Not installed'}"></span>
      </div>
      <div class="mm-item-name">${escapeHtml(m.label)}</div>
      <div class="mm-item-meta">${escapeHtml(m.size)} · ${escapeHtml(m.total_gb)}</div>
    `;
    item.addEventListener('click', () => { state.managerModel = m.id; renderManagerList(); renderManagerDetail(); });
    host.appendChild(item);
  });
}

function renderManagerDetail() {
  const m = state.models.find(x => x.id === state.managerModel) || state.models[0];
  if (!m) return;
  const inst = !!m.status?.installed;
  $('#mm-title').textContent = m.label;
  const pill = $('#mm-pill');
  pill.textContent = m.variant;
  pill.style.color = m.variant_color;
  pill.style.background = m.variant_color + '22';
  const status = $('#mm-status');
  status.textContent = inst ? '✓ Installed' : '○ Not installed';
  status.classList.toggle('ok', inst);
  status.classList.toggle('no', !inst);
  $('#mm-desc').textContent = m.desc;

  const body = $('#mm-body'); body.innerHTML = '';
  if (state.managerTab === 'install') body.appendChild(renderInstallTab(m));
  else if (state.managerTab === 'path') body.appendChild(renderPathTab(m));
  else body.appendChild(renderCodeTab(m));
}

function renderInstallTab(m) {
  const div = document.createElement('div');
  const present = new Set(m.status?.files_present || []);
  div.innerHTML = `
    <div class="mm-grid">
      <div class="mm-card opt-a">
        <div class="head">OPTION A — Auto (recommended)</div>
        <div class="body">Models download automatically on first <code>from_pretrained()</code> call. Just install the package and run your code.</div>
      </div>
      <div class="mm-card opt-b">
        <div class="head">OPTION B — Manual (offline)</div>
        <div class="body">Download files from HuggingFace, place them in the folder below, then refresh.</div>
        <a class="hf-link" href="https://huggingface.co/${escapeHtml(m.hf_repo)}" target="_blank" rel="noopener">🤗 Open on HuggingFace ↗</a>
      </div>
    </div>
    <div style="margin-bottom:8px"><div class="path-block label">REQUIRED FILES — place all in the model folder:</div></div>
    <div class="files-list" id="mm-files"></div>
  `;
  div.querySelector('#mm-files').innerHTML = '';
  (m.required_files || []).forEach(f => {
    const has = present.has(f);
    const row = document.createElement('div');
    row.className = 'files-list-item' + (has ? ' present' : '');
    row.innerHTML = `
      <span style="font-size:14px">📄</span>
      <span class="name">${escapeHtml(f)}</span>
      <span class="kind">${f.endsWith('.onnx') ? 'onnx' : 'safetensors / pt'}</span>
      <span class="ind ${has ? '' : 'no'}">${has ? '✓ found' : '· missing'}</span>
    `;
    div.querySelector('#mm-files').appendChild(row);
  });
  // Auto-install code snippet
  const snip = document.createElement('div');
  snip.style.marginTop = '14px';
  snip.appendChild(makeSnip('pip install chatterbox-tts'));
  div.appendChild(snip);
  return div;
}

function renderPathTab(m) {
  const winPath = `C:\\ChatterBox\\models\\tts\\${m.id}\\`;
  const macPath = `~/ChatterBox/models/tts/${m.id}/`;
  const hfPath = `~/.cache/huggingface/hub/models--${m.hf_repo.replace('/', '--')}/snapshots/main/`;
  const div = document.createElement('div');
  div.innerHTML = `
    <div class="path-block">
      <div class="label">WINDOWS</div>
      <div id="p1"></div>
    </div>
    <div class="path-block">
      <div class="label">macOS / LINUX</div>
      <div id="p2"></div>
    </div>
    <div class="path-block">
      <div class="label">HuggingFace CACHE (auto-download path)</div>
      <div id="p3"></div>
    </div>
    <div class="tree-card">
      <div class="head">📁 Expected folder structure</div>
      <pre>ChatterBox/
└── models/
    └── tts/
        └── ${escapeHtml(m.id)}/
${(m.required_files || []).map(f => `            ├── ${escapeHtml(f)}`).join('\n')}</pre>
      <div class="foot">
        💡 After placing files, click <strong style="color:var(--muted)">Refresh Models</strong> in the top bar or press <kbd>R</kbd>
      </div>
    </div>
    <div class="env-card">
      <div class="head">🔗 Custom path via env var</div>
      <div id="p4"></div>
    </div>
  `;
  div.querySelector('#p1').appendChild(makeSnip(winPath));
  div.querySelector('#p2').appendChild(makeSnip(macPath));
  div.querySelector('#p3').appendChild(makeSnip(hfPath));
  div.querySelector('#p4').appendChild(makeSnip(`# Set BEFORE importing chatterbox\nimport os\nos.environ["HF_HOME"] = "/your/custom/path"\nos.environ["CHATTERBOX_MODELS_DIR"] = "/your/models"`));
  return div;
}

function renderCodeTab(m) {
  let snippet;
  if (m.type === 'tts_turbo') {
    snippet = `from chatterbox.tts_turbo import ChatterboxTurboTTS
import torchaudio as ta

model = ChatterboxTurboTTS.from_pretrained(device="cuda")

text = "Hi there [chuckle], have you got a minute?"
wav = model.generate(text, audio_prompt_path="ref.wav")
ta.save("output.wav", wav, model.sr)`;
  } else if (m.type === 'tts') {
    snippet = `from chatterbox.tts import ChatterboxTTS
import torchaudio as ta

model = ChatterboxTTS.from_pretrained(device="cuda")

wav = model.generate(
    "Your text here",
    exaggeration=0.7,
    cfg_weight=0.3,
    audio_prompt_path="voice_ref.wav",
)
ta.save("output.wav", wav, model.sr)`;
  } else if (m.type === 'mtl_tts') {
    snippet = `from chatterbox.mtl_tts import ChatterboxMultilingualTTS
import torchaudio as ta

model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")

# French
wav = model.generate(
    "Bonjour, comment ça va?",
    language_id="fr",
    audio_prompt_path="french_ref.wav",
)
ta.save("output_fr.wav", wav, model.sr)`;
  } else {
    snippet = `# ONNX — no PyTorch needed
from huggingface_hub import hf_hub_download
import onnxruntime

model_path = hf_hub_download("${m.hf_repo}", "t3_turbo_fp32.onnx")
session = onnxruntime.InferenceSession(model_path)`;
  }
  const div = document.createElement('div');
  div.innerHTML = `
    <div class="path-block label">QUICK START</div>
    <div id="c1"></div>
    <div class="path-block label" style="margin-top:14px">USE THIS STUDIO FROM CLI</div>
    <div id="c2"></div>
  `;
  div.querySelector('#c1').appendChild(makeSnip(snippet));
  div.querySelector('#c2').appendChild(makeSnip(`# Drop required files into:\n${m.local_folder}\n# Then start the studio (auto-rescan on R):\npython chatterbox_app.py --auto-launch`));
  return div;
}

function makeSnip(text) {
  const wrap = document.createElement('div'); wrap.className = 'snip';
  wrap.innerHTML = `<pre></pre><button class="copy">copy</button>`;
  wrap.querySelector('pre').textContent = text;
  const copy = wrap.querySelector('.copy');
  copy.addEventListener('click', () => {
    navigator.clipboard.writeText(text).catch(() => {});
    copy.textContent = '✓ copied';
    copy.classList.add('copied');
    setTimeout(() => { copy.textContent = 'copy'; copy.classList.remove('copied'); }, 1500);
  });
  return wrap;
}

// ─── Hotkeys (ComfyUI-style) ───────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') { e.preventDefault(); generate(); return; }
  if (inEditable(e.target)) return;
  const k = e.key.toLowerCase();
  if (k === 'r') refreshModels();
  else if (k === 'm') openManager();
  else if (k === 'escape' && state.managerOpen) closeManager();
  else if (/^[1-9]$/.test(k)) {
    const idx = parseInt(k, 10) - 1;
    const m = state.models[idx];
    if (m) {
      state.activeModelId = m.id;
      localStorage.setItem('cb_active', m.id);
      state.params = { ...m.params };
      state.text = m.default_text || state.text;
      syncTextInput();
      renderLeft(); renderModelHeader(); renderParams(); renderFolderInfo(); renderStatusCard();
    }
  }
});
function inEditable(el) {
  if (!el) return false;
  const tag = (el.tagName || '').toLowerCase();
  return tag === 'textarea' || tag === 'input' || el.isContentEditable;
}

// ─── Boot ──────────────────────────────────────────────────────────────────
async function boot() {
  // language list (shared)
  try { const l = await api('/api/languages'); state.languages = l.languages; } catch { state.languages = []; }
  await loadModels();
  await loadHistory();
  await refreshTopStatus();

  // initial state from active model
  const m = activeModel();
  if (m) {
    if (!state.text) state.text = m.default_text || '';
    state.params = { ...m.params };
    syncTextInput();
    renderModelHeader(); renderParams(); renderFolderInfo(); renderStatusCard();
  }

  startWavAnim('idle', m?.variant_color);
  setGenButton('idle');

  // background polling
  state.statusPoll = setInterval(refreshTopStatus, 2500);
}
boot();
