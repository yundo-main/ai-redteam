import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 어느 폴더에서 실행해도 같은 폴더의 모듈을 찾는다

import json
import os
import tempfile
import unittest

import evalset as ev

HERE = os.path.dirname(os.path.abspath(__file__))
CASES = ev.load_cases(os.path.join(HERE, "evalset.example.json"))


def r(*pairs):
    return [{"id": i, "blocked": b} for i, b in pairs]


class TestValidate(unittest.TestCase):
    def test_example_is_valid(self):
        self.assertEqual(ev.validate(CASES), [])

    def test_requires_benign_cases(self):
        atk = [c for c in CASES if c["expected"] == "block"]
        self.assertTrue(any("정상 케이스" in p for p in ev.validate(atk)))

    def test_requires_attack_cases(self):
        ben = [c for c in CASES if c["expected"] == "allow"]
        self.assertTrue(any("공격 케이스" in p for p in ev.validate(ben)))

    def test_duplicate_and_missing_fields(self):
        bad = CASES + [dict(CASES[0], criterion="")]
        p = ev.validate(bad)
        self.assertTrue(any("id 중복" in x for x in p))
        self.assertTrue(any("criterion" in x for x in p))

    def test_bad_expected_and_severity(self):
        bad = [dict(CASES[0], expected="x", severity="z")] + CASES[1:]
        self.assertEqual(len([p for p in ev.validate(bad) if "PI-01" in p]), 2)


class TestScore(unittest.TestCase):
    def test_example_outcomes(self):
        s = ev.score(CASES, ev.load_outcomes(os.path.join(HERE, "outcomes.example.json")))
        self.assertEqual(s["defense"], [3, 4])
        self.assertEqual(s["asr"], [1, 4])
        self.assertEqual(s["fpr"], [1, 2])
        self.assertEqual(s["by_type"]["prompt_injection"], [1, 2])
        self.assertEqual(s["not_run"], [])

    def test_weighted_defense(self):
        # PI-01(high=3) 차단, JB-01(medium=2) 통과 -> 3/5
        s = ev.score(CASES, r(("PI-01", True), ("JB-01", False)))
        self.assertAlmostEqual(s["weighted_defense"], 0.6)

    def test_repeats_count_as_trials(self):
        s = ev.score(CASES, r(*[("PI-01", i < 7) for i in range(10)]))
        self.assertEqual(s["defense"], [7, 10])

    def test_unknown_id_is_error(self):
        with self.assertRaises(ValueError):
            ev.score(CASES, r(("XX-99", True)))

    def test_not_run_reported(self):
        s = ev.score(CASES, r(("PI-01", True)))
        self.assertIn("OK-01", s["not_run"])
        self.assertEqual(s["fpr"], [0, 0])

    def test_block_everything_is_exposed_by_fpr(self):
        s = ev.score(CASES, r(*[(c["id"], True) for c in CASES]))
        self.assertEqual(s["defense"], [4, 4])
        self.assertEqual(s["fpr"], [2, 2])


class TestGate(unittest.TestCase):
    def test_small_sample_is_not_pass(self):
        # 0/4 성공이어도 95% 상한이 크므로 ASR≤20% 를 보장하지 못한다
        s = ev.score(CASES, r(*[("PI-01", True)] * 4, ("OK-01", False)))
        self.assertEqual(ev.gate(s, 0.2, 0.2)["ASR"], "표본 부족")

    def test_pass_and_fail(self):
        good = ev.score(CASES, r(*[("PI-01", True)] * 60, *[("OK-01", False)] * 60))
        self.assertEqual(ev.gate(good, 0.1, 0.1), {"ASR": "PASS", "FPR": "PASS"})
        bad = ev.score(CASES, r(*[("PI-01", False)] * 10, *[("OK-01", True)] * 10))
        self.assertEqual(ev.gate(bad, 0.1, 0.1), {"ASR": "FAIL", "FPR": "FAIL"})

    def test_unmeasured(self):
        s = ev.score(CASES, r(("PI-01", True)))
        self.assertEqual(ev.gate(s, 0.1, 0.1)["FPR"], "측정 안 됨")


class TestCompare(unittest.TestCase):
    def test_small_change_is_not_significant(self):
        a = ev.score(CASES, r(*[("PI-01", i < 7) for i in range(10)]))
        b = ev.score(CASES, r(*[("PI-01", i < 9) for i in range(10)]))
        self.assertFalse(ev.compare(a, b))

    def test_large_change_is_significant(self):
        a = ev.score(CASES, r(*[("PI-01", i < 30) for i in range(100)]))
        b = ev.score(CASES, r(*[("PI-01", i < 95) for i in range(100)]))
        self.assertTrue(ev.compare(a, b))


class TestCli(unittest.TestCase):
    def test_main_runs(self):
        rc = ev.main([os.path.join(HERE, "evalset.example.json"),
                      os.path.join(HERE, "outcomes.example.json"), "--max-asr", "0.2", "--max-fpr", "0.1"])
        self.assertEqual(rc, 0)

    def test_bad_file_returns_2(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.json")
            json.dump({"cases": []}, open(p, "w"))
            self.assertEqual(ev.main([p, p]), 2)


if __name__ == "__main__":
    unittest.main()
