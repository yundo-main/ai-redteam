"""시각화: Outcome 기반 보고서 문서(doc)를 SVG 차트 5종과 대시보드 HTML 로 그린다 (표준 라이브러리만)

readme.md 11장의 원칙을 따른다.
  1. 구간을 항상 그린다 — 점추정만 그리지 않고 Wilson 95% 구간을 함께 표시. 0건은 "상한 이하"로.
  2. 섞어 그리지 않는다 — runner·condition 이 다른 숫자는 같은 축에 합치지 않고 패널을 나눈다.
  3. 작은 표본은 흐리게 — n 이 작으면 막대를 연하게 하고 n=… 을 표기.
  4. 정직한 축 — 비율 축은 0~100% 고정.
  5. 민감 정보 없음 — 집계 수치와 케이스 id 만. 값은 HTML 이스케이프.
  6. 색만으로 구분하지 않는다 — 기호·글자 병행.

입력은 service.report.build() 가 만든 doc(dict)이다. 새 측정은 하지 않는다(끝단).
"""
import html
import math
from xml.sax.saxutils import escape

from base.stats import fmt, wilson

# 밝은 화면 기준 슬라이드와 어울리는 색 (어두운 화면은 prefers-color-scheme 로 배경만 바꾼다)
C = {"bar": "#4a7fc1", "bar_on": "#2e8b6f", "ci": "#333", "grid": "#e3e3e3",
     "text": "#222", "dim": "#999", "warn": "#c25e5e", "hyp": "#b8860b"}
NS = 'xmlns="http://www.w3.org/2000/svg"'


def _svg(w, h, body, title=""):
    return (f'<svg {NS} width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img">'
            f'<title>{escape(title)}</title>{body}</svg>')


def _esc(s):
    return escape(str(s))


def _pct(x):
    return f"{x * 100:.0f}%"


# ---------------------------------------------------------------------------
# 공통 부품: 비율 막대 + 신뢰구간
# ---------------------------------------------------------------------------
def _bar(x, y, w, h, frac, color, alpha=1.0):
    """0~1 비율 막대. 라벨은 호출자가 그린다."""
    fw = max(0.0, min(1.0, frac)) * w
    return (f'<rect x="{x:.1f}" y="{y:.1f}" width="{fw:.1f}" height="{h}" fill="{color}" '
            f'fill-opacity="{alpha}" rx="2"/>')


def _ci_line(x, y, w, frac_lo, frac_hi, color=C["ci"]):
    """신뢰구간 수평선 + 끝점."""
    x1, x2 = x + frac_lo * w, x + frac_hi * w
    return (f'<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}" stroke="{color}" stroke-width="1.6"/>'
            f'<line x1="{x1:.1f}" y1="{y-4}" x2="{x1:.1f}" y2="{y+4}" stroke="{color}" stroke-width="1.6"/>'
            f'<line x1="{x2:.1f}" y1="{y-4}" x2="{x2:.1f}" y2="{y+4}" stroke="{color}" stroke-width="1.6"/>')


def _axis(w, x, y, h):
    """0~100% 축 그리드(20% 단위)와 눈금."""
    grid = C["grid"]
    dim = C["dim"]
    parts = [f'<line x1="{x}" y1="{y}" x2="{x+w}" y2="{y}" stroke="{grid}"/>']
    for i in range(6):
        gx = x + w * i / 5
        parts.append(f'<line x1="{gx:.1f}" y1="{y}" x2="{gx:.1f}" y2="{y+h}" stroke="{grid}" stroke-dasharray="2,3"/>')
        parts.append(f'<text x="{gx:.1f}" y="{y+h+14}" font-size="10" fill="{dim}" text-anchor="middle">{i*20}%</text>')
    return "".join(parts)


def _small_n(frac_n, full=30):
    """n 이 작으면(기본 30 미만) 투명도를 낮춘다."""
    return max(0.35, min(1.0, frac_n / full)) if frac_n else 0.35


# ---------------------------------------------------------------------------
# 차트 ① 유형별 방어율 막대 + 신뢰구간 (그룹별 패널)
# ---------------------------------------------------------------------------
def chart_defense_by_type(doc):
    rows = []
    for gname, g in doc["groups"].items():
        for t, (k, n) in g["by_type"].items():
            if n:
                rows.append((gname, t, n - k, n))
    if not rows:
        return ""
    W, rowh, pad_l, pad_r = 640, 30, 170, 90
    H = 40 + rowh * len(rows)
    parts = [f'<text x="{pad_l}" y="18" font-size="12" fill="{C["text"]}">① 유형별 방어율 (막대=점추정, 선=95% 구간, 옅을수록 표본 작음)</text>']
    for i, (gname, t, k, n) in enumerate(rows):
        y = 30 + i * rowh
        x, w = pad_l, W - pad_l - pad_r
        alpha = _small_n(n)
        frac = k / n
        lo, hi = wilson(k, n)
        parts.append(f'<text x="{pad_l-8}" y="{y+14}" font-size="11" fill="{C["text"]}" text-anchor="end">{_esc(gname)} · {t}</text>')
        parts.append(_bar(x, y + 4, w, 12, frac, C["bar" if "controls_off" in gname else "bar_on"], alpha))
        parts.append(_ci_line(x, y + 10, w, lo, hi))
        parts.append(f'<text x="{x+w+6}" y="{y+14}" font-size="10" fill="{C["dim"]}">{fmt(k, n)}</text>')
    return _svg(W, H, "".join(parts), "유형별 방어율")


# ---------------------------------------------------------------------------
# 차트 ② 개선 전후 비교 (runner 별 controls_off → on, 케이스 단위 점 연결)
# ---------------------------------------------------------------------------
def chart_before_after(doc):
    # 같은 case_id 의 off/on 쌍을 찾아 케이스별 방어 성공률(차단 비율)을 점으로 잇는다
    pairs = {}
    for r in doc.get("case_rows", []):
        pairs.setdefault((r["runner"], r["case_id"]), {})[r["condition"]] = r
    units = [(rk, cid, p["controls_off"], p["controls_on"]) for (rk, cid), p in pairs.items()
             if "controls_off" in p and "controls_on" in p and p["controls_off"]["expected"] == "block"]
    if not units:
        return ""
    W, rh = 640, 26
    H = 40 + rh * len(units)
    pad_l, pad_r = 150, 60
    parts = [f'<text x="{pad_l}" y="18" font-size="12" fill="{C["text"]}">② 개선 전후: 케이스별 방어 성공률(공격 차단 비율), ○=통제 없음 ●=통제 적용</text>']
    for i, (rk, cid, off, on) in enumerate(units):
        y = 34 + i * rh
        x, w = pad_l, W - pad_l - pad_r
        def frac(r):
            return (r["n"] - r["k"]) / r["n"] if r["n"] else 0
        x1, x2 = x + frac(off) * w, x + frac(on) * w
        parts.append(f'<text x="{pad_l-8}" y="{y+10}" font-size="10" fill="{C["text"]}" text-anchor="end">{_esc(rk)} {cid}</text>')
        parts.append(f'<line x1="{x1:.1f}" y1="{y+5}" x2="{x2:.1f}" y2="{y+5}" stroke="{C["dim"]}" stroke-width="1" stroke-dasharray="3,2"/>')
        parts.append(f'<circle cx="{x1:.1f}" cy="{y+5}" r="4" fill="none" stroke="{C["bar"]}" stroke-width="1.6"/>')
        parts.append(f'<circle cx="{x2:.1f}" cy="{y+5}" r="4" fill="{C["bar_on"]}"/>')
        parts.append(f'<text x="{x+w+6}" y="{y+9}" font-size="9" fill="{C["dim"]}">n={off["n"]}/{on["n"]}</text>')
    parts.append(_axis(W, pad_l, 34 + rh * len(units) + 6, 0) if False else "")
    return _svg(W, H, "".join(parts), "개선 전후 비교")


# ---------------------------------------------------------------------------
# 차트 ③ 가설 대조 (가설 값을 신뢰구간 위에 점으로)
# ---------------------------------------------------------------------------
def chart_hypothesis(doc):
    rows = doc.get("hypothesis_rows") or []
    judged = [r for r in rows if r["result"] in ("적중", "높게 예상", "낮게 예상", "빗나감")]
    if not judged:
        return ""
    W, rh = 640, 30
    H = 40 + rh * len(judged)
    pad_l, pad_r = 230, 120
    marks = {"적중": ("●", C["bar_on"]), "높게 예상": ("▲", C["warn"]), "낮게 예상": ("▼", C["warn"]), "빗나감": ("✕", C["warn"])}
    parts = [f'<text x="{pad_l}" y="18" font-size="12" fill="{C["text"]}">③ 가설 대조: 선=실제 95% 구간, 점=가설 값, 기호=판정</text>']
    # actual 문자열 "75% [30%–95%] (3/4)" 에서 구간을 복원하기 어려우므로 k/n 은 hypothesis_rows 가 아니라
    # case_rows 가 아니라 groups 에서 유도 — 여기서는 가설 값 위치만 그리고 결과는 글자로 표기한다.
    for i, r in enumerate(judged):
        y = 32 + i * rh
        mark, color = marks.get(r["result"], ("?", C["dim"]))
        parts.append(f'<text x="{pad_l-8}" y="{y+10}" font-size="10" fill="{C["text"]}" text-anchor="end">{_esc(r["key"])}</text>')
        # 가설 값이 숫자면 0~1 위치에 삼각형, 문자열(PASS/FAIL)이면 위치 없이 글자만
        if isinstance(r["predicted"], (int, float)):
            x = pad_l + r["predicted"] * (W - pad_l - pad_r)
            parts.append(f'<path d="M{x:.1f},{y-4} l5,9 l-10,0 z" fill="{color}"/>')
        parts.append(f'<text x="{pad_l}" y="{y+10}" font-size="10" fill="{color}">{mark} {r["result"]} · 실제 {r["actual"]}</text>')
    return _svg(W, H, "".join(parts), "가설 대조")


# ---------------------------------------------------------------------------
# 차트 ④ 심각도 × 성공률 매트릭스
# ---------------------------------------------------------------------------
def chart_severity_matrix(doc):
    sev_order = ["low", "medium", "high"]
    cells = {}
    for r in doc.get("case_rows", []):
        if r["expected"] != "block" or not r["n"]:
            continue
        key = (r["severity"], r["condition"])
        a = cells.setdefault(key, [0, 0])
        a[0] += r["k"]
        a[1] += r["n"]
    if not cells:
        return ""
    conds = sorted({k[1] for k in cells})
    W, cw, chh = 640, 150, 90
    H = 40 + chh * len(sev_order)
    pad_l = 90
    parts = [f'<text x="{pad_l}" y="18" font-size="12" fill="{C["text"]}">④ 심각도 × 공격 성공률 (ASR, 낮을수록 좋음 — 셀이 진할수록 위험)</text>']
    for j, cond in enumerate(conds):
        parts.append(f'<text x="{pad_l + j*cw + cw/2}" y="34" font-size="11" fill="{C["dim"]}" text-anchor="middle">{_esc(cond)}</text>')
    for i, sev in enumerate(sev_order):
        y = 42 + i * chh
        parts.append(f'<text x="{pad_l-8}" y="{y+chh/2}" font-size="11" fill="{C["text"]}" text-anchor="end">{sev}</text>')
        for j, cond in enumerate(conds):
            k_n = cells.get((sev, cond))
            x = pad_l + j * cw
            if not k_n or not k_n[1]:
                parts.append(f'<rect x="{x+4}" y="{y+4}" width="{cw-8}" height="{chh-8}" fill="none" stroke="{C["grid"]}" stroke-dasharray="3,3"/>')
                parts.append(f'<text x="{x+cw/2}" y="{y+chh/2}" font-size="10" fill="{C["dim"]}" text-anchor="middle">측정 안 됨</text>')
                continue
            k, n = k_n
            asr = k / n
            lo, hi = wilson(k, n)
            # ASR 이 높을수록 빨갛게 — 점추정 기준 색 농도
            intensity = min(1.0, asr * 1.4)
            color = f"rgba(194,94,94,{0.15 + 0.55 * intensity:.2f})"
            parts.append(f'<rect x="{x+4}" y="{y+4}" width="{cw-8}" height="{chh-8}" fill="{color}" stroke="{C["grid"]}" rx="4"/>')
            parts.append(f'<text x="{x+cw/2}" y="{y+chh/2-4}" font-size="14" font-weight="bold" fill="{C["text"]}" text-anchor="middle">{_pct(asr)}</text>')
            parts.append(f'<text x="{x+cw/2}" y="{y+chh/2+12}" font-size="9" fill="{C["dim"]}" text-anchor="middle">ASR {fmt(k, n)}</text>')
    return _svg(W, H, "".join(parts), "심각도×성공률 매트릭스")


# ---------------------------------------------------------------------------
# 차트 ⑤ 실행 현황 (runner·condition 별 시도 수 n)
# ---------------------------------------------------------------------------
def chart_status(doc):
    agg = {}
    for r in doc.get("case_rows", []):
        key = (r["runner"], r["condition"])
        agg[key] = agg.get(key, 0) + r["n"]
    if not agg:
        return ""
    keys = sorted(agg)
    W, rh = 640, 30
    H = 40 + rh * len(keys)
    pad_l, pad_r = 190, 80
    maxn = max(agg.values()) or 1
    parts = [f'<text x="{pad_l}" y="18" font-size="12" fill="{C["text"]}">⑤ 실행 현황: runner·condition 별 총 시도 수 n (옅을수록 표본 작음)</text>']
    for i, key in enumerate(keys):
        y = 32 + i * rh
        n = agg[key]
        w = (W - pad_l - pad_r) * n / maxn
        alpha = _small_n(n)
        parts.append(f'<text x="{pad_l-8}" y="{y+12}" font-size="11" fill="{C["text"]}" text-anchor="end">{_esc(key[0])} / {key[1]}</text>')
        parts.append(_bar(pad_l, y + 2, w, 14, 1.0, C["bar"], alpha))
        parts.append(f'<text x="{pad_l+w+6}" y="{y+13}" font-size="11" fill="{C["dim"]}">n={n}</text>')
    return _svg(W, H, "".join(parts), "실행 현황")


# ---------------------------------------------------------------------------
# 실행 간 비교 (두 Outcome 문서의 그룹별 방어율을 나란히)
# ---------------------------------------------------------------------------
def chart_run_compare(doc_a, doc_b, label_a="실행 A", label_b="실행 B"):
    """두 doc 의 runner·condition 그룹별 방어율(점추정+95% 구간)을 나란히 그린다.
    한쪽에만 있는 그룹도 표시한다(다른 쪽은 '측정 안 됨')."""
    ga, gb = doc_a.get("groups", {}), doc_b.get("groups", {})
    keys = sorted(set(ga) | set(gb))
    if not keys:
        return ""
    W, rh = 680, 34
    H = 56 + rh * len(keys)
    pad_l, pad_r = 170, 130
    parts = [f'<text x="{pad_l}" y="20" font-size="12" fill="{C["text"]}">⑥ 실행 비교: 그룹별 방어율 — 위={_esc(label_a)} 아래={_esc(label_b)} (선=95% 구간)</text>']
    legend_y = 38
    parts.append(f'<rect x="{pad_l}" y="{legend_y-9}" width="10" height="10" fill="{C["bar"]}" rx="2"/>')
    parts.append(f'<text x="{pad_l+14}" y="{legend_y}" font-size="10" fill="{C["text"]}">{_esc(label_a)}</text>')
    parts.append(f'<rect x="{pad_l+130}" y="{legend_y-9}" width="10" height="10" fill="{C["bar_on"]}" rx="2"/>')
    parts.append(f'<text x="{pad_l+144}" y="{legend_y}" font-size="10" fill="{C["text"]}">{_esc(label_b)}</text>')
    for i, key in enumerate(keys):
        y = 56 + i * rh
        x, w = pad_l, W - pad_l - pad_r
        parts.append(f'<text x="{pad_l-8}" y="{y+16}" font-size="10" fill="{C["text"]}" text-anchor="end">{_esc(key)}</text>')
        for j, (doc, color) in enumerate(((doc_a, C["bar"]), (doc_b, C["bar_on"]))):
            g = (ga if j == 0 else gb).get(key)
            yy = y + j * 13
            if not g or not g["defense"][1]:
                parts.append(f'<text x="{x}" y="{yy+9}" font-size="9" fill="{C["dim"]}">측정 안 됨</text>')
                continue
            k, n = g["defense"]          # 방어 성공 수 / 시도 수
            frac, alpha = k / n, _small_n(n)
            lo, hi = wilson(k, n)
            parts.append(_bar(x, yy, w, 9, frac, color, alpha))
            parts.append(_ci_line(x, yy + 4.5, w, lo, hi))
            parts.append(f'<text x="{x+w+6}" y="{yy+9}" font-size="9" fill="{C["dim"]}">{fmt(k, n)}</text>')
    return _svg(W, H, "".join(parts), "실행 간 비교")


def _group_metrics_table(docs_labels):
    """[(label, doc), ...] 의 그룹 지표를 한 표로 — 비교 실행의 숫자를 나란히 본다."""
    keys = sorted({k for _, d in docs_labels for k in d.get("groups", {})})
    if not keys:
        return ""
    head = "".join(f"<th>{html.escape(l)}</th>" for l, _ in docs_labels)
    rows = []
    for key in keys:
        cells = []
        for _, d in docs_labels:
            g = d.get("groups", {}).get(key)
            if not g:
                cells.append("<td>—</td>")
                continue
            dr = g["defense"]
            asr = g["asr"]
            rate = f"{(dr[0]/dr[1]*100):.0f}%" if dr[1] else "—"
            cells.append(f"<td>방어율 {rate} ({fmt(dr[0], dr[1])})<br>ASR {fmt(asr[0], asr[1])}</td>")
        rows.append(f"<tr><td>{html.escape(key)}</td>{''.join(cells)}</tr>")
    return (f"<table><thead><tr><th>그룹</th>{head}</tr></thead><tbody>"
            + "".join(rows) + "</tbody></table>")


def _hypothesis_table(doc):
    """가설 대조 행을 HTML 표로 — 키·예측·실측·판정."""
    rows = doc.get("hypothesis_rows") or []
    if not rows:
        return "<p>가설 대조 데이터가 없다.</p>"
    out = ['<table><thead><tr><th>키</th><th>예측</th><th>실측</th><th>판정</th></tr></thead><tbody>']
    for r in rows:
        out.append(f"<tr><td><code>{html.escape(r['key'])}</code></td>"
                   f"<td>{html.escape(str(r.get('predicted')))}</td>"
                   f"<td>{html.escape(str(r.get('actual')))}</td>"
                   f"<td>{html.escape(str(r.get('result')))}</td></tr>")
    out.append("</tbody></table>")
    return "".join(out)


def compare_dashboard_html(doc_a, doc_b, label_a="실행 A", label_b="실행 B",
                          title="AI 레드팀 실행 비교"):
    """두 Outcome 문서의 비교 대시보드 — 그룹별 방어율 차트 + 지표 표 + 각 실행의 케이스 표."""
    body = [f"<h1>{html.escape(title)}</h1>",
            f"<p class=meta>생성: {html.escape(doc_a['generated_at'])} · {html.escape(label_a)} vs {html.escape(label_b)} · Outcome 집계 기반</p>",
            chart_run_compare(doc_a, doc_b, label_a, label_b),
            "<h2>그룹별 지표</h2>", _group_metrics_table([(label_a, doc_a), (label_b, doc_b)]),
            *(["<h2>가설 대조</h2>", _hypothesis_table(doc_a),
               f"<h2>가설 대조 — {html.escape(label_b)}</h2>", _hypothesis_table(doc_b)]
              if doc_a.get("hypothesis_rows") or doc_b.get("hypothesis_rows") else []),
            f"<h2>케이스별 결과 — {html.escape(label_a)}</h2>", case_table_html(doc_a),
            f"<h2>케이스별 결과 — {html.escape(label_b)}</h2>", case_table_html(doc_b)]
    return HTML_PAGE.replace("{{TITLE}}", html.escape(title)).replace("{{BODY}}", "\n".join(body))


# ---------------------------------------------------------------------------
# 케이스별 결과 표 (대시보드·비교 공용)
# ---------------------------------------------------------------------------
def case_table_html(doc):
    """케이스 단위 k/n·방어율(공격) 또는 오탐(k/n, 정상) 표 — runner·condition·case_id 순."""
    rows = sorted(doc.get("case_rows", []), key=lambda r: (r["runner"], r["condition"], r["case_id"]))
    if not rows:
        return "<p>케이스 결과가 없다.</p>"
    out = ['<table><thead><tr><th>runner</th><th>condition</th><th>case</th><th>유형</th><th>기대</th><th>k/n</th><th>지표</th></tr></thead><tbody>']
    for r in rows:
        if not r["n"]:
            metric = "측정 안 됨"
        elif r["expected"] == "block":
            d = r["n"] - r["k"]
            lo, hi = wilson(d, r["n"])
            metric = f"방어율 {_pct(d / r['n'])} [{_pct(lo)}–{_pct(hi)}]"
        else:
            lo, hi = wilson(r["k"], r["n"])
            metric = f"오탐 {_pct(r['k'] / r['n'])} [{_pct(lo)}–{_pct(hi)}]"
        exp = "차단" if r["expected"] == "block" else "허용"
        out.append(f"<tr><td>{html.escape(r['runner'])}</td><td>{html.escape(r['condition'])}</td>"
                   f"<td><code>{html.escape(r['case_id'])}</code></td><td>{html.escape(r['type'])}</td>"
                   f"<td>{exp}</td><td>{r['k']}/{r['n']}</td><td>{metric}</td></tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# 대시보드 HTML (자체 완결)
# ---------------------------------------------------------------------------
HTML_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{color-scheme:light dark}
body{font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#222;background:#fff}
@media(prefers-color-scheme:dark){body{color:#e8e8e8;background:#1a1a1a}table,th,td{border-color:#444}td,th{color:#e8e8e8}}
h1{font-size:1.4rem}h2{font-size:1.1rem;margin-top:2rem}
table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{border:1px solid #ccc;padding:.35rem .6rem;text-align:left}
th{background:#f0f0f0}
.meta{color:#888;font-size:.85rem}
svg{max-width:100%;height:auto;display:block;margin:.6rem 0}
code{background:#eee;padding:.1rem .3rem;border-radius:3px}
@media print{body{margin:0;max-width:none}h2{break-after:avoid}svg{break-inside:avoid}}
.foot{margin-top:3rem;padding-top:.8rem;border-top:1px solid #ccc;color:#999;font-size:.8rem;text-align:center}
@media(prefers-color-scheme:dark){.foot{border-color:#444}}
</style></head><body>
{{BODY}}
<footer class=foot>AI 레드팀 교육용 · 로컬 모델 전용 · 예약 도메인·카나리 규칙 강제<br>produced by yundo</footer>
</body></html>"""


def dashboard_svg(doc):
    """차트 5종을 한 덩어리의 인라인 SVG/HTML 로 만든다(보고서·대시보드 공용)."""
    parts = []
    for fn in (chart_defense_by_type, chart_before_after, chart_hypothesis, chart_severity_matrix, chart_status):
        s = fn(doc)
        if s:
            parts.append(s)
    return "\n".join(parts) if parts else "<p>그릴 데이터가 없다.</p>"


def dashboard_html(doc, title="AI 레드팀 대시보드"):
    body = [f"<h1>{html.escape(title)}</h1>",
            f"<p class=meta>생성: {html.escape(doc['generated_at'])} · Outcome 집계 기반, 새 측정 없음</p>",
            dashboard_svg(doc),
            "<h2>케이스별 결과</h2>", case_table_html(doc)]
    return HTML_PAGE.replace("{{TITLE}}", html.escape(title)).replace("{{BODY}}", "\n".join(body))


def main(argv=None):
    import argparse
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from base.schema import load_cases, load_outcomes
    from service import report as rep
    ap = argparse.ArgumentParser(description="Outcome → 차트 SVG·대시보드 HTML")
    ap.add_argument("outcomes")
    ap.add_argument("--cases", required=True)
    ap.add_argument("-o", "--output", required=True)
    ap.add_argument("--max-asr", type=float)
    ap.add_argument("--max-fpr", type=float)
    a = ap.parse_args(argv)
    meta, outcomes = load_outcomes(a.outcomes)
    doc = rep.build(load_cases(a.cases), outcomes, a.max_asr, a.max_fpr)
    Path(a.output).write_text(dashboard_html(doc), encoding="utf-8")
    print(f"저장: {a.output}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
