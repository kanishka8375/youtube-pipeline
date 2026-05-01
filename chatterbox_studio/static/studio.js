// Chatterbox Studio frontend — vanilla JS, no frameworks.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

const PRESETS = {
  conversational: { exaggeration: 0.5,  cfg_weight: 0.5, temperature: 0.8 },
  narration:      { exaggeration: 0.4,  cfg_weight: 0.6, temperature: 0.7 },
  dramatic:       { exaggeration: 0.85, cfg_weight: 0.4, temperature: 1.1 },
};
const EU_LANGS  = ["en", "es", "fr", "de", "it", "pt", "nl", "pl", "sv", "fi", "no", "da", "el", "tr"];
const ASIA_LANGS = ["zh", "ja", "ko", "hi", "ms"];

const state = {
  languages: [],
  langSet: new Set(),
  recentLangs: ["en"],
  selectedLang: "en",
  refs: [],
  selectedRef: null, // null = default voice
  preset: "conversational",
  params: { ...PRESETS.conversational, seed: null, language_transfer: false },
  jobId: null,
  jobPoll: null,
  statusPoll: null,
  audioBuffer: null,
  audioCtx: null,
  player: null,
  history: [],
  batchSelected: new Set(),
  batchActive: null, // {batchId, jobIds}
  batchPoll: null,
};

// ----------- toast -----------
function toast(msg, type = "info") {
  const el = $("#toast");
  el.textContent = msg;
  el.className = "toast" + (type === "error" ? " error" : "");
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (el.hidden = true), 3000);
}

// ----------- routing -----------
function gotoRoute(name) {
  $$(".route").forEach((r) => (r.hidden = r.dataset.route !== name));
  $$(".rail-item").forEach((b) => b.classList.toggle("active", b.dataset.route === name));
  if (name === "history") loadHistory();
  if (name === "voices") renderVoiceGrid();
  if (name === "queue") refreshQueue();
  if (name === "batch") renderBatchGrid();
}

document.addEventListener("click", (e) => {
  const target = e.target.closest("[data-route]");
  if (target) {
    gotoRoute(target.dataset.route);
  }
});

// ----------- status polling -----------
async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function pollStatus() {
  try {
    const s = await fetchJSON("/api/status");
    const dev = s.device || {};
    $("#device-label").textContent = (dev.device || "cpu").toUpperCase();
    const devDot = $("#device-pill .dot");
    devDot.className = "dot " + (dev.device === "cuda" ? "dot--success" : dev.device === "mps" ? "dot--accent" : "dot--muted");
    if (dev.vram_free_gb != null) {
      $("#device-pill").title = `${dev.name} • ${dev.vram_free_gb} GB free`;
    } else {
      $("#device-pill").title = dev.name || "CPU";
    }

    const m = s.model || {};
    $("#model-label").textContent =
      m.status === "ready" ? "Ready" :
      m.status === "loading" ? "Loading model…" :
      m.status === "error" ? "Error" :
      "Idle";
    const modelDot = $("#model-pill .dot");
    modelDot.className = "dot " + (
      m.status === "ready" ? "dot--success" :
      m.status === "loading" ? "dot--warn" :
      m.status === "error" ? "dot--danger" :
      "dot--muted"
    );

    const queued = (s.queue?.queued || 0) + (s.queue?.generating || 0);
    $("#queue-count").textContent = queued;
    const railBadge = $("#rail-queue-badge");
    if (queued > 0) {
      railBadge.hidden = false;
      railBadge.textContent = queued;
    } else {
      railBadge.hidden = true;
    }
  } catch (e) {
    /* swallow */
  }
}

// ----------- languages -----------
async function loadLanguages() {
  const data = await fetchJSON("/api/languages");
  state.languages = data.languages;
  state.langSet = new Set(data.languages.map((l) => l.code));
  renderLangChips();
}

function renderLangChips() {
  const root = $("#lang-chips");
  root.innerHTML = "";
  state.recentLangs.forEach((code) => {
    const meta = state.languages.find((l) => l.code === code);
    const btn = document.createElement("button");
    btn.className = "chip" + (code === state.selectedLang ? " active" : "");
    btn.dataset.lang = code;
    btn.innerHTML = `${meta ? meta.name : code} <span class="lang-code">(${code})</span>`;
    btn.addEventListener("click", () => {
      state.selectedLang = code;
      renderLangChips();
      updateChunkHint();
    });
    root.appendChild(btn);
  });
}

$("#lang-add").addEventListener("click", () => {
  const modal = $("#lang-modal");
  modal.hidden = false;
  const list = $("#lang-pick-list");
  const search = $("#lang-search");
  search.value = "";
  function render() {
    const q = search.value.trim().toLowerCase();
    list.innerHTML = "";
    state.languages
      .filter((l) => !q || l.name.toLowerCase().includes(q) || l.code.includes(q))
      .forEach((l) => {
        const row = document.createElement("div");
        row.className = "lp-row";
        row.innerHTML = `<span>${l.name}</span><span class="lp-code">${l.code}</span>`;
        row.addEventListener("click", () => {
          if (!state.recentLangs.includes(l.code)) {
            state.recentLangs.unshift(l.code);
            if (state.recentLangs.length > 8) state.recentLangs.pop();
          }
          state.selectedLang = l.code;
          renderLangChips();
          modal.hidden = true;
        });
        list.appendChild(row);
      });
  }
  search.oninput = render;
  render();
  setTimeout(() => search.focus(), 50);
});

// ----------- voice cards -----------
async function loadRefs() {
  const data = await fetchJSON("/api/refs");
  state.refs = data.refs || [];
  renderVoiceCards();
  renderVoiceGrid();
}

function renderVoiceCards() {
  const root = $("#voice-cards");
  root.innerHTML = "";

  const def = document.createElement("div");
  def.className = "voice-card" + (state.selectedRef === null ? " active" : "");
  def.innerHTML = `
    <div class="vc-name">Default</div>
    <div class="vc-thumb"></div>
    <div class="vc-sub">Built-in voice</div>
  `;
  def.addEventListener("click", () => {
    state.selectedRef = null;
    renderVoiceCards();
  });
  root.appendChild(def);

  state.refs.forEach((r) => {
    const card = document.createElement("div");
    card.className = "voice-card" + (state.selectedRef === r.name ? " active" : "");
    card.innerHTML = `
      <div class="vc-name">${escapeHtml(r.name)}</div>
      <div class="vc-thumb"></div>
      <div class="vc-sub">${(r.duration_sec || 0).toFixed(1)}s ref</div>
    `;
    card.addEventListener("click", () => {
      state.selectedRef = r.name;
      renderVoiceCards();
    });
    root.appendChild(card);
  });

  const add = document.createElement("div");
  add.className = "voice-card add";
  add.textContent = "+ Upload";
  add.addEventListener("click", () => openUploadModal());
  root.appendChild(add);
}

function renderVoiceGrid() {
  const root = $("#voice-grid");
  if (!root) return;
  root.innerHTML = "";
  if (state.refs.length === 0) {
    root.innerHTML = `<div class="hint">No reference voices yet — upload a 5–10 s audio clip to clone a voice across all 23 languages.</div>`;
    return;
  }
  state.refs.forEach((r) => {
    const c = document.createElement("div");
    c.className = "vg-card";
    c.innerHTML = `
      <div class="vg-name">${escapeHtml(r.name)}</div>
      <div class="vg-meta">${(r.duration_sec || 0).toFixed(1)}s • ${escapeHtml(r.filename || "")}</div>
      <div class="vg-actions">
        <button class="btn small" data-act="select">Use</button>
        <button class="btn small ghost" data-act="delete">Delete</button>
      </div>
    `;
    c.querySelector('[data-act="select"]').addEventListener("click", () => {
      state.selectedRef = r.name;
      renderVoiceCards();
      gotoRoute("studio");
      toast(`Selected "${r.name}"`);
    });
    c.querySelector('[data-act="delete"]').addEventListener("click", async () => {
      if (!confirm(`Delete reference voice "${r.name}"?`)) return;
      await fetchJSON(`/api/refs/${encodeURIComponent(r.name)}`, { method: "DELETE" });
      if (state.selectedRef === r.name) state.selectedRef = null;
      await loadRefs();
    });
    root.appendChild(c);
  });
}

$("#voice-upload-btn").addEventListener("click", openUploadModal);

function openUploadModal() {
  $("#upload-name").value = "";
  $("#upload-file").value = "";
  $("#upload-error").textContent = "";
  $("#upload-modal").hidden = false;
}

$("#upload-confirm").addEventListener("click", async () => {
  const name = $("#upload-name").value.trim();
  const file = $("#upload-file").files[0];
  if (!name) { $("#upload-error").textContent = "Name required"; return; }
  if (!file) { $("#upload-error").textContent = "File required"; return; }
  const fd = new FormData();
  fd.append("name", name);
  fd.append("file", file);
  try {
    await fetchJSON("/api/refs", { method: "POST", body: fd });
    $("#upload-modal").hidden = true;
    await loadRefs();
    toast(`Uploaded "${name}"`);
  } catch (e) {
    $("#upload-error").textContent = e.message;
  }
});

// ----------- presets / sliders -----------
function applyPreset(name) {
  state.preset = name;
  if (PRESETS[name]) {
    Object.assign(state.params, PRESETS[name]);
    syncSlidersFromState();
  }
  $$(".preset-chip").forEach((c) => c.classList.toggle("active", c.dataset.preset === name));
}

function syncSlidersFromState() {
  ["exaggeration", "cfg_weight", "temperature"].forEach((k) => {
    const slider = $("#" + k);
    const label = $("#" + k + "-value");
    slider.value = state.params[k];
    label.textContent = (+state.params[k]).toFixed(2);
  });
}

$$(".preset-chip").forEach((c) =>
  c.addEventListener("click", () => applyPreset(c.dataset.preset))
);
$("#reset-settings").addEventListener("click", () => applyPreset("conversational"));

["exaggeration", "cfg_weight", "temperature"].forEach((k) => {
  const slider = $("#" + k);
  slider.addEventListener("input", () => {
    state.params[k] = +slider.value;
    $("#" + k + "-value").textContent = (+slider.value).toFixed(2);
    state.preset = "custom";
    $$(".preset-chip").forEach((c) => c.classList.toggle("active", c.dataset.preset === "custom"));
  });
});

$("#seed").addEventListener("input", (e) => {
  const v = e.target.value;
  state.params.seed = v === "" ? null : Number(v);
});

$("#seed-random").addEventListener("click", () => {
  const v = Math.floor(Math.random() * (2 ** 31 - 1));
  $("#seed").value = v;
  state.params.seed = v;
});

$("#language-transfer").addEventListener("change", (e) => {
  state.params.language_transfer = e.target.checked;
  $("#cfg_weight").disabled = e.target.checked;
});

// ----------- script + chunk hint -----------
const scriptInput = $("#script-input");
scriptInput.addEventListener("input", () => {
  $("#char-count").textContent = scriptInput.value.length;
  updateChunkHint();
});

function updateChunkHint() {
  const len = scriptInput.value.length;
  let chunks = 1;
  if (len > 300) chunks = Math.ceil(len / 280);
  $("#chunk-hint").textContent = chunks === 1 ? "1 chunk" : `${chunks} chunks`;
}

// ----------- generate (single) -----------
$("#generate-btn").addEventListener("click", () => generate());

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
    e.preventDefault();
    generate();
  } else if (e.key === "?" && !inEditableField(e.target)) {
    $("#hotkeys-modal").hidden = false;
  } else if (!inEditableField(e.target)) {
    if (e.key === "q" || e.key === "Q") gotoRoute("queue");
    else if (e.key === "h" || e.key === "H") gotoRoute("history");
    else if (e.key === "v" || e.key === "V") gotoRoute("voices");
    else if (e.key === "b" || e.key === "B") gotoRoute("batch");
    else if (/^[1-9]$/.test(e.key)) {
      const idx = parseInt(e.key, 10) - 1;
      const code = state.recentLangs[idx];
      if (code) {
        state.selectedLang = code;
        renderLangChips();
      }
    }
  }
});

function inEditableField(el) {
  if (!el) return false;
  const tag = (el.tagName || "").toLowerCase();
  return tag === "textarea" || tag === "input" || el.isContentEditable;
}

async function generate() {
  const text = scriptInput.value.trim();
  if (!text) { toast("Type some text first", "error"); return; }
  const payload = {
    text,
    language_id: state.selectedLang,
    ref_name: state.selectedRef,
    exaggeration: state.params.exaggeration,
    cfg_weight: state.params.cfg_weight,
    temperature: state.params.temperature,
    seed: state.params.seed,
    language_transfer: state.params.language_transfer,
  };
  try {
    const data = await fetchJSON("/api/synthesize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.jobId = data.job_id;
    showPlayerPlaceholder();
    toast(`Queued (${data.chunks} chunk${data.chunks === 1 ? "" : "s"})`);
    if (state.jobPoll) clearInterval(state.jobPoll);
    state.jobPoll = setInterval(pollJob, 800);
  } catch (e) {
    toast(e.message, "error");
  }
}

async function pollJob() {
  if (!state.jobId) return;
  try {
    const j = await fetchJSON(`/api/status/${state.jobId}`);
    if (j.state === "complete") {
      clearInterval(state.jobPoll); state.jobPoll = null;
      onJobComplete(j);
    } else if (j.state === "error") {
      clearInterval(state.jobPoll); state.jobPoll = null;
      toast(j.error || "Generation failed", "error");
      hidePlayer();
    } else {
      drawProgress(j.progress || 0);
    }
  } catch (e) { /* network blip — keep polling */ }
}

function showPlayerPlaceholder() {
  $("#player-panel").hidden = false;
  $("#player-meta").textContent = "Generating…";
  drawProgress(0);
}

function hidePlayer() {
  $("#player-panel").hidden = true;
}

function drawProgress(p) {
  const c = $("#waveform");
  const ctx = c.getContext("2d");
  const w = c.width, h = c.height;
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#1f2230";
  for (let x = 0; x < w; x += 4) {
    const amp = (Math.sin((x + Date.now() / 200) * 0.04) * 0.4 + 0.5) * (h * 0.6);
    ctx.fillRect(x, h / 2 - amp / 2, 2, amp);
  }
  ctx.fillStyle = "rgba(124,92,255,0.7)";
  ctx.fillRect(0, h - 4, w * p, 4);
}

async function onJobComplete(j) {
  const c = $("#waveform");
  const ctx = c.getContext("2d");
  const audio = $("#player-audio");
  audio.src = j.audio_url + "?t=" + Date.now();
  audio.load();

  await drawWaveformFromUrl(j.audio_url, ctx, c.width, c.height);
  $("#player-meta").textContent = `${j.duration_sec || 0}s • ${j.chunk_count} chunk${j.chunk_count === 1 ? "" : "s"} • ${j.language_id}`;
  $("#dl-btn").onclick = () => {
    const a = document.createElement("a");
    a.href = j.audio_url;
    a.download = `chatterbox-${j.id}.wav`;
    a.click();
  };
  $("#srt-btn").onclick = () => {
    const srt = buildSRT(j);
    navigator.clipboard.writeText(srt).then(() => toast("SRT copied"));
  };
  $("#reroll-btn").onclick = async () => {
    try {
      const r = await fetchJSON(`/api/history/${j.id}/reroll`, { method: "POST" });
      state.jobId = r.job_id;
      showPlayerPlaceholder();
      if (state.jobPoll) clearInterval(state.jobPoll);
      state.jobPoll = setInterval(pollJob, 800);
    } catch (e) { toast(e.message, "error"); }
  };
}

async function drawWaveformFromUrl(url, ctx, w, h) {
  try {
    if (!state.audioCtx) state.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const arr = await fetch(url).then((r) => r.arrayBuffer());
    const buf = await state.audioCtx.decodeAudioData(arr);
    state.audioBuffer = buf;
    drawWaveform(buf, ctx, w, h);
  } catch (e) {
    drawWaveformFlat(ctx, w, h);
  }
}

function drawWaveform(buf, ctx, w, h) {
  ctx.clearRect(0, 0, w, h);
  const ch = buf.getChannelData(0);
  const step = Math.max(1, Math.floor(ch.length / w));
  ctx.fillStyle = "#7C5CFF";
  for (let x = 0; x < w; x++) {
    let min = 1, max = -1;
    for (let i = 0; i < step; i++) {
      const v = ch[x * step + i] || 0;
      if (v < min) min = v;
      if (v > max) max = v;
    }
    const yMin = (1 + min) * 0.5 * h;
    const yMax = (1 + max) * 0.5 * h;
    ctx.fillRect(x, yMin, 1, Math.max(1, yMax - yMin));
  }
}

function drawWaveformFlat(ctx, w, h) {
  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#262936";
  ctx.fillRect(0, h / 2 - 1, w, 2);
}

function buildSRT(j) {
  const total = j.duration_sec || 0;
  const chunks = j.chunk_count || 1;
  const each = total / chunks;
  const out = [];
  let t = 0;
  for (let i = 0; i < chunks; i++) {
    out.push(`${i + 1}\n${fmtTs(t)} --> ${fmtTs(t + each)}\n[chunk ${i + 1}]\n`);
    t += each;
  }
  return out.join("\n");
}

function fmtTs(sec) {
  const ms = Math.floor((sec % 1) * 1000);
  const s = Math.floor(sec) % 60;
  const m = Math.floor(sec / 60) % 60;
  const h = Math.floor(sec / 3600);
  return `${pad(h)}:${pad(m)}:${pad(s)},${String(ms).padStart(3, "0")}`;
}
function pad(n) { return String(n).padStart(2, "0"); }

// ----------- player controls -----------
const audio = $("#player-audio");
$("#play-btn").addEventListener("click", () => {
  if (audio.paused) audio.play(); else audio.pause();
});
audio.addEventListener("play",  () => $("#play-btn").textContent = "❚❚");
audio.addEventListener("pause", () => $("#play-btn").textContent = "▶");
audio.addEventListener("ended", () => $("#play-btn").textContent = "▶");
audio.addEventListener("timeupdate", () => {
  const t = audio.currentTime || 0;
  const d = audio.duration || 0;
  $("#player-time").textContent = `${fmtClock(t)} / ${fmtClock(d)}`;
  $("#player-seek").value = d ? (t / d) * 1000 : 0;
});
$("#player-seek").addEventListener("input", (e) => {
  if (audio.duration) audio.currentTime = (e.target.value / 1000) * audio.duration;
});
function fmtClock(s) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, "0")}`;
}

// ----------- batch -----------
function renderBatchGrid() {
  const root = $("#batch-grid");
  if (!root) return;
  root.innerHTML = "";
  state.languages.forEach((l) => {
    const card = document.createElement("div");
    card.className = "lg-card" + (state.batchSelected.has(l.code) ? " selected" : "");
    card.innerHTML = `<div class="lg-name">${l.name}</div><div class="lg-code">${l.code}</div>`;
    card.addEventListener("click", () => {
      if (state.batchSelected.has(l.code)) state.batchSelected.delete(l.code);
      else state.batchSelected.add(l.code);
      renderBatchGrid();
      $("#batch-count").textContent = state.batchSelected.size;
    });
    root.appendChild(card);
  });
  $("#batch-count").textContent = state.batchSelected.size;
}

$$("[data-batch-preset]").forEach((b) => {
  b.addEventListener("click", () => {
    if (b.dataset.batchPreset === "all") state.batchSelected = new Set(state.languages.map((l) => l.code));
    else if (b.dataset.batchPreset === "eu") state.batchSelected = new Set(EU_LANGS);
    else if (b.dataset.batchPreset === "asia") state.batchSelected = new Set(ASIA_LANGS);
    else if (b.dataset.batchPreset === "clear") state.batchSelected.clear();
    renderBatchGrid();
  });
});

$("#batch-input").addEventListener("input", (e) => {
  $("#batch-char-count").textContent = e.target.value.length;
});

$("#batch-generate-btn").addEventListener("click", async () => {
  const text = $("#batch-input").value.trim();
  if (!text) return toast("Type some text first", "error");
  if (state.batchSelected.size === 0) return toast("Select at least one language", "error");
  const payload = {
    text,
    language_ids: Array.from(state.batchSelected),
    ref_name: state.selectedRef,
    exaggeration: state.params.exaggeration,
    cfg_weight: state.params.cfg_weight,
    temperature: state.params.temperature,
    seed: state.params.seed,
    language_transfer: state.params.language_transfer,
  };
  try {
    const data = await fetchJSON("/api/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.batchActive = data;
    $("#batch-progress-panel").hidden = false;
    if (state.batchPoll) clearInterval(state.batchPoll);
    state.batchPoll = setInterval(pollBatch, 1000);
    pollBatch();
    toast(`Queued ${data.job_ids.length} job${data.job_ids.length === 1 ? "" : "s"}`);
  } catch (e) { toast(e.message, "error"); }
});

async function pollBatch() {
  if (!state.batchActive) return;
  const root = $("#batch-list");
  root.innerHTML = "";
  let allDone = true;
  for (const id of state.batchActive.job_ids) {
    let j;
    try { j = await fetchJSON(`/api/status/${id}`); } catch { continue; }
    const row = document.createElement("div");
    row.className = "batch-row";
    row.innerHTML = `
      <span class="lang-tag">${j.language_id}</span>
      <span class="snippet">${escapeHtml((j.text || "").slice(0, 80))}</span>
      <span class="state ${j.state}">${j.state}</span>
      <span>${j.audio_url ? `<a href="${j.audio_url}" download>Download</a>` : ""}</span>
    `;
    root.appendChild(row);
    if (j.state !== "complete" && j.state !== "error" && j.state !== "cancelled") allDone = false;
  }
  if (allDone) {
    clearInterval(state.batchPoll); state.batchPoll = null;
    toast("Batch complete");
  }
}

// ----------- history -----------
async function loadHistory() {
  try {
    const data = await fetchJSON("/api/history");
    state.history = data.entries || [];
    renderHistory();
  } catch (e) { toast(e.message, "error"); }
}
$("#history-search").addEventListener("input", () => renderHistory());

function renderHistory() {
  const root = $("#history-list");
  const q = ($("#history-search").value || "").toLowerCase();
  root.innerHTML = "";
  const rows = state.history.filter((e) => !q || (e.text || "").toLowerCase().includes(q));
  if (rows.length === 0) {
    root.innerHTML = `<div class="hint">No history yet.</div>`;
    return;
  }
  rows.forEach((e) => {
    const row = document.createElement("div");
    row.className = "history-row";
    const when = e.finished_at ? new Date(e.finished_at * 1000).toLocaleString() : "";
    row.innerHTML = `
      <span class="lang-tag">${e.language_id}</span>
      <span class="snippet">${escapeHtml((e.text || "").slice(0, 140))}</span>
      <span class="when">${when}</span>
      <span class="actions">
        <button class="btn small ghost" data-act="play">▶</button>
        <button class="btn small ghost" data-act="reroll">↻</button>
        <button class="btn small ghost" data-act="load">📋</button>
        <button class="btn small ghost" data-act="del">🗑</button>
      </span>
    `;
    row.querySelector('[data-act="play"]').addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (!e.audio_url) return;
      const a = new Audio(e.audio_url);
      a.play();
    });
    row.querySelector('[data-act="reroll"]').addEventListener("click", async (ev) => {
      ev.stopPropagation();
      try {
        const r = await fetchJSON(`/api/history/${e.id}/reroll`, { method: "POST" });
        state.jobId = r.job_id;
        gotoRoute("studio");
        showPlayerPlaceholder();
        if (state.jobPoll) clearInterval(state.jobPoll);
        state.jobPoll = setInterval(pollJob, 800);
      } catch (err) { toast(err.message, "error"); }
    });
    row.querySelector('[data-act="load"]').addEventListener("click", (ev) => {
      ev.stopPropagation();
      scriptInput.value = e.text || "";
      $("#char-count").textContent = scriptInput.value.length;
      state.selectedLang = e.language_id;
      if (!state.recentLangs.includes(e.language_id)) state.recentLangs.unshift(e.language_id);
      if (e.params) Object.assign(state.params, e.params);
      syncSlidersFromState();
      state.selectedRef = e.ref_name || null;
      renderLangChips();
      renderVoiceCards();
      gotoRoute("studio");
    });
    row.querySelector('[data-act="del"]').addEventListener("click", async (ev) => {
      ev.stopPropagation();
      if (!confirm("Delete this entry?")) return;
      await fetchJSON(`/api/history/${e.id}`, { method: "DELETE" });
      loadHistory();
    });
    root.appendChild(row);
  });
}

// ----------- queue -----------
async function refreshQueue() {
  try {
    const data = await fetchJSON("/api/jobs");
    fillQueueCol("#q-generating", data.generating);
    fillQueueCol("#q-queued", data.queued);
    fillQueueCol("#q-recent", data.recent);
  } catch (e) { /* ignore */ }
}
function fillQueueCol(sel, items) {
  const root = $(sel);
  root.innerHTML = "";
  if (!items || items.length === 0) {
    root.innerHTML = `<div class="hint">—</div>`;
    return;
  }
  items.forEach((j) => {
    const card = document.createElement("div");
    card.className = "queue-card";
    const elapsed = j.started_at ? Math.round((Date.now() / 1000 - j.started_at)) : null;
    card.innerHTML = `
      <div class="qc-snippet">${escapeHtml((j.text || "").slice(0, 80))}</div>
      <div class="qc-meta">
        <span>${j.language_id} · ${j.state}</span>
        <span>${elapsed != null ? elapsed + "s" : ""}</span>
      </div>
    `;
    root.appendChild(card);
  });
}

// ----------- modal close -----------
document.addEventListener("click", (e) => {
  if (e.target.matches("[data-close-modal]")) {
    e.target.closest(".modal").hidden = true;
  } else if (e.target.matches(".modal")) {
    e.target.hidden = true;
  }
});

$("#hotkeys-btn").addEventListener("click", () => $("#hotkeys-modal").hidden = false);

// ----------- helpers -----------
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

// ----------- boot -----------
async function boot() {
  syncSlidersFromState();
  await Promise.all([loadLanguages(), loadRefs()]);
  pollStatus();
  state.statusPoll = setInterval(pollStatus, 2000);
  setInterval(() => {
    const route = $$(".route").find((r) => !r.hidden)?.dataset.route;
    if (route === "queue") refreshQueue();
  }, 1500);
}
boot();
