"""6-5 스캐너 스크립트의 모델 없는 점검: 리포트 파싱, 가설 키 일치. (Garak·PyRIT 설치와 Ollama 없이 돈다)

실행: python -m unittest -v 05_garak_pyrit_automated_testing/src/test_scan.py
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scan_garak
import hypothesis_log as hyp

SRC = Path(__file__).resolve().parent


class TestReadEval(unittest.TestCase):
    def test_reads_fails_and_total_per_probe_detector(self):
        lines = [
            {"entry_type": "start_run setup"},
            {"entry_type": "attempt", "probe_classname": "x"},
            {"entry_type": "eval", "probe": "encoding.InjectBase64", "detector": "encoding.DecodeMatch",
             "passed": 30, "fails": 0, "total_evaluated": 30},
            {"entry_type": "eval", "probe": "latentinjection.LatentInjectionTranslationEnFr",
             "detector": "base.TriggerListDetector", "passed": 6, "fails": 24, "total_evaluated": 30},
        ]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "r.report.jsonl"
            f.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
            ev = scan_garak.read_eval(f)
        self.assertEqual(ev[("encoding.InjectBase64", "encoding.DecodeMatch")], (0, 30))
        self.assertEqual(ev[("latentinjection.LatentInjectionTranslationEnFr", "base.TriggerListDetector")], (24, 30))


class TestHypothesisKeys(unittest.TestCase):
    def test_example_file_has_every_scan_key(self):
        # 스캔 스크립트가 기록하는 키가 예시 가설 파일과 어긋나면 '측정 안 됨'·'가설 없음'이 나온다.
        ex = hyp.load(str(SRC / "hypothesis.example.json"))["predictions"]
        for _, _, key, _ in scan_garak.PROBES:
            self.assertIn(key, ex)
        self.assertIn("ch05-pyrit.leak_rate", ex)

    def test_scan_keys_have_their_own_prefix(self):
        # 같은 'ch05' 접두사를 쓰면 다른 스크립트 실행에서 '측정 안 됨'으로 잘못 표시된다.
        for _, _, key, _ in scan_garak.PROBES:
            self.assertTrue(key.startswith("ch05-garak."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
