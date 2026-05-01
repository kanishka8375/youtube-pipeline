"""Single-worker job queue: one GPU, fair scheduling, visible queue position."""

from __future__ import annotations

import queue
import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import tts_engine, chunker, history


OUTPUTS_DIR = Path(__file__).parent / "outputs"
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class Job:
    id: str
    text: str
    language_id: str
    params: Dict[str, Any]
    ref_path: Optional[str] = None
    ref_name: Optional[str] = None
    batch_id: Optional[str] = None
    state: str = "queued"  # queued | generating | complete | error | cancelled
    progress: float = 0.0
    audio_url: Optional[str] = None
    audio_path: Optional[str] = None
    duration_sec: Optional[float] = None
    chunk_count: Optional[int] = None
    error: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "language_id": self.language_id,
            "params": self.params,
            "ref_name": self.ref_name,
            "batch_id": self.batch_id,
            "state": self.state,
            "progress": self.progress,
            "audio_url": self.audio_url,
            "duration_sec": self.duration_sec,
            "chunk_count": self.chunk_count,
            "error": self.error,
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_q: "queue.Queue[Job]" = queue.Queue()
_jobs: Dict[str, Job] = {}
_jobs_lock = threading.Lock()
_worker_started = False
_worker_lock = threading.Lock()
_cancelled: set[str] = set()


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        threading.Thread(target=_worker_loop, daemon=True, name="chatterbox-worker").start()
        _worker_started = True


def _refresh_positions() -> None:
    with _jobs_lock:
        position = 1
        for j in list(_q.queue):
            j.progress = 0.0
            j.params["queue_position"] = position
            position += 1


def enqueue(
    text: str,
    language_id: str,
    params: Dict[str, Any],
    ref_path: Optional[str] = None,
    ref_name: Optional[str] = None,
    batch_id: Optional[str] = None,
) -> Job:
    _ensure_worker()
    job = Job(
        id=uuid.uuid4().hex[:12],
        text=text,
        language_id=language_id,
        params=dict(params),
        ref_path=ref_path,
        ref_name=ref_name,
        batch_id=batch_id,
    )
    with _jobs_lock:
        _jobs[job.id] = job
    _q.put(job)
    _refresh_positions()
    return job


def get(job_id: str) -> Optional[Job]:
    with _jobs_lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 100) -> List[dict]:
    with _jobs_lock:
        items = sorted(_jobs.values(), key=lambda j: j.enqueued_at, reverse=True)
    return [j.to_dict() for j in items[:limit]]


def list_active() -> Dict[str, List[dict]]:
    with _jobs_lock:
        gen = [j.to_dict() for j in _jobs.values() if j.state == "generating"]
        queued = [j.to_dict() for j in _jobs.values() if j.state == "queued"]
        recent = [
            j.to_dict()
            for j in sorted(
                (j for j in _jobs.values() if j.state in ("complete", "error", "cancelled")),
                key=lambda j: j.finished_at or 0,
                reverse=True,
            )[:10]
        ]
    return {"generating": gen, "queued": queued, "recent": recent}


def cancel(job_id: str) -> bool:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job or job.state != "queued":
            return False
        job.state = "cancelled"
        job.finished_at = time.time()
        _cancelled.add(job_id)
    return True


def counts() -> Dict[str, int]:
    with _jobs_lock:
        c = {"queued": 0, "generating": 0, "complete": 0, "error": 0, "cancelled": 0}
        for j in _jobs.values():
            c[j.state] = c.get(j.state, 0) + 1
        return c


def _worker_loop() -> None:
    while True:
        job = _q.get()
        if job.id in _cancelled or job.state == "cancelled":
            _cancelled.discard(job.id)
            _refresh_positions()
            _q.task_done()
            continue
        try:
            _run_job(job)
        except Exception as e:
            job.state = "error"
            job.error = f"{e}\n{traceback.format_exc()}"
            job.finished_at = time.time()
        finally:
            _refresh_positions()
            _q.task_done()


def _run_job(job: Job) -> None:
    job.state = "generating"
    job.started_at = time.time()
    job.progress = 0.05

    chunks = chunker.split_for_tts(job.text, job.language_id)
    if not chunks:
        raise ValueError("empty input text")
    job.chunk_count = len(chunks)

    wavs = []
    sr = 24000
    for i, chunk_text in enumerate(chunks):
        wav, sr = tts_engine.synthesize(
            chunk_text,
            language_id=job.language_id,
            ref_path=job.ref_path,
            exaggeration=float(job.params.get("exaggeration", 0.5)),
            cfg_weight=float(job.params.get("cfg_weight", 0.5)),
            temperature=float(job.params.get("temperature", 0.8)),
            seed=job.params.get("seed"),
        )
        wavs.append(wav)
        job.progress = 0.05 + 0.9 * (i + 1) / len(chunks)

    final = tts_engine.concat_wavs(wavs, sr) if len(wavs) > 1 else wavs[0]
    out_path = OUTPUTS_DIR / f"{job.id}.wav"
    tts_engine.save_wav(final, sr, out_path)

    samples = final.shape[-1]
    job.duration_sec = round(samples / sr, 2)
    job.audio_path = str(out_path)
    job.audio_url = f"/audio/{job.id}.wav"
    job.state = "complete"
    job.progress = 1.0
    job.finished_at = time.time()

    history.add_entry(job.to_dict())
