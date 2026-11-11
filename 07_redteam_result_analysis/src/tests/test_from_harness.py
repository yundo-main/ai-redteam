"""from_harness.py 단위 테스트 (모델 호출 없음).  실행:  python -m unittest -v 07_redteam_result_analysis/src/tests/test_from_harness.py"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/ 를 모듈 검색 경로에 둔다 (run·base 패키지)

from run import from_harness as fh
from run import report as rp

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OLD = {"meta": {"started_at": "2026-11-02T14:29:24+09:00", "model": "m", "extra": 1},
       "hypothesis": {"predictions": {"ch03.TA-01.off": 0.7, "other": 1}, "memo": {"ch03.TA-01.off": "x"}, "file": "h.json"},
       "measurements": [{"key": "ch03.TA-01.off", "k": 8, "n": 10}],
       "results": [{"case_id": "TA-01", "controls_on": False, "trials": 10, "successes": 8, "evidence": [{"trial": 0}],
                    "audit_log": [{"tool": "t"}], "model": "m", "params": {"seed": 7}, "success_rate": 0.8, "ci95": [0.4, 0.9]},
                   {"case_id": "TA-01", "controls_on": True, "trials": 10, "successes": 0}]}


class TestConvert(unittest.TestCase):
    def setUp(self):
        self.rec = fh.convert(OLD)

    def test_fields_are_renamed(self):
        r = self.rec["runs"][0]
        self.assertEqual((r["scenario"], r["controls"], r["trials"], r["successes"]), ("TA-01", "off", 10, 8))
        self.assertEqual(r["audit"], [{"tool": "t"}])
        self.assertEqual(self.rec["runs"][1]["controls"], "on")

    def test_derived_values_are_dropped(self):
        r = self.rec["runs"][0]
        self.assertNotIn("success_rate", r)
        self.assertNotIn("ci95", r)
        self.assertNotIn("measurements", self.rec)

    def test_hypothesis_keys_are_rekeyed_only_for_prefix(self):
        h = self.rec["hypothesis"]
        self.assertEqual(set(h["predictions"]), {"ch07.TA-01.off", "other"})
        self.assertEqual(set(h["memo"]), {"ch07.TA-01.off"})
        self.assertEqual(h["file"], "h.json")

    def test_meta_keeps_only_known_fields(self):
        self.assertEqual(self.rec["meta"], {"started_at": "2026-11-02T14:29:24+09:00", "model": "m"})

    def test_result_is_valid_07_input(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(self.rec, f)
            self.assertEqual(len(rp.load_record(p)["runs"]), 2)


class TestCli(unittest.TestCase):
    def test_bundled_harness_example_converts_to_the_bundled_run_example(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.json")
            self.assertEqual(fh.main([os.path.join(DATA, "harness", "ch03.example.json"), "-o", out]), 0)
            got = json.load(open(out, encoding="utf-8"))
            want = json.load(open(os.path.join(DATA, "run.example.json"), encoding="utf-8"))
            self.assertEqual(got, want)

    def test_not_a_harness_record_returns_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.json")
            open(p, "w").write("{}")
            self.assertEqual(fh.main([p]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
