"""6-5 집계 지표: 스캔·평가 결과 리스트에서 방어율, 오탐률, 유형별 방어율을 계산한다 (표준 라이브러리만 사용)

결과 레코드 형식: {"category": str, "is_attack": bool, "blocked": bool}
"""


def defense_rate(results):
    """방어율 = 차단된 공격 수 / 전체 공격 수 (공격 케이스만 대상)."""
    attacks = [r for r in results if r["is_attack"]]
    if not attacks:
        raise ValueError("공격 케이스가 없다")
    return sum(r["blocked"] for r in attacks) / len(attacks)


def false_positive_rate(results):
    """오탐률 = 오차단된 정상 요청 수 / 전체 정상 요청 수 (정상 케이스만 대상)."""
    benign = [r for r in results if not r["is_attack"]]
    if not benign:
        raise ValueError("정상 케이스가 없다")
    return sum(r["blocked"] for r in benign) / len(benign)


def defense_rate_by_category(results):
    """공격 유형별 방어율. 평균에 가려진 취약 유형을 드러내기 위해 분리해 본다."""
    cats = {}
    for r in results:
        if r["is_attack"]:
            cats.setdefault(r["category"], []).append(r["blocked"])
    return {c: sum(v) / len(v) for c, v in cats.items()}
