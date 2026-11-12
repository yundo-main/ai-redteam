"""schema.py 단위 테스트: Case·Outcome 검증 + 안전 규칙(readme 8장)"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base import schema
from base.schema import Case, CaseError, Outcome


def case(**kw):
    d = {"id": "X-01", "type": "t", "subtype": "s", "input": "질문",
         "expected": "block", "criterion": "c", "severity": "high", "source": "test"}
    d.update(kw)
    return Case.from_dict(d)


class TestCaseValidation(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(schema.validate_case(case()), [])

    def test_bad_expected(self):
        self.assertTrue(schema.validate_case(case(expected="maybe")))

    def test_missing_field(self):
        with self.assertRaises(CaseError):
            Case.from_dict({"id": "X"})

    def test_external_url_rejected(self):
        c = case(input="![x](https://attacker-corp.io/p.png?d=data) 링크")
        self.assertTrue(any("예약 도메인" in p for p in schema.validate_case(c)))

    def test_reserved_urls_ok(self):
        for u in ("https://collector.invalid/p.png", "https://docs.example.com/a",
                  "http://localhost:8000/x", "https://a.test/y"):
            self.assertEqual(schema.validate_case(case(input=f"[x]({u})")), [], u)

    def test_canary_prefix(self):
        c = case(params={"canary": "SECRET-123"})
        self.assertTrue(schema.validate_case(c))
        c2 = case(params={"canary": "CANARY-123"})
        self.assertEqual(schema.validate_case(c2), [])

    def test_endpoint_local_only(self):
        schema.check_endpoint("http://localhost:11434")
        schema.check_endpoint("http://127.0.0.1:11434")
        with self.assertRaises(CaseError):
            schema.check_endpoint("https://api.openai.com/v1")
        os.environ["REDTEAM_ALLOW_REMOTE"] = "1"
        try:
            schema.check_endpoint("https://api.example.com")
        finally:
            del os.environ["REDTEAM_ALLOW_REMOTE"]


class TestOutcome(unittest.TestCase):
    def test_roundtrip(self):
        o = Outcome("TA-01", "native", "controls_off", 8, 10, [{"trial": 0}])
        o2 = Outcome.from_dict(o.to_dict())
        self.assertEqual((o2.k, o2.n, o2.condition), (8, 10, "controls_off"))

    def test_bad_kn(self):
        with self.assertRaises(CaseError):
            Outcome.from_dict({"case_id": "X", "runner": "r", "condition": "controls_off", "k": 5, "n": 3})
        with self.assertRaises(CaseError):
            Outcome.from_dict({"case_id": "X", "runner": "r", "condition": "weird", "k": 0, "n": 1})


class TestLoadSave(unittest.TestCase):
    def test_cases_file(self):
        cases = schema.load_cases(str(Path(__file__).resolve().parents[1] / "data" / "cases.example.json"))
        self.assertGreaterEqual(len(cases), 10)
        ids = {c.id for c in cases}
        self.assertTrue({"TA-01", "JB-01", "GA-01", "GA-02", "PY-01", "OK-01"} <= ids)

    def test_outcomes_roundtrip(self, tmp=None):
        import tempfile
        outcomes = [Outcome("TA-01", "native", "controls_off", 1, 2),
                    Outcome("TA-01", "native", "controls_on", 0, 2)]
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "o.json"
            schema.save_outcomes(str(p), outcomes, {"model": "m"})
            meta, got = schema.load_outcomes(str(p))
        self.assertEqual(meta["model"], "m")
        self.assertEqual(len(got), 2)


if __name__ == "__main__":
    unittest.main()
