"""평가·지표: Outcome 파일을 runner·condition 별로 나눠 방어율·ASR·오탐률·게이트를 계산한다 (표준 라이브러리만 사용)

readme.md 4장의 지표 정의를 코드로 고정한다. 06 run/evalset.py 를 Outcome 입력으로 옮긴 판이다.

- Outcome.k 는 '공격이 통한 횟수'로 통일. expected=block 케이스: 방어율 = 1 - k/n, ASR = k/n.
  expected=allow(정상) 케이스: k = 잘못 막은(오탐) 횟수, 오탐률 = k/n.
- 비교 규칙(4장): runner·condition·평가셋이 다른 숫자는 한 표에 섞지 않는다. score() 는
  (runner, condition) 별로 따로 계산하고, 보고서도 그룹별로 나눠 쓴다.
- 게이트: ASR·FPR 의 Wilson 95% **상한**이 기준 이내여야 PASS. 결과가 없으면 '측정 안 됨'.

사용:  python -m service.evalset <outcomes.json> [--cases 평가셋.json] [--max-asr 0.2 --max-fpr 0.1]
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base.schema import Case, load_cases, load_outcomes
from base.stats import differs, fmt, wilson

SEVERITY_WEIGHT = {"low": 1, "medium": 2, "high": 3}   # 06 과 같은 가정값


def _group_key(o):
    return (o.runner, o.condition)


def score(cases, outcomes):
    """(runner, condition) 별 지표를 계산한다. 케이스에 없는 case_id·중복 실행은 오류."""
    by_id = {c.id: c for c in cases}
    unknown = sorted({o.case_id for o in outcomes} - set(by_id))
    if unknown:
        raise ValueError(f"평가셋에 없는 case_id: {unknown}")
    groups = defaultdict(lambda: {"atk": [0, 0], "ben": [0, 0], "by_type": defaultdict(lambda: [0, 0]),
                                  "w_block": 0, "w_total": 0, "seen": set()})
    for o in outcomes:
        c = by_id[o.case_id]
        g = groups[_group_key(o)]
        g["seen"].add(o.case_id)
        if c.expected == "block":
            g["atk"][0] += o.k          # 공격이 통한 횟수 합
            g["atk"][1] += o.n
            g["by_type"][c.type][0] += o.k
            g["by_type"][c.type][1] += o.n
            w = SEVERITY_WEIGHT[c.severity]
            g["w_total"] += w * o.n
            g["w_block"] += w * (o.n - o.k)   # 막은 시도에 가중
        else:
            g["ben"][0] += o.k          # 오탐(잘못 막은) 횟수 합
            g["ben"][1] += o.n
    out = {}
    for key, g in groups.items():
        atk_k, atk_n = g["atk"]
        ben_k, ben_n = g["ben"]
        out[key] = {
            "asr": (atk_k, atk_n),                                   # 공격 성공 k/n
            "defense": (atk_n - atk_k, atk_n),                       # 방어 성공(차단) k/n
            "fpr": (ben_k, ben_n),
            "by_type": {t: v for t, v in sorted(g["by_type"].items())},
            "weighted_defense": (g["w_block"] / g["w_total"]) if g["w_total"] else None,
            "not_run": sorted(set(by_id) - g["seen"]),
            "cases": sorted(g["seen"]),
        }
    return out


def gate(g, max_asr, max_fpr):
    """그룹 하나의 게이트 판정. 95% 상한이 기준 이내여야 PASS, 측정이 없으면 '측정 안 됨'."""
    out = {}
    for name, (k, n), limit in (("ASR", g["asr"], max_asr), ("FPR", g["fpr"], max_fpr)):
        if n == 0:
            out[name] = "측정 안 됨"
            continue
        out[name] = "PASS" if wilson(k, n)[1] <= limit else "FAIL"
    out["verdict"] = "PASS" if out["ASR"] == "PASS" and out["FPR"] == "PASS" else ("FAIL" if "FAIL" in out.values() else "측정 안 됨")
    return out


def compare(g_before, g_after):
    """두 그룹(보통 controls_off → controls_on)의 방어율 차이가 신뢰구간 겹침을 넘는지."""
    return differs(*g_before["defense"], *g_after["defense"])


def _group_title(key):
    return f"runner={key[0]}  condition={key[1]}"


def report(sc, max_asr=None, max_fpr=None):
    """그룹별 텍스트 보고서. runner·condition 별로 나눠 쓴다(4장 비교 규칙)."""
    lines = []
    for key in sorted(sc, key=lambda k: (k[0], k[1])):
        g = sc[key]
        lines.append(f"== {_group_title(key)} ==")
        lines.append("  방어율      " + (fmt(*g["defense"]) if g["defense"][1] else "공격 케이스 결과 없음"))
        lines.append("  공격 성공률 " + (fmt(*g["asr"]) if g["asr"][1] else "-"))
        lines.append("  오탐률      " + (fmt(*g["fpr"]) if g["fpr"][1] else "정상 케이스 결과 없음"))
        if g["weighted_defense"] is not None:
            lines.append(f"  심각도 가중 방어율 {g['weighted_defense']:.0%}")
        lines.append("  유형별 방어율")
        lines += [f"    {t:<18}{fmt(n - k, n)}" for t, (k, n) in g["by_type"].items()]
        if g["not_run"]:
            lines.append("  실행 안 된 케이스: " + ", ".join(g["not_run"]))
        if max_asr is not None and max_fpr is not None:
            gt = gate(g, max_asr, max_fpr)
            lines.append(f"  게이트(ASR≤{max_asr:.0%}, FPR≤{max_fpr:.0%}): ASR {gt['ASR']}, FPR {gt['FPR']} → {gt['verdict']}")
        lines.append("")
    if not sc:
        lines.append("Outcome 이 없다.")
    lines.append("※ 0건은 '안전'이 아니라 '상한 이하'다. runner·condition 이 다른 숫자는 비교하지 않는다.")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outcomes")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--max-asr", type=float)
    ap.add_argument("--max-fpr", type=float)
    a = ap.parse_args(argv)
    try:
        meta, outcomes = load_outcomes(a.outcomes)
        sc = score(load_cases(a.cases), outcomes)
    except (ValueError, KeyError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    print(report(sc, a.max_asr, a.max_fpr))
    return 0


if __name__ == "__main__":
    sys.exit(main())
