"""base/llm.py OpenAI 호환 백엔드 단위 테스트 (모델 호출 없이 요청 형식만 검증)"""
import io
import json
import sys
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from base import llm


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestOpenAIBackend(unittest.TestCase):
    def test_chat_openai_request_and_response(self):
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            captured["auth"] = req.get_header("Authorization")
            return _Resp(json.dumps({"choices": [{"message": {
                "role": "assistant", "content": "답변",
                "tool_calls": [{"id": "1", "type": "function",
                                "function": {"name": "send_email", "arguments": "{}"}}]}}]}).encode())

        with mock.patch.object(llm.urllib.request, "urlopen", fake_urlopen), \
             mock.patch.object(llm, "API_URL", "http://localhost:1234/v1"), \
             mock.patch.object(llm, "API_KEY", "k"):
            msg = llm._chat_openai([{"role": "user", "content": "hi"}], "m1",
                                   tools=[{"type": "function"}], seed=3, max_tokens=64)
        self.assertEqual(captured["url"], "http://localhost:1234/v1/chat/completions")
        self.assertEqual(captured["body"]["model"], "m1")
        self.assertEqual(captured["body"]["max_tokens"], 64)
        self.assertEqual(captured["body"]["seed"], 3)
        self.assertEqual(captured["auth"], "Bearer k")
        self.assertEqual(msg["content"], "답변")
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "send_email")

    def test_chat_openai_no_toolcalls_key(self):
        def fake_urlopen(req, timeout=0):
            return _Resp(json.dumps({"choices": [{"message": {
                "role": "assistant", "content": "그냥 답변"}}]}).encode())

        with mock.patch.object(llm.urllib.request, "urlopen", fake_urlopen), \
             mock.patch.object(llm, "API_URL", "http://localhost:1234/v1"), \
             mock.patch.object(llm, "API_KEY", ""):
            msg = llm._chat_openai([{"role": "user", "content": "hi"}], "m1")
        self.assertNotIn("tool_calls", msg)
        self.assertEqual(msg["content"], "그냥 답변")

    def test_endpoint_dispatch(self):
        self.assertEqual(llm.endpoint_url(), llm.API_URL if llm.BACKEND == "openai" else llm.BASE_URL)


class TestAnthropicBackend(unittest.TestCase):
    def test_chat_anthropic_request_and_response(self):
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            captured["key"] = req.get_header("X-api-key")
            captured["version"] = req.get_header("Anthropic-version")
            return _Resp(json.dumps({"content": [
                {"type": "text", "text": "답변 "},
                {"type": "text", "text": "끝"},
                {"type": "tool_use", "id": "tu1", "name": "send_email",
                 "input": {"to": "a@b.invalid"}}]}).encode())

        msgs = [{"role": "system", "content": "규칙"},
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "반가워"},
                {"role": "user", "content": "계속"}]
        with mock.patch.object(llm.urllib.request, "urlopen", fake_urlopen), \
             mock.patch.object(llm, "API_URL", "https://api.anthropic.com"), \
             mock.patch.object(llm, "API_KEY", "sk-test"):
            msg = llm._chat_anthropic(msgs, "claude-x",
                                      tools=[{"type": "function", "function": {
                                          "name": "send_email", "description": "메일",
                                          "parameters": {"type": "object"}}}],
                                      max_tokens=64)
        self.assertEqual(captured["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(captured["key"], "sk-test")
        self.assertEqual(captured["version"], "2023-06-01")
        self.assertEqual(captured["body"]["system"], "규칙")
        self.assertEqual([m["role"] for m in captured["body"]["messages"]],
                         ["user", "assistant", "user"])
        self.assertEqual(captured["body"]["tools"][0]["name"], "send_email")
        self.assertEqual(captured["body"]["tools"][0]["input_schema"], {"type": "object"})
        self.assertEqual(msg["content"], "답변 끝")
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "send_email")
        self.assertEqual(json.loads(msg["tool_calls"][0]["function"]["arguments"]),
                         {"to": "a@b.invalid"})


class TestGeminiBackend(unittest.TestCase):
    def test_chat_gemini_request_and_response(self):
        captured = {}

        def fake_urlopen(req, timeout=0):
            captured["url"] = req.full_url
            captured["body"] = json.loads(req.data)
            captured["key"] = req.get_header("X-goog-api-key")
            return _Resp(json.dumps({"candidates": [{"content": {"parts": [
                {"text": "답변"},
                {"functionCall": {"name": "send_email", "args": {"to": "a@b.invalid"}}}]}}]}).encode())

        msgs = [{"role": "system", "content": "규칙"},
                {"role": "user", "content": "안녕"},
                {"role": "assistant", "content": "반가워"}]
        with mock.patch.object(llm.urllib.request, "urlopen", fake_urlopen), \
             mock.patch.object(llm, "API_URL", "https://generativelanguage.googleapis.com"), \
             mock.patch.object(llm, "API_KEY", "g-key"):
            msg = llm._chat_gemini(msgs, "gemini-x",
                                   tools=[{"type": "function", "function": {
                                       "name": "send_email", "description": "메일",
                                       "parameters": {"type": "object"}}}],
                                   max_tokens=64)
        self.assertEqual(captured["url"],
                         "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent")
        self.assertEqual(captured["key"], "g-key")
        self.assertEqual(captured["body"]["systemInstruction"]["parts"][0]["text"], "규칙")
        self.assertEqual([c["role"] for c in captured["body"]["contents"]], ["user", "model"])
        self.assertEqual(captured["body"]["tools"][0]["functionDeclarations"][0]["name"], "send_email")
        self.assertEqual(msg["content"], "답변")
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "send_email")

    def test_remote_backend_requires_model_env(self):
        with mock.patch.object(llm, "BACKEND", "anthropic"), \
             mock.patch.object(llm, "endpoint_url", return_value="http://localhost:9"), \
             mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("REDTEAM_LLM_MODEL", None)
            ok, why, _ = llm.ready()
        self.assertFalse(ok)
        self.assertIn("REDTEAM_LLM_MODEL", why)


if __name__ == "__main__":
    unittest.main()
