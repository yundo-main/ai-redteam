"""웹 서버 + 정적 파일 서빙 (표준 라이브러리 http.server, 의존성 0)

ROE: 기본 127.0.0.1 에만 바인딩한다. 외부 인터페이스는 --host + --allow-remote 를
둘 다 명시해야 열리고, 그 경우에도 이 서버는 인증이 없으므로 교육용 로컬 전용이다.

API
  GET  /                     GUI (web/index.html)
  GET  /app.js /style.css    정적 파일
  GET  /api/jobs             작업 목록
  POST /api/jobs             측정 시작 {"cases","runners","quick","out_dir","max_asr","max_fpr","model"}
  GET  /api/jobs/<id>        작업 상태·진행
  POST /api/jobs/<id>/cancel 취소
  GET  /api/score?outcomes=&cases=   지표 텍스트
  GET  /api/evallog?limit=50         평가(지표 계산·분석) 실행 로그 — results/eval_log.jsonl
  GET  /api/viz?outcomes=&cases=     대시보드 HTML
  GET  /api/report?outcomes=&cases=&format=md|html|both  보고서 생성/조회
  GET  /api/results?dir=results      결과 파일 목록
"""
import argparse
import json
import mimetypes
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SRC = Path(__file__).resolve().parents[1]          # src/
WEB = SRC / "web"
ROOT = SRC.parent                                   # 10_redteam_framework/
REPO = ROOT.parent                                  # 저장소 루트
SETTINGS_FILE = ROOT / "settings.json"              # GUI 저장 설정(API 키 포함 가능 — gitignore 대상)
EVAL_LOG = ROOT / "results" / "eval_log.jsonl"       # 평가 실행 로그(지표 계산·분석 실행마다 한 줄 추가)


def _log_eval(kind, outcomes, cases, groups, hypothesis=None):
    """평가(지표 계산·분석) 1회 실행을 results/eval_log.jsonl 에 한 줄 추가한다. 실패해도 응답에 영향 없음."""
    import datetime
    try:
        EVAL_LOG.parent.mkdir(parents=True, exist_ok=True)
        verdicts = {k: (g.get("gate") or {}).get("verdict") for k, g in groups.items()}
        entry = {"at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                 "kind": kind, "outcomes": outcomes, "cases": cases,
                 "hypothesis": hypothesis, "groups": verdicts}
        with open(EVAL_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _read_eval_log(limit=50):
    if not EVAL_LOG.is_file():
        return []
    lines = EVAL_LOG.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        try:
            e = json.loads(line)
            e["idx"] = i
            out.append(e)
        except json.JSONDecodeError:
            continue
    return list(reversed(out[-limit:]))


def _delete_eval_log_idx(idx):
    """eval_log.jsonl에서 idx 번째 줄만 제거. 파일이 재작성됨."""
    if not EVAL_LOG.is_file() or not isinstance(idx, int) or idx < 0:
        return False
    lines = EVAL_LOG.read_text(encoding="utf-8").splitlines()
    if idx >= len(lines):
        return False
    del lines[idx]
    EVAL_LOG.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return True


class Handler(BaseHTTPRequestHandler):
    server_version = "redteam/0.1"

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype=None):
        if path is None:
            return self._json({"error": "not found"}, 404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype or mimetypes.guess_type(str(path))[0] or "application/octet-stream")
        if (ctype or "").startswith(("text/html", "text/css", "text/javascript")):
            self.send_header("Cache-Control", "no-store")   # GUI 갱신 즉시 반영
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass

    # ---------------- GET ----------------
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        try:
            if path == "/":
                return self._file(WEB / "index.html", "text/html; charset=utf-8")
            if path in ("/app.js", "/style.css"):
                return self._file(WEB / path.lstrip("/"),
                                  "text/javascript" if path.endswith(".js") else "text/css")
            if path.startswith("/docs/"):
                name = path[len("/docs/"):]
                if "/" in name or ".." in name:
                    return self._json({"error": "bad path"}, 400)
                f = ROOT / "docs" / name
                return self._file(f if f.is_file() and f.suffix in (".svg", ".md") else None,
                                  "image/svg+xml" if name.endswith(".svg") else "text/plain; charset=utf-8")
            if path == "/api/info":
                import os, sys, importlib.util
                from base import llm
                def has(mod):
                    try:
                        return importlib.util.find_spec(mod) is not None
                    except Exception:
                        return False
                return self._json({
                    "backend": llm.BACKEND,
                    "endpoint": llm.endpoint_url(),
                    "api_url": llm.api_root(),
                    "model_env": os.environ.get("REDTEAM_LLM_MODEL") or (
                        llm.PREFERRED if llm.BACKEND == "ollama" else "(미설정 — 필수)"),
                    "python": sys.version.split()[0],
                    "runners": {"native": True, "graph": has("langgraph"),
                                "pyrit": has("pyrit"), "garak": has("garak")},
                })
            if path == "/api/settings":
                from base import llm
                return self._json(llm.settings_view())
            if path == "/api/llmtest":
                from base import llm
                try:
                    ok, why, model = llm.ready()
                except Exception as e:
                    return self._json({"ok": False, "reason": str(e), "model": None})
                return self._json({"ok": ok, "reason": why, "model": model,
                                   "backend": llm.BACKEND, "endpoint": llm.endpoint_url()})
            if path == "/api/evalset":
                p = Path(self._resolve(q["path"][0]))
                if not p.is_file():
                    return self._json({"error": "not found"}, 404)
                return self._json({"path": str(p), "content": p.read_text(encoding="utf-8")})
            if path == "/api/casesets":
                files = []
                for d in (SRC / "data", ROOT / "exchange" / "evalset"):
                    if d.is_dir():
                        files += [str(p.relative_to(REPO)) for p in sorted(d.glob("*.json"))
                                  if not p.name.startswith("hypothesis")]
                return self._json({"files": sorted(set(files))})
            if path == "/api/outcomesets":
                files = []
                for d in (ROOT / "results", ROOT / "exchange" / "outcomes"):
                    if d.is_dir():
                        files += [str(p.relative_to(REPO)) for p in sorted(d.glob("*.json"))]
                return self._json({"files": sorted(set(files))})
            if path == "/api/analyze":
                from service import report as rep
                from base.schema import load_cases, load_outcomes
                _, outcomes = load_outcomes(self._resolve(q["outcomes"][0]))
                cases = load_cases(self._resolve(q["cases"][0]))
                max_asr = float(q.get("max_asr", ["0.2"])[0])
                max_fpr = float(q.get("max_fpr", ["0.1"])[0])
                h = self._hypothesis(q)
                if isinstance(h, str):
                    return self._json({"error": f"가설 파일: {h}"}, 400)
                doc = rep.build(cases, outcomes, max_asr, max_fpr, h)
                groups = {k: {"defense": g["defense"], "asr": g["asr"], "fpr": g["fpr"],
                              "weighted_defense": g.get("weighted_defense"),
                              "not_run": g.get("not_run", []), "gate": g.get("gate")}
                          for k, g in doc["groups"].items()}
                _log_eval("analyze", q["outcomes"][0], q["cases"][0], groups, q.get("hypothesis", [None])[0])
                return self._json({"generated_at": doc["generated_at"], "groups": groups,
                                   "max_asr": max_asr, "max_fpr": max_fpr,
                                   "hypothesis_rows": doc.get("hypothesis_rows"),
                                   "pairs": doc.get("pairs", [])})
            if path == "/api/hypotheses":
                found = []
                for d in (ROOT / "exchange" / "hypothesis", SRC / "data", ROOT / "results"):
                    if d.is_dir():
                        found += [str(p.relative_to(REPO)) for p in d.glob("*hypothesis*.json")]
                return self._json({"files": sorted(set(found))})
            if path == "/api/hypothesis":
                p = Path(self._resolve(q["path"][0]))
                if not p.is_file():
                    return self._json({"error": "not found"}, 404)
                return self._json({"path": str(p), "content": p.read_text(encoding="utf-8")})
            if path == "/api/jobs":
                from run import jobs
                return self._json({"jobs": jobs.list_jobs()})
            if path.startswith("/api/jobs/"):
                from run import jobs
                job = jobs.get(path.rsplit("/", 1)[-1])
                return self._json(job if job else {"error": "not found"}, 200 if job else 404)
            if path == "/api/results":
                rel = q.get("dir", ["results"])[0].lstrip("/")
                d = Path(self._resolve(rel))
                if not str(d).startswith(str(REPO.resolve())) or not d.is_dir():
                    return self._json({"error": "bad dir"}, 400)
                files = sorted(p.name for p in d.iterdir() if p.is_file())
                return self._json({"dir": str(d), "files": files})
            if path == "/api/cases":
                from base.schema import load_cases
                cases = load_cases(self._resolve(q["path"][0]))
                return self._json({"cases": [{
                    "id": c.id, "type": c.type, "subtype": c.subtype, "input": c.input,
                    "expected": c.expected, "criterion": c.criterion, "severity": c.severity,
                    "source": c.source, "scenario_id": c.scenario_id} for c in cases],
                    "counts": {"attack": sum(c.expected == "block" for c in cases),
                               "benign": sum(c.expected == "allow" for c in cases)}})
            if path == "/api/score":
                from service import evalset as ev
                from base.schema import load_cases, load_outcomes
                _, outcomes = load_outcomes(self._resolve(q["outcomes"][0]))
                cases = load_cases(self._resolve(q["cases"][0]))
                sc = ev.score(cases, outcomes)
                groups = {f"{r} / {c}": {"gate": None} for (r, c) in sc}
                _log_eval("score", q["outcomes"][0], q["cases"][0], groups)
                return self._text(ev.report(sc))
            if path == "/api/evallog":
                return self._json({"entries": _read_eval_log(int(q.get("limit", ["50"])[0]))})
            if path == "/api/viz":
                from service import report as rep, viz
                from base.schema import load_cases, load_outcomes
                _, outcomes = load_outcomes(self._resolve(q["outcomes"][0]))
                cases = load_cases(self._resolve(q["cases"][0]))
                h = self._hypothesis(q)
                if isinstance(h, str):
                    return self._json({"error": h}, 400)
                doc = rep.build(cases, outcomes, hypothesis=h)
                _log_eval("viz", q["outcomes"][0], q["cases"][0], {}, q.get("hypothesis", [None])[0])
                return self._file_text(viz.dashboard_html(doc), "text/html; charset=utf-8")
            if path == "/api/compare":
                from service import report as rep, viz
                from base.schema import load_cases, load_outcomes
                _, oa = load_outcomes(self._resolve(q["outcomes_a"][0]))
                _, ob = load_outcomes(self._resolve(q["outcomes_b"][0]))
                cases = load_cases(self._resolve(q["cases"][0]))
                la = q.get("label_a", ["실행 A"])[0][:60]
                lb = q.get("label_b", ["실행 B"])[0][:60]
                h = self._hypothesis(q)
                if isinstance(h, str):
                    return self._json({"error": h}, 400)
                da = rep.build(cases, oa, hypothesis=h)
                db = rep.build(cases, ob, hypothesis=h)
                _log_eval("compare", f"{q['outcomes_a'][0]} ↔ {q['outcomes_b'][0]}", q["cases"][0], {}, q.get("hypothesis", [None])[0])
                return self._file_text(viz.compare_dashboard_html(da, db, la, lb),
                                       "text/html; charset=utf-8")
            if path == "/api/report":
                from service import report as rep
                from base.schema import load_cases, load_outcomes
                fmt = q.get("format", ["md"])[0]
                _, outcomes = load_outcomes(self._resolve(q["outcomes"][0]))
                cases = load_cases(self._resolve(q["cases"][0]))
                h = self._hypothesis(q)
                if isinstance(h, str):
                    return self._json({"error": f"가설 파일: {h}"}, 400)
                doc = rep.build(cases, outcomes, hypothesis=h)
                _log_eval(f"report-{fmt}", q["outcomes"][0], q["cases"][0], {}, h if isinstance(h, dict) else None)
                if fmt == "html":
                    return self._file_text(rep.to_html(doc), "text/html; charset=utf-8")
                return self._file_text(rep.to_markdown(doc), "text/markdown; charset=utf-8")
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def _evalset_post(self, path, body):
        """평가셋 편집기 API — validate(내용 검사) / save(저장) / append(케이스 추가) / case/validate."""
        from base.schema import Case, validate_case

        def problems_of(data):
            """{"cases":[...]} dict 를 검사해 문제 목록을 돌려준다."""
            problems = []
            cases_raw = data.get("cases") if isinstance(data, dict) else None
            if not isinstance(cases_raw, list) or not cases_raw:
                return ["'cases' 가 비어 있거나 없다"]
            has_block = has_allow = False
            for d in cases_raw:
                try:
                    c = Case.from_dict(d)
                    problems += validate_case(c)
                    has_block |= c.expected == "block"
                    has_allow |= c.expected == "allow"
                except Exception as e:
                    problems.append(str(e))
            if not has_block:
                problems.append("공격 케이스(expected=block)가 없다")
            if not has_allow:
                problems.append("정상 케이스(expected=allow)가 없다")
            return problems

        if path == "/api/case/validate":
            problems = []
            try:
                c = Case.from_dict(body.get("case", {}))
                problems = validate_case(c)
            except Exception as e:
                problems = [str(e)]
            return self._json({"ok": not problems, "errors": problems, "warnings": []})

        if path == "/api/evalset/validate":
            try:
                data = json.loads(body.get("content", ""))
            except json.JSONDecodeError as e:
                return self._json({"ok": False, "errors": [f"JSON 오류: {e}"], "warnings": []})
            problems = problems_of(data)
            return self._json({"ok": not problems, "errors": problems, "warnings": []})

        if path == "/api/evalset":
            rel = body.get("path", "")
            p = Path(self._resolve(rel))
            if p.suffix != ".json" or ".." in rel:
                return self._json({"error": "JSON 파일 경로만 허용"}, 400)
            try:
                data = json.loads(body.get("content", ""))
            except json.JSONDecodeError as e:
                return self._json({"error": f"JSON 오류: {e}"}, 400)
            problems = problems_of(data)
            if problems:
                return self._json({"error": "검증 실패: " + "; ".join(problems[:5])}, 400)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body.get("content", ""), encoding="utf-8")
            return self._json({"ok": True, "path": str(p)})

        # /api/evalset/append — 기존 파일에 케이스 하나 추가
        rel = body.get("path", "")
        p = Path(self._resolve(rel))
        if p.suffix != ".json" or ".." in rel or not p.is_file():
            return self._json({"error": "평가셋 JSON 파일이 필요하다"}, 400)
        try:
            case = body.get("case")
            if not isinstance(case, dict):
                return self._json({"error": "case 객체가 필요하다"}, 400)
            c = Case.from_dict(case)
            probs = validate_case(c)
            if probs:
                return self._json({"error": "케이스 검증 실패: " + "; ".join(probs)}, 400)
            data = json.loads(p.read_text(encoding="utf-8"))
            data.setdefault("cases", []).append(case)
            p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return self._json({"ok": True, "path": str(p), "count": len(data["cases"])})
        except Exception as e:
            return self._json({"error": str(e)}, 400)

    def _hypothesis(self, q):
        """?hypothesis= 경로를 읽어 가설 스냅샷을 돌려준다. 없으면 None, 오류면 문자열."""
        hyp_path = q.get("hypothesis", [""])[0]
        if not hyp_path:
            return None
        try:
            from base import hypothesis_log as hyp
            return hyp.load(self._resolve(hyp_path))
        except Exception as e:
            return str(e)

    def _resolve(self, rel):
        """API 경로 인자를 src/ 기준 절대 경로로. 상대 경로는 저장소 루트 기준."""
        p = Path(rel)
        if p.is_absolute():
            return str(p)
        for base in (REPO, ROOT, SRC):
            cand = base / rel
            if cand.exists():
                return str(cand)
        return str(REPO / rel)

    def _text(self, s, ctype="text/plain; charset=utf-8", code=200):
        body = s.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file_text(self, s, ctype):
        self._text(s, ctype)

    def do_DELETE(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            body = {}
        try:
            if u.path == "/api/jobs":
                from run import jobs
                deleted, skipped = 0, 0
                for j in jobs.list_jobs():
                    if j["status"] in ("running", "pending"):
                        skipped += 1
                        continue
                    p = jobs.JOBS_DIR / f"{j['id']}.json"
                    if p.is_file():
                        p.unlink()
                    jobs._jobs.pop(j["id"], None)
                    deleted += 1
                return self._json({"ok": True, "deleted": deleted, "skipped": skipped})
            if u.path.startswith("/api/jobs/"):
                from run import jobs
                jid = u.path.rsplit("/", 1)[-1]
                job = jobs.get(jid)
                if not job:
                    return self._json({"error": "not found"}, 404)
                if job["status"] in ("running", "pending"):
                    return self._json({"error": "실행 중인 작업은 삭제할 수 없습니다 — 먼저 취소하세요"}, 400)
                p = jobs.JOBS_DIR / f"{jid}.json"
                if p.is_file():
                    p.unlink()
                jobs._jobs.pop(jid, None)
                return self._json({"ok": True})
            if u.path == "/api/evallog":
                if isinstance(body, dict) and "idx" in body:
                    if not _delete_eval_log_idx(body["idx"]):
                        return self._json({"error": "not found"}, 404)
                    return self._json({"ok": True})
                if EVAL_LOG.is_file():
                    EVAL_LOG.unlink()
                return self._json({"ok": True})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    # ---------------- POST ----------------
    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._json({"error": "bad json"}, 400)
        try:
            if u.path == "/api/hypothesis/validate":
                from base import hypothesis_log as hyp
                errors, warnings = hyp.validate(body.get("content", ""))
                return self._json({"ok": not errors, "errors": errors, "warnings": warnings})
            if u.path in ("/api/evalset", "/api/evalset/validate", "/api/evalset/append", "/api/case/validate"):
                return self._evalset_post(u.path, body)
            if u.path == "/api/hypothesis":
                rel = body.get("path", "")
                p = Path(self._resolve(rel))
                if p.suffix != ".json" or ".." in rel:
                    return self._json({"error": "JSON 파일 경로만 허용"}, 400)
                try:
                    json.loads(body.get("content", ""))
                except json.JSONDecodeError as e:
                    return self._json({"error": f"JSON 오류: {e}"}, 400)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body.get("content", ""), encoding="utf-8")
                return self._json({"ok": True, "path": str(p)})
            if u.path == "/api/settings":
                from base import llm
                backend = body.get("backend")
                if backend is not None and backend not in ("ollama", "openai", "anthropic", "gemini"):
                    return self._json({"error": f"알 수 없는 백엔드: {backend}"}, 400)
                llm.configure(
                    backend=backend,
                    url=body.get("url"),
                    model=body.get("model"),
                    key=body.get("key"),
                    ollama_url=body.get("ollama_url"),
                    allow_remote=body.get("allow_remote"))
                keep_key = llm.API_KEY
                SETTINGS_FILE.write_text(json.dumps({
                    "backend": llm.BACKEND, "url": llm.API_URL, "model": body.get("model") or "",
                    "key": keep_key, "ollama_url": llm.BASE_URL,
                    "allow_remote": llm.settings_view()["allow_remote"]}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
                return self._json({"ok": True, **llm.settings_view()})
            if u.path == "/api/jobs":
                from run import jobs
                job = jobs.start(self._resolve(body.get("cases", "exchange/evalset/sample-cases.json")),
                                 runners=tuple(body.get("runners", ["native"])),
                                 quick=bool(body.get("quick")),
                                 out_dir=self._resolve(body.get("out_dir") or "results"),
                                 max_asr=float(body.get("max_asr", 0.2)),
                                 max_fpr=float(body.get("max_fpr", 0.1)),
                                 model=body.get("model"),
                                 hypothesis=self._resolve(body["hypothesis"]) if body.get("hypothesis") else None)
                return self._json(job, 201)
            if u.path.startswith("/api/jobs/") and u.path.endswith("/cancel"):
                from run import jobs
                jid = u.path.split("/")[-2]
                return self._json({"cancelled": jobs.cancel(jid)})
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)}, 500)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--allow-remote", action="store_true")
    a = ap.parse_args(argv)
    host = a.host
    if host not in ("127.0.0.1", "localhost", "::1") and not a.allow_remote:
        raise SystemExit(f"외부 바인딩({host})은 --allow-remote 명시가 필요하다(ROE: 기본은 127.0.0.1)")
    # 저장된 GUI 설정(settings.json)을 환경변수보다 우선 적용
    try:
        if SETTINGS_FILE.is_file():
            from base import llm
            llm.configure(**json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception as e:
        print(f"settings.json 적용 실패(무시하고 계속): {e}")
    srv = ThreadingHTTPServer((host, a.port), Handler)
    print(f"redteam 서버: http://{host}:{a.port}  (Ctrl+C 로 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
