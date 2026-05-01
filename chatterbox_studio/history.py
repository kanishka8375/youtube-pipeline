"""Lock-guarded JSON persistence for past generations and saved reference voices."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import List, Optional

HISTORY_PATH = Path(__file__).parent / "history.json"
REFS_PATH = Path(__file__).parent / "refs.json"

_history_lock = threading.Lock()
_refs_lock = threading.Lock()


def _read(path: Path) -> dict:
    if not path.exists():
        return {"entries": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"entries": []}


def _write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def add_entry(entry: dict) -> None:
    with _history_lock:
        data = _read(HISTORY_PATH)
        entries = data.setdefault("entries", [])
        entries.insert(0, entry)
        if len(entries) > 500:
            del entries[500:]
        _write(HISTORY_PATH, data)


def list_entries(limit: int = 100) -> List[dict]:
    with _history_lock:
        data = _read(HISTORY_PATH)
        return list(data.get("entries", []))[:limit]


def delete_entry(entry_id: str) -> bool:
    with _history_lock:
        data = _read(HISTORY_PATH)
        entries = data.get("entries", [])
        before = len(entries)
        entries = [e for e in entries if e.get("id") != entry_id]
        if len(entries) == before:
            return False
        data["entries"] = entries
        _write(HISTORY_PATH, data)
        return True


def get_entry(entry_id: str) -> Optional[dict]:
    with _history_lock:
        for e in _read(HISTORY_PATH).get("entries", []):
            if e.get("id") == entry_id:
                return e
    return None


def list_refs() -> List[dict]:
    with _refs_lock:
        data = _read(REFS_PATH)
        return list(data.get("entries", []))


def add_ref(name: str, sha: str, filename: str, path: str, duration_sec: float) -> dict:
    entry = {
        "name": name,
        "sha": sha,
        "filename": filename,
        "path": path,
        "duration_sec": duration_sec,
        "created_at": time.time(),
    }
    with _refs_lock:
        data = _read(REFS_PATH)
        entries = data.setdefault("entries", [])
        entries = [e for e in entries if e.get("name") != name]
        entries.insert(0, entry)
        data["entries"] = entries
        _write(REFS_PATH, data)
    return entry


def get_ref(name: str) -> Optional[dict]:
    for r in list_refs():
        if r.get("name") == name:
            return r
    return None


def delete_ref(name: str) -> bool:
    with _refs_lock:
        data = _read(REFS_PATH)
        entries = data.get("entries", [])
        target = next((e for e in entries if e.get("name") == name), None)
        if not target:
            return False
        data["entries"] = [e for e in entries if e.get("name") != name]
        _write(REFS_PATH, data)
        try:
            p = Path(target["path"])
            if p.exists():
                p.unlink()
        except OSError:
            pass
        return True
