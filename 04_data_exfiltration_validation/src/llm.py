"""6-3 ~ 6-5 실습용(일차마다 같은 내용의 복사본을 둔다): 로컬 Ollama 모델 호출 도우미 (표준 라이브러리만 사용)

환경 변수
  OLLAMA_MODEL      사용할 모델 이름. 없으면 qwen2.5:3b, 그것도 없으면 설치된 첫 번째 모델을 쓴다.
  OLLAMA_BASE_URL   Ollama 주소 (기본 http://localhost:11434)

준비:  ollama serve   (모델이 없으면  ollama pull qwen2.5:3b)

모델 선택 기준 (학습용): 2~4B 급, 용량 약 2GB 안팎이면 충분하다. 7B 이상은 반복 실습 시간이 몇 배로 늘어 권장하지 않는다.
  TA-01 은 도구 호출(tool calling)을 지원하는 모델이어야 의미가 있다. qwen2.5:3b, llama3.2:3b 는 지원하고
  gemma3 는 Ollama 에서 도구 호출을 지원하지 않는다. 지원을 표방해도 1.5B 급 미세조정 모델은 호출 형식을 못 지키는 경우가 있다.
서버가 꺼져 있거나 모델이 없으면 ready()가 (False, 사유, None)을 돌려주고, 테스트는 건너뛴다.
"""
import json
import os
import urllib.request

PREFERRED = "qwen2.5:3b"
BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def installed_models():
    with urllib.request.urlopen(f"{BASE_URL}/api/tags", timeout=2) as r:
        return [m["name"] for m in json.load(r).get("models", [])]


def ready():
    """(사용 가능 여부, 사유, 모델 이름)"""
    try:
        names = installed_models()
    except Exception:
        return False, "Ollama 서버에 연결할 수 없음 (ollama serve)", None
    want = os.environ.get("OLLAMA_MODEL")
    if want:
        # 'gemma3:4b' 와 'gemma3:4b-it-qat' 처럼 접미사가 붙은 이름도 허용한다.
        found = next((n for n in names if n == want or n.startswith(want)), None)
        if found is None:
            return False, f"모델 미설치: {want} (ollama pull {want})", None
        return True, "", found
    if not names:
        return False, "설치된 모델이 없음 (ollama pull qwen2.5:3b)", None
    preferred = next((n for n in names if n.startswith(PREFERRED)), None)
    return True, "", preferred or names[0]


def chat(messages, model, tools=None, temperature=0.2, seed=None, max_tokens=256, timeout=180):
    """/api/chat 을 한 번 호출하고 응답 message(dict)를 돌려준다.

    seed 를 주면 같은 입력에서 같은 응답이 나오도록 시도한다(재현성).
    max_tokens 로 응답 길이를 제한한다(작은 모델이 같은 말을 끝없이 반복하는 것을 막는다).
    도구를 주면 message["tool_calls"] 에 모델이 제안한 호출이 들어온다.
    """
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens}}
    if seed is not None:
        body["options"]["seed"] = seed
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(f"{BASE_URL}/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["message"]


if __name__ == "__main__":
    print(ready())          # (True, "", "모델명") 이면 준비 완료. python NN_.../src/llm.py
