"""ComfyUI-style /api/system_stats payload."""

from __future__ import annotations

import platform
import sys
from typing import Any, Dict


def collect() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "system": {
            "os": platform.system(),
            "os_version": platform.release(),
            "python_version": sys.version.split()[0],
        },
        "devices": [],
    }
    try:
        import torch
        info["torch_version"] = torch.__version__
        info["cuda_available"] = bool(torch.cuda.is_available())
        if torch.cuda.is_available():
            for i in range(torch.cuda.device_count()):
                free, total = torch.cuda.mem_get_info(i)
                info["devices"].append({
                    "type": "cuda",
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "vram_total_gb": round(total / (1024 ** 3), 2),
                    "vram_free_gb": round(free / (1024 ** 3), 2),
                })
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            info["devices"].append({"type": "mps", "name": "Apple Silicon (MPS)"})
        if not info["devices"]:
            info["devices"].append({"type": "cpu", "name": platform.processor() or "CPU"})
    except Exception as e:
        info["torch_error"] = str(e)
        info["devices"].append({"type": "cpu", "name": "CPU (no torch)"})
    return info
