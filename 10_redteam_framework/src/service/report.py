"""보고서: Outcome 파일을 읽어 Markdown·자체 완결 HTML 보고서를 만든다 (표준 라이브러리만 사용)

readme.md 11.2.1·11.5 의 원칙을 따른다.
- 같은 숫자: 평가는 service.evalset.score() 한 곳에서만 계산하고, md·html 은 그 결과를 그린다.
- runner·condition 별로 나눠 쓴다(4장 비교 규칙). 한 표에 섞지 않는다.
- 안전(8장): 집계 수치와 케이스 id 만 싣는다. 모델 원본 응답·입력 본문·카나리 원문은 싣지 않고
  이메일은 마스킹한다. HTML 은 외부 링크·CDN 없이 한 파일로 자체 완결된다.
- 구간 항상 표시: 0건은 "0%"가 아니라 Wilson 상한과 함께 쓴다.

사용:
  python -m service.report <outcomes.json> --cases 평가셋.json -o report.md
  python -m service.report <outcomes.json> --cases 평가셋.json --format html -o report.html
  python -m service.report <outcomes.json> --cases 평가셋.json --format both -o report   (report.md+report.html)
"""
import argparse
import datetime
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base import hypothesis_log as hyp
from base.schema import load_cases, load_outcomes
from base.stats import fmt, wilson
from service import evalset as ev
from service import viz


def mask(text):
    return re.sub(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", "[email]", str(text))


def _group_name(key):
    return f"{key[0]} / {key[1]}"


# ---------------------------------------------------------------------------
# 공통 계산: 보고서가 쓰는 모든 수치를 한 곳에서 만든다
# ---------------------------------------------------------------------------
def build(cases, outcomes, max_asr=None, max_fpr=None, hypothesis=None):
    sc = ev.score(cases, outcomes)
    doc = {"generated_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
           "groups": {}, "pairs": [], "hypothesis_rows": None, "case_rows": []}
    by_id = {c.id: c for c in cases}
    for o in outcomes:
        c = by_id[o.case_id]
        doc["case_rows"].append({"case_id": o.case_id, "type": c.type, "severity": c.severity,
                                 "expected": c.expected, "runner": o.runner,
                                 "condition": o.condition, "k": o.k, "n": o.n})
    for key in sorted(sc, key=lambda k: (k[0], k[1])):
        g = sc[key]
        entry = dict(g)
        entry["gate"] = ev.gate(g, max_asr, max_fpr) if (max_asr is not None and max_fpr is not None) else None
        doc["groups"][_group_name(key)] = entry
    # 개선 전후 비교: 같은 runner 의 controls_off/on 쌍
    runners = {k[0] for k in sc}
    for r in sorted(runners):
        off, on = sc.get((r, "controls_off")), sc.get((r, "controls_on"))
        if off and on:
            doc["pairs"].append({"runner": r, "differs": ev.compare(off, on),
                                 "off": off["defense"], "on": on["defense"]})
    # 가설 대조: 그룹 지표를 측정값으로 바꿔 hypothesis_log.compare 에 넣는다
    if hypothesis:
        measurements = []
        for key, g in doc["groups"].items():
            runner, cond = key.split(" / ")
            for metric, (k, n) in (("asr", g["asr"]), ("defense_rate", g["defense"]), ("fpr", g["fpr"])):
                if n:
                    measurements.append({"key": f"ch10.{runner}.{cond}.{metric}", "k": k if metric != "defense_rate" else n - k, "n": n})
        doc["hypothesis_rows"] = hyp.compare(hypothesis, measurements)
        doc["hypothesis"] = hypothesis
    return doc


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------
def _md_group(name, g):
    lines = [f"### {name}", "",
             "| 지표 | 값 (95% 구간) |",
             "| --- | --- |",
             f"| 방어율 | {fmt(*g['defense']) if g['defense'][1] else '측정 안 됨'} |",
             f"| 공격 성공률(ASR) | {fmt(*g['asr']) if g['asr'][1] else '측정 안 됨'} |",
             f"| 오탐률(FPR) | {fmt(*g['fpr']) if g['fpr'][1] else '측정 안 됨'} |"]
    if g["weighted_defense"] is not None:
        lines.append(f"| 심각도 가중 방어율 | {g['weighted_defense']:.0%} |")
    lines += ["", "| 유형 | 방어율 |", "| --- | --- |"]
    lines += [f"| {t} | {fmt(n - k, n)} |" for t, (k, n) in g["by_type"].items()]
    if g["not_run"]:
        lines += ["", "실행 안 된 케이스: " + ", ".join(f"`{c}`" for c in g["not_run"])]
    if g.get("gate"):
        gt = g["gate"]
        lines += ["", f"게이트: ASR {gt['ASR']}, FPR {gt['FPR']} → **{gt['verdict']}**"]
    return "\n".join(lines)


def to_markdown(doc, max_asr=None, max_fpr=None):
    lines = ["# AI 레드팀 측정 보고서", "",
             f"생성: {doc['generated_at']}  ·  집계만 담는다(모델 원문·입력 본문·카나리 제외)", ""]
    if not doc["groups"]:
        lines.append("측정 결과(Outcome)가 없다.")
        return "\n".join(lines)
    lines += ["## 1. 요약", ""]
    for name, g in doc["groups"].items():
        d = fmt(*g["defense"]) if g["defense"][1] else "측정 안 됨"
        a = fmt(*g["asr"]) if g["asr"][1] else "-"
        lines.append(f"- **{name}** — 방어율 {d}, ASR {a}" + (f", 게이트 {g['gate']['verdict']}" if g.get("gate") else ""))
    if doc["pairs"]:
        lines += ["", "## 2. 개선 전후 비교 (controls_off → controls_on)", "",
                  "| runner | 방어율 전 | 방어율 후 | 차이가 우연 변동을 넘는가 |", "| --- | --- | --- | --- |"]
        for p in doc["pairs"]:
            lines.append(f"| {p['runner']} | {fmt(*p['off'])} | {fmt(*p['on'])} | {'예' if p['differs'] else '아니오(구간 겹침)'} |")
    lines += ["", "## 3. 그룹별 지표", ""]
    lines += [_md_group(n, g) for n, g in doc["groups"].items()]
    if doc.get("hypothesis_rows"):
        lines += ["", "## 4. 가설 대비", "", "| 항목 | 가설 | 실제 | 결과 |", "| --- | --- | --- | --- |"]
        memo = doc["hypothesis"].get("memo", {})
        for r in doc["hypothesis_rows"]:
            pv = r["predicted"] if isinstance(r["predicted"], str) else (f"{r['predicted']:.0%}" if r["predicted"] is not None else "-")
            lines.append(f"| `{r['key']}` | {pv} | {r['actual']} | {r['result']} | {memo.get(r['key'], '')} |")
    lines += ["", "## 5. 한계", "",
              "- 표본이 작으면 신뢰구간이 넓다. 0건은 '안전'이 아니라 '상한 이하'다.",
              "- runner·condition·평가셋이 다른 숫자는 직접 비교하지 않는다(4장 비교 규칙).",
              "- 이 보고서는 초안이다. 잔여 위험 수용·조치 담당 지정은 사람이 한다.", "",
              "---", "",
              "*AI 레드팀 교육용 · 로컬 모델 전용 · 예약 도메인·카나리 규칙 강제*", "",
              "*produced by yundo*"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML (자체 완결, 11.5)
# ---------------------------------------------------------------------------
def to_html(doc, max_asr=None, max_fpr=None):
    charts = viz.dashboard_svg(doc)
    esc = html.escape
    body = [f"<h1>AI 레드팀 측정 보고서</h1><p class=meta>생성: {esc(doc['generated_at'])} · 집계 수치와 케이스 id 만 포함</p>"]
    body.append("<h2>그룹별 지표</h2><table><tr><th>그룹</th><th>방어율</th><th>ASR</th><th>오탐률</th><th>게이트</th></tr>")
    for name, g in doc["groups"].items():
        f = lambda kn: fmt(*g[kn]) if g[kn][1] else "측정 안 됨"
        gate = g["gate"]["verdict"] if g.get("gate") else "-"
        body.append(f"<tr><td>{esc(name)}</td><td>{esc(f('defense'))}</td><td>{esc(f('asr'))}</td><td>{esc(f('fpr'))}</td><td>{esc(gate)}</td></tr>")
    body.append("</table>")
    if doc["pairs"]:
        body.append("<h2>개선 전후 비교</h2><table><tr><th>runner</th><th>방어율 전</th><th>방어율 후</th><th>유의한 차이</th></tr>")
        for p in doc["pairs"]:
            body.append(f"<tr><td>{esc(p['runner'])}</td><td>{esc(fmt(*p['off']))}</td><td>{esc(fmt(*p['on']))}</td><td>{'예' if p['differs'] else '아니오'}</td></tr>")
        body.append("</table>")
    if doc.get("hypothesis_rows"):
        body.append("<h2>가설 대비</h2><table><tr><th>항목</th><th>가설</th><th>실제</th><th>결과</th></tr>")
        for r in doc["hypothesis_rows"]:
            pv = r["predicted"] if isinstance(r["predicted"], str) else (f"{r['predicted']:.0%}" if r["predicted"] is not None else "-")
            body.append(f"<tr><td><code>{esc(r['key'])}</code></td><td>{esc(str(pv))}</td><td>{esc(r['actual'])}</td><td>{esc(r['result'])}</td></tr>")
        body.append("</table>")
    body.append("<h2>차트</h2>" + charts)
    body.append("<h2>한계</h2><ul><li>표본이 작으면 신뢰구간이 넓다. 0건은 '안전'이 아니라 '상한 이하'다.</li>"
                "<li>runner·condition 이 다른 숫자는 직접 비교하지 않는다.</li><li>초안 보고서 — 수용 결정은 사람이 한다.</li></ul>")
    return viz.HTML_PAGE.replace("{{TITLE}}", "AI 레드팀 측정 보고서").replace("{{BODY}}", "\n".join(body))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("outcomes")
    ap.add_argument("--cases", required=True)
    ap.add_argument("-o", "--output")
    ap.add_argument("--format", choices=["md", "html", "both"], default="md")
    ap.add_argument("--max-asr", type=float)
    ap.add_argument("--max-fpr", type=float)
    ap.add_argument("--hypothesis", help="가설 JSON — 주면 가설 대비 표를 넣는다")
    a = ap.parse_args(argv)
    try:
        meta, outcomes = load_outcomes(a.outcomes)
        hypothesis = hyp.load(a.hypothesis) if a.hypothesis else None
        doc = build(load_cases(a.cases), outcomes, a.max_asr, a.max_fpr, hypothesis)
    except (ValueError, KeyError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    base = a.output or "report"
    base = str(Path(base).with_suffix(""))
    made = []
    if a.format in ("md", "both"):
        p = base + ".md"
        Path(p).write_text(to_markdown(doc, a.max_asr, a.max_fpr), encoding="utf-8")
        made.append(p)
    if a.format in ("html", "both"):
        p = base + ".html"
        Path(p).write_text(to_html(doc, a.max_asr, a.max_fpr), encoding="utf-8")
        made.append(p)
    if not a.output:
        print(to_markdown(doc, a.max_asr, a.max_fpr))
    else:
        print("저장: " + ", ".join(made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
