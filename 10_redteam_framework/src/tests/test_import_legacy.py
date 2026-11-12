"""import_legacy 회귀 테스트: 앞 일차 기록 3종이 Outcome 으로 변환되고 k/n 합계가 보존되는지."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base.schema import load_outcomes
from run import import_legacy as il

DATA = Path(__file__).resolve().parents[1] / "data" / "legacy"


class TestHarness(unittest.TestCase):
    def test_ch03_record(self):
        doc = json.loads((DATA / "harness-ch03.example.json").read_text(encoding="utf-8"))
        outcomes, meta = il.from_harness(doc)
        self.assertTrue(outcomes)
        for o in outcomes:
            self.assertEqual(o.runner, "native")
            self.assertIn(o.condition, ("controls_off", "controls_on"))
        # 원본 results 의 trials·successes 합이 보존되는지
        src = {(r["case_id"], "on" if r["controls_on"] else "off"): (r["successes"], r["trials"])
               for r in doc["results"]}
        for o in outcomes:
            cond = "on" if o.condition == "controls_on" else "off"
            self.assertEqual((o.k, o.n), src[(o.case_id, cond)])

    def test_redteam_run1(self):
        doc = json.loads((DATA / "run.example.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["format"], "redteam-run/1")
        outcomes, _ = il.from_harness(doc)
        self.assertTrue(all(o.runner == "native" for o in outcomes))


class TestScan(unittest.TestCase):
    def test_garak_raw(self):
        doc = json.loads((DATA / "garak-raw.example.json").read_text(encoding="utf-8"))
        outcomes, _ = il.from_scan(doc, "garak")
        ids = {o.case_id for o in outcomes}
        self.assertTrue({"GA-01", "GA-02"} <= ids)
        for o in outcomes:
            self.assertEqual(o.runner, "garak")
            self.assertEqual(o.condition, "controls_off")   # raw = 방어 없음

    def test_pyrit_guard(self):
        doc = json.loads((DATA / "pyrit-guard.example.json").read_text(encoding="utf-8"))
        outcomes, _ = il.from_scan(doc, "pyrit")
        self.assertTrue(all(o.condition == "controls_on" for o in outcomes))
        ids = {o.case_id for o in outcomes}
        self.assertTrue({"PY-01", "PY-02", "PY-03", "PY-04", "OK-01"} <= ids)


class TestEvalset(unittest.TestCase):
    def test_outcomes_file(self):
        from base import schema
        cases = schema.load_cases(str(DATA / "evalset.example.json"))
        doc = json.loads((DATA / "outcomes.example.json").read_text(encoding="utf-8"))
        outcomes, _ = il.from_evalset(doc, cases)
        self.assertEqual(len(outcomes), len(doc["results"]))
        # 공격 케이스: blocked=False -> k=1(통과), blocked=True -> k=0
        by_id = {o.case_id: o for o in outcomes}
        self.assertEqual((by_id["PI-02"].k, by_id["PI-02"].n), (1, 1))
        self.assertEqual((by_id["PI-01"].k, by_id["PI-01"].n), (0, 1))
        # 정상 케이스: blocked=True(오차단) -> k=1
        self.assertEqual((by_id["OK-02"].k, by_id["OK-02"].n), (1, 1))

    def test_cli_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.json"
            rc = il.main([str(DATA / "harness-ch03.example.json"), "-o", str(out)])
            self.assertEqual(rc, 0)
            meta, outcomes = load_outcomes(str(out))
            self.assertTrue(outcomes)


if __name__ == "__main__":
    unittest.main()
