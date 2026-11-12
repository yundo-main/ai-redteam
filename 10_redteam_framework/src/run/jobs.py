"""측정 작업 큐: 백그라운드 스레드로 pipeline.all_in_one 을 돌리고 진행 상태를 기록한다.

상태는 results/jobs/<id>.json 에 저장해 서버 재시작 후에도 완료된 결과가 남는다.
취소는 cancel_event 로 파이프라인의 케이스·러너 경계에서 검사한다(진행 중인 모델 호출 한 번은 끝까지 간다).
"""
import datetime
import json
import os
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]        # 10_redteam_framework/
JOBS_DIR = ROOT / "results" / "jobs"
_lock = threading.Lock()
_jobs = {}          # id -> job dict (메모리 캐시, 디스크가 진실의 원천)


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _path(job_id):
    return JOBS_DIR / f"{job_id}.json"


def _save(job):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _path(job["id"]).with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, _path(job["id"]))


def _load_all():
    out = {}
    if JOBS_DIR.exists():
        for p in JOBS_DIR.glob("*.json"):
            try:
                j = json.loads(p.read_text(encoding="utf-8"))
                out[j["id"]] = j
            except (json.JSONDecodeError, KeyError):
                continue
    return out


def list_jobs():
    with _lock:
        fresh = _load_all()
        _jobs.update(fresh)
        return sorted(_jobs.values(), key=lambda j: j.get("created_at", ""), reverse=True)


def get(job_id):
    with _lock:
        if job_id not in _jobs:
            _jobs.update(_load_all())
        return _jobs.get(job_id)


def start(cases_path, runners=("native",), quick=False, out_dir=None,
          max_asr=0.2, max_fpr=0.1, model=None, hypothesis=None):
    """측정 작업을 시작하고 job dict 를 돌려준다. out_dir=None 이면 ROOT/results."""
    out_dir = str(out_dir or (ROOT / "results"))
    job = {"id": uuid.uuid4().hex[:12], "status": "pending", "progress": "대기 중",
           "log": [],
           "params": {"cases": cases_path, "runners": list(runners), "quick": quick,
                      "out_dir": out_dir, "max_asr": max_asr, "max_fpr": max_fpr, "model": model,
                      "hypothesis": hypothesis},
           "created_at": _now(), "started_at": None, "finished_at": None,
           "result": None, "error": None}
    job["cancel_event"] = None     # 스레드 전용, 저장하지 않는다
    with _lock:
        _jobs[job["id"]] = job
        _save({k: v for k, v in job.items() if k != "cancel_event"})
    t = threading.Thread(target=_run, args=(job,), daemon=True)
    t.start()
    return {k: v for k, v in job.items() if k != "cancel_event"}


def _run(job):
    import threading
    from run import pipeline
    job["cancel_event"] = threading.Event()
    job["status"] = "running"
    job["started_at"] = _now()
    _save({k: v for k, v in job.items() if k != "cancel_event"})

    def prog(msg):
        job["progress"] = msg
        job.setdefault("log", []).append({"t": _now(), "msg": msg})
        if len(job["log"]) > 500:      # 비정상 루프 방지 — 최근 500건만 유지
            job["log"] = job["log"][-500:]
        _save({k: v for k, v in job.items() if k != "cancel_event"})

    p = job["params"]
    try:
        job["result"] = pipeline.all_in_one(
            p["cases"], tuple(p["runners"]), ("controls_off", "controls_on"),
            p["quick"], p["out_dir"], p["max_asr"], p["max_fpr"], p["model"],
            on_progress=prog, cancel_event=job["cancel_event"],
            hypothesis=p.get("hypothesis"))
        job["status"] = "done"
        job["progress"] = "완료"
    except pipeline.Cancelled:
        job["status"] = "cancelled"
        job["progress"] = "취소됨"
    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["progress"] = "실패"
    finally:
        job["finished_at"] = _now()
        job.setdefault("log", []).append({"t": job["finished_at"],
                                          "msg": f"종료 — 상태: {job['status']}" + (f" ({job['error']})" if job.get("error") else "")})
        _save({k: v for k, v in job.items() if k != "cancel_event"})


def cancel(job_id):
    job = get(job_id)
    if not job:
        return False
    if job["status"] == "running" and job.get("cancel_event"):
        job["cancel_event"].set()
        return True
    if job["status"] == "pending":
        job["status"] = "cancelled"
        job["finished_at"] = _now()
        _save({k: v for k, v in job.items() if k != "cancel_event"})
        return True
    return False
