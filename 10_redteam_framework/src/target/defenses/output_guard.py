"""6-6 출력 방어: 모델이 내놓은 응답을 검사해 유출을 막는다 (표준 라이브러리만 사용)

응답에 카나리가 있으면 차단하고, 허용 목록 밖 링크·이미지는 제거한다. RAG 검색 결과의 문서 단위 ACL 필터도 여기에 있다.
입력 쪽 방어는 input_guard.py 에 있다. 방어율·오탐률 계산은 run/evalset.py 가 한다.
"""
import base64
import re
from urllib.parse import quote, urlparse

# 스캔 실습의 보호 대상(카나리)과 허용 호스트. garak_target.py·pyrit_target.py·스캐너가 같은 값을 쓴다.
CANARY = "CANARY-7f3a91"
ALLOWED = {"docs.example.com"}


# ---------------------------------------------------------------------------
# 출력 방어 (실제 앱에서는 이 모듈을 그대로 import 해서 쓴다)
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
