"""Flask app for the Chatterbox Multilingual Voice-over Studio.

Run:
    pip install -r requirements-chatterbox.txt
    python chatterbox_app.py        # serves on http://localhost:5001
"""

from __future__ import annotations

import re
import shutil
import time
import uuid
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory, abort
from flask_cors import CORS

from chatterbox_studio import history, job_queue, chunker, tts_engine

ROOT = Path(__file__).parent / "chatterbox_studio"
OUTPUTS_DIR = ROOT / "outputs"
REFS_DIR = ROOT / "refs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
REFS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(
    __name__,
    template_folder=str(ROOT / "templates"),
    static_folder=str(ROOT / "static"),
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024  # 20 MB ref uploads
CORS(app)

_NAME_RE = re.compile(r"[^A-Za-z0-9 _\-]+")


def _safe_name(name: str) -> str:
    name = _NAME_RE.sub("", (name or "").strip()).strip()
    return name[:64] or f"voice-{uuid.uuid4().hex[:6]}"


@app.route("/")
def index():
    tts_engine.warm_up_async()
    return render_template("studio.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "model": tts_engine.get_load_state(),
        "device": tts_engine.get_device_info(),
        "queue": job_queue.counts(),
    })


@app.route("/api/languages")
def api_languages():
    langs = tts_engine.get_supported_languages()
    rows = [{"code": code, "name": name} for code, name in sorted(langs.items(), key=lambda x: x[1])]
    return jsonify({"languages": rows})


@app.route("/api/refs", methods=["GET"])
def api_refs_list():
    return jsonify({"refs": history.list_refs()})


@app.route("/api/refs", methods=["POST"])
def api_refs_upload():
    if "file" not in request.files:
        return jsonify({"error": "missing 'file'"}), 400
    file = request.files["file"]
    name = _safe_name(request.form.get("name") or Path(file.filename or "voice").stem)

    tmp = REFS_DIR / f".tmp-{uuid.uuid4().hex[:8]}"
    file.save(tmp)
    try:
        sha = tts_engine.sha256_file(tmp)
        ext = (Path(file.filename or "").suffix or ".wav").lower()
        if ext not in {".wav", ".mp3", ".flac", ".m4a", ".ogg"}:
            tmp.unlink(missing_ok=True)
            return jsonify({"error": f"unsupported audio extension {ext}"}), 400
        final = REFS_DIR / f"{sha[:16]}{ext}"
        if not final.exists():
            shutil.move(str(tmp), final)
        else:
            tmp.unlink(missing_ok=True)
        duration = _probe_duration(final)
        entry = history.add_ref(name, sha, file.filename or final.name, str(final), duration)
        return jsonify({"ref": entry})
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/refs/<name>", methods=["DELETE"])
def api_refs_delete(name: str):
    ok = history.delete_ref(_safe_name(name))
    return jsonify({"ok": ok})


@app.route("/refs/<path:filename>")
def serve_ref(filename: str):
    return send_from_directory(REFS_DIR, filename)


def _probe_duration(path: Path) -> float:
    try:
        import torchaudio as ta

        info = ta.info(str(path))
        return round(info.num_frames / float(info.sample_rate), 2)
    except Exception:
        return 0.0


def _resolve_ref(ref_name: str | None):
    if not ref_name:
        return None, None
    entry = history.get_ref(_safe_name(ref_name))
    if not entry:
        return None, None
    return entry["path"], entry["name"]


def _parse_params(src: dict) -> dict:
    def f(key, default, lo, hi):
        try:
            return max(lo, min(hi, float(src.get(key, default))))
        except (TypeError, ValueError):
            return default

    params = {
        "exaggeration": f("exaggeration", 0.5, 0.25, 2.0),
        "cfg_weight": f("cfg_weight", 0.5, 0.0, 1.0),
        "temperature": f("temperature", 0.8, 0.05, 5.0),
    }
    if str(src.get("language_transfer", "")).lower() in ("1", "true", "on", "yes"):
        params["cfg_weight"] = 0.0
    seed = src.get("seed")
    if seed not in (None, "", "random"):
        try:
            params["seed"] = int(seed)
        except (TypeError, ValueError):
            pass
    return params


@app.route("/api/synthesize", methods=["POST"])
def api_synthesize():
    payload = request.get_json(silent=True) or request.form.to_dict()
    text = (payload.get("text") or "").strip()
    language_id = (payload.get("language_id") or "en").strip()
    if not text:
        return jsonify({"error": "text required"}), 400
    if language_id not in tts_engine.get_supported_languages():
        return jsonify({"error": f"unsupported language_id {language_id}"}), 400

    params = _parse_params(payload)
    ref_path, ref_name = _resolve_ref(payload.get("ref_name"))
    job = job_queue.enqueue(text, language_id, params, ref_path=ref_path, ref_name=ref_name)
    return jsonify({"job_id": job.id, "chunks": chunker.estimate_chunks(text, language_id)})


@app.route("/api/batch", methods=["POST"])
def api_batch():
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "").strip()
    language_ids = payload.get("language_ids") or []
    if not text:
        return jsonify({"error": "text required"}), 400
    supported = tts_engine.get_supported_languages()
    language_ids = [lid for lid in language_ids if lid in supported]
    if not language_ids:
        return jsonify({"error": "no valid language_ids"}), 400

    params = _parse_params(payload)
    ref_path, ref_name = _resolve_ref(payload.get("ref_name"))
    batch_id = uuid.uuid4().hex[:12]
    job_ids = []
    for lid in language_ids:
        job = job_queue.enqueue(text, lid, params, ref_path=ref_path, ref_name=ref_name, batch_id=batch_id)
        job_ids.append(job.id)
    return jsonify({"batch_id": batch_id, "job_ids": job_ids})


@app.route("/api/status/<job_id>")
def api_job_status(job_id: str):
    job = job_queue.get(job_id)
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify(job.to_dict())


@app.route("/api/jobs")
def api_jobs():
    return jsonify(job_queue.list_active())


@app.route("/api/jobs/<job_id>/cancel", methods=["POST"])
def api_cancel(job_id: str):
    return jsonify({"ok": job_queue.cancel(job_id)})


@app.route("/api/history")
def api_history_list():
    return jsonify({"entries": history.list_entries(200)})


@app.route("/api/history/<entry_id>", methods=["DELETE"])
def api_history_delete(entry_id: str):
    return jsonify({"ok": history.delete_entry(entry_id)})


@app.route("/api/history/<entry_id>/reroll", methods=["POST"])
def api_history_reroll(entry_id: str):
    entry = history.get_entry(entry_id)
    if not entry:
        return jsonify({"error": "not found"}), 404
    params = dict(entry.get("params") or {})
    import random
    params["seed"] = random.randint(1, 2 ** 31 - 1)
    ref_path, ref_name = _resolve_ref(entry.get("ref_name"))
    job = job_queue.enqueue(
        entry["text"],
        entry["language_id"],
        params,
        ref_path=ref_path,
        ref_name=ref_name,
    )
    return jsonify({"job_id": job.id})


@app.route("/audio/<path:filename>")
def serve_audio(filename: str):
    return send_from_directory(OUTPUTS_DIR, filename)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "ts": time.time()})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
