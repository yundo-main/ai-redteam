"""redteam CLI: run · score · report · viz · all · import · serve

사용 (저장소 루트에서)
  python 10_redteam_framework/src/run/cli.py run <cases.json> [--runners native,pyrit,garak] [--quick] [-o out.json]
  python 10_redteam_framework/src/run/cli.py score <outcomes.json> --cases <cases.json> [--max-asr 0.2 --max-fpr 0.1]
  python 10_redteam_framework/src/run/cli.py report <outcomes.json> --cases <cases.json> -o report [--format md|html|both]
  python 10_redteam_framework/src/run/cli.py viz <outcomes.json> --cases <cases.json> -o dashboard.html
  python 10_redteam_framework/src/run/cli.py all <cases.json> [--quick] [--out-dir results]
  python 10_redteam_framework/src/run/cli.py import <legacy.json> -o outcomes.json [--cases cases.json]
  python 10_redteam_framework/src/run/cli.py serve [--port 8000] [--host 127.0.0.1]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _runners(s):
    return tuple(x.strip() for x in s.split(",") if x.strip())


def _conds(s):
    m = {"off": "controls_off", "on": "controls_on", "off,on": None}
    if s == "off,on":
        return ("controls_off", "controls_on")
    return (m.get(s, s),)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="redteam", description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="측정만 실행해 Outcome JSON 저장")
    p.add_argument("cases")
    p.add_argument("--runners", default="native")
    p.add_argument("--conditions", default="off,on")
    p.add_argument("--quick", action="store_true")
    p.add_argument("-o", "--output", default="10_redteam_framework/results/ch10-outcomes.json")
    p.add_argument("--model")

    p = sub.add_parser("score", help="Outcome → 지표·게이트 텍스트")
    p.add_argument("outcomes")
    p.add_argument("--cases", required=True)
    p.add_argument("--max-asr", type=float)
    p.add_argument("--max-fpr", type=float)

    p = sub.add_parser("report", help="Outcome → 보고서 md/html")
    p.add_argument("outcomes")
    p.add_argument("--cases", required=True)
    p.add_argument("-o", "--output")
    p.add_argument("--format", choices=["md", "html", "both"], default="md")
    p.add_argument("--max-asr", type=float)
    p.add_argument("--max-fpr", type=float)
    p.add_argument("--hypothesis")

    p = sub.add_parser("viz", help="Outcome → 대시보드 HTML")
    p.add_argument("outcomes")
    p.add_argument("--cases", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--max-asr", type=float)
    p.add_argument("--max-fpr", type=float)

    p = sub.add_parser("compare", help="두 Outcome 파일 비교 대시보드 HTML")
    p.add_argument("outcomes_a")
    p.add_argument("outcomes_b")
    p.add_argument("--cases", required=True)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--label-a", default="실행 A")
    p.add_argument("--label-b", default="실행 B")
    p.add_argument("--max-asr", type=float)
    p.add_argument("--max-fpr", type=float)

    p = sub.add_parser("all", help="측정→평가→보고→대시보드 한 번에")
    p.add_argument("cases")
    p.add_argument("--runners", default="native")
    p.add_argument("--quick", action="store_true")
    p.add_argument("--out-dir", default="10_redteam_framework/results")
    p.add_argument("--max-asr", type=float, default=0.2)
    p.add_argument("--max-fpr", type=float, default=0.1)
    p.add_argument("--model")
    p.add_argument("--hypothesis", help="가설 JSON — 보고서·대시보드에 가설 대조를 넣는다")

    p = sub.add_parser("worksheet", help="6-2 워크시트 JSON → Case 목록 변환")
    p.add_argument("worksheets", nargs="+")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--merge", help="기존 cases 파일에 병합")

    p = sub.add_parser("import", help="앞 일차(03~07) 기록 → Outcome 변환")
    p.add_argument("record")
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--cases")
    p.add_argument("--kind", default="auto", choices=["auto", "harness", "scan", "evalset"])

    p = sub.add_parser("serve", help="웹 서버 + GUI (기본 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--allow-remote", action="store_true", help="외부 인터페이스 바인딩 허용(비권장)")

    a = ap.parse_args(argv)

    try:
        if a.cmd == "run":
            from base import schema
            from run import pipeline
            cases = schema.load_cases(a.cases)
            outcomes, meta = pipeline.measure(cases, _runners(a.runners), _conds(a.conditions), a.quick, a.model)
            schema.save_outcomes(a.output, outcomes, meta)
            print(f"저장: {a.output} ({len(outcomes)}개 Outcome)")
            return 0
        if a.cmd == "score":
            from service import evalset as ev
            from base.schema import load_cases, load_outcomes
            _, outcomes = load_outcomes(a.outcomes)
            print(ev.report(ev.score(load_cases(a.cases), outcomes), a.max_asr, a.max_fpr))
            return 0
        if a.cmd == "report":
            from service import report as rep
            from base.schema import load_cases, load_outcomes
            from base import hypothesis_log as hyp
            _, outcomes = load_outcomes(a.outcomes)
            h = hyp.load(a.hypothesis) if a.hypothesis else None
            doc = rep.build(load_cases(a.cases), outcomes, a.max_asr, a.max_fpr, h)
            if not a.output:
                print(rep.to_markdown(doc, a.max_asr, a.max_fpr))
                return 0
            base = str(Path(a.output).with_suffix(""))
            made = []
            if a.format in ("md", "both"):
                Path(base + ".md").write_text(rep.to_markdown(doc, a.max_asr, a.max_fpr), encoding="utf-8")
                made.append(base + ".md")
            if a.format in ("html", "both"):
                Path(base + ".html").write_text(rep.to_html(doc, a.max_asr, a.max_fpr), encoding="utf-8")
                made.append(base + ".html")
            print("저장: " + ", ".join(made))
            return 0
        if a.cmd == "viz":
            from service import viz
            sys.argv = ["viz", a.outcomes, "--cases", a.cases, "-o", a.output,
                        *(["--max-asr", str(a.max_asr)] if a.max_asr is not None else []),
                        *(["--max-fpr", str(a.max_fpr)] if a.max_fpr is not None else [])]
            return viz.main(sys.argv[1:])
        if a.cmd == "compare":
            from service import report as rep, viz
            from base.schema import load_cases, load_outcomes
            from pathlib import Path
            _, oa = load_outcomes(a.outcomes_a)
            _, ob = load_outcomes(a.outcomes_b)
            cases = load_cases(a.cases)
            da = rep.build(cases, oa, a.max_asr, a.max_fpr)
            db = rep.build(cases, ob, a.max_asr, a.max_fpr)
            Path(a.output).write_text(
                viz.compare_dashboard_html(da, db, a.label_a, a.label_b), encoding="utf-8")
            print(f"저장: {a.output}")
            return 0
        if a.cmd == "all":
            from run import pipeline
            pipeline.all_in_one(a.cases, _runners(a.runners), _conds("off,on"), a.quick,
                                a.out_dir, a.max_asr, a.max_fpr, a.model,
                                hypothesis=a.hypothesis)
            return 0
        if a.cmd == "worksheet":
            from run import from_worksheet
            return from_worksheet.main([*a.worksheets, "-o", a.output,
                                        *( ["--merge", a.merge] if a.merge else [] )])
        if a.cmd == "import":
            from run import import_legacy
            return import_legacy.main([a.record, "-o", a.output, "--kind", a.kind,
                                       *(["--cases", a.cases] if a.cases else [])])
        if a.cmd == "serve":
            from run import server
            return server.main(["--port", str(a.port), "--host", a.host,
                                *(["--allow-remote"] if a.allow_remote else [])])
    except (ValueError, KeyError, OSError) as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
