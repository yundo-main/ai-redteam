"""6-6 실습용: 로컬 모델 호출 도우미 (표준 라이브러리만 사용)

환경 변수
  OLLAMA_MODEL      사용할 모델 이름. 없으면 qwen2.5:3b, 그것도 없으면 설치된 첫 번째 모델을 쓴다.
  OLLAMA_BASE_URL   Ollama 주소 (기본 http://localhost:11434)

  REDTEAM_LLM_BACKEND  "ollama"(기본) | "openai" | "anthropic" | "gemini"
  REDTEAM_LLM_URL      백엔드 주소. 기본값은 백엔드별:
                       openai    http://localhost:11434/v1  (Ollama /v1 — LM Studio, llama.cpp, vLLM 도 같은 형식)
                       anthropic https://api.anthropic.com
                       gemini    https://generativelanguage.googleapis.com
  REDTEAM_LLM_KEY      API 키 (anthropic: x-api-key, gemini: x-goog-api-key, openai: Bearer)
  REDTEAM_LLM_MODEL    모델 이름. anthropic·gemini 는 반드시 설정해야 한다(유료 API — 잘못 고르면 비용 발생).
                       openai 백엔드는 없으면 서버의 첫 모델, ollama 는 OLLAMA_MODEL→PREFERRED→첫 모델 순.

준비:  ollama serve   (모델이 없으면  ollama pull qwen2.5:3b)

모델 선택 기준 (학습용): 2~4B 급, 용량 약 2GB 안팎이면 충분하다. 7B 이상은 반복 실습 시간이 몇 배로 늘어 권장하지 않는다.
  TA-01 은 도구 호출(tool calling)을 지원하는 모델이어야 의미가 있다. qwen2.5:3b, llama3.2:3b 는 지원하고
  gemma3 는 Ollama 에서 도구 호출을 지원하지 않는다. 지원을 표방해도 1.5B 급 미세조정 모델은 호출 형식을 못 지키는 경우가 있다.
서버가 꺼져 있거나 모델이 없으면 ready()가 (False, 사유, None)을 돌려주고, 테스트는 건너뛴다.

안전: 어떤 백엔드든 주소는 localhost 계열만 허용한다(schema.check_endpoint). 외부 주소는
REDTEAM_ALLOW_REMOTE=1 을 명시한 경우에만 연결한다(ROE — 외부 전송 금지).
"""
import json
import os
import urllib.request

PREFERRED = "qwen2.5:3b"
BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
BACKEND = os.environ.get("REDTEAM_LLM_BACKEND", "ollama")
_BACKEND_URLS = {
    "openai": f"{BASE_URL}/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
}
API_URL = os.environ.get("REDTEAM_LLM_URL") or _BACKEND_URLS.get(BACKEND, f"{BASE_URL}/v1")
API_KEY = os.environ.get("REDTEAM_LLM_KEY", "")
REMOTE_BACKENDS = {"anthropic", "gemini"}   # 유료 원격 API — REDTEAM_ALLOW_REMOTE=1 필수


def endpoint_url():
    """현재 백엔드의 주소 — 안전 검증(check_endpoint)에 넘기는 값."""
    return BASE_URL if BACKEND == "ollama" else API_URL


def api_root():
    """OpenAI 호환 /v1 루트 — ollama·openai 백엔드에서만 의미가 있다(pyrit 연동용)."""
    return f"{BASE_URL}/v1" if BACKEND == "ollama" else API_URL


def configure(backend=None, url=None, model=None, key=None, ollama_url=None,
              allow_remote=None):
    """실행 중 백엔드 설정을 바꾼다 — 모듈 전역과 환경변수를 함께 갱신한다.

    웹 GUI 저장값(settings.json)이 환경변수보다 우선한다. url="" 은 백엔드 기본값으로 되돌린다.
    key="" 은 기존 키를 유지한다(키는 입력창을 비워 두면 덮어쓰지 않는다).
    """
    global BACKEND, API_URL, API_KEY, BASE_URL
    if ollama_url is not None:
        BASE_URL = ollama_url
        os.environ["OLLAMA_BASE_URL"] = ollama_url
    if backend is not None:
        BACKEND = backend
        os.environ["REDTEAM_LLM_BACKEND"] = backend
    if key is not None and key != "":
        API_KEY = key
        os.environ["REDTEAM_LLM_KEY"] = key
    if model is not None:
        if model:
            os.environ["REDTEAM_LLM_MODEL"] = model
        else:
            os.environ.pop("REDTEAM_LLM_MODEL", None)
    if url is not None:
        API_URL = url or _BACKEND_URLS.get(BACKEND, f"{BASE_URL}/v1")
        os.environ["REDTEAM_LLM_URL"] = API_URL
    elif backend is not None:
        API_URL = _BACKEND_URLS.get(BACKEND, f"{BASE_URL}/v1")
        os.environ["REDTEAM_LLM_URL"] = API_URL
    if allow_remote is not None:
        if allow_remote:
            os.environ["REDTEAM_ALLOW_REMOTE"] = "1"
        else:
            os.environ.pop("REDTEAM_ALLOW_REMOTE", None)


def settings_view():
    """GUI 설정 화면·/api/info 가 보여줄 현재 유효 설정(키 원문은 제외)."""
    return {"backend": BACKEND, "endpoint": endpoint_url(), "api_url": api_root(),
            "url": API_URL, "ollama_url": BASE_URL,
            "model": os.environ.get("REDTEAM_LLM_MODEL") or (PREFERRED if BACKEND == "ollama" else None),
            "allow_remote": os.environ.get("REDTEAM_ALLOW_REMOTE") == "1",
            "key_set": bool(API_KEY), "key_hint": API_KEY[-4:] if len(API_KEY) >= 4 else ""}


def _get_json(url, headers, timeout=5):
    req = urllib.request.Request(url)
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def installed_models():
    if BACKEND == "openai":
        req = urllib.request.Request(f"{API_URL}/models")
        _auth(req)
        with urllib.request.urlopen(req, timeout=2) as r:
            return [m["id"] for m in json.load(r).get("data", [])]
    if BACKEND == "anthropic":
        data = _get_json(f"{API_URL}/v1/models",
                         {"x-api-key": API_KEY, "anthropic-version": "2023-06-01"})
        return [m["id"] for m in data.get("data", [])]
    if BACKEND == "gemini":
        data = _get_json(f"{API_URL}/v1beta/models", {"x-goog-api-key": API_KEY})
        return [m["name"].removeprefix("models/") for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])]
    with urllib.request.urlopen(f"{BASE_URL}/api/tags", timeout=2) as r:
        return [m["name"] for m in json.load(r).get("models", [])]


def _auth(req):
    if API_KEY:
        req.add_header("Authorization", f"Bearer {API_KEY}")


def ready():
    """(사용 가능 여부, 사유, 모델 이름)"""
    from base import schema
    schema.check_endpoint(endpoint_url())
    if BACKEND in REMOTE_BACKENDS:
        want = os.environ.get("REDTEAM_LLM_MODEL")
        if not want:
            return False, (f"{BACKEND} 백엔드는 REDTEAM_LLM_MODEL=<모델명> 설정이 필요합니다 "
                           "(유료 API — 모델을 명시해야 오용을 막습니다)"), None
        try:
            names = installed_models()
        except Exception:
            return False, f"{BACKEND} 서버에 연결할 수 없음 — REDTEAM_LLM_KEY·REDTEAM_LLM_URL 확인", None
        found = next((n for n in names if n == want or n.startswith(want) or want in n), want)
        return True, "", found
    try:
        names = installed_models()
    except Exception:
        where = "OpenAI 호환 서버" if BACKEND == "openai" else "Ollama 서버"
        hint = "(서버를 켜고 REDTEAM_LLM_URL 로 주소를 확인)" if BACKEND == "openai" else "(ollama serve)"
        return False, f"{where}에 연결할 수 없음 {hint}", None
    if BACKEND == "openai":
        want = os.environ.get("REDTEAM_LLM_MODEL")
        if want:
            found = next((n for n in names if n == want or n.startswith(want)), None)
            if found is None:
                return False, f"모델 미설치: {want} (서버의 모델 목록 확인)", None
            return True, "", found
        return (True, "", names[0]) if names else (False, "서버에 모델이 없음", None)
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


def _chat_openai(messages, model, tools=None, temperature=0.2, seed=None, max_tokens=256, timeout=180):
    """OpenAI 호환 /chat/completions 호출 → ollama /api/chat 의 message dict 와 같은 형태로 돌려준다."""
    body = {"model": model, "messages": messages, "stream": False,
            "temperature": temperature, "max_tokens": max_tokens}
    if seed is not None:
        body["seed"] = seed
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(f"{API_URL}/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    _auth(req)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        msg = json.load(r)["choices"][0]["message"]
    return {"role": "assistant", "content": msg.get("content") or "",
            **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})}


# ---------------------------------------------------------------------------
# anthropic / gemini 어댑터 — 메시지는 {"role","content"} 형태로 통일해 돌려준다.
# seed 는 두 API 모두 지원하지 않아 무시한다(재현성은 보장되지 않음).
# ---------------------------------------------------------------------------
def _split_system(messages):
    """system 메시지를 분리하고 user/assistant 대화만 남긴다 (role tool → user 로 강등)."""
    system, conv = [], []
    for m in messages:
        role, content = m.get("role"), m.get("content") or ""
        if role == "system":
            system.append(content)
        else:
            conv.append({"role": "assistant" if role == "assistant" else "user",
                         "content": content})
    return "\n\n".join(system) or None, conv


def _anthropic_tool(t):
    fn = t.get("function", {})
    return {"name": fn.get("name", ""), "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}}


def _chat_anthropic(messages, model, tools=None, temperature=0.2, seed=None,
                    max_tokens=256, timeout=180):
    """Anthropic Messages API → 통일 message dict. 도구는 tool_use 블록으로 돌아온다."""
    system, conv = _split_system(messages)
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
            "messages": conv}
    if system:
        body["system"] = system
    if tools:
        body["tools"] = [_anthropic_tool(t) for t in tools]
    req = urllib.request.Request(f"{API_URL}/v1/messages", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "x-api-key": API_KEY,
                                          "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    text, calls = [], []
    for b in data.get("content", []):
        if b.get("type") == "text":
            text.append(b.get("text", ""))
        elif b.get("type") == "tool_use":
            calls.append({"id": b.get("id", ""), "type": "function",
                          "function": {"name": b.get("name", ""),
                                       "arguments": json.dumps(b.get("input") or {})}})
    return {"role": "assistant", "content": "".join(text),
            **({"tool_calls": calls} if calls else {})}


def _gemini_tool(t):
    fn = t.get("function", {})
    return {"name": fn.get("name", ""), "description": fn.get("description", ""),
            "parameters": fn.get("parameters") or {"type": "object", "properties": {}}}


def _chat_gemini(messages, model, tools=None, temperature=0.2, seed=None,
                 max_tokens=256, timeout=180):
    """Gemini generateContent API → 통일 message dict. 함수 호출은 functionCall 파트로 돌아온다."""
    system, conv = _split_system(messages)
    body = {"contents": [{"role": "model" if m["role"] == "assistant" else "user",
                          "parts": [{"text": m["content"]}]} for m in conv],
            "generationConfig": {"temperature": temperature,
                                 "maxOutputTokens": max_tokens}}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if tools:
        body["tools"] = [{"functionDeclarations": [_gemini_tool(t) for t in tools]}]
    req = urllib.request.Request(f"{API_URL}/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json",
                                          "x-goog-api-key": API_KEY})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    cand = (data.get("candidates") or [{}])[0]
    parts = ((cand.get("content") or {}).get("parts")) or []
    text, calls = [], []
    for i, p in enumerate(parts):
        if p.get("text") is not None:
            text.append(p["text"])
        elif p.get("functionCall"):
            fc = p["functionCall"]
            calls.append({"id": f"call_{i}", "type": "function",
                          "function": {"name": fc.get("name", ""),
                                       "arguments": json.dumps(fc.get("args") or {})}})
    return {"role": "assistant", "content": "".join(text),
            **({"tool_calls": calls} if calls else {})}


def chat(messages, model, tools=None, temperature=0.2, seed=None, max_tokens=256, timeout=180):
    """모델을 한 번 호출하고 응답 message(dict)를 돌려준다. 백엔드는 REDTEAM_LLM_BACKEND 가 정한다.

    seed 를 주면 같은 입력에서 같은 응답이 나오도록 시도한다(재현성 — ollama·openai 호환만 지원).
    max_tokens 로 응답 길이를 제한한다(작은 모델이 같은 말을 끝없이 반복하는 것을 막는다).
    도구를 주면 message["tool_calls"] 에 모델이 제안한 호출이 들어온다.
    """
    if BACKEND == "anthropic":
        return _chat_anthropic(messages, model, tools, temperature, seed, max_tokens, timeout)
    if BACKEND == "gemini":
        return _chat_gemini(messages, model, tools, temperature, seed, max_tokens, timeout)
    if BACKEND == "openai":
        return _chat_openai(messages, model, tools, temperature, seed, max_tokens, timeout)
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
