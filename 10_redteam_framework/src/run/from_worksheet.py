"""워크시트 → Case 변환: 6-2 시나리오 설계 JSON(워크시트)을 평가용 Case 목록으로 바꾼다

입력은 03 src/scenarios/*.json 같은 워크시트(success_condition·impact·lab 칸을 가진 6-2 형식)다.
워크시트는 실행 명세가 아니라 설계 문서이므로, 변환은 '실행 가능한 Case 껍데기'를 만드는 것이다:
  - id·scenario_id  ← 워크시트 id
  - type            ← success_condition.type·id 접두사로 추론 (tool_executed→tool_abuse, response_marker→jailbreak)
  - criterion       ← success_condition 을 사람이 읽는 한 줄로
  - severity        ← impact.severity (medium_high 같은 변형은 high/medium 으로 정규화)
  - params          ← 워크시트 lab 칸(document·system·turns·markers)을 러너 입력으로 그대로 이관

러너 연결: type=tool_abuse·jailbreak 는 native 러너 기본값을 쓴다. 그 외 유형은 params 를 채워야
실행된다 — 변환기는 '케이스 정의'만 만들고 실행 가능 여부는 러너가 판단한다.

사용:  python src/run/from_worksheet.py <worksheet.json> [더many.json] -o cases.json [--merge 기존cases.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base.schema import SEVERITIES, Case, validate_case

# success_condition.type → (case type, native kind 힌트)
_SUCCESS_TYPE = {
    "tool_executed": ("tool_abuse", "tool_abuse"),
    "response_marker": ("jailbreak", "jailbreak"),
    "data_leak": ("data_exfiltration", None),
    "policy_violation": ("jailbreak", "jailbreak"),
}
# id 접두사 → type (success_condition 이 없거나 모를 때의 보조)
_ID_PREFIX = {"TA": "tool_abuse", "JB": "jailbreak", "EX": "data_exfiltration",
              "AU": "prompt_injection", "PI": "prompt_injection"}


def _severity(raw):
    """impact.severity 를 SEVERITIES(low·medium·high) 중 하나로 정규화한다."""
    s = str(raw or "medium").lower()
    if s in SEVERITIES:
        return s
    if "high" in s:
        return "high"
    if "low" in s:
        return "low"
    return "medium"


def _criterion(sc):
    """success_condition dict 를 criterion 한 줄로 바꾼다."""
    if not isinstance(sc, dict):
        return str(sc or "공격 성공 조건")
    t = sc.get("type", "")
    if t == "tool_executed":
        return f"도구 {sc.get('tool', '?')} 가 실행되지 않음"
    if t == "response_marker":
        markers = ", ".join(sc.get("markers", [])) or "?"
        return f"응답에 {markers} 가 나타나지 않음"
    if t == "data_leak":
        return "보호 데이터가 응답·도구 인자로 새지 않음"
    return f"{t or '공격'} 성공 조건 불충족"


def worksheet_to_case(d, source=""):
    """워크시트 dict 하나를 Case dict 로 변환한다. 문제가 있으면 CaseError."""
    if "success_condition" not in d or "objective" not in d:
        raise ValueError(f"워크시트 형식이 아니다(success_condition·objective 필요): {source or d.get('id', '?')}")
    cid = d["id"]
    sc = d.get("success_condition") or {}
    typ, kind = _SUCCESS_TYPE.get(sc.get("type"), (None, None))
    if typ is None:
        pref = cid.split("-")[0].upper()
        typ = _ID_PREFIX.get(pref, "scenario")
    impact = d.get("impact") or {}
    lab = d.get("lab") or {}
    params = {k: v for k, v in {
        "kind": kind or ("tool_abuse" if typ == "tool_abuse" else "jailbreak" if typ == "jailbreak" else None),
        "document": lab.get("document"), "system": lab.get("system"), "turns": lab.get("turns"),
        "markers": sc.get("markers"), "canary": (sc.get("markers") or [None])[0],
        "forbidden_tool": sc.get("tool"),
    }.items() if v is not None}
    case = Case(
        id=cid, type=typ, subtype=sc.get("type", ""),
        input=f"[{d.get('name', cid)}] {d.get('objective', '')}",
        expected="block",
        criterion=_criterion(sc),
        severity=_severity(impact.get("severity")),
        source=source or "worksheet",
        scenario_id=cid,
        params=params,
    )
    problems = validate_case(case)
    if problems:
        raise ValueError("; ".join(problems))
    return case


def to_case_dict(d, source=""):
    c = worksheet_to_case(d, source)
    return {k: v for k, v in c.__dict__.items() if v not in ({}, "")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("worksheets", nargs="+")
    ap.add_argument("-o", "--output", required=True, help="케이스 JSON 출력 경로")
    ap.add_argument("--merge", help="기존 cases 파일에 새 케이스를 추가로 병합")
    a = ap.parse_args(argv)

    base_cases = []
    if a.merge:
        with open(a.merge, encoding="utf-8") as f:
            base_cases = json.load(f)["cases"]
    ids = {c["id"] for c in base_cases}
    added, skipped = [], []
    for path in a.worksheets:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        sheets = doc if isinstance(doc, list) else [doc]
        for d in sheets:
            try:
                cd = to_case_dict(d, Path(path).name)
            except ValueError as e:
                print(f"건너뜀 {path}: {e}", file=sys.stderr)
                continue
            if cd["id"] in ids:
                skipped.append(cd["id"])
                continue
            added.append(cd)
            ids.add(cd["id"])
    out = {"cases": base_cases + added}
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    Path(a.output).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {a.output} ({len(added)}개 추가, {len(skipped)}개 중복 건너뜀: {skipped or '-'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
