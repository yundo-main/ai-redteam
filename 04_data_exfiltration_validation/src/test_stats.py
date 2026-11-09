"""신뢰구간·반복 횟수 도구 단위 테스트 (모델 호출 없음).  실행:  python -m unittest -v <일차폴더>/src/test_stats.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 어느 폴더에서 실행해도 같은 폴더의 모듈을 찾는다

import os
import unittest
from unittest import mock

import stats as st


class TestWilson(unittest.TestCase):
    def test_known_values(self):
        lo, hi = st.wilson(1, 10)
        self.assertAlmostEqual(lo, 0.018, places=2)
        self.assertAlmostEqual(hi, 0.404, places=2)

    def test_zero_successes_has_nonzero_upper_bound(self):
        # '0건 = 안전'이 아니다: 30회 0건이어도 상한은 약 11% 이다.
        lo, hi = st.wilson(0, 30)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.114, places=2)

    def test_all_successes(self):
        lo, hi = st.wilson(30, 30)
        self.assertEqual(hi, 1.0)
        self.assertAlmostEqual(lo, 0.886, places=2)

    def test_more_trials_narrow_the_interval(self):
        w = lambda k, n: st.wilson(k, n)[1] - st.wilson(k, n)[0]
        self.assertGreater(w(5, 10), w(15, 30))
        self.assertGreater(w(15, 30), w(25, 50))

    def test_invalid_input(self):
        for k, n in ((1, 0), (-1, 5), (6, 5)):
            with self.assertRaises(ValueError):
                st.wilson(k, n)


class TestDiffers(unittest.TestCase):
    def test_clear_difference(self):
        self.assertTrue(st.differs(0, 30, 25, 30))

    def test_small_sample_cannot_tell(self):
        self.assertFalse(st.differs(1, 10, 3, 10))     # 10% 대 30% 는 N=10 으로는 구분되지 않는다

    def test_fmt(self):
        self.assertEqual(st.fmt(1, 10), "10% [2%–40%] (1/10)")


class TestTrials(unittest.TestCase):
    def test_defaults_and_quick(self):
        with mock.patch.dict(os.environ, {"QUICK": ""}):
            self.assertEqual(st.trials("ta"), 30)
        with mock.patch.dict(os.environ, {"QUICK": "1"}):
            self.assertEqual(st.trials("ta"), 10)
            self.assertGreaterEqual(st.trials("rag"), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
