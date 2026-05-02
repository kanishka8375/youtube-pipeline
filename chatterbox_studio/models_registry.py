"""Static model registry + install-status detection.

Mirrors the v2 design's MODEL_REGISTRY: each model entry knows the local
folder where its `.safetensors` files should live and which Python class
should load it. Install detection scans those folders + the HF cache.
"""

from __future__ import annotations

import importlib
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = Path(os.environ.get("CHATTERBOX_MODELS_DIR", PROJECT_ROOT / "chatterbox_studio" / "models" / "tts"))

# Extra search roots loaded from extra_model_paths.yaml (ComfyUI-style).
# Each entry: Path. Searched in addition to MODELS_DIR/<id>/ for required files.
_EXTRA_ROOTS: list[Path] = []
_status_cache: dict | None = None


@dataclass
class ModelEntry:
    id: str
    hf_repo: str
    label: str
    variant: str
    variant_color: str
    size: str
    total_gb: str
    desc: str
    lang: str
    type: str
    required_files: List[str]
    import_class: Optional[str]
    import_mod: Optional[str]
    tags: List[str] = field(default_factory=list)
    default_text: str = ""
    params: dict = field(default_factory=dict)

    @property
    def local_folder(self) -> Path:
        return MODELS_DIR / self.id

    def to_dict(self) -> dict:
        d = asdict(self)
        d["local_folder"] = str(self.local_folder)
        return d


MODEL_REGISTRY: List[ModelEntry] = [
    ModelEntry(
        id="chatterbox-turbo",
        hf_repo="ResembleAI/chatterbox-turbo",
        label="Chatterbox Turbo",
        variant="⚡ Turbo",
        variant_color="#c96a2e",
        size="350M",
        total_gb="1.8 GB",
        desc="Fastest · 1-step decoder · paralinguistic tags · real-time agents",
        lang="EN",
        type="tts_turbo",
        required_files=["t3_turbo.safetensors", "s3gen_turbo.safetensors", "conds.pt"],
        import_class="ChatterboxTurboTTS",
        import_mod="chatterbox.tts_turbo",
        tags=["[clear throat]", "[sigh]", "[shush]", "[cough]", "[groan]", "[sniff]", "[gasp]", "[chuckle]", "[laugh]"],
        default_text=(
            "Hi there, Sarah here from MochaFone calling you back [chuckle], "
            "have you got one minute to chat about the billing issue?"
        ),
        params={"temperature": 0.8, "top_p": 0.95, "top_k": 1000, "repetition_penalty": 1.2, "min_p": 0.0, "norm_loudness": True},
    ),
    ModelEntry(
        id="chatterbox",
        hf_repo="ResembleAI/chatterbox",
        label="Chatterbox",
        variant="Standard",
        variant_color="#5a7cc0",
        size="500M",
        total_gb="2.1 GB",
        desc="Full expressiveness · CFG weight · exaggeration tuning · narration",
        lang="EN",
        type="tts",
        required_files=["t3_cfg.safetensors", "s3gen.safetensors", "conds.pt"],
        import_class="ChatterboxTTS",
        import_mod="chatterbox.tts",
        default_text=(
            "Ezreal and Jinx teamed up with Ahri, Yasuo, and Teemo to take down "
            "the enemy's Nexus in an epic late-game pentakill."
        ),
        params={"exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8, "min_p": 0.05, "top_p": 1.0, "repetition_penalty": 1.2},
    ),
    ModelEntry(
        id="chatterbox-multilingual",
        hf_repo="ResembleAI/chatterbox-multilingual",
        label="Chatterbox Multilingual",
        variant="🌍 MTL",
        variant_color="#3d9e6a",
        size="500M",
        total_gb="2.1 GB",
        desc="Zero-shot cloning · 23 languages · cross-lingual transfer",
        lang="23 langs",
        type="mtl_tts",
        required_files=["t3_multilingual.safetensors", "s3gen.safetensors", "conds.pt"],
        import_class="ChatterboxMultilingualTTS",
        import_mod="chatterbox.mtl_tts",
        default_text="Bonjour, comment ça va? Ceci est le modèle de synthèse vocale multilingue Chatterbox.",
        params={"language_id": "fr", "exaggeration": 0.5, "cfg_weight": 0.5, "temperature": 0.8},
    ),
    ModelEntry(
        id="chatterbox-turbo-onnx",
        hf_repo="ResembleAI/chatterbox-turbo-ONNX",
        label="Chatterbox Turbo ONNX",
        variant="⚙ ONNX",
        variant_color="#9060c8",
        size="350M",
        total_gb="3.2 GB",
        desc="ONNX runtime · no PyTorch needed · CPU/GPU compatible",
        lang="EN",
        type="onnx",
        required_files=["t3_turbo_fp32.onnx", "t3_turbo_fp16.onnx", "s3gen_turbo.onnx"],
        import_class=None,
        import_mod=None,
        tags=["[cough]", "[laugh]", "[chuckle]", "[sigh]"],
        default_text="This is the ONNX version of Chatterbox Turbo. It runs without PyTorch.",
        params={"temperature": 0.8, "top_p": 0.95, "top_k": 1000, "repetition_penalty": 1.2},
    ),
]


def find_by_id(model_id: str) -> Optional[ModelEntry]:
    for m in MODEL_REGISTRY:
        if m.id == model_id:
            return m
    return None


def _yaml_candidates() -> List[Path]:
    return [
        PROJECT_ROOT / "extra_model_paths.yaml",
        PROJECT_ROOT / "chatterbox_studio" / "extra_model_paths.yaml",
        Path.home() / ".config" / "chatterbox" / "extra_model_paths.yaml",
    ]


def load_extra_model_paths() -> List[Path]:
    """Parse extra_model_paths.yaml (ComfyUI format) and store extra TTS roots.

    Schema (matches ComfyUI's example):
        chatterbox:
          base_path: ~/ChatterBox
          is_default: true
          tts: models/tts/
    Multiple roots can be combined with `|` newline-separated values.
    """
    global _EXTRA_ROOTS
    _EXTRA_ROOTS = []
    try:
        import yaml  # PyYAML
    except Exception:
        return _EXTRA_ROOTS

    for cfg_path in _yaml_candidates():
        if not cfg_path.exists():
            continue
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue
        for _section, body in data.items():
            if not isinstance(body, dict):
                continue
            base = Path(os.path.expanduser(str(body.get("base_path", "."))))
            tts_val = body.get("tts") or body.get("checkpoints") or ""
            for line in str(tts_val).splitlines():
                line = line.strip()
                if not line:
                    continue
                root = base / line
                _EXTRA_ROOTS.append(root)
    return _EXTRA_ROOTS


def search_roots(model_id: str) -> List[Path]:
    """All folders to scan for a given model id (default + extras + per-model subdir)."""
    entry = find_by_id(model_id)
    if not entry:
        return []
    roots = [entry.local_folder]
    for r in _EXTRA_ROOTS:
        roots.append(r / entry.id)
    return roots


def _hf_cache_dirs(repo: str) -> List[Path]:
    """Possible HuggingFace cache locations for a given repo id."""
    hf_home = Path(os.environ.get("HF_HOME") or os.environ.get("HUGGINGFACE_HUB_CACHE") or (Path.home() / ".cache" / "huggingface"))
    safe = repo.replace("/", "--")
    candidates = [
        hf_home / "hub" / f"models--{safe}" / "snapshots",
        hf_home / f"models--{safe}" / "snapshots",
    ]
    return candidates


def _present_in_dir(folder: Path, files: List[str]) -> bool:
    if not folder.exists() or not folder.is_dir():
        return False
    have = {p.name for p in folder.iterdir() if p.is_file()}
    return all(f in have for f in files)


def _present_in_hf_cache(m: ModelEntry) -> bool:
    for snap_root in _hf_cache_dirs(m.hf_repo):
        if not snap_root.exists():
            continue
        for sub in snap_root.iterdir():
            if sub.is_dir() and _present_in_dir(sub, m.required_files):
                return True
    return False


def _import_class_available(m: ModelEntry) -> bool:
    if not m.import_mod or not m.import_class:
        return False
    try:
        mod = importlib.import_module(m.import_mod)
        return hasattr(mod, m.import_class)
    except Exception:
        return False


def detect_install_status(use_cache: bool = True) -> dict:
    """Return {model_id: {installed, where, files_present, files_missing, importable}}."""
    global _status_cache
    if use_cache and _status_cache is not None:
        return _status_cache
    out = {}
    for m in MODEL_REGISTRY:
        roots = search_roots(m.id)
        local_root = next((r for r in roots if _present_in_dir(r, m.required_files)), None)
        hf_ok = _present_in_hf_cache(m)
        importable = _import_class_available(m) if m.type != "onnx" else _onnx_available()

        # an ONNX model is "installed" purely by file presence (no Python class needed)
        if m.type == "onnx":
            installed = bool(local_root) or hf_ok
        else:
            installed = importable and (bool(local_root) or hf_ok)

        present = []
        missing = []
        for fname in m.required_files:
            found_in = next((r for r in roots if (r / fname).exists()), None)
            if found_in:
                present.append(fname)
            else:
                missing.append(fname)

        where = "local" if local_root else ("hf_cache" if hf_ok else None)

        out[m.id] = {
            "installed": installed,
            "where": where,
            "where_path": str(local_root) if local_root else None,
            "importable": importable,
            "files_present": present,
            "files_missing": missing,
            "local_folder": str(m.local_folder),
            "search_roots": [str(r) for r in roots],
        }
    _status_cache = out
    return out


def refresh() -> dict:
    """Invalidate the install-status cache and rescan."""
    global _status_cache
    _status_cache = None
    load_extra_model_paths()
    return detect_install_status(use_cache=False)


def _onnx_available() -> bool:
    try:
        import onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def serialize_models(include_status: bool = True) -> List[dict]:
    statuses = detect_install_status() if include_status else {}
    rows = []
    for m in MODEL_REGISTRY:
        d = m.to_dict()
        if include_status:
            d["status"] = statuses.get(m.id, {})
        rows.append(d)
    return rows


# Load yaml on first import so search roots include user overrides.
load_extra_model_paths()


def supported_languages() -> List[dict]:
    """23-language list — matches the design's LANGUAGES array."""
    items = [
        ("ar", "Arabic"), ("da", "Danish"), ("de", "German"), ("el", "Greek"),
        ("en", "English"), ("es", "Spanish"), ("fi", "Finnish"), ("fr", "French"),
        ("he", "Hebrew"), ("hi", "Hindi"), ("it", "Italian"), ("ja", "Japanese"),
        ("ko", "Korean"), ("ms", "Malay"), ("nl", "Dutch"), ("no", "Norwegian"),
        ("pl", "Polish"), ("pt", "Portuguese"), ("ru", "Russian"), ("sv", "Swedish"),
        ("sw", "Swahili"), ("tr", "Turkish"), ("zh", "Chinese"),
    ]
    return [{"code": c, "name": n} for c, n in items]
