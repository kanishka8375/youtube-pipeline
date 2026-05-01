"""Wrapper around ChatterboxMultilingualTTS with lazy load and ref-voice caching."""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional


_model = None
_model_lock = threading.Lock()
_load_state = {"status": "idle", "error": None}

_REF_CACHE: "OrderedDict[str, object]" = OrderedDict()
_REF_CACHE_MAX = 16
_ref_lock = threading.Lock()


def get_load_state() -> dict:
    return dict(_load_state)


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


def get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        _load_state["status"] = "loading"
        _load_state["error"] = None
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            device = _select_device()
            _model = ChatterboxMultilingualTTS.from_pretrained(device=device)
            _load_state["status"] = "ready"
        except Exception as e:
            _load_state["status"] = "error"
            _load_state["error"] = str(e)
            raise
        return _model


def warm_up_async() -> None:
    """Kick off model loading on a background thread (non-blocking)."""
    if _load_state["status"] in ("loading", "ready"):
        return

    def _run():
        try:
            get_model()
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name="chatterbox-warmup").start()


def get_supported_languages() -> dict:
    try:
        from chatterbox.mtl_tts import SUPPORTED_LANGUAGES
        return dict(SUPPORTED_LANGUAGES)
    except Exception:
        return {
            "ar": "Arabic", "da": "Danish", "de": "German", "el": "Greek",
            "en": "English", "es": "Spanish", "fi": "Finnish", "fr": "French",
            "he": "Hebrew", "hi": "Hindi", "it": "Italian", "ja": "Japanese",
            "ko": "Korean", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
            "pl": "Polish", "pt": "Portuguese", "ru": "Russian", "sv": "Swedish",
            "sw": "Swahili", "tr": "Turkish", "zh": "Chinese",
        }


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
    text: str,
    language_id: str,
    ref_path: Optional[str] = None,
    exaggeration: float = 0.5,
    cfg_weight: float = 0.5,
    temperature: float = 0.8,
    seed: Optional[int] = None,
):
    """Run a single synthesis. Returns (wav_tensor_cpu, sample_rate)."""
    import torch

    model = get_model()

    if seed is not None:
        torch.manual_seed(int(seed))
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(int(seed))

    cache_hit = False
    if ref_path:
        key = sha256_file(ref_path)
        cached = _cache_get(key)
        if cached is None:
            model.prepare_conditionals(ref_path, exaggeration=exaggeration)
            try:
                _cache_put(key, model.conds)
            except AttributeError:
                pass
        else:
            cache_hit = True
            try:
                model.conds = cached
            except AttributeError:
                model.prepare_conditionals(ref_path, exaggeration=exaggeration)

    wav = model.generate(
        text,
        language_id=language_id,
        audio_prompt_path=ref_path if not cache_hit else None,
        exaggeration=exaggeration,
        cfg_weight=cfg_weight,
        temperature=temperature,
    )

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
