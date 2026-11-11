"""6-7 실습용: 가설 기록과 대조 도구 (표준 라이브러리만 사용, 모델 호출 없음)

실습은 '실행 전에 예상을 적고, 실행 후에 예상과 결과의 차이를 설명'하는 것이 목표다.
이 모듈은 그 예상(가설)을 파일로 고정하고, 실행 결과와 자동으로 대조한다.

가설 파일 (JSON)   src/data/hypothesis.example.json 을 results/hypothesis-ch03.json 처럼 복사해 값을 고친다.
                    항목 키(chNN.xxx)는 예제 파일에 적힌 것을 그대로 쓴다.
  {"predictions": {"chNN.<항목키>": 0.70}, "memo": {"chNN.<항목키>": "이유 한 줄"}}
  - 비율 항목은 0~1 사이 숫자, 판정 항목은 "PASS" 또는 "FAIL".

대조 규칙
  - 비율: 가설 값이 실제 95% 신뢰구간(Wilson) 안에 있으면 '적중'. 구간 밖이면 '높게 예상'/'낮게 예상'.
  - 판정: 같으면 '적중', 다르면 '빗나감'.
  - 가설 파일이 실행 시작 이후에 수정됐으면 '사후 작성'으로 표시한다(사전 가설로 인정하지 않는다).

사용 (저장소 루트에서 실행)
  - report.py 에는 --hypothesis 로 가설 경로를 준다(결과 파일에 가설이 들어 있으면 그것을 쓴다).
  - 저장된 실행 파일 대조: python <이 파일 경로> results/chNN.json
"""
import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile

from base.stats import fmt, wilson

STARTED_AT = datetime.datetime.now().astimezone()      # 이 프로세스가 시작한 시각(가설이 이보다 먼저 쓰였는지 확인에 쓴다)
VERDICTS = ("PASS", "FAIL")

_measurements = []


# ---------------------------------------------------------------------------
# 가설 읽기
# ---------------------------------------------------------------------------
def load(path):
    """가설 파일을 읽어 기록용 스냅샷을 만든다. 형식이 틀리면 ValueError."""
    with open(path, "rb") as f:
        raw = f.read()
    data = json.loads(raw)
    preds = data.get("predictions")
    if not isinstance(preds, dict) or not preds:
        raise ValueError("가설 파일에 'predictions' 가 비어 있다")
    for key, v in preds.items():
        if isinstance(v, bool) or not (isinstance(v, (int, float)) and 0 <= v <= 1 or v in VERDICTS):
            raise ValueError(f"{key}: 가설 값은 0~1 숫자 또는 PASS/FAIL 이어야 한다 (받은 값: {v!r})")
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path)).astimezone()
    return {"predictions": preds, "memo": data.get("memo", {}), "file": os.path.basename(path),
            "sha256": hashlib.sha256(raw).hexdigest()[:16], "file_mtime": mtime.isoformat(timespec="seconds")}


def written_after(hyp, started_at):
    """가설 파일이 실행 시작 이후에 수정됐는가 (True 면 사후 작성)."""
    if not hyp or not started_at:
        return False
    return datetime.datetime.fromisoformat(hyp["file_mtime"]) > datetime.datetime.fromisoformat(started_at)


# ---------------------------------------------------------------------------
# 대조
# ---------------------------------------------------------------------------
def rate(key, k, n):
    return {"key": key, "k": k, "n": n}


def verdict(key, value):
    return {"key": key, "verdict": value}


def _prefix(key):
    return key.split(".", 1)[0]


def compare(hyp, measurements):
    """측정값마다 가설과 비교한 행을 돌려준다. 측정된 일차(접두사)의 가설만 대상으로 한다."""
    preds = (hyp or {}).get("predictions", {})
    measured = {m["key"] for m in measurements}
    seen = {_prefix(k) for k in measured}
    rows = []
    for m in measurements:
        key, p = m["key"], preds.get(m["key"])
        if "verdict" in m:
            actual = m["verdict"]
            res = "가설 없음" if p is None else ("적중" if p == actual else "빗나감")
            rows.append({"key": key, "predicted": p, "actual": actual, "result": res})
            continue
        lo, hi = wilson(m["k"], m["n"])
        if p is None:
            res = "가설 없음"
        elif isinstance(p, str):
            res = "빗나감"
        else:
            res = "적중" if lo <= p <= hi else ("높게 예상" if p > hi else "낮게 예상")
        rows.append({"key": key, "predicted": p, "actual": fmt(m["k"], m["n"]), "result": res})
    for key, p in preds.items():                        # 가설은 있는데 측정되지 않은 항목(오타 포함)
        if _prefix(key) in seen and key not in measured:
            rows.append({"key": key, "predicted": p, "actual": "-", "result": "측정 안 됨"})
    return rows


def _pred_text(p):
    if p is None:
        return "-"
    return p if isinstance(p, str) else f"{p:.0%}"


def summary(rows):
    judged = [r for r in rows if r["result"] in ("적중", "높게 예상", "낮게 예상", "빗나감")]
    return f"{sum(r['result'] == '적중' for r in judged)}/{len(judged)}"


def text_table(hyp, measurements, started_at=None):
    rows = compare(hyp, measurements)
    lines = ["가설 대비 결과 (적중 = 가설 값이 실제 95% 구간 안, 판정은 일치)"]
    for r in rows:
        lines.append(f"  {r['key']:<31} 가설 {_pred_text(r['predicted']):<5} 실제 {r['actual']:<26} {r['result']}")
    lines.append(f"  적중 {summary(rows)}")
    if written_after(hyp, started_at):
        lines.append(f"  ※ 가설 파일이 실행 시작({started_at}) 이후({hyp['file_mtime']})에 수정됐다. 사후 작성이라 사전 가설로 인정하지 않는다.")
    lines.append("  빗나간 항목은 이유를 한 줄로 쓴다(memo 또는 보고서의 '차이와 이유').")
    return "\n".join(lines)


def md_rows(hyp, measurements):
    """보고서 표 행: | 항목 | 가설 | 실제 | 결과 | 가설 메모 |"""
    memo = (hyp or {}).get("memo", {})
    return [f"| `{r['key']}` | {_pred_text(r['predicted'])} | {r['actual']} | {r['result']} | {memo.get(r['key'], '')} |"
            for r in compare(hyp, measurements)]


# ---------------------------------------------------------------------------
# 실행 기록 저장
# ---------------------------------------------------------------------------
def safe_write(path, text):
    """결과 파일을 안전하게 쓴다. (1) 같은 이름이 이미 있으면 지우지 않고 같은 폴더의 history/ 로 옮겨 보관한다.
    (2) 임시 파일에 쓴 뒤 바꿔치기해서, 중간에 끊겨도 반쪽짜리 파일이 남지 않는다. 보관한 경로(없었으면 None)를 돌려준다."""
    path = os.path.abspath(path)
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    kept = None
    if os.path.exists(path):
        stamp = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y%m%dT%H%M%S")
        base, ext = os.path.splitext(os.path.basename(path))
        hist = os.path.join(folder, "history")
        os.makedirs(hist, exist_ok=True)
        kept, n = os.path.join(hist, f"{base}.{stamp}{ext}"), 1
        while os.path.exists(kept):
            kept = os.path.join(hist, f"{base}.{stamp}-{n}{ext}")
            n += 1
        shutil.copy2(path, kept)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    return kept


def save_run(path, measurements, hyp, meta=None, results=None):
    """실행 기록(JSON)을 저장한다(safe_write: 같은 이름이 있으면 history/ 로 보관). 폴더가 없으면 만든다. results 가 있으면 6-7 보고서 입력으로도 쓰인다.
    이전 파일을 보관했으면 그 경로를, 아니면 None 을 돌려준다."""
    doc = {"meta": {"started_at": STARTED_AT.isoformat(timespec="seconds"), **(meta or {})},
           "hypothesis": hyp, "measurements": measurements}
    if results is not None:
        doc["results"] = results
    return safe_write(path, json.dumps(doc, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# 측정값 수집기 (record 로 모아 flush 로 저장)
# ---------------------------------------------------------------------------
def record(key, k, n):
    _measurements.append(rate(key, k, n))


def record_verdict(key, value):
    _measurements.append(verdict(key, value))


def flush(meta=None):
    """환경 변수 HYPOTHESIS(가설 파일), RESULT_JSON(저장 경로)에 따라 대조표를 출력하고 기록을 저장한다."""
    if not _measurements:
        return
    hyp_path, out_path = os.environ.get("HYPOTHESIS"), os.environ.get("RESULT_JSON")
    hyp = load(hyp_path) if hyp_path else None
    started = STARTED_AT.isoformat(timespec="seconds")
    if hyp:
        print("\n" + text_table(hyp, _measurements, started))
    else:
        print("\n가설 파일 없음: HYPOTHESIS=경로 를 주면 가설 대비 결과를 비교한다.")
    if out_path:
        kept = save_run(out_path, _measurements, hyp, meta)
        print(f"실행 기록 저장: {out_path}" + (f"  (이전 파일은 {kept} 로 보관)" if kept else ""))


# ---------------------------------------------------------------------------
# 저장된 실행 파일 대조:  python <이 파일 경로> results/chNN.json
# ---------------------------------------------------------------------------
def load_run(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):                          # 예전 형식(결과 목록만 있는 파일): 가설·측정 없음
        return {"meta": {}, "hypothesis": None, "measurements": [], "results": data}
    return data


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"사용법: python {sys.argv[0]} <실행 기록 JSON>")
    run = load_run(sys.argv[1])
    if not run.get("hypothesis"):
        raise SystemExit("이 실행 기록에는 가설이 없다. 실행할 때 가설 파일을 함께 주었는지 확인한다.")
    print(text_table(run["hypothesis"], run["measurements"], run["meta"].get("started_at")))
