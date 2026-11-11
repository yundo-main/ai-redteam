"""6-7 실습: 하네스(03)가 저장한 실행 기록을 07 입력 형식(redteam-run/1)으로 바꾼다 (표준 라이브러리만 사용, 모델 호출 없음)

report.py 는 하네스 기록의 모양을 모른다. 이 변환 도구만 그 모양을 안다 — 앞 일차의 저장 형식이 바뀌면 이 파일만 고친다.

하네스 기록(03 의 --json 결과)                         07 입력 기록 (redteam-run/1)
  {"meta", "hypothesis", "measurements", "results"}       {"format", "meta", "runs", "hypothesis"}
  results[].case_id        시나리오 ID                    runs[].scenario
  results[].controls_on    true / false                   runs[].controls   "on" / "off"
  results[].audit_log      통제 로그                      runs[].audit
  results[].success_rate · ci95                           (버림 — 07 이 trials·successes 에서 다시 계산한다)
  results[].trials · successes · evidence · model · params   그대로
  hypothesis.predictions · memo 의 키  ch03.<ID>.<off|on>    ch07.<ID>.<off|on>
  measurements                                            (버림 — 07 이 runs 에서 다시 센다)
예전 형식(결과 목록만 있는 파일)도 읽는다.

사용 (저장소 루트에서)
  python 07_redteam_result_analysis/src/run/from_harness.py [하네스기록.json] [-o 출력.json]
  인자를 생략하면 src/data/harness/ch03.example.json 을 읽는다. -o 를 생략하면 화면에 출력한다.
  변환한 파일을 report.py 의 입력으로 준다:  python 07_redteam_result_analysis/src/run/report.py 출력.json
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/ 를 모듈 검색 경로에 둔다 (run·base 패키지)

from base import hypothesis_log as hyp

FORMAT = "redteam-run/1"
OLD_PREFIX, NEW_PREFIX = "ch03.", "ch07."


def _rekey(d):
    return {(NEW_PREFIX + k[len(OLD_PREFIX):] if k.startswith(OLD_PREFIX) else k): v for k, v in d.items()}


def convert(old):
    """하네스 기록(dict, hypothesis_log.load_run 이 돌려주는 모양)을 07 입력 기록으로 바꾼다."""
    runs = []
    for r in old["results"]:
        run = {"scenario": r["case_id"], "controls": "on" if r["controls_on"] else "off",
               "trials": r["trials"], "successes": r["successes"]}
        for k_old, k_new in (("evidence", "evidence"), ("audit_log", "audit"), ("model", "model"), ("params", "params")):
            if k_old in r:
                run[k_new] = r[k_old]
        runs.append(run)
    snap = old.get("hypothesis")
    if snap:
        snap = {**snap, "predictions": _rekey(snap.get("predictions", {})), "memo": _rekey(snap.get("memo", {}))}
    meta = {k: v for k, v in (old.get("meta") or {}).items() if k in ("started_at", "model")}
    return {"format": FORMAT, "meta": meta, "runs": runs, "hypothesis": snap}


def main(argv=None):
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("harness", nargs="?", default=os.path.join(here, "data", "harness", "ch03.example.json"),
                    help="하네스가 --json 으로 저장한 기록 (생략하면 src/data/harness/ch03.example.json)")
    ap.add_argument("-o", "--output", help="07 입력 기록을 저장할 경로(이미 있으면 history/ 로 보관). 생략하면 화면에 출력")
    a = ap.parse_args(argv)
    try:
        old = hyp.load_run(a.harness)
        if "results" not in old:
            raise ValueError("results 가 없다")
        rec = convert(old)
    except (OSError, KeyError, ValueError) as e:
        print(f"변환 실패: {e!r} — 하네스 기록 형식을 확인(03 의 --json 결과)", file=sys.stderr)
        return 2
    text = json.dumps(rec, ensure_ascii=False, indent=2)
    if a.output:
        kept = hyp.safe_write(a.output, text)
        print(f"저장: {a.output} ({len(rec['runs'])}개 실행)" + (f"  (이전 파일은 {kept} 로 보관)" if kept else ""))
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
