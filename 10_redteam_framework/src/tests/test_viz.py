"""viz·report 단위 테스트: 경계 사례 렌더링 + 차트 숫자가 evalset 과 같은지."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base.schema import Case, Outcome
from service import evalset as ev
from service import report as rep
from service import viz

CASES = [
    Case.from_dict({"id": "A-01", "type": "t1", "subtype": "s", "input": "[d]", "expected": "block",
                    "criterion": "c", "severity": "high", "source": "t"}),
    Case.from_dict({"id": "A-02", "type": "t1", "subtype": "s", "input": "[d]", "expected": "block",
                    "criterion": "c", "severity": "low", "source": "t"}),
    Case.from_dict({"id": "B-01", "type": "benign", "subtype": "s", "input": "[d]", "expected": "allow",
                    "criterion": "c", "severity": "low", "source": "t"}),
]


def doc_for(outcomes):
    return rep.build(CASES, outcomes)


class TestBoundary(unittest.TestCase):
    """11.6: 경계 사례(전부 0건, 전부 성공, n=1, 한쪽 condition 만)가 그려져야 한다."""

    def test_all_blocked(self):
        doc = doc_for([Outcome("A-01", "native", "controls_on", 0, 5),
                       Outcome("A-02", "native", "controls_on", 0, 5),
                       Outcome("B-01", "native", "controls_on", 0, 5)])
        html = viz.dashboard_html(doc)
        self.assertIn("<svg", html)
        self.assertNotIn("NaN", html)

    def test_all_success(self):
        doc = doc_for([Outcome("A-01", "native", "controls_off", 5, 5),
                       Outcome("A-02", "native", "controls_off", 3, 5),
                       Outcome("B-01", "native", "controls_off", 5, 5)])
        html = viz.dashboard_html(doc)
        self.assertIn("<svg", html)

    def test_n1(self):
        doc = doc_for([Outcome("A-01", "native", "controls_on", 1, 1)])
        html = viz.dashboard_html(doc)
        self.assertIn("<svg", html)

    def test_one_condition_only(self):
        doc = doc_for([Outcome("A-01", "native", "controls_off", 2, 4)])
        html = viz.dashboard_html(doc)   # controls_on 없음 → ② 차트는 빈 결과여야 한다
        self.assertIn("<svg", html)

    def test_empty(self):
        html = viz.dashboard_html(doc_for([]))
        self.assertIn("데이터가 없다", html)


class TestNumbers(unittest.TestCase):
    """차트·보고서 숫자가 evalset 계산과 같은 값인지."""

    def test_report_uses_evalset(self):
        outcomes = [Outcome("A-01", "native", "controls_on", 1, 4),
                    Outcome("A-02", "native", "controls_on", 0, 4),
                    Outcome("B-01", "native", "controls_on", 1, 2)]
        doc = doc_for(outcomes)
        g = doc["groups"]["native / controls_on"]
        sc = ev.score(CASES, outcomes)[("native", "controls_on")]
        self.assertEqual(g["asr"], sc["asr"])
        self.assertEqual(g["defense"], sc["defense"])
        md = rep.to_markdown(doc)
        self.assertIn("공격 성공률", md)

    def test_html_self_contained(self):
        doc = doc_for([Outcome("A-01", "native", "controls_on", 1, 4)])
        html = rep.to_html(doc)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))   # 외부 링크 금지(네임스페이스 제외)
        self.assertIn("<svg", html)
        # 러너 이름 같은 문자열은 차트에서 이스케이프되어야 한다(XSS 방지)
        evil = doc_for([Outcome("A-01", "<script>alert(1)</script>", "controls_on", 0, 1)])
        self.assertNotIn("<script>alert(1)</script>", viz.dashboard_html(evil))


class TestCompareAndCaseTable(unittest.TestCase):
    """실행 간 비교 차트·비교 대시보드·케이스별 표 (승인된 확장분)."""

    def _docs(self):
        off = [Outcome("A-01", "native", "controls_off", 3, 4),
               Outcome("B-01", "native", "controls_off", 1, 2)]
        on = [Outcome("A-01", "native", "controls_on", 0, 4),
              Outcome("B-01", "native", "controls_on", 0, 2),
              Outcome("A-01", "graph", "controls_on", 1, 4)]
        return doc_for(off + on[:2]), doc_for(on)

    def test_run_compare_renders_both_groups(self):
        da, db = self._docs()
        svg = viz.chart_run_compare(da, db, "전", "후")
        self.assertIn("<svg", svg)
        self.assertIn("native / controls_off", svg)
        self.assertIn("native / controls_on", svg)
        self.assertIn("graph / controls_on", svg)      # B에만 있는 그룹도 표시
        self.assertIn("측정 안 됨", svg)               # A에 없는 graph 그룹

    def test_compare_dashboard_has_tables(self):
        da, db = self._docs()
        html = viz.compare_dashboard_html(da, db, "실행A", "실행B")
        for marker in ("실행 비교", "그룹별 지표", "케이스별 결과 — 실행A",
                       "케이스별 결과 — 실행B", "<table"):
            self.assertIn(marker, html)
        self.assertNotIn("http://", html.replace("http://www.w3.org", ""))

    def test_case_table_n0_and_expected_allow(self):
        doc = doc_for([Outcome("A-01", "native", "controls_on", 0, 0),
                       Outcome("B-01", "native", "controls_on", 1, 2)])
        html = viz.case_table_html(doc)
        self.assertIn("측정 안 됨", html)     # n=0 → ZeroDivision 없이 표시
        self.assertIn("오탐", html)           # expected=allow 행
        self.assertIn("차단", html)           # expected=block 행의 기대값

    def test_dashboard_includes_case_table(self):
        da, _ = self._docs()
        self.assertIn("케이스별 결과", viz.dashboard_html(da))

    def test_compare_empty_docs(self):
        self.assertEqual(viz.chart_run_compare(doc_for([]), doc_for([])), "")
        html = viz.compare_dashboard_html(doc_for([]), doc_for([]))
        self.assertIn("케이스 결과가 없다", html)


if __name__ == "__main__":
    unittest.main()
