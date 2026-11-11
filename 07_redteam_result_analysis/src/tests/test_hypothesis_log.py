"""가설 기록·대조 도구 단위 테스트 (모델 호출 없음).  실행:  python -m unittest -v 07_redteam_result_analysis/src/tests/test_hypothesis_log.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # src/ 를 모듈 검색 경로에 둔다 (run·base 패키지)

import json
import os
import tempfile
import unittest

from base import hypothesis_log as hyp


def write(directory, data, name="hypothesis.json"):
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return path


class TestLoad(unittest.TestCase):
    def test_example_file_is_valid(self):
        here = os.path.dirname(os.path.abspath(__file__))
        snap = hyp.load(os.path.join(os.path.dirname(here), "data", "hypothesis.example.json"))
        self.assertTrue(snap["predictions"])
        self.assertTrue(all(k.startswith("ch") for k in snap["predictions"]))
        self.assertEqual(len(snap["sha256"]), 16)

    def test_rejects_bad_values(self):
        with tempfile.TemporaryDirectory() as d:
            for bad in ({"predictions": {}}, {"predictions": {"k": 1.5}}, {"predictions": {"k": "pass"}},
                        {"predictions": {"k": True}}, {}):
                with self.assertRaises(ValueError):
                    hyp.load(write(d, bad))


class TestCompare(unittest.TestCase):
    H = {"predictions": {"ch07.TA-01.off": 0.70, "ch07.TA-01.on": 0.0, "ch07.JB-01.off": 0.10,
                         "ch05.guard.verdict": "PASS", "ch07.TYPO.off": 0.5}}

    def result(self, rows, key):
        return next(r["result"] for r in rows if r["key"] == key)

    def test_hit_when_prediction_inside_interval(self):
        rows = hyp.compare(self.H, [hyp.rate("ch07.TA-01.off", 22, 30), hyp.rate("ch07.TA-01.on", 0, 30)])
        self.assertEqual(self.result(rows, "ch07.TA-01.off"), "적중")      # 70% 는 [56%–86%] 안
        self.assertEqual(self.result(rows, "ch07.TA-01.on"), "적중")       # 0% 는 [0%–11%] 안

    def test_miss_direction(self):
        rows = hyp.compare(self.H, [hyp.rate("ch07.JB-01.off", 15, 15)])   # 실제 [80%–100%], 가설 10%
        self.assertEqual(self.result(rows, "ch07.JB-01.off"), "낮게 예상")
        rows = hyp.compare({"predictions": {"ch07.X.off": 0.9}}, [hyp.rate("ch07.X.off", 0, 30)])
        self.assertEqual(rows[0]["result"], "높게 예상")

    def test_verdict_must_match(self):
        self.assertEqual(hyp.compare(self.H, [hyp.verdict("ch05.guard.verdict", "PASS")])[0]["result"], "적중")
        self.assertEqual(hyp.compare(self.H, [hyp.verdict("ch05.guard.verdict", "FAIL")])[0]["result"], "빗나감")

    def test_unmeasured_prediction_in_measured_chapter_is_listed(self):
        rows = hyp.compare(self.H, [hyp.rate("ch07.TA-01.off", 22, 30)])
        self.assertEqual(self.result(rows, "ch07.TYPO.off"), "측정 안 됨")   # 오타·누락을 숨기지 않는다
        self.assertNotIn("ch05.guard.verdict", [r["key"] for r in rows])      # 측정하지 않은 일차의 가설은 제외

    def test_measurement_without_prediction(self):
        rows = hyp.compare(self.H, [hyp.rate("ch07.NEW.off", 1, 10)])
        self.assertEqual(rows[0]["result"], "가설 없음")

    def test_summary_counts_judged_rows_only(self):
        rows = hyp.compare(self.H, [hyp.rate("ch07.TA-01.off", 22, 30), hyp.rate("ch07.JB-01.off", 15, 15),
                                    hyp.rate("ch07.NEW.off", 1, 10)])
        self.assertEqual(hyp.summary(rows), "1/2")


class TestWrittenAfter(unittest.TestCase):
    def test_detects_hypothesis_edited_after_start(self):
        snap = {"file_mtime": "2026-11-01T10:00:05+09:00"}
        self.assertTrue(hyp.written_after(snap, "2026-11-01T10:00:00+09:00"))
        self.assertFalse(hyp.written_after(snap, "2026-11-01T10:00:09+09:00"))
        self.assertFalse(hyp.written_after(None, "2026-11-01T10:00:00+09:00"))

    def test_late_hypothesis_is_flagged_in_table(self):
        snap = {"predictions": {"ch07.A.off": 0.5}, "memo": {}, "file_mtime": "2026-11-01T10:00:05+09:00"}
        text = hyp.text_table(snap, [hyp.rate("ch07.A.off", 5, 10)], "2026-11-01T10:00:00+09:00")
        self.assertIn("사후 작성", text)


class TestSaveRun(unittest.TestCase):
    def test_roundtrip_creates_folder_and_keeps_results(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "new", "run.json")
            hyp.save_run(path, [hyp.rate("ch07.A.off", 1, 10)], {"predictions": {"ch07.A.off": 0.1}}, {"model": "m"},
                         results=[{"case_id": "A"}])
            run = hyp.load_run(path)
            self.assertEqual(run["results"], [{"case_id": "A"}])
            self.assertEqual(run["meta"]["model"], "m")
            self.assertIn("started_at", run["meta"])

    def test_old_list_format_still_loads(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(d, [{"case_id": "A"}], "old.json")
            run = hyp.load_run(path)
            self.assertEqual(run["results"], [{"case_id": "A"}])
            self.assertIsNone(run["hypothesis"])

class TestSafeWrite(unittest.TestCase):
    def test_first_write_has_nothing_to_keep(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "out", "a.json")
            self.assertIsNone(hyp.safe_write(p, "1"))
            self.assertEqual(open(p, encoding="utf-8").read(), "1")
            self.assertFalse(os.path.exists(os.path.join(d, "out", "history")))

    def test_existing_file_is_kept_in_history_not_lost(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            hyp.safe_write(p, "old")
            kept = hyp.safe_write(p, "new")
            self.assertEqual(open(p, encoding="utf-8").read(), "new")
            self.assertEqual(open(kept, encoding="utf-8").read(), "old")
            self.assertEqual(os.path.dirname(kept), os.path.join(d, "history"))

    def test_same_second_does_not_collide(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            hyp.safe_write(p, "1")
            kept = {hyp.safe_write(p, str(i)) for i in range(2, 6)}
            self.assertEqual(len(kept), 4)
            self.assertEqual(len(os.listdir(os.path.join(d, "history"))), 4)

    def test_no_temp_file_left_and_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.json")
            hyp.safe_write(p, "ok")
            with self.assertRaises(TypeError):
                hyp.safe_write(p, None)                     # 문자열이 아니면 쓰다가 실패한다
            self.assertEqual(open(p, encoding="utf-8").read(), "ok")
            self.assertEqual([f for f in os.listdir(d) if f.startswith(".tmp-")], [])

    def test_save_run_twice_keeps_first_run(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "run.json")
            self.assertIsNone(hyp.save_run(p, [hyp.rate("ch07.A.off", 1, 10)], None))
            kept = hyp.save_run(p, [hyp.rate("ch07.A.off", 2, 10)], None)
            self.assertEqual(hyp.load_run(kept)["measurements"][0]["k"], 1)
            self.assertEqual(hyp.load_run(p)["measurements"][0]["k"], 2)


if __name__ == "__main__":
    unittest.main()
