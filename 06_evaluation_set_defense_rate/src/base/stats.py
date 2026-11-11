"""6-6 실습용: 반복 실행 횟수와 비율의 신뢰구간 (표준 라이브러리만 사용)

모델 출력은 비결정적이므로 "10회 중 1회 성공 = 10%"는 점추정일 뿐이다.
이 모듈은 성공 비율을 Wilson 95% 신뢰구간과 함께 보고하는 도구를 제공한다.

권장 반복 횟수 (DEFAULT_TRIALS)
  기준: 학습용 소형 모델(1.5B~4B)로 케이스당 1~2분 안에 끝나면서, 결론을 낼 만큼의 정밀도를 확보한다.
  - 0건일 때 95% 상한: N=10 -> 28%, N=30 -> 11%, N=50 -> 7%   (N=30 이면 오탐 기준 '10% 이하'를 논할 수 있다)
  - 비율 50% 근처의 신뢰구간 폭: N=10 -> ±27%p, N=30 -> ±17%p, N=50 -> ±14%p
  N=30 이하에서는 구간이 넓다는 점 자체가 학습 포인트이고, N 을 두 배로 늘려도 폭은 √2 배만 줄어든다.

환경 변수  QUICK=1  이면 횟수를 1/3(최소 3)로 줄여 빠르게 동작만 확인한다(통계적 결론용이 아님).
"""
import math
import os

# 이름 -> 기본 반복 횟수
DEFAULT_TRIALS = {
    "ta": 30,            # TA-01 도구 오용: 시도당 모델 호출 1회
    "jb": 15,            # JB-01 멀티턴: 시도당 모델 호출 4회(턴 수)
    "benign": 10,        # 정상 질문 오탐률: 질문 3개 x 10회 = 30건
    "attack_case": 10,   # 공격 유형당 시도 횟수(PyRIT 스캔: 4유형 x 10회 = 40건)
    "rag": 10,           # ACL RAG 질의 반복
}
SAMPLING_TEMPERATURE = 0.7   # 시도끼리 서로 다른 응답이 나오도록 하는 값(낮으면 사실상 같은 표본을 반복하게 된다)


def quick():
    return os.environ.get("QUICK", "") not in ("", "0")


def trials(name):
    n = DEFAULT_TRIALS[name]
    return max(3, n // 3) if quick() else n


def wilson(k, n, z=1.96):
    """성공 k/n 의 Wilson 95% 신뢰구간 (0 건·n 건에서도 0~1 범위를 벗어나지 않는다)."""
    if n <= 0 or not 0 <= k <= n:
        raise ValueError("0 <= k <= n, n > 0 이어야 한다")
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, center - half), min(1.0, center + half)


def fmt(k, n):
    """'10% [2%–40%] (1/10)' 형태. 점추정과 구간, 원 횟수를 함께 보인다."""
    lo, hi = wilson(k, n)
    return f"{k / n:.0%} [{lo:.0%}–{hi:.0%}] ({k}/{n})"


def differs(k1, n1, k2, n2):
    """두 비율의 신뢰구간이 겹치지 않으면 True. 겹쳐도 차이가 없다는 뜻은 아니다(표본이 부족할 수 있다)."""
    lo1, hi1 = wilson(k1, n1)
    lo2, hi2 = wilson(k2, n2)
    return hi1 < lo2 or hi2 < lo1
