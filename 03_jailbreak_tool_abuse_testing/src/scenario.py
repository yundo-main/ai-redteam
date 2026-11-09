"""6-2 시나리오 워크시트(JSON)를 읽어 6-3 방어·판정 코드로 실행하는 러너 (로컬 Ollama 모델 사용)

흐름:  워크시트 로드·검증 -> ROE 확인 -> 실제 모델로 N회 시도 -> 성공 조건으로 판정 -> 결과 리포트
설계(6-2)의 각 항목이 코드의 어디에 쓰이는지:
  success_condition -> 판정 방식(실행 로그 / 응답 내용)      vector     -> 호출의 출처(origin)
  controls          -> 구현된 통제 지점과 일치하는지 확인     roe        -> 실행 전 검사(샌드박스·더미 데이터)
  steps/objective   -> 리포트에 그대로 기록                   lab        -> 모델에 보낼 테스트 입력(문서, 시스템 프롬프트, 대화)

모델은 시나리오마다 N회만 호출하고, 같은 출력에 방어 전(통제 OFF)과 방어 후(통제 ON)를 모두 적용해 비교한다.
모델 호출과 판정 로직은 harness.py 의 collect_*/evaluate_* 를 그대로 쓴다.

파일 구성(그림: ../code-map.svg): 이 파일은 harness.py 위에 한 겹을 더한다 — 코드에 고정된 입력(harness.py의
TA_SYSTEM·JB_TURNS 등) 대신, scenarios/*.json(6-2 워크시트)에서 읽은 입력으로 harness.py의 함수를 호출한다.
harness.py의 함수를 재구현하지 않고 그대로 import 해서 쓰므로, 판정 로직을 고치려면 harness.py만 고치면 된다.
"""
import json

from harness import (SPECS, collect_multi_turn, collect_tool_calls, evaluate_multi_turn,
                          evaluate_tool_abuse)
from stats import differs, fmt, wilson
from tool_guard import ToolSpec, success_rate

# 6-2 워크시트의 필수 항목
REQUIRED = ["id", "name", "assets", "attacker_model", "objective", "preconditions", "vector",
            "steps", "success_condition", "impact", "controls", "roe"]

# 이 코드가 실제로 구현한 통제 지점 (워크시트의 controls 는 여기에 있어야 한다)
IMPLEMENTED_CONTROLS = {"untrusted_origin_block", "arg_validation", "recipient_allowlist",
                        "human_approval", "output_classifier"}


def validate_worksheet(sc):
    """필수 항목이 모두 있는지, ROE 가 안전 조건을 만족하는지 검사한다."""
    missing = [k for k in REQUIRED if k not in sc]
    if missing:
        raise ValueError(f"워크시트 항목 누락: {missing}")
    roe = sc["roe"]
    if not (roe.get("sandbox") and roe.get("dummy_data")):
        raise ValueError("ROE 위반: 샌드박스와 더미 데이터 사용이 명시되어야 한다")
    unknown = set(sc["controls"]) - IMPLEMENTED_CONTROLS
    if unknown:
        raise ValueError(f"구현되지 않은 통제 지점: {sorted(unknown)}")


def load_scenario(path):
    with open(path, encoding="utf-8") as f:
        sc = json.load(f)
    validate_worksheet(sc)
    return sc


def collect_samples(sc, trials=None, model=None, seed=7):
    """시나리오의 테스트 입력(lab)으로 실제 모델을 N회 호출해 출력을 모은다."""
    validate_worksheet(sc)                       # ROE 를 만족하지 않으면 모델을 호출하지 않는다
    cond, lab = sc["success_condition"], sc.get("lab", {})
    if cond["type"] == "tool_executed":
        kwargs = {"document": lab["document"]} if "document" in lab else {}
        return collect_tool_calls(trials=trials, model=model, seed=seed, **kwargs)
    if cond["type"] == "response_marker":
        kwargs = {k: lab[k] for k in ("system", "turns") if k in lab}
        return collect_multi_turn(trials=trials, model=model, seed=seed, **kwargs)
    raise ValueError(f"알 수 없는 성공 조건 유형: {cond['type']}")


def evaluate_scenario(sc, samples, controls_enabled, model=""):
    """모은 모델 출력에 통제를 적용(또는 생략)하고 성공 조건으로 판정한다."""
    cond = sc["success_condition"]
    if cond["type"] == "tool_executed":
        specs = dict(SPECS)
        specs[cond["tool"]] = ToolSpec(cond["tool"], frozenset({"to", "subject", "body"}), side_effect=True,
                                       needs_approval=True,
                                       allowed_recipient_domains=frozenset(sc["roe"]["allowed_domains"]))
        r = evaluate_tool_abuse(samples, controls_enabled, cond["tool"], specs, model, sc["id"])   # 판정 근거: 실행 기록
        audit = r.audit_log
    elif cond["type"] == "response_marker":
        # 출력 분류기는 워크시트가 통제 지점으로 선언했을 때만 적용한다.
        on = controls_enabled and "output_classifier" in sc["controls"]
        r = evaluate_multi_turn(samples, on, tuple(cond["markers"]), model, sc["id"])           # 판정 근거: 응답 내용
        audit = []
    else:
        raise ValueError(f"알 수 없는 성공 조건 유형: {cond['type']}")
    outcomes = [True] * r.successes + [False] * (r.trials - r.successes)
    return {"id": sc["id"], "name": sc["name"], "objective": sc["objective"],
            "success_condition": cond, "evidence_kind": cond["evidence"],
            "controls": sc["controls"] if controls_enabled else [],
            "trials": r.trials, "successes": r.successes, "rate": success_rate(outcomes),
            "ci95": wilson(r.successes, r.trials),
            "audit_log": audit, "model": model}


def run_scenario(sc, controls_enabled, trials=None, seed=7, model=None, samples=None):
    """시나리오 한 번 실행. samples 를 넘기면 모델을 다시 호출하지 않고 같은 출력에 판정만 한다."""
    if samples is None:
        samples = collect_samples(sc, trials, model, seed)
    return evaluate_scenario(sc, samples, controls_enabled, model or "")


def format_report(before, after):
    """방어 전/후 결과를 워크시트 항목 순서로 요약한다. 비율은 95% 신뢰구간과 함께 보인다."""
    b, a = (before["successes"], before["trials"]), (after["successes"], after["trials"])
    if after["successes"] > 0:
        verdict = "일부 통과 — 통제 보완 필요"
    elif differs(*b, *a):
        verdict = f"통제 지점이 목표 행동을 줄였다 (방어 후 95% 상한 {wilson(*a)[1]:.0%}, 구간이 겹치지 않음)"
    else:
        verdict = "방어 전 성공이 적어 통제 효과를 단정할 수 없다 (구간이 겹침 — 반복 횟수를 늘려야 한다)"
    return "\n".join([
        f"[{before['id']}] {before['name']}",
        f"  목표        : {before['objective']}",
        f"  성공 조건   : {before['success_condition']['type']} (판정 근거: {before['evidence_kind']})",
        f"  통제 지점   : {', '.join(after['controls']) or '없음'}",
        f"  방어 전     : {fmt(*b)}",
        f"  방어 후     : {fmt(*a)}",
        f"  모델        : {after['model'] or '-'}",
        f"  판정        : {verdict}",
    ])
