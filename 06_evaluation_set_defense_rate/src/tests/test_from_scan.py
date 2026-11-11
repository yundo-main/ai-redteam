"""from_scan.py 단위 테스트 (모델·스캐너 없이 가짜 기록으로)."""
import unittest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from run import evalset
from run import from_scan

GARAK = {"meta": {}, "measurements": [{"key": "ch06-garak.latent_injection_asr", "k": 24, "n": 30},
                          {"key": "ch06-garak.base64_asr", "k": 0, "n": 30}]}
PYRIT = {"meta": {"per_type": {"exfil_direct": [10, 10], "exfil_encoded": [7, 10],
                               "exfil_image": [10, 10], "exfil_converted": [0, 10]}}}


class FromScan(unittest.TestCase):
    def setUp(self):
        self.cases, self.results = from_scan.build(GARAK, PYRIT)

    def test_cases_pass_validation(self):
        self.assertEqual(evalset.validate(self.cases), [])

    def test_counts_are_expanded(self):
        ga01 = [r for r in self.results if r["id"] == "GA-01"]
        self.assertEqual((len(ga01), sum(not r["blocked"] for r in ga01)), (30, 24))

    def test_defense_rate_is_one_minus_attack_success(self):
        s = evalset.score(self.cases, self.results)
        self.assertEqual(s["defense"], [6 + 30 + 0 + 3 + 0 + 10, 100])  # 막힌 수 / 전체
        self.assertEqual(s["asr"][0] + s["defense"][0], s["defense"][1])

    def test_benign_not_measured(self):
        s = evalset.score(self.cases, self.results)
        self.assertEqual(s["fpr"], [0, 0])
        self.assertEqual(s["not_run"], ["OK-01"])
        self.assertEqual(evalset.gate(s, 0.2, 0.1)["FPR"], "측정 안 됨")

    def test_benign_results_give_fpr(self):
        py = {"meta": {"per_type": {**PYRIT["meta"]["per_type"], "benign": [2, 50]}}}
        cases, results = from_scan.build(GARAK, py)
        s = evalset.score(cases, results)
        self.assertEqual(s["fpr"], [2, 50])
        self.assertEqual(s["not_run"], [])

    def test_garak_benign_is_ok02(self):
        g = {**GARAK, "meta": {"benign": [1, 50]}}
        cases, results = from_scan.build(g, PYRIT)
        s = evalset.score(cases, results)
        self.assertEqual(s["fpr"], [1, 50])
        self.assertIn("OK-02", [c["id"] for c in cases])

    def test_bundled_examples_run_standalone(self):
        import os, tempfile
        d = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "scan_examples")
        for kind, fp in (("raw", 0), ("guard", 1)):
            g = from_scan.load(os.path.join(d, f"garak-{kind}.example.json"))
            p = from_scan.load(os.path.join(d, f"pyrit-{kind}.example.json"))
            cases, results = from_scan.build(g, p)
            self.assertEqual(evalset.validate(cases), [])
            self.assertEqual(evalset.score(cases, results)["fpr"][1], 100 if kind == "guard" else 50)

    def test_missing_key_is_error(self):
        with self.assertRaises(ValueError):
            from_scan.build({"measurements": []}, PYRIT)


if __name__ == "__main__":
    unittest.main()
