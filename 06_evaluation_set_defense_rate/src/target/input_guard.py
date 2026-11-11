"""6-6 입력 방어: 모델에 보내기 전에 입력을 검사해 의심스러우면 모델을 부르지 않고 거절한다 (표준 라이브러리만 사용)

규칙은 '일반적인 공격 형태'만 본다. 특정 프로브의 정답 문자열(트리거)을 알고 만든 규칙이 아니다.
  1. 입력 안에 끼어든 지시: "이전 지시를 무시", "ignore previous instructions", 문서 한가운데의 "User:" 같은 역할 표시,
     "다음 문장을 그대로 반복하라" 류의 따라 말하기 요구
  2. 인코딩 우회: 실제로 디코딩되는 긴 Base64 덩어리가 들어 있는 입력
정상 질문은 통과해야 한다(오탐). 휴리스틱이라 못 잡는 변형이 있고, 그 한계는 방어율 숫자로 드러난다.

사용
  from target.input_guard import check_input
  blocked, reason = check_input(text)        # (차단 여부, 사유 또는 "")
  REFUSAL                                    # 차단 시 모델 대신 돌려주는 응답
"""
import base64
import binascii
import re

REFUSAL = "[입력 차단됨: 의심스러운 지시 또는 인코딩 입력]"

# 입력에 끼어든 지시의 일반적인 형태
_INJECTION = [
    (re.compile(r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions?|prompts?|rules?)", re.I), "이전 지시 무시 요구"),
    (re.compile(r"disregard\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)", re.I), "이전 지시 무시 요구"),
    (re.compile(r"(이전|앞선|위의)\s*(모든\s*)?(지시|명령|지침|프롬프트)[을를]?\s*(모두\s*)?(무시|잊)"), "이전 지시 무시 요구"),
    (re.compile(r"(repeat|say|print|output|write)\s+(exactly\s+)?the\s+following\s+(sentence|text|words?|phrase|string)", re.I), "따라 말하기 요구"),
    (re.compile(r"다음\s*(문장|문구|텍스트)[을를]?\s*(그대로\s*)?(반복|출력|따라)"), "따라 말하기 요구"),
    (re.compile(r"(^|\n)\s*(user|system|assistant|사용자|시스템)\s*:", re.I), "입력 안의 역할 표시"),
]

# Base64 후보: 24자 이상 연속된 Base64 문자 (패딩 포함)
_B64 = re.compile(r"[A-Za-z0-9+/]{24,}={0,2}")


def _decodes_to_text(token):
    """토큰이 실제 Base64 로 디코딩되고 결과가 글자(출력 가능한 문자)로 읽히면 True."""
    pad = "=" * (-len(token) % 4)
    try:
        raw = base64.b64decode(token + pad, validate=True)
    except (binascii.Error, ValueError):
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return len(text) >= 8 and sum(c.isprintable() or c.isspace() for c in text) / len(text) > 0.9


def check_input(text):
    """(차단 여부, 사유). 규칙에 하나라도 걸리면 차단한다."""
    for pattern, reason in _INJECTION:
        if pattern.search(text):
            return True, reason
    for token in _B64.findall(text):
        if _decodes_to_text(token):
            return True, "디코딩되는 Base64 덩어리"
    return False, ""
