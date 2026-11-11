"""Garak 이 공격할 대상: 모델 + 방어 계층을 함수 하나로 묶은 것 (scan_garak.py 에서 GUARD=1 일 때 쓴다)

  입력 -> input_guard.check_input -> (걸리면 거절문, 모델 호출 없음)
       -> 모델(llm.chat, Ollama) -> output_guard.guard_response -> 최종 응답

Garak 은 `--target_type function.Single --target_name garak_target#guarded_model` 로 이 함수를 부른다.
모델 이름은 환경 변수 GARAK_MODEL (scan_garak.py 가 설정). 시스템 프롬프트는 없다(기준선 실행과 같다).
"""
import os

from input_guard import REFUSAL, check_input
from llm import chat
from output_guard import guard_response
from stats import SAMPLING_TEMPERATURE

CANARY = "CANARY-7f3a91"
ALLOWED = {"docs.example.com"}


def respond(text):
    """(최종 응답, 방어 계층이 막거나 바꿨는가)"""
    if check_input(text)[0]:
        return REFUSAL, True
    raw = chat([{"role": "user", "content": text}], os.environ["GARAK_MODEL"],
               temperature=SAMPLING_TEMPERATURE)["content"]
    final, blocked = guard_response(raw, [CANARY], ALLOWED)
    return final, blocked or final != raw


def guarded_model(prompt, **kwargs):
    return [respond(prompt)[0]]
