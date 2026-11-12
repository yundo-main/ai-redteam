"""앞 일차(03~07)의 결과 기록을 공통 형식(redteam-outcomes/1)의 Outcome 파일로 변환한다.

이 파일만이 앞 일차의 저장 형식을 안다(readme 6장 대응표, layout.md 변환기 규칙).
앞 일차 형식이 바뀌면 이 파일만 고친다.

읽는 형식
  03 하네스 기록 / 07 redteam-run/1 : results[](case_id·controls_on·trials·successes) 또는 runs[]
  06 스캔 기록(garak·pyrit)          : measurements[{key,k,n}] / meta.per_type / meta.bench·benign, meta.guard
  06 평가셋 결과                     : {"results":[{"id","blocked"}]} (+ --cases 로 expected 판별)

사용 (저장소 루트에서, src/ 를 경로에 둔 채)
  python 10_redteam_framework/src/run/import_legacy.py <입력.json> -o results/outcomes.json [--cases 평가셋.json]
  --kind auto(기본, 내용으로 판별) | harness | scan | evalset
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base import schema
from base.schema import Outcome

# 스캔 기록 안의 이름 -> (case_id, runner)   (06 from_scan.py 의 ATTACKS 표를 Outcome 용으로 옮긴 것)
SCAN_MAP = {
    "ch06-garak.latent_injection_asr": ("GA-01", "garak"),
    "ch06-garak.base64_asr": ("GA-02", "garak"),
    "exfil_direct": ("PY-01", "pyrit"),
    "exfil_encoded": ("PY-02", "pyrit"),
    "exfil_image": ("PY-03", "pyrit"),
    "exfil_converted": ("PY-04", "pyrit"),
}
RUNNERS = {"garak": "garak", "pyrit": "pyrit", "native": "native", "ch03": "native", "ch07": "native"}


def _cond(on):
    return "controls_on" if on else "controls_off"


def from_harness(doc):
    """03 하네스 기록 또는 07 redteam-run/1 -> Outcome 목록."""
    outcomes = []
    if doc.get("format") == "redteam-run/1":
        for r in doc.get("runs", []):
            outcomes.append(Outcome(r["scenario"], "native", _cond(r["controls"] == "on"),
                                    r["successes"], r["trials"], r.get("evidence", []),
                                    r.get("model", "")))
        return outcomes, doc.get("meta", {})
    for r in doc.get("results", []):
        outcomes.append(Outcome(r["case_id"], "native", _cond(bool(r["controls_on"])),
                                r["successes"], r["trials"], r.get("evidence", []), r.get("model", "")))
    return outcomes, doc.get("meta", {})


def from_scan(doc, kind):
    """06 스캔 기록(garak.jsonl 요약 JSON 또는 pyrit JSON) -> Outcome 목록."""
    meta = doc.get("meta", {})
    guard = bool(meta.get("guard"))
    condition = _cond(guard)
    model = meta.get("model", "")
    outcomes = []
    pairs = []
    if kind == "garak":
        pairs = [(m["key"], m["k"], m["n"]) for m in doc.get("measurements", [])]
        if meta.get("benign"):
            fp, n = meta["benign"]
            pairs.append(("__benign__", fp, n))
    else:  # pyrit
        pairs = [(k, v[0], v[1]) for k, v in meta.get("per_type", {}).items()]
    for name, k, n in pairs:
        if name == "__benign__":
            cid = "OK-02" if kind == "garak" else "OK-01"
        elif name == "benign":
            cid = "OK-01"
        else:
            cid = SCAN_MAP.get(name, (name, kind))[0]
        runner = SCAN_MAP.get(name, (None, kind))[1]
        outcomes.append(Outcome(cid, runner, condition, int(k), int(n), model=model))
    return outcomes, meta


def from_evalset(doc, cases):
    """06 평가셋 결과({"results":[{id,blocked}]}) -> Outcome 목록. expected 로 k 의미를 정한다."""
    by_id = {c.id: c for c in cases}
    outcomes = []
    for r in doc["results"]:
        c = by_id.get(r["id"])
        if c is None:
            raise ValueError(f"평가셋에 없는 id: {r['id']}")
        # 공격 케이스: blocked=False 가 곧 '공격이 통함'(k). 정상 케이스: blocked=True 가 '오탐'(k).
        k = 0 if (r["blocked"] if c.expected == "block" else not r["blocked"]) else 1
        outcomes.append(Outcome(r["id"], "native", "controls_on", k, 1))
    return outcomes, {}


def detect(doc):
    if doc.get("format") == "redteam-run/1" or "results" in doc and isinstance(doc["results"], list) and doc["results"] and "case_id" in doc["results"][0]:
        return "harness"
    if "measurements" in doc or "per_type" in doc.get("meta", {}):
        return "scan"
    if "results" in doc:
        return "evalset"
    raise ValueError("알 수 없는 기록 형식")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("record")
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--cases", help="평정할 평가셋 JSON (evalset 형식 입력 또는 검증용)")
    ap.add_argument("--kind", choices=["auto", "harness", "scan", "evalset"], default="auto")
    a = ap.parse_args(argv)
    try:
        with open(a.record, encoding="utf-8") as f:
            doc = json.load(f)
        kind = a.kind if a.kind != "auto" else detect(doc)
        if kind == "scan":
            is_garak = "garak" in json.dumps(doc.get("meta", {})) or any("garak" in m.get("key", "") for m in doc.get("measurements", []))
            outcomes, meta = from_scan(doc, "garak" if is_garak else "pyrit")
        elif kind == "evalset":
            if not a.cases:
                raise ValueError("evalset 형식은 --cases 평가셋 JSON 이 필요하다(expected 판별용)")
            outcomes, meta = from_evalset(doc, schema.load_cases(a.cases))
        else:
            outcomes, meta = from_harness(doc)
        schema.save_outcomes(a.output, outcomes, meta)
    except (OSError, KeyError, ValueError) as e:
        print(f"변환 실패: {e!r}", file=sys.stderr)
        return 2
    print(f"변환: {a.record} -> {a.output} ({len(outcomes)}개 Outcome, kind={kind})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
