"""파이프라인: 측정(runner) → Outcome 저장 → 평가(evalset) → 보고(report)·대시보드(viz) 조합

run/pipeline.py 는 run 계층의 조합 지점이다. target/runners 에게 측정을 시키고
service/ 에게 계산·출력을 시킨다. 방향은 run → target → service → base 한 방향뿐.
"""
import datetime
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base import schema
from base.schema import Case
from base.stats import quick as stats_quick

ROOT = Path(__file__).resolve().parents[2]        # 10_redteam_framework/
RUNNERS = ("native", "pyrit", "garak", "graph")


def _set_quick(flag):
    if flag:
        import os
        os.environ["QUICK"] = "1"


class Cancelled(Exception):
    pass


def measure(cases, runners=("native",), conditions=("controls_off", "controls_on"), quick=False,
            model=None, on_progress=None, cancel_event=None):
    """선택한 러너·조건으로 측정해 (Outcome 목록, meta dict) 를 돌려준다. LLM 이 필요하다.
    on_progress(메시지): 진행 표시 콜백. cancel_event.set() 되면 Cancelled 를 던진다."""
    _set_quick(quick)
    outcomes, metas = [], {}

    def prog(msg):
        if on_progress:
            on_progress(msg)
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled()

    for r in runners:
        prog(f"runner {r} 시작")
        if r == "native":
            from target.runners import native
            for c in cases:
                if c.expected != "block":
                    continue                      # native 는 정상 케이스를 다루지 않는다(스캔 러너의 benign 담당)
                prog(f"native {c.id}")
                try:
                    got, meta = native.run_case(c, model=model)
                except Exception as e:
                    print(f"[native] {c.id} 건너뜀: {e}", file=sys.stderr)
                    continue
                for o in got:
                    if o.condition in conditions:
                        outcomes.append(o)
                metas["native"] = meta
        elif r == "pyrit":
            from target.runners import pyrit
            for cond in conditions:
                prog(f"pyrit {cond}")
                got, metas["pyrit"] = pyrit.run(cond, model=model)
                outcomes += got
        elif r == "garak":
            from target.runners import garak
            for cond in conditions:
                prog(f"garak {cond}")
                got, metas["garak"] = garak.run(cond, model=model)
                outcomes += got
        elif r == "graph":
            from target.runners import graph
            prog("graph (LangGraph 평가 게이트)")
            got, metas["graph"] = graph.run(model=model)   # 두 condition 을 한 번에 돌려준다
            outcomes += [o for o in got if o.condition in conditions]
        else:
            raise ValueError(f"모르는 러너: {r} (가능: {RUNNERS})")
        prog(f"runner {r} 완료")
    meta = {"started_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "runners": list(runners), "conditions": list(conditions), "quick": bool(quick),
            "tools": metas}
    return outcomes, meta


def all_in_one(cases_path, runners=("native",), conditions=("controls_off", "controls_on"),
              quick=False, out_dir=None, max_asr=0.2, max_fpr=0.1, model=None,
              on_progress=None, cancel_event=None, hypothesis=None):
    """측정 → outcomes.json → evalset → report.md/html → dashboard.html 까지 한 번에.
    hypothesis: 가설 JSON 경로 또는 dict — 주면 보고서·대시보드에 가설 대조(차트③)를 넣는다."""
    from service import evalset as ev
    from service import report as rep
    from service import viz
    from base import hypothesis_log as hyp

    cases = schema.load_cases(cases_path)
    outcomes, meta = measure(cases, runners, conditions, quick, model, on_progress, cancel_event)
    h = hypothesis if isinstance(hypothesis, dict) else (hyp.load(hypothesis) if hypothesis else None)
    out_dir = Path(out_dir or (ROOT / "results"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    opath = out_dir / f"ch10-outcomes-{stamp}.json"
    latest = out_dir / "ch10-outcomes.json"
    schema.save_outcomes(str(opath), outcomes, meta)
    schema.save_outcomes(str(latest), outcomes, meta)     # 최신본은 고정 이름(GUI 기본 경로)
    sc = ev.score(cases, outcomes)
    doc = rep.build(cases, outcomes, max_asr, max_fpr, h)
    md_t = out_dir / f"ch10-report-{stamp}.md"
    html_t = out_dir / f"ch10-report-{stamp}.html"
    dash_t = out_dir / f"ch10-dashboard-{stamp}.html"
    md_t.write_text(rep.to_markdown(doc, max_asr, max_fpr), encoding="utf-8")
    html_t.write_text(rep.to_html(doc, max_asr, max_fpr), encoding="utf-8")
    dash_t.write_text(viz.dashboard_html(doc), encoding="utf-8")
    # 고정 이름 최신본도 함께 둔다(이전 실행을 덮어쓰지 않도록 타임스탬프본이 정본)
    shutil.copyfile(md_t, out_dir / "ch10-report.md")
    shutil.copyfile(html_t, out_dir / "ch10-report.html")
    shutil.copyfile(dash_t, out_dir / "ch10-dashboard.html")
    print(f"Outcome: {opath}  (최신본: {latest.name})")
    print(f"보고서:   {md_t.name}, {html_t.name}  (최신본: ch10-report.md/html)")
    print(f"대시보드: {dash_t.name}  (최신본: ch10-dashboard.html)")
    print()
    print(ev.report(sc, max_asr, max_fpr))
    return {"outcomes": str(latest), "outcomes_history": str(opath),
            "report_md": str(md_t), "report_html": str(html_t), "dashboard": str(dash_t)}
