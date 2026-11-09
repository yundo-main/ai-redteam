"""6-4 방어 모듈 + 6-5 집계 지표 (테스트와 LangChain/LangGraph 예제가 함께 쓰는 공용 모듈)

표준 라이브러리만 사용한다. 실제 앱에서는 이 모듈을 그대로 import 해서 쓴다.

파일 구성(그림: ../code-map.svg): 이 모듈이 중심이다 — 같은 폴더의 모델 테스트
  (LangChain/LangGraph 실습, 파일명은 각 code-map.svg 참조)와 test_defense.py
  (모델 없는 단위 테스트)가 이 모듈을 import 해서 쓴다.
  04·05의 defense.py는 완전히 같은 복사본이다.
"""
import base64
import re
from urllib.parse import quote, urlparse


# ---------------------------------------------------------------------------
# 6-4 방어 모듈 (실제 앱에서는 별도 파일로 분리해 import 한다)
# ---------------------------------------------------------------------------

def contains_canary(text, canaries):
    """응답/요청 텍스트에 카나리 문자열이 나타나는지 검사한다.

    평문뿐 아니라 Base64·URL 인코딩된 형태도 확인한다(Stealth Extraction 대비).
    """
    variants = []
    for c in canaries:
        variants.append(c)                                      # 평문
        variants.append(quote(c, safe=""))                      # URL 인코딩
        variants.append(base64.b64encode(c.encode()).decode())  # Base64
    return any(v in text for v in variants)


# 마크다운 이미지 ![alt](url) 와 링크 [text](url) 를 찾는 패턴
_MD_URL = re.compile(r"(!?)\[([^\]]*)\]\(([^)\s]+)[^)]*\)")


def sanitize_markdown(text, allowed_hosts):
    """허용 목록에 없는 호스트를 가리키는 마크다운 이미지/링크를 제거한다.

    이미지는 렌더링 즉시 외부 요청이 발생하므로 가장 먼저 막아야 한다.
    허용된 호스트만 그대로 두고, 나머지는 대체 문구로 바꾼다.
    """
    def _replace(m):
        is_image, label, url = m.group(1), m.group(2), m.group(3)
        host = (urlparse(url).hostname or "").lower()
        if host in allowed_hosts:
            return m.group(0)                                   # 허용: 원문 유지
        return "[외부 링크 제거됨]" if not is_image else "[외부 이미지 제거됨]"

    return _MD_URL.sub(_replace, text)


def filter_by_acl(docs, user_groups):
    """요청 사용자의 그룹과 겹치는 문서만 반환한다(RAG 검색 결과용 문서 단위 ACL)."""
    return [d for d in docs if set(d["groups"]) & set(user_groups)]


def guard_response(text, canaries, allowed_hosts):
    """응답 후처리 파이프라인: 카나리가 있으면 차단, 아니면 URL을 정리해 반환한다.

    반환값: (최종 텍스트, 차단 여부)
    """
    if contains_canary(text, canaries):
        return "[응답 차단됨: 민감 정보 포함]", True
    return sanitize_markdown(text, allowed_hosts), False


# ---------------------------------------------------------------------------
# 6-5 집계 지표 (스캔 결과 리스트를 입력으로 받는다)
# 결과 레코드 형식: {"category": str, "is_attack": bool, "blocked": bool}
# ---------------------------------------------------------------------------

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
