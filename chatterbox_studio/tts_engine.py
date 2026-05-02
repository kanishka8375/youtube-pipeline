"""Multi-model wrapper around the three Chatterbox model types.

Lazy-loads exactly one model class per `model_id`, with SHA-256-keyed
caching of reference voice conditionals so repeat refs skip the encoder.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional

from . import models_registry as registry


_models: dict = {}
_model_lock = threading.Lock()
_load_state: dict = {}  # model_id -> {status, error}

_REF_CACHE: "OrderedDict[str, object]" = OrderedDict()
_REF_CACHE_MAX = 16
_ref_lock = threading.Lock()


def get_load_state(model_id: Optional[str] = None) -> dict:
    if model_id is None:
        return {k: dict(v) for k, v in _load_state.items()}
    return dict(_load_state.get(model_id, {"status": "idle", "error": None}))


def _select_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def get_device_info() -> dict:
    info = {"device": "cpu", "name": "CPU", "vram_free_gb": None}
    try:
        import torch

        if torch.cuda.is_available():
            idx = torch.cuda.current_device()
            info["device"] = "cuda"
            info["name"] = torch.cuda.get_device_name(idx)
            free, _total = torch.cuda.mem_get_info(idx)
            info["vram_free_gb"] = round(free / (1024 ** 3), 2)
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            info["device"] = "mps"
            info["name"] = "Apple Silicon (MPS)"
    except Exception:
        pass
    return info


def get_model(model_id: str, device: Optional[str] = None):
    if model_id in _models:
        return _models[model_id]
    entry = registry.find_by_id(model_id)
    if entry is None:
        raise ValueError(f"unknown model_id {model_id}")
    if not entry.import_mod or not entry.import_class:
        raise RuntimeError(f"model {model_id} has no Python loader (ONNX-only)")
    with _model_lock:
        if model_id in _models:
            return _models[model_id]
        _load_state[model_id] = {"status": "loading", "error": None}
        try:
            import importlib
            mod = importlib.import_module(entry.import_mod)
            cls = getattr(mod, entry.import_class)
            dev = device or _select_device()
            m = cls.from_pretrained(device=dev)
            _models[model_id] = m
            _load_state[model_id] = {"status": "ready", "error": None}
            return m
        except Exception as e:
            _load_state[model_id] = {"status": "error", "error": str(e)}
            raise


def warm_up_async(model_id: str) -> None:
    if _load_state.get(model_id, {}).get("status") in ("loading", "ready"):
        return

    def _run():
        try:
            get_model(model_id)
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name=f"chatterbox-warm-{model_id}").start()


def unload(model_id: Optional[str] = None) -> dict:
    """Drop loaded model(s) and free VRAM. Returns counts."""
    with _model_lock:
        ids = [model_id] if model_id else list(_models.keys())
        n = 0
        for mid in ids:
            if mid in _models:
                _models.pop(mid, None)
                _load_state[mid] = {"status": "idle", "error": None}
                n += 1
        with _ref_lock:
            cleared = len(_REF_CACHE)
            _REF_CACHE.clear()
    try:
        import gc, torch
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    return {"models_unloaded": n, "ref_cache_cleared": cleared}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _cache_get(key: str):
    with _ref_lock:
        if key in _REF_CACHE:
            _REF_CACHE.move_to_end(key)
            return _REF_CACHE[key]
        return None


def _cache_put(key: str, value) -> None:
    with _ref_lock:
        _REF_CACHE[key] = value
        _REF_CACHE.move_to_end(key)
        while len(_REF_CACHE) > _REF_CACHE_MAX:
            _REF_CACHE.popitem(last=False)


def synthesize(
    model_id: str,
    text: str,
    ref_path: Optional[str] = None,
    params: Optional[dict] = None,
    seed: Optional[int] = None,
):
    """Run a single synthesis on the chosen model. Returns (wav_cpu, sr)."""
    import torch

    entry = registry.find_by_id(model_id)
    if entry is None:
        raise ValueError(f"unknown model_id {model_id}")

    model = get_model(model_id)
    params = dict(params or {})

    if seed is not None and int(seed) > 0:
        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

    cache_hit = False
    if ref_path:
        key = sha256_file(ref_path)
        cached = _cache_get(key)
        if cached is None:
            try:
                model.prepare_conditionals(ref_path, exaggeration=float(params.get("exaggeration", 0.5)))
                _cache_put(key, getattr(model, "conds", None))
            except Exception:
                pass
        else:
            cache_hit = True
            try:
                model.conds = cached
            except Exception:
                cache_hit = False

    gen_kwargs = {}
    if entry.type == "tts_turbo":
        gen_kwargs = {
            k: params[k]
            for k in ("temperature", "top_p", "top_k", "repetition_penalty", "min_p")
            if k in params
        }
    elif entry.type == "tts":
        gen_kwargs = {
            k: params[k]
            for k in ("exaggeration", "cfg_weight", "temperature", "min_p", "top_p", "repetition_penalty")
            if k in params
        }
    elif entry.type == "mtl_tts":
        gen_kwargs = {
            k: params[k]
            for k in ("exaggeration", "cfg_weight", "temperature")
            if k in params
        }
        gen_kwargs["language_id"] = params.get("language_id", "en")

    if not cache_hit and ref_path:
        gen_kwargs["audio_prompt_path"] = ref_path

    wav = model.generate(text, **gen_kwargs)

    if hasattr(wav, "detach"):
        wav = wav.detach().to("cpu")
    return wav, getattr(model, "sr", 24000)


def save_wav(wav, sr: int, out_path: str | Path) -> str:
    import torchaudio as ta

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if wav.ndim == 1:
        wav = wav.unsqueeze(0)
    ta.save(str(out_path), wav, sr)
    return str(out_path)


def concat_wavs(wavs: list, sr: int, gap_ms: int = 100):
    import torch

    if not wavs:
        raise ValueError("no wavs to concat")
    silence = torch.zeros(int(sr * gap_ms / 1000.0))
    pieces = []
    for i, w in enumerate(wavs):
        if w.ndim == 2:
            w = w.squeeze(0)
        pieces.append(w)
        if i != len(wavs) - 1:
            pieces.append(silence)
    return torch.cat(pieces, dim=0)
