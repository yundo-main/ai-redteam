"""PyRIT 공격에 붙이는 방어 계층: 입력 검사와 응답 검사 두 단계 (scan_pyrit.py 에서 GUARD=1 일 때 쓴다)

  입력 -> screen_input (걸리면 거절문, 모델 호출 없음)
       -> 모델(PyRIT 의 OpenAIChatTarget 이 호출) -> screen_output -> 최종 응답

garak_target.py 는 모델 호출까지 함수 하나로 묶지만, PyRIT 는 모델 호출을 PyRIT 가 직접 하므로
방어 계층을 호출 앞뒤의 두 함수로 나눠 둔다. 판정 규칙은 input_guard.py·output_guard.py 것을 그대로 쓴다.
"""
from target.input_guard import REFUSAL, check_input
from target.output_guard import ALLOWED, CANARY, contains_canary, guard_response


def screen_input(text):
    """(막았는가, 막았다면 대신 돌려줄 거절문). 실제로 보내는 문장(변환 후)을 넣는다."""
    blocked = check_input(text)[0]
    return blocked, (REFUSAL if blocked else None)


def screen_output(raw):
    """(최종 응답, 방어 계층이 막거나 바꿨는가)"""
    final, blocked = guard_response(raw, [CANARY], ALLOWED)
    return final, blocked or final != raw


def leaks_after_guard(raw):
    """방어 계층을 통과한 최종 응답에도 카나리가 남아 있는가(= 유출)"""
    return contains_canary(screen_output(raw)[0], [CANARY])
