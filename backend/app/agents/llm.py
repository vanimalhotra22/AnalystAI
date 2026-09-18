"""LLM adapters.

The model has exactly two jobs in this system:

  1. decide the next investigative step (tool + arguments) given what is known;
  2. turn validated findings into business language.

It never computes a business number.  If no provider is configured -- or a call
fails mid-run -- the graph falls back to the deterministic planner and template
narration, so the demo always completes.  `describe()` reports which mode is
actually in use, and the UI shows it.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from app.config import settings

_ANTHROPIC_MODELS = {"anthropic": "claude-sonnet-5"}
_OPENAI_DEFAULT = "gpt-4.1"
_GEMINI_DEFAULT = "gemini-2.0-flash"


@dataclass
class LLMInfo:
    provider: str
    model: str | None
    available: bool
    reason: str = ""

    def as_dict(self) -> dict:
        return {"provider": self.provider, "model": self.model,
                "available": self.available, "reason": self.reason}


def _key(name: str) -> str | None:
    return getattr(settings, name, None) or os.environ.get(name.upper())


def resolve_provider() -> LLMInfo:
    want = settings.llm_provider
    if want == "none":
        return LLMInfo("none", None, False, "disabled by configuration")
    candidates = [want] if want != "auto" else ["anthropic", "openai", "gemini"]
    for provider in candidates:
        if provider == "anthropic" and _key("anthropic_api_key"):
            model = settings.llm_model if "claude" in settings.llm_model else _ANTHROPIC_MODELS["anthropic"]
            return LLMInfo("anthropic", model, True)
        if provider == "openai" and _key("openai_api_key"):
            model = settings.llm_model if "gpt" in settings.llm_model else _OPENAI_DEFAULT
            return LLMInfo("openai", model, True)
        if provider == "gemini" and _key("google_api_key"):
            model = settings.llm_model if "gemini" in settings.llm_model else _GEMINI_DEFAULT
            return LLMInfo("gemini", model, True)
    return LLMInfo("none", None, False, "no API key configured - running the deterministic planner")


class LLM:
    """Thin, provider-agnostic wrapper around 'pick a tool' and 'write prose'."""

    def __init__(self) -> None:
        self.info = resolve_provider()
        self._client = None
        self.last_error: str | None = None

    # ---------------------------------------------------------------- infra
    @property
    def available(self) -> bool:
        return self.info.available

    def describe(self) -> dict:
        d = self.info.as_dict()
        if self.last_error:
            d["last_error"] = self.last_error
        return d

    def _anthropic(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=_key("anthropic_api_key"))
        return self._client

    def _httpx(self):
        import httpx
        return httpx.Client(timeout=60.0)

    def _disable(self, err: Exception) -> None:
        self.last_error = f"{type(err).__name__}: {err}"
        self.info = LLMInfo(self.info.provider, self.info.model, False,
                            f"provider call failed, fell back to the deterministic planner ({self.last_error})")

    # --------------------------------------------------------- tool choice
    def choose_tool(self, system: str, prompt: str, tools: list[dict]) -> dict | None:
        """Return {'tool': name, 'args': {...}, 'rationale': str} or
        {'done': True, 'rationale': str}.  None means 'ask the fallback'."""
        if not self.available:
            return None
        try:
            if self.info.provider == "anthropic":
                return self._choose_anthropic(system, prompt, tools)
            if self.info.provider == "openai":
                return self._choose_openai(system, prompt, tools)
            if self.info.provider == "gemini":
                return self._choose_gemini(system, prompt, tools)
        except Exception as e:  # noqa: BLE001 - a demo must not die on a 429
            self._disable(e)
        return None

    def _choose_anthropic(self, system: str, prompt: str, tools: list[dict]) -> dict | None:
        client = self._anthropic()
        finish = {"name": "finish_investigation",
                  "description": "Stop investigating: enough evidence has been gathered.",
                  "input_schema": {"type": "object",
                                   "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}
        msg = client.messages.create(
            model=self.info.model, max_tokens=1024, system=system,
            tools=tools + [finish], tool_choice={"type": "any"},
            messages=[{"role": "user", "content": prompt}],
        )
        for block in msg.content:
            if getattr(block, "type", None) == "tool_use":
                if block.name == "finish_investigation":
                    return {"done": True, "rationale": (block.input or {}).get("reason", "")}
                return {"tool": block.name, "args": dict(block.input or {}),
                        "rationale": (block.input or {}).get("rationale", "")}
        return None

    def _choose_openai(self, system: str, prompt: str, tools: list[dict]) -> dict | None:
        payload = {
            "model": self.info.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "tools": [{"type": "function",
                       "function": {"name": t["name"], "description": t["description"],
                                    "parameters": t["input_schema"]}} for t in tools]
            + [{"type": "function", "function": {
                "name": "finish_investigation", "description": "Stop investigating.",
                "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}}}}],
            "tool_choice": "required",
        }
        with self._httpx() as c:
            r = c.post("https://api.openai.com/v1/chat/completions", json=payload,
                       headers={"Authorization": f"Bearer {_key('openai_api_key')}"})
            r.raise_for_status()
            calls = r.json()["choices"][0]["message"].get("tool_calls") or []
        if not calls:
            return None
        fn = calls[0]["function"]
        args = json.loads(fn.get("arguments") or "{}")
        if fn["name"] == "finish_investigation":
            return {"done": True, "rationale": args.get("reason", "")}
        return {"tool": fn["name"], "args": args, "rationale": args.get("rationale", "")}

    def _choose_gemini(self, system: str, prompt: str, tools: list[dict]) -> dict | None:
        decls = [{"name": t["name"], "description": t["description"],
                  "parameters": _gemini_schema(t["input_schema"])} for t in tools]
        decls.append({"name": "finish_investigation", "description": "Stop investigating.",
                      "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING"}}}})
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{self.info.model}:generateContent?key={_key('google_api_key')}")
        payload = {"system_instruction": {"parts": [{"text": system}]},
                   "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "tools": [{"function_declarations": decls}],
                   "tool_config": {"function_calling_config": {"mode": "ANY"}}}
        with self._httpx() as c:
            r = c.post(url, json=payload)
            r.raise_for_status()
            parts = r.json()["candidates"][0]["content"]["parts"]
        for p in parts:
            call = p.get("functionCall")
            if call:
                args = dict(call.get("args") or {})
                if call["name"] == "finish_investigation":
                    return {"done": True, "rationale": args.get("reason", "")}
                return {"tool": call["name"], "args": args, "rationale": args.get("rationale", "")}
        return None

    # ------------------------------------------------------------- narration
    def write(self, system: str, prompt: str, max_tokens: int = 1200) -> str | None:
        if not self.available:
            return None
        try:
            if self.info.provider == "anthropic":
                msg = self._anthropic().messages.create(
                    model=self.info.model, max_tokens=max_tokens, system=system,
                    messages=[{"role": "user", "content": prompt}])
                return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
            if self.info.provider == "openai":
                with self._httpx() as c:
                    r = c.post("https://api.openai.com/v1/chat/completions",
                               json={"model": self.info.model, "max_tokens": max_tokens,
                                     "messages": [{"role": "system", "content": system},
                                                  {"role": "user", "content": prompt}]},
                               headers={"Authorization": f"Bearer {_key('openai_api_key')}"})
                    r.raise_for_status()
                    return r.json()["choices"][0]["message"]["content"].strip()
            if self.info.provider == "gemini":
                url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                       f"{self.info.model}:generateContent?key={_key('google_api_key')}")
                with self._httpx() as c:
                    r = c.post(url, json={"system_instruction": {"parts": [{"text": system}]},
                                          "contents": [{"role": "user", "parts": [{"text": prompt}]}]})
                    r.raise_for_status()
                    return r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as e:  # noqa: BLE001
            self._disable(e)
        return None


def _gemini_schema(schema: dict) -> dict:
    """JSON-Schema -> Gemini's upper-cased type names."""
    def conv(node: Any) -> Any:
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k == "type" and isinstance(v, str):
                    out[k] = v.upper()
                elif k in ("required",) and isinstance(v, bool):
                    continue
                else:
                    out[k] = conv(v)
            return out
        if isinstance(node, list):
            return [conv(v) for v in node]
        return node
    return conv(schema)


_llm_singleton: LLM | None = None


def get_llm() -> LLM:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LLM()
    return _llm_singleton
