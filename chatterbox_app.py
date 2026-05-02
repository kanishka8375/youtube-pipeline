"""ChatterBox Studio — Flask web app, ComfyUI-style multi-model TTS.

Run:
    pip install -r requirements-chatterbox.txt
    python chatterbox_app.py                       # http://localhost:5001
    python chatterbox_app.py --port 8188 --auto-launch
    python chatterbox_app.py --models-dir /custom/path

Drop model files into chatterbox_studio/models/tts/<model-id>/ then click
"⟳ Refresh Models" in the top bar (or press R) — exactly like ComfyUI.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import time
import uuid
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, jsonify, render_template, request, send_from_directory
from flask_cors import CORS

from chatterbox_studio import (
    chunker,
    history,
    job_queue,
    models_registry,
    system_info,
    tts_engine,
)

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
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
CORS(app)

_NAME_RE = re.compile(r"[^A-Za-z0-9 _\-]+")


def _safe_name(name: str) -> str:
    name = _NAME_RE.sub("", (name or "").strip()).strip()
    return name[:64] or f"voice-{uuid.uuid4().hex[:6]}"


# ─── Pages ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("studio.html")


# ─── Models registry (ComfyUI-style) ──────────────────────────────────────────

@app.route("/api/models")
def api_models():
    """Full registry + per-model install status."""
    return jsonify({
        "models": models_registry.serialize_models(include_status=True),
        "search_roots_default": str(models_registry.MODELS_DIR),
    })


@app.route("/api/models/refresh", methods=["POST"])
def api_models_refresh():
    """Rescan model folders. Equivalent to pressing R in ComfyUI."""
    statuses = models_registry.refresh()
    return jsonify({"ok": True, "statuses": statuses})


@app.route("/api/models/<model_id>/warm", methods=["POST"])
def api_models_warm(model_id: str):
    if not models_registry.find_by_id(model_id):
        return jsonify({"error": "unknown model"}), 404
    tts_engine.warm_up_async(model_id)
    return jsonify({"ok": True, "state": tts_engine.get_load_state(model_id)})


@app.route("/api/models/<model_id>/state")
def api_models_state(model_id: str):
    return jsonify(tts_engine.get_load_state(model_id))


# ─── System / runtime ─────────────────────────────────────────────────────────

@app.route("/api/system_stats")
def api_system_stats():
    return jsonify(system_info.collect())


@app.route("/api/free", methods=["POST"])
def api_free():
    payload = request.get_json(silent=True) or {}
    model_id = payload.get("model_id")
    return jsonify(tts_engine.unload(model_id))


@app.route("/api/languages")
def api_languages():
    return jsonify({"languages": models_registry.supported_languages()})


# ─── Reference voices ─────────────────────────────────────────────────────────

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
    return jsonify({"ok": history.delete_ref(_safe_name(name))})


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


def _resolve_ref(ref_name):
    if not ref_name:
        return None, None
    entry = history.get_ref(_safe_name(ref_name))
    if not entry:
        return None, None
    return entry["path"], entry["name"]


# ─── Synthesis ────────────────────────────────────────────────────────────────

def _coerce_params(model_entry, src: dict) -> dict:
    """Filter and clamp per-model params from raw request body."""
    p = {}

    def num(key, default, lo, hi):
        try:
            return max(lo, min(hi, float(src.get(key, default))))
        except (TypeError, ValueError):
            return default

    if model_entry.type == "tts_turbo" or model_entry.type == "onnx":
        p["temperature"] = num("temperature", 0.8, 0.05, 2.0)
        p["top_p"] = num("top_p", 0.95, 0.0, 1.0)
        p["top_k"] = int(num("top_k", 1000, 0, 1000))
        p["repetition_penalty"] = num("repetition_penalty", 1.2, 1.0, 2.0)
        p["min_p"] = num("min_p", 0.0, 0.0, 1.0)
        p["norm_loudness"] = bool(src.get("norm_loudness", True))
    elif model_entry.type == "tts":
        p["exaggeration"] = num("exaggeration", 0.5, 0.25, 2.0)
        p["cfg_weight"] = num("cfg_weight", 0.5, 0.0, 1.0)
        p["temperature"] = num("temperature", 0.8, 0.05, 5.0)
        p["min_p"] = num("min_p", 0.05, 0.0, 1.0)
        p["top_p"] = num("top_p", 1.0, 0.0, 1.0)
        p["repetition_penalty"] = num("repetition_penalty", 1.2, 1.0, 2.0)
    elif model_entry.type == "mtl_tts":
        p["exaggeration"] = num("exaggeration", 0.5, 0.25, 2.0)
        p["cfg_weight"] = num("cfg_weight", 0.5, 0.0, 1.0)
        p["temperature"] = num("temperature", 0.8, 0.05, 5.0)
        lid = str(src.get("language_id", "en")).strip()
        if lid not in {l["code"] for l in models_registry.supported_languages()}:
            lid = "en"
        p["language_id"] = lid

    seed = src.get("seed")
    if seed not in (None, "", "random", 0, "0"):
        try:
            p["seed"] = int(seed)
        except (TypeError, ValueError):
            pass
    return p


@app.route("/api/synthesize", methods=["POST"])
def api_synthesize():
    payload = request.get_json(silent=True) or request.form.to_dict()
    text = (payload.get("text") or "").strip()
    model_id = (payload.get("model_id") or "chatterbox-multilingual").strip()
    if not text:
        return jsonify({"error": "text required"}), 400

    entry = models_registry.find_by_id(model_id)
    if not entry:
        return jsonify({"error": f"unknown model_id {model_id}"}), 400

    status = models_registry.detect_install_status().get(model_id, {})
    if not status.get("installed"):
        return jsonify({
            "error": f"model {model_id} is not installed",
            "files_missing": status.get("files_missing", []),
            "local_folder": status.get("local_folder"),
        }), 409

    params = _coerce_params(entry, payload)
    ref_path, ref_name = _resolve_ref(payload.get("ref_name"))
    job = job_queue.enqueue(text, model_id, params, ref_path=ref_path, ref_name=ref_name)
    return jsonify({
        "job_id": job.id,
        "model_id": model_id,
        "chunks": chunker.estimate_chunks(text, params.get("language_id", "en")),
    })


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
    import random
    params = dict(entry.get("params") or {})
    params["seed"] = random.randint(1, 2 ** 31 - 1)
    ref_path, ref_name = _resolve_ref(entry.get("ref_name"))
    model_id = entry.get("model_id") or "chatterbox-multilingual"
    job = job_queue.enqueue(entry["text"], model_id, params, ref_path=ref_path, ref_name=ref_name)
    return jsonify({"job_id": job.id})


@app.route("/audio/<path:filename>")
def serve_audio(filename: str):
    return send_from_directory(OUTPUTS_DIR, filename)


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "ts": time.time()})


# ─── Status (combined topbar payload) ─────────────────────────────────────────

@app.route("/api/status")
def api_status():
    """Topbar payload: device + per-model load state + queue counts."""
    states = tts_engine.get_load_state()
    statuses = models_registry.detect_install_status()
    return jsonify({
        "device": _device_summary(),
        "load_state": states,
        "install_status": statuses,
        "queue": job_queue.counts(),
    })


def _device_summary() -> dict:
    info = system_info.collect()
    devs = info.get("devices") or [{"type": "cpu", "name": "CPU"}]
    primary = devs[0]
    return {
        "device": primary.get("type", "cpu"),
        "name": primary.get("name", "CPU"),
        "vram_free_gb": primary.get("vram_free_gb"),
    }


# ─── CLI / entry ──────────────────────────────────────────────────────────────

def _open_browser_later(url: str, delay: float = 1.2):
    Timer(delay, lambda: webbrowser.open_new_tab(url)).start()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="ChatterBox Studio — multi-model TTS web UI (ComfyUI-style)",
    )
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "5001")))
    parser.add_argument("--models-dir", default=None,
                        help="Override CHATTERBOX_MODELS_DIR (where to scan for model files)")
    parser.add_argument("--output-dir", default=None,
                        help="Where generated WAVs are written (default: chatterbox_studio/outputs)")
    parser.add_argument("--auto-launch", action="store_true", help="Open the studio in the default browser")
    parser.add_argument("--no-warm-up", action="store_true",
                        help="Don't pre-load any model on startup (default: don't preload)")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    if args.models_dir:
        os.environ["CHATTERBOX_MODELS_DIR"] = args.models_dir
        # rebind the registry root since module already imported
        models_registry.MODELS_DIR = Path(args.models_dir)
    if args.output_dir:
        out = Path(args.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        OUTPUTS_DIR_resolved = out
        # Patch the queue's output directory + the route
        job_queue.OUTPUTS_DIR = OUTPUTS_DIR_resolved
        app.view_functions["serve_audio"] = lambda filename: send_from_directory(OUTPUTS_DIR_resolved, filename)

    # Re-scan after possibly overriding the models dir
    models_registry.refresh()

    url = f"http://{'localhost' if args.host in ('0.0.0.0','127.0.0.1') else args.host}:{args.port}/"
    banner = f"\n  ChatterBox Studio — {url}\n  Models dir: {models_registry.MODELS_DIR}\n"
    print(banner)

    if args.auto_launch:
        _open_browser_later(url)

    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)


if __name__ == "__main__":
    main()
